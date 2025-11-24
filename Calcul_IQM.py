
import processing
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingAlgorithm,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterFeatureSink
)


class compute_iqm(QgsProcessingAlgorithm):

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('bande_riv', self.tr('Bande riveraine (peuplement forestier; MELCCFP)'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('dem', self.tr('MNT LiDAR (10 m)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('routes', self.tr('Réseau routier (OSM)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('structures', self.tr('Structures (MTMD)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink('Iqm', self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):
		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
		results = {}
		outputs = {}

		# Calcule pointeur D8
		alg_params = {
			'dem': parameters['dem'],
			'stream_network': parameters['stream_network'],
			#'D8pointer': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['CalculePointeurD8'] = processing.run('script:computed8', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# Filtrer structures
		alg_params = {
			'cours_eau': parameters['stream_network'],
			'routes': parameters['routes'],
			'structures': parameters['structures'],
			'New_structures': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['FiltrerStructures'] = processing.run('script:filterstructures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# A1 A2 A3 F1
		alg_params = {
			'd8': outputs['CalculePointeurD8']['D8pointer'],
			'dams': parameters['dams'],
			'landuse': parameters['landuse'],
			'ptrefs_largeur': parameters['ptref_widths'],
			'stream_network': parameters['stream_network'],
			'structures': outputs['FiltrerStructures']['New_structures'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['A1A2A3F1'] = processing.run('script:calculA123', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}

		# Indice A4
		alg_params = {
			'INPUT': outputs['A1A2A3F1']['OUTPUT'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['IndiceA4'] = processing.run('script:indicea4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(4)
		if feedback.isCanceled():
			return {}

		# Indice F2
		alg_params = {
			'anthropic_layers': parameters['routes'],
			'landuse': parameters['landuse'],
			'ptref_widths': parameters['ptref_widths'],
			'rivnet': outputs['IndiceA4']['OUTPUT'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['IndiceF2'] = processing.run('script:indicef2', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(5)
		if feedback.isCanceled():
			return {}

		# Indice F3
		alg_params = {
			'anthropic_layers': parameters['routes'],
			'landuse': parameters['landuse'],
			'ptref_widths': parameters['ptref_widths'],
			'rivnet': outputs['IndiceF2']['OUTPUT'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['IndiceF3'] = processing.run('script:indicef3', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(6)
		if feedback.isCanceled():
			return {}

		# Indice F4
		alg_params = {
			'ptref_widths': parameters['ptref_widths'],
			'ratio': 2.5,
			'rivnet': outputs['IndiceF3']['OUTPUT'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['IndiceF4'] = processing.run('script:indicef4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(7)
		if feedback.isCanceled():
			return {}

		# Indice F5
		alg_params = {
			'bande_riveraine_polly': parameters['bande_riv'],
			'ptref_widths': parameters['ptref_widths'],
			'ratio': 2.5,
			'rivnet': outputs['IndiceF4']['OUTPUT'],
			'transectsegment': 25,
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['IndiceF5'] = processing.run('script:indicef5', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(8)
		if feedback.isCanceled():
			return {}

		# Field calculator
		alg_params = {
			'FIELD_LENGTH': 2,
			'FIELD_NAME': 'Score IQM',
			'FIELD_PRECISION': 2,
			'FIELD_TYPE': 0,  # Décimal (double)
			'FORMULA': '1 - (array_sum(array( "Indice A1",  "Indice A2" ,  "Indice A3" ,  "Indice A4" ,  "Indice F1" ,  "Indice F2" ,  "Indice F3" ,  "Indice F4" ,  "Indice F5"))) / 38',
			'INPUT': outputs['IndiceF5']['OUTPUT'],
			'OUTPUT': parameters['Iqm']
		}
		outputs['FieldCalculator'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		results['Iqm'] = outputs['FieldCalculator']['OUTPUT']

		feedback.setCurrentStep(9)
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return results

	def name(self):
		return 'calculiqm'

	def displayName(self):
		return self.tr('Calcul IQM')

	def group(self):
		return ''

	def groupId(self):
		return ''

	def shortHelpString(self):
		return self.tr(
			"Calcule les neufs indices de qualité morphologique (IQM) de l'IQM9 de manière automatisée\n Voir les descriptions des indices individuels pour plus d'informations sur chacun.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Bande riveraine : Vectoriel (polygones)\n" \
			"-> Données vectorielles surfacique des peuplements écoforestiers pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Carte écoforestière à jour, [Jeu de données], dans Données Québec.\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"MNT LiDAR (10 m) : Matriciel\n" \
			"-> Modèle numérique de terrain par levés aériennes LiDAR de résolution de 1 m rééchantilloné à 10 m pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Lidar - Modèles numériques (terrain, canopée, pente, courbe de niveau), [Jeu de données], dans Données Québec.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Réseau routier : Vectoriel (lignes)\n" \
			"-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
			"Structures : Vectoriel (points)\n" \
			"-> Ensemble de données vectorielles ponctuelles des structures sous la gestion du Ministère des Transports et de la Mobilité durable du Québec (MTMD) (pont, ponceau, portique, mur et tunnel). Source des données : MTMD. Structure, [Jeu de données], dans Données Québec.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec les scores de chaque indice de l'IQM9 calculés pour chaque UEA."
		)

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return compute_iqm()