"""
*********************************************************************************
*																				*
*		QGIS-IQM9 is a program developed for QGIS as a tool to automatically	*
*	calculate the Morphological Quality Index (MQI) of river systems			*
*	Copyright (C) 2025 Laboratoire d'expertise et de recherche en géographie	*
*	appliquée (LERGA) de l'Université du Québec à Chicoutimi (UQAC)				*
*																				*
*	This program is free software: you can redistribute it and/or modify		*
*	it under the terms of the GNU Affero General Public License as published	*
*	by the Free Software Foundation, either version 3 of the License, or		*
*	(at your option) any later version.											*
*																				*
*	This program is distributed in the hope that it will be useful,				*
*	but WITHOUT ANY WARRANTY; without even the implied warranty of				*
*	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the				*
*	GNU Affero General Public License for more details.							*
*																				*
*	You should have received a copy of the GNU Affero General Public License	*
*	along with this program.  If not, see <https://www.gnu.org/licenses/>.		*
*																				*
*********************************************************************************
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingUtils,
	QgsUnitTypes,
	QgsVectorLayer,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterEnum,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSink,
	QgsProject
)
from qgis import processing


class Extract_OSM_roads(QgsProcessingAlgorithm):
	#OUTPUT = "OUTPUT"
	LINES = "OSM_lines"

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer(self.LINES, self.tr('lines (du fichier map.osm de OSM)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('watershed_area', self.tr('Superficie du BV'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterEnum('road_type', self.tr('Type de route à extraire'), options=[self.tr('Tout'), 'cycleway', 'motorway','motorway_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','trunk','trunk_link','residential'], defaultValue='Tout', allowMultiple=True, usesStaticStrings=True, optional=True))
		self.addParameter(QgsProcessingParameterEnum('railway_type', self.tr('Type de chemin de fer à extraire'), options=[self.tr('Tout'),'disused','light_rail','narrow_gauge','rail','tram'], defaultValue='Tout', allowMultiple=True, usesStaticStrings=True, optional=True))
		self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT', self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=False, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Make sure that the project set projection is in metric
		if not is_metric_crs(QgsProject.instance().crs()) :
			return False, self.tr(f"Le projet n'est pas dans un CRS en mètres! Veuillez utiliser un CRS approprié.")
		return True, ''


	def processAlgorithm(self, parameters, context, feedback):
		# Extracting the road and railway type selected by the user
		selected_road_type = self.parameterAsEnumStrings(parameters, 'road_type', context)
		selected_rail_type = self.parameterAsEnumStrings(parameters, 'railway_type', context)

		# Expression used to select the type of roads and railway wanted
		if self.tr("Tout") in selected_road_type :
			expression_road = "(\"highway\" IN ('cycleway','motorway','motorway_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','trunk','trunk_link','residential'))"
		else :
			expression_road = "(\"highway\" IN ({}))".format(", ".join([f"'{t}'" for t in selected_road_type]))

		if self.tr("Tout") in selected_rail_type :
			expression_rail = "(\"railway\" IN ('disused','light_rail','narrow_gauge','rail','tram'))"
		else :
			expression_rail = "(\"railway\" IN ({}))".format(", ".join([f"'{t}'" for t in selected_rail_type]))

		expression = expression_road+" OR "+expression_rail

		if feedback.isCanceled():
			return {}

		OSM_lines = self.parameterAsVectorLayer(parameters, self.LINES, context)
		# Verify that the layer is in the right projection
		if OSM_lines.crs().authid() != QgsProject.instance().crs().authid() :
			feedback.pushInfo(self.tr(f"CRS de la couche OSM_lines non conforme au projet. La couche sera reprojeté à {QgsProject.instance().crs().authid()}"))
			# Making the projection the same as the project
			try:
				alg_params = {
					'INPUT': OSM_lines,
					'TARGET_CRS': QgsProject.instance().crs().authid(),
					'OUTPUT': 'memory:'
				}
				reproj_lyr = processing.run('native:reprojectlayer', alg_params,context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
				OSM_lines = make_layer(reproj_lyr, context, "reproj_layer")
			except Exception as e :
				feedback.reportError(self.tr(f"Erreur lors de la reprojection de la couche de lignes OSM : {str(e)}"))
				return {}

		# Selecting the lines that are roads or train tracks
		alg_params = {
			'INPUT' : OSM_lines,
			'EXPRESSION': expression,
			'METHOD' : 0, # Creating new selection
		}
		try :
			processing.run("qgis:selectbyexpression", alg_params, context=context, feedback=None, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(f"Erreur lors de la sélection par expression : {str(e)}")
			return {}

		feedback.setProgressText(self.tr(f"{OSM_lines.selectedFeatureCount()} routes sélectionnées depuis le fichier d'OpenStreetMap"))

		if feedback.isCanceled():
			return {}

		# Selecting the road that are within (intersect) the watershed
		watershed_area = self.parameterAsVectorLayer(parameters, 'watershed_area', context)
		alg_params = {
			'INPUT': OSM_lines,
			'PREDICATE': [0],
			'INTERSECT': watershed_area,
			'METHOD': 2
		}
		try :
			processing.run("qgis:selectbylocation", alg_params, context=context, feedback=None, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors de la sélection par localisation : {str(e)}"))
			return {}

		feedback.setProgressText(self.tr(f"{OSM_lines.selectedFeatureCount()} routes dans le BV à partir des routes sélectionnées"))

		# Stop the algorithm if cancel button has been clicked
		if feedback.isCanceled():
			return {}

		# Extract the selection into a new layer
		alg_params = {
			'INPUT': OSM_lines,
			'OUTPUT': 'memory:'
		}
		try :
			extracted_roads = processing.run("native:saveselectedfeatures", alg_params, context=context, feedback=None, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors du traitement : {str(e)}"))
			return {}

		# Adding the half width (m) of roads, railways and bike paths (to adjust to your situation)
		feedback.setProgressText(self.tr("Ajout de la demi emprise du réseau routier, ferroviaire et cyclable..."))
		demi_rail = { # Based on data found in Transport Canada. (2014, 12 mars). Norme relative aux gabarits ferroviaires.
			'rail': 5.486,
			'light_rail': 5.486,
			'tram': 5.486,
			'narrow_gauge': 5.486, # Note : there is no narrow gauge (space between rail <= 1m) used in Canada (1435mm gauge is used), but we leave it here as an option for other users
			'disused': 5.486
		}
		demi_road = { # Based on data found in ministère des Transports du Québec. (2012, 15 juin). Tome I - Conception routière (13e éd.). Les Publications du Québec.
			'motorway': 22.5, 'motorway_link': 4,
			'trunk': 21.25, 'trunk_link' : 2.5,
			'primary': 21.25, 'primary_link': 2.5,
			'secondary': 17.5, 'secondary_link': 2.5,
			'tertiary': 15, 'tertiary_link': 2.5,
			'unclassified': 12.5,
			'residential': 10,
			'cycleway': 1.5
			# motif *_link handled separetaly
		}

		def case_when_from_map(field, mp):
			parts = [f'WHEN "{field}" = \'{k}\' THEN {v}' for k, v in mp.items()]
			return " \n".join(parts)

		demi_emp_expr = f"""
		CASE
			{case_when_from_map('railway', demi_rail)}
			{case_when_from_map('highway', demi_road)}
			ELSE 10
		END
		"""

		try:
			fc_params = {
				'INPUT': extracted_roads['OUTPUT'],
				'FIELD_NAME': 'demi_emp',
				'FIELD_TYPE': 0,        # Decimal/double
				'FIELD_LENGTH': 10,
				'FIELD_PRECISION': 3,
				'FORMULA': demi_emp_expr,
				'OUTPUT': parameters['OUTPUT']
			}
			width_field = processing.run(
				"qgis:fieldcalculator", fc_params,
				context=context, feedback=None, is_child_algorithm=True
			)['OUTPUT']
		except Exception as e:
			feedback.reportError(self.tr(f"Erreur lors de l'ajout de la demi-emprise : {str(e)}"))
			return {}

		# Remove the selection in the source layer
		try :
			OSM_lines.removeSelection()
		except Exception as e :
			feedback.reportError(self.tr(f"Impossible de désélectionner les entités : {str(e)}"))

		feedback.setProgressText(self.tr("Fin de l'extraction des routes du BV"))

		if feedback.isCanceled():
			return {}

		return {'OUTPUT': width_field}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def name(self):
		return 'Extract_OSM_roads'

	def displayName(self):
		return self.tr("Extraction routes d'OSM")

	def group(self):
		return self.tr('IQM utils')

	def groupId(self):
		return 'iqmutils'

	def shortHelpString(self):
		return self.tr(
			"Extrait le réseau routier et chemin de fer à partir des données d'OpenStreetMap et ajoute les largeurs d'emprise de celles-ci\n" \
			"Paramètres\n" \
			"----------\n" \
			"lines : Vectoriel (lignes)\n" \
			"-> Lignes représentant le réseau routier et autres particularités du territoire (lignes électriques, rivières etc.). Source des données : OpenStreetMap (à partir du fichier map.osm téléchargé pour la superficie du bassin-versant).\n" \
			"Aire du bassin versant : Vectoriel (polygone)\n" \
			"-> Superficie du bassin versant étudié dans laquelle isoler les routes. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Bassins hydrographiques multiéchelles du Québec, [Jeu de données], dans Données Québec.\n" \
			"Type de route à extraire : Liste[str] (optionnel; valeur par défaut : Tout)\n" \
			"-> Menu déroulant du type de route à sélectionner (selon les valeurs de la colonne highway de la table attributaire de lines). Voir la définition des valeurs sur la page Key:highway du wiki d'OpenStreetMap.\n" \
			"Type de chemin de fer à extraire : Liste[str] (optionnel; valeur par défaut : Tout)\n" \
			"-> Menu déroulant du type de chemin de fer à sélectionner (selon les valeurs de la colonne railway de la table attributaire de lines). Voir la définition des valeurs sur la page Key:railway du wiki d'OpenStreetMap.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau routier et ferroviaire du bassin versant."
		)

	def createInstance(self):
		return Extract_OSM_roads()


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters


def make_layer(obj, context, name='layer'):
	"""
	Make sure we have a QgsVectorLayer.
	- If obj is already a layer it is returned
	- If obj is a string (path/ID), we convert is to a OGR layer.
	"""
	if isinstance(obj, QgsVectorLayer):
		return obj
	if isinstance(obj, str):
		lyr = QgsProcessingUtils.mapLayerFromString(obj, context)
		if lyr is None or not lyr.isValid():
			raise RuntimeError(f"Impossible de charger la couche '{name}' depuis: {obj}")
		return lyr
	raise TypeError(f"Type inattendu pour '{name}': {type(obj)}")
