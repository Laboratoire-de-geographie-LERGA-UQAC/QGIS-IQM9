
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsProcessingUtils,
	QgsProcessingAlgorithm,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterBoolean,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink
)


class IndiceA2(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterBoolean('SUB_WATERSHED_GIVEN', self.tr('Couche de sous-BV fournie ?'), defaultValue=False))
		self.addParameter(QgsProcessingParameterVectorLayer('watersheds', self.tr('Sous bassins versants et util. terr (sortant de Extract. sous-BV)'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		use_sub_watershed = self.parameterAsBool(parameters, 'SUB_WATERSHED_GIVEN', context)

		if use_sub_watershed:
			if parameters['watersheds'] is None:
				return False, self.tr('Vous avez choisi d’utiliser la couche de sous-BV, mais elle n’est pas fournie.')
		else:
			if parameters['D8'] is None or parameters['dams'] is None or parameters['landuse'] is None :
				return False, self.tr('Vous devez fournir les couches nécessaires (WBT D8 Pointer, Barrages et Util. du terr.) pour créer la couche de sous-BV.')
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
		outputs = {}

		# Define stream netwprk as source for data output
		source = self.parameterAsVectorLayer(parameters, 'stream_network', context)

		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Indice A2", QVariant.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		if feedback.isCanceled():
			return {}

		watersheds = self.parameterAsVectorLayer(parameters, 'watersheds', context)
		if watersheds is None :
			# If the sub watershed layer is not given
			feedback.setProgressText(self.tr(f"Création de la couche de sous-BV"))
			try :
				# Create the sub watersheds
				alg_params = {
					'stream_network' : parameters['stream_network'],
					'D8' : parameters['D8'],
					'dams' : parameters['dams'],
					'landuse' : parameters['landuse'],
					'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
				}
				watersheds_data = processing.run('script:extract_subwatershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
				watersheds = QgsProcessingUtils.mapLayerFromString(watersheds_data, context)
				if not watersheds or not watersheds.isValid() :
					# Verify if the created layer is valid
					feedback.reportError(self.tr("La couche watersheds est invalide."))
					return {}
			except Exception as e :
				feedback.reportError(self.tr(f"Erreur dans la création de la couche de sous-BV : {str(e)}"))
		feedback.setCurrentStep(1)
		# Compute A2 index
		feedback.setProgressText(self.tr(f"Calcul de l'indice A2"))
		try :
			outputs['watersheds'] = computeA2(watersheds, context, feedback=None)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de l'indice A2 : {str(e)}"))
		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# Getting results ready to output
		feedback.setProgressText(self.tr(f"Sortie des résultats."))
		try :
			# Convert watershed features to vector layers
			watersheds_lyr = QgsVectorLayer(outputs['watersheds'], 'ws', 'ogr')
			# Map feature ID and index values for each watershed layer
			a2_map = {f['DN']: f['Indice A2'] for f in watersheds_lyr.getFeatures()}
			# Write final indices to sink using map
			for feat in source.getFeatures():
				seg = feat['Segment']
				vals = feat.attributes()
				vals += [a2_map.get(seg, None)]
				feat.setAttributes(vals)
				sink.addFeature(feat, QgsFeatureSink.FastInsert)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la sortie des résultats : {str(e)}"))
		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}

		# Ending message
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT: dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceA2()

	def name(self):
		return 'Indice A2'

	def displayName(self):
		return self.tr('Indice A2')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice A2 afin d'évaluer l’impact des barrages présents à l’amont du segment sur les processus hydrogéomorphologiques en aval en fonction de l’aire d’alimentation affectée.\n Les barrages localisés sur l’ensemble du réseau hydrographique à l’amont du segment analysé sont considérés dans le calcul de l’aire de drainage.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Couche de sous-BV fournis: Booléen (optionnel; valeur par défaut : Faux)\n" \
			"-> Détermine si la couche de sous-BV (préalablement produite par Extract sous-BV et landuse [A123]) est fournie par l'utilisateur.\n" \
			"Sous bassins versants et util. terr: Vectoriel (polygone) (optionnel, mais obligatoire si couche de sous-BV fournis est coché)\n" \
			"-> Couche de polygones contenant les sous bassin versant du BV donné ainsi que l'information d'utilisation du territoire. Produit par le script IQM utils Extract sous-BV et landuse (A123). Source des données : À produire soi-même préalablement.\n" \
			"WBT D8 Pointer: Matriciel (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Barrages : Vectoriel (point) (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice A2 calculé pour chaque UEA."
		)


def computeA2(watersheds, context, feedback) :
	a2_formula = """
		CASE
			WHEN "watershed_area" = 0 THEN 2
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.05 THEN 0
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.33 THEN 2
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.66 THEN 3
			ELSE 4
		END
		"""
	alg_params = {
		'INPUT': watersheds,
		'FIELD_NAME': 'Indice A2',
		'FIELD_TYPE': 2,  # 2 = Integer
		'FIELD_LENGTH': 3,
		'FIELD_PRECISION': 0,
		'NEW_FIELD': True,
		'FORMULA': a2_formula,
		'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds.shp")
	}
	return processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']