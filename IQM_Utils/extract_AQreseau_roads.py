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

import processing
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingUtils,
	QgsUnitTypes,
	QgsVectorLayer,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSink,
	QgsProject
)

class extract_AQreseau_roads(QgsProcessingAlgorithm):

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer("roads", self.tr('Réseau routier (MRNF)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer("cycleway", self.tr('Réseau cyclable (MRNF)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer("railway", self.tr('Réseau ferroviaire (MRNF)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('watershed_area', self.tr('Superficie du BV (MELCCFP)'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink('OUTPUT', self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorLine, createByDefault=False, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		road_network = self.parameterAsVectorLayer(parameters, 'roads', context)
		cycleway_network = self.parameterAsVectorLayer(parameters, 'cycleway', context)
		railway_network = self.parameterAsVectorLayer(parameters, 'railway', context)
		# Make sure that the project set projection is in metric
		if not is_metric_crs(QgsProject.instance().crs()) :
			return False, self.tr(f"Le projet n'est pas dans un CRS en mètres! Veuillez utiliser un CRS approprié.")
		# Make sure the given layers are the right ones
		for attrib_name in ["CaractRte", "ClsRte"]:
			if attrib_name not in [f.name() for f in road_network.fields()] :
				return False, self.tr(f"La couche de réseau routier donné n'est pas la bonne (ne contient pas l'attribut {attrib_name}) ! Veuillez fournir une couche conforme.")
		for attrib_name in ["CodEtatAvc", "CodTypVCyc"]:
			if attrib_name not in [f.name() for f in cycleway_network.fields()] :
				return False, self.tr(f"La couche de réseau cyclable donné n'est pas la bonne (ne contient pas l'attribut {attrib_name}) ! Veuillez fournir une couche conforme.")
		if "Classvoie" not in [f.name() for f in railway_network.fields()] :
			return False, self.tr(f"La couche de réseau ferroviaire donné n'est pas la bonne (ne contient pas l'attribut Classvoie) ! Veuillez fournir une couche conforme.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(5, model_feedback)

		# Creating the layers needed
		road_network = self.parameterAsVectorLayer(parameters, 'roads', context)
		cycleway_network = self.parameterAsVectorLayer(parameters, 'cycleway', context)
		railway_network = self.parameterAsVectorLayer(parameters, 'railway', context)
		watershed_area = self.parameterAsVectorLayer(parameters, 'watershed_area', context)

		# Verify the layers are created properly and that they are in the right projection
		layers = {road_network : "réseau routier", cycleway_network : "réseau cyclable", railway_network : "réseau ferroviaire", watershed_area : "superficie du BV"}
		feedback.setProgressText(self.tr("Vérification de la validité et SCR des couches..."))
		for layer, name in layers.items():
			if layer is None or not layer.isValid() : 
				raise RuntimeError(self.tr(f"Couche {name} invalide."))
			if layer.crs().authid() != QgsProject.instance().crs().authid() :
				feedback.pushInfo(self.tr(f"SCR de la couche {name} non conforme au projet. La couche sera reprojeté à {QgsProject.instance().crs().authid()}"))
				# Making the projection the same as the project
				try:
					alg_params = {
						'INPUT': layer,
						'TARGET_CRS': QgsProject.instance().crs().authid(),
						'OUTPUT': 'memory:'
					}
					reproj_lyr = processing.run('native:reprojectlayer', alg_params,context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
					layer = make_layer(reproj_lyr, context, "reproj_layer")
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur lors de la reprojection de la couche de {name}: {str(e)}"))
					return {}
		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}


		# Selection of road in the watershed (if none or empty just do the rest on all)
		if watershed_area.featureCount() > 0 :
			feedback.setProgressText(self.tr("Sélection des routes, chemins de fers et pistes cyclables dans le BV..."))
		else :
			feedback.setProgressText(self.tr("Couche de superficie de bassin vide. Le traitement et la fusion sera faite sur l'ensemble du territoire."))
		clipped_layers = []
		for layer in [road_network, cycleway_network, railway_network]:
			if watershed_area.featureCount() > 0 : 
				alg_params = {
					'INPUT': layer,
					'PREDICATE': [0], # 0 = Intersect
					'INTERSECT': watershed_area,
					'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
				}
				try :
					extract_lyr = processing.run("native:extractbylocation", alg_params, context=context, feedback=None, is_child_algorithm=True)
					clipped_layers.append(extract_lyr)
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur lors de la sélection par localisation : {str(e)}"))
					return {}
			else : # If an empty watershed area layer is given it will do the rest on all features of the layers
				clipped_layers.append(layer)
		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}


		# Filtering each layers to only keep relevant lines
		feedback.setProgressText(self.tr("Sélection des routes, chemins de fers et pistes cyclables pertinentes..."))
		filtered_layers = []
		# Filtering roads wanted
		try :
			roads_expression = "(\"CaractRte\" IS NOT 'Tunnel') AND (\"ClsRte\" NOT IN ('Sans classe' , 'Liaison maritime'))" # Removes tunnels (Tunnel) and roads that are either not drivable areas (Sans Classe) or that are ferry ways (Liaison maritime)
			alg_params = {
				'INPUT' : clipped_layers[0]['OUTPUT'] if watershed_area.featureCount() > 0 else clipped_layers[0],
				'EXPRESSION' : roads_expression,
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			filtered_layers.append(processing.run("native:extractbyexpression", alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT'])
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors de l'extraction par expr. des routes' : {str(e)}"))
			return {}
		if feedback.isCanceled():
			return {}
		# Filtering cycleways
		try :
			cycleway_expression = "(\"CodEtatAvc\" IN ('B' , 'E')) AND (\"CodTypVCyc\" = '5' )" # Only marked and existing cycleways (B, E) as well as only cycleways that are apart from the road (5)
			alg_params = {
				'INPUT' : clipped_layers[1]['OUTPUT'] if watershed_area.featureCount() > 0 else clipped_layers[1],
				'EXPRESSION' : cycleway_expression,
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			filtered_layers.append(processing.run("native:extractbyexpression", alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT'])
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors de l'extraction par expr. des pistes cyclables' : {str(e)}"))
			return {}
		if feedback.isCanceled():
			return {}
		# Filtering railways
		try :
			railway_expression = "\"Classvoie\" IS NOT 'Transbordeur'" # Remove train ferry (transbordeur)
			alg_params = {
				'INPUT' : clipped_layers[2]['OUTPUT'] if watershed_area.featureCount() > 0 else clipped_layers[2],
				'EXPRESSION' : railway_expression,
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			filtered_layers.append(processing.run("native:extractbyexpression", alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT'])
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors de l'extraction par expr. des chemins de fers' : {str(e)}"))
			return {}
		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}


		# Fuse all three layers into one
		feedback.setProgressText(self.tr("Fusion des trois couches en une couche unie..."))
		try:
			alg_params = {
				'LAYERS' : filtered_layers,
				'CRS': QgsProject.instance().crs().authid(),
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			fused_layer = processing.run("native:mergevectorlayers", alg_params, context=context, feedback=None, is_child_algorithm=True )
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur lors de la fusion des trois couches' : {str(e)}"))
			return {}
		feedback.setCurrentStep(4)
		if feedback.isCanceled():
			return {}


		# Adding road width to each type of road
		feedback.setProgressText(self.tr("Ajout des largeurs des routes..."))
		demi_road = { # Based on data found in ministère des Transports du Québec. (2012, 15 juin). Tome I - Conception routière (13e éd.). Les Publications du Québec.
			# Based on half of the nominal width
			'Autoroute' :  22.5, # Type A : Autoroute à quatre voies et terre plein central de 15 m
			'Nationale' : 21.25, # Type B : Route nationale
			'Régionale' : 17.50, # Type C : Route nationale ou régionale
			'Artère' : 15.0, # Type D : Route nationale régionale - collectrice ou locale
			'Collectrice de transit': 12.5, # Type E : Route régionale - collectrice ou locale
			'Collectrice municipale' : 10, # Type F : Collectrice ou locale,
			'Locale' : 10, # Type F : Collectrice ou locale
			'Accès aux ressources' : 10, # Type F : Collectrice ou locale
			'Accès aux ressources et aux localités isolées' : 10, # Type F : Collectrice ou locale
			'Rue piétonne': 10, # Type F : Collectrice ou locale
		}
		demi_bretelle = {
			'Bretelle' : 4.0 # Musoirs et bretelles d'autoroute une voie
		}
		demi_cycleway = { # Based on data found in ministère des Transports du Québec. (2012, 15 juin). Tome I - Conception routière (13e éd.). Les Publications du Québec.
			1 : 1.25,  # Unidirectional cycleway
			2 : 1.5    # Bidirectional cycleway
		}

		def case_when_from_map(field, mp):
			parts = [f'WHEN "{field}" = \'{k}\' THEN {v}' for k, v in mp.items()]
			return " \n".join(parts)

		demi_emp_expr = f"""
		CASE
			{case_when_from_map('ClsRte', demi_road)}
			{case_when_from_map('CaractRte', demi_bretelle)}
			{case_when_from_map('NbrVoieCyc', demi_cycleway)}
			WHEN "Etat" IS NOT NULL THEN 5.486
			ELSE NULL
		END
		"""
		try:
			fc_params = {
				'INPUT': fused_layer['OUTPUT'],
				'FIELD_NAME': 'demi_emp',
				'FIELD_TYPE': 0,        # Decimal/double
				'FIELD_LENGTH': 10,
				'FIELD_PRECISION': 3,
				'FORMULA': demi_emp_expr,
				'OUTPUT': parameters['OUTPUT']
			}
			width_field = processing.run("qgis:fieldcalculator", fc_params,context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		except Exception as e:
			feedback.reportError(self.tr(f"Erreur lors de l'ajout de la demi-emprise : {str(e)}"))
			return {}
		feedback.setCurrentStep(5)
		if feedback.isCanceled():
			return {}

		# Ending message
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {'OUTPUT': width_field}


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def name(self):
		return 'extract_AQreseau_roads'


	def displayName(self):
		return self.tr("Extraction routes AQréseau+")


	def group(self):
		return self.tr('IQM utils')


	def groupId(self):
		return 'iqmutils'


	def shortHelpString(self):
		return self.tr(
			"Extrais le réseau routier, ferroviaire et cyclable à partir des données d'AQréseau+ (pour le territoire québécois seulement) pour le bassin versant donné et ajoute les largeurs d'emprise de celles-ci\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau routier : Vectoriel (lignes)\n" \
			"-> Couche Reseau_routier d'AQréseau+ de lignes représentant le réseau routier. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Adresses Québec, [Jeu de données], dans Données Québec.\n" \
			"Réseau cyclable : Vectoriel (lignes)\n" \
			"-> Couche Route_Verte d'AQréseau+ de lignes représentant le réseau de pistes cyclables constituant la Route Verte. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Adresses Québec, [Jeu de données], dans Données Québec.\n" \
			"Réseau ferroviaire : Vectoriel (lignes)\n" \
			"-> Couche Reseau_ferroviaire d'AQréseau+ de lignes représentant le réseau de chemins de fer. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Adresses Québec, [Jeu de données], dans Données Québec.\n" \
			"Superficie du bassin versant : Vectoriel (polygone)\n" \
			"-> Superficie du bassin versant étudié dans laquelle isoler les routes. Note : si cette couche est vide l'algorithme fera les traitements et fusionnera les routes, chemins de fers et pistes cyclables sur l'emsemble du territoire québecois. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Bassins hydrographiques multiéchelles du Québec, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau routier, cyclable et ferroviaire du bassin versant."
		)


	def createInstance(self):
		return extract_AQreseau_roads()


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