
import processing
import time
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingUtils,
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
		feedback = QgsProcessingMultiStepFeedback(13, model_feedback)
		current_step = 0
		results = {}
		outputs = {}

		# =======================$|  Preprocessing  |$=======================
		# (intermediate results required for calculating indices)

		feedback.setProgressText(self.tr(f"Initialisation des étapes de prétraitement..."))

		# 	Compute D8 pointer
		feedback.setProgressText(self.tr(f"- Création du WBT D8 pointer"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'dem': parameters['dem'],
				'stream_network': parameters['stream_network'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT 
			}
			outputs['CalculePointeurD8'] = processing.run('script:computed8', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul du WBT D8 pointer : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul WBT D8 pointer", feedback)
		if feedback.isCanceled():
			return {}

		# 	Filter structures
		feedback.setProgressText(self.tr(f"- Extraction des structures filtrées"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'cours_eau': parameters['stream_network'],
				'routes': parameters['routes'],
				'structures': parameters['structures'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['FiltrerStructures'] = processing.run('script:filterstructures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le filtre des structures : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "filtre struct", feedback)
		if feedback.isCanceled():
			return {}

		# 	Extract sub watersheds
		feedback.setProgressText(self.tr(f"- Extraction de la couche de sous-BV"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'stream_network' : parameters['stream_network'],
				'D8' : outputs['CalculePointeurD8']['OUTPUT'],
				'dams' : parameters['dams'],
				'landuse' : parameters['landuse'],
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			watersheds_data = processing.run('script:extract_subwatershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			watersheds = QgsProcessingUtils.mapLayerFromString(watersheds_data, context)
			if not watersheds or not watersheds.isValid() :
					# Verifies if the created layer is valid
					feedback.reportError(self.tr("La couche watersheds est invalide."))
					return {}
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans l'extraction des sous-BV : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "extract sous-BV", feedback)
		if feedback.isCanceled():
			return {}

		# =====================$|  Index calculation  |$=====================

		feedback.setProgressText(self.tr(f"Calcul des indices..."))

		# 	Index A1
		feedback.setProgressText(self.tr(f"- Calcul de l'indice A1"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'SUB_WATERSHED_GIVEN' : True,
				'watersheds' : watersheds,
				'stream_network' : parameters['stream_network'],
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceA1'] = processing.run('script:indicea1', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de A1 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul A1", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index A2
		feedback.setProgressText(self.tr(f"- Calcul de l'indice A2"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'SUB_WATERSHED_GIVEN' : True,
				'watersheds' : watersheds,
				'stream_network' : outputs['IndiceA1']['OUTPUT'],
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceA2'] = processing.run('script:indicea2', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de A2 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul A2", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index A3
		feedback.setProgressText(self.tr(f"- Calcul de l'indice A3"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'stream_network' : outputs['IndiceA2']['OUTPUT'],
				'dams' : parameters['dams'],
				'landuse' : parameters['landuse'],
				'ptref_widths' : parameters['ptref_widths'],
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceA3'] = processing.run('script:indicea3', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de A3 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul A3", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index A4
		feedback.setProgressText(self.tr(f"- Calcul de l'indice A4"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'INPUT': outputs['IndiceA3']['OUTPUT'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceA4'] = processing.run('script:indicea4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de A4 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul A4", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index F1
		feedback.setProgressText(self.tr(f"- Calcul de l'indice F1"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'INPUT': outputs['IndiceA4']['OUTPUT'],
				'structs' : outputs['FiltrerStructures']['OUTPUT'],
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceF1'] = processing.run('script:indicef1', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de F1 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul F1", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index F2
		feedback.setProgressText(self.tr(f"- Calcul de l'indice F2"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'anthropic_layers': parameters['routes'],
				'ptref_widths': parameters['ptref_widths'],
				'rivnet': outputs['IndiceF1']['OUTPUT'],
				'landuse': parameters['landuse'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceF2'] = processing.run('script:indicef2', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de F2 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul F2", feedback)
		if feedback.isCanceled():
			return {}


		# Index F3
		feedback.setProgressText(self.tr(f"- Calcul de l'indice F3"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'ptref_widths': parameters['ptref_widths'],
				'anthropic_layers': parameters['routes'],
				'rivnet': outputs['IndiceF2']['OUTPUT'],
				'landuse': parameters['landuse'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceF3'] = processing.run('script:indicef3', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de F3 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul F3", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index F4
		feedback.setProgressText(self.tr(f"- Calcul de l'indice F4"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'ptref_widths': parameters['ptref_widths'],
				#'ratio': 2.5,
				'rivnet': outputs['IndiceF3']['OUTPUT'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceF4'] = processing.run('script:indicef4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de F4 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul F4", feedback)
		if feedback.isCanceled():
			return {}


		# 	Index F5
		feedback.setProgressText(self.tr(f"- Calcul de l'indice F5"))
		start_time = time.perf_counter()
		try :
			alg_params = {
				'bande_riveraine_polly': parameters['bande_riv'],
				'ptref_widths': parameters['ptref_widths'],
				#'ratio': 2.5,
				'rivnet': outputs['IndiceF4']['OUTPUT'],
				#'transectsegment': 25,
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['IndiceF5'] = processing.run('script:indicef5', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de F5 : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul F5", feedback)
		if feedback.isCanceled():
			return {}


		# ======================$|  IQM calculation  |$======================

		feedback.setProgressText(self.tr(f"Calcul de l'IQM total des segments..."))

		# Field calculator for total IQM calculation of each segments
		start_time = time.perf_counter()
		try :
			alg_params = {
				'FIELD_LENGTH': 2,
				'FIELD_NAME': 'Score IQM9',
				'FIELD_PRECISION': 2,
				'FIELD_TYPE': 0,  # Décimal (double)
				'FORMULA': '1 - (array_sum(array( "Indice A1",  "Indice A2" ,  "Indice A3" ,  "Indice A4" ,  "Indice F1" ,  "Indice F2" ,  "Indice F3" ,  "Indice F4" ,  "Indice F5"))) / 40', # for each river segment : IQM = 1 - (total score/max score)
				'INPUT': outputs['IndiceF5']['OUTPUT'],
				'OUTPUT': parameters['Iqm']
			}
			outputs['FieldCalculator'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
			results['Iqm'] = outputs['FieldCalculator']['OUTPUT']
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de l'IQM : {str(e)}"))
		current_step = self.get_ET_and_current_step(start_time, current_step, "calcul IQM", feedback)

		# Ending message
		feedback.setProgressText(self.tr('Processus terminé !'))

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


	def get_ET_and_current_step(self, start_time, current_step, step, feedback):
		# Simple function to output the time elapsed and update the current step to the journal
		end_time = time.perf_counter()
		elapsed_time = end_time - start_time
		time_string = '{:.2f} secondes'.format(elapsed_time)
		if elapsed_time > 120 : # if time greater than 2 minutes display in minutes seconds
			m, s = divmod(elapsed_time, 60)
			time_string = '{:.0f} minutes et {:.2f} secondes'.format(m,s)
			if m > 60 : # if time greater than an hour add hours too
				h, m = divmod(m, 60)
				time_string = '{:.0f} heures, {:.0f} minutes et {:.2f} secondes'.format(h, m, s)
		# Increments current step count for progress bar
		current_step += 1
		feedback.setCurrentStep(current_step)
		feedback.setProgressText(self.tr(f"--> Temps écoulé pour l'étape {step} : {time_string}"))
		return current_step


	def createInstance(self):
		return compute_iqm()

