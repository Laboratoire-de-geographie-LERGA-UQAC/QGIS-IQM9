"""
***************************************************************************
*																		 *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or	 *
*   (at your option) any later version.								   *
*																		 *
***************************************************************************
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterEnum,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSink,
)
from qgis import processing


class Extract_OSM_roads(QgsProcessingAlgorithm):
	#OUTPUT = "OUTPUT"
	LINES = "OSM_lines"

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer(self.LINES, self.tr('lines (du fichier map.osm de OSM)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('watershed_area', self.tr('Superficie du BV'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterEnum('road_type', self.tr('Type de route à extraire'), options=[self.tr('Toutes'),'motorway','motorway_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','trunk','trunk_link','residential'], defaultValue='Toutes', allowMultiple=True, usesStaticStrings=True, optional=True))
		self.addParameter(QgsProcessingParameterEnum('railway_type', self.tr('Type de chemin de fer à extraire'), options=[self.tr('Tous'),'abandoned','disused','funicular','light_rail','narrow_gauge','rail','tram'], defaultValue='Tous', allowMultiple=True, usesStaticStrings=True, optional=True))
		self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT', self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=False, defaultValue=None))

	def processAlgorithm(self, parameters, context, feedback):

		# Extracting the road and railway type selected by the user
		selected_road_type = self.parameterAsEnumStrings(parameters, 'road_type', context)
		selected_rail_type = self.parameterAsEnumStrings(parameters, 'railway_type', context)

		# Expression used to select the type of roads and railway wanted
		if self.tr("Toutes") in selected_road_type :
			expression_road = "(\"highway\" IN ('motorway','motorway_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','trunk','trunk_link','residential'))"
		else :
			expression_road = "(\"highway\" IN ({}))".format(", ".join([f"'{t}'" for t in selected_road_type]))

		if self.tr("Tous") in selected_rail_type :
			expression_rail = "(\"railway\" IN ('abandoned','disused','funicular','light_rail','narrow_gauge','rail','tram'))"
		else :
			expression_rail = "(\"railway\" IN ({}))".format(", ".join([f"'{t}'" for t in selected_rail_type]))

		expression = expression_road+" OR "+expression_rail

		if feedback.isCanceled():
			return {}

		# Selecting the lines that are roads
		OSM_lines = self.parameterAsVectorLayer(parameters, self.LINES, context)
		alg_params = {
			'INPUT' : OSM_lines,
			'EXPRESSION': expression,
			'METHOD' : 0, # Creating new selection
		}
		try :
			processing.run("qgis:selectbyexpression", alg_params, context=context, feedback=None, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(f"Erreur lors du traitement : {str(e)}")
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
			feedback.reportError(f"Erreur lors du traitement : {str(e)}")
			return {}

		feedback.setProgressText(self.tr(f"{OSM_lines.selectedFeatureCount()} routes dans le BV à partir des routes sélectionnées"))

		# Stop the algorithm if cancel button has been clicked
		if feedback.isCanceled():
			return {}

		# Extract the selection into a new layer
		alg_params = {
			'INPUT': OSM_lines,
			'OUTPUT': parameters['OUTPUT']
		}
		try :
			extracted_roads = processing.run("native:saveselectedfeatures", alg_params, context=context, feedback=None, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(f"Erreur lors du traitement : {str(e)}")
			return {}

		# Remove the selection in the source layer
		try :
			OSM_lines.removeSelection()
		except Exception as e :
			feedback.reportError(f"Impossible de désélectionner les entités : {str(e)}")

		feedback.setProgressText(self.tr("Fin de l'extraction des routes du BV"))

		if feedback.isCanceled():
			return {}

		return {'OUTPUT': extracted_roads['OUTPUT']}

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
			"Extrait le réseau routier à partir des données d'OpenStreetMap\n" \
			"Paramètres\n" \
			"----------\n" \
			"lines : Vectoriel (lignes)\n" \
			"-> Lignes représentant le réseau routier et autres particularités du territoire (lignes électriques, rivières etc.). Source des données : OpenStreetMap (à partir du fichier map.osm téléchargé pour la superficie du bassin-versant).\n" \
			"Aire du bassin versant : Vectoriel (polygone)\n" \
			"-> Superficie du bassin versant étudié dans laquelle isoler les routes. Source des données : À faire soi-même.\n" \
			"Type de route à extraire : Liste[str] (optionnel; valeur par défaut : Toutes)\n" \
			"-> Menu déroulant du type de route à sélectionner (selon les valeurs de la colonne highway de la table attributaire de lines). Voir la définition des valeurs sur la page Key:highway du wiki d'OpenStreetMap.\n" \
			"Type de chemin de fer à extraire : Liste[str] (optionnel; valeur par défaut : Tous)\n" \
			"-> Menu déroulant du type de chemin de fer à sélectionner (selon les valeurs de la colonne railway de la table attributaire de lines). Voir la définition des valeurs sur la page Key:railway du wiki d'OpenStreetMap.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau routier et ferroviaire du bassin versant."
		)

	def createInstance(self):
		return Extract_OSM_roads()