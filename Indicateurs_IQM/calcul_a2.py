
from tempfile import NamedTemporaryFile as Ntf
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
					   QgsField,
					   QgsFeatureSink,
					   QgsVectorLayer,
					   )
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsCoordinateReferenceSystem
import processing


class IndiceA2(QgsProcessingAlgorithm):
	ID_FIELD = 'Id'
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr("Réseau hydrographique (CRHQ)"), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))



	def processAlgorithm(self, parameters, context, model_feedback):

		outputs = {}

		# Create temporary file locations
		tmp = {
			'mainWatershed' : Ntf(suffix="watershed.tif"),
			'subWatershed' : Ntf(suffix="sub-watershed.tif"),
		}

		# Define source stream net
		source = self.parameterAsSource(parameters, 'stream_network', context)

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

		if model_feedback.isCanceled():
			return {}

		# Snap dams to river network
		alg_params = {
			'BEHAVIOR': 1,  # Prefer closest point, insert extra vertices where required
			'INPUT': parameters['dams'],
			'REFERENCE_LAYER': parameters['stream_network'],
			'TOLERANCE': 75,
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['SnappedDams'] = processing.run('native:snapgeometries', alg_params, context=context, feedback=None, is_child_algorithm=True)


		# Extract specific vertex
		# TODO : try and remove is_child_algorithm
		alg_params = {
			'INPUT': parameters['stream_network'],
			'VERTICES': '-2',
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['ExtractSpecificVertex'] = processing.run(
			'native:extractspecificvertices', alg_params, context=context, feedback=None, is_child_algorithm=True)

		if model_feedback.isCanceled():
			return {}

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for feature in source.getFeatures():
			fid = feature[fid_idx]
			# For each segment
			# Compute waterhed
			if model_feedback.isCanceled():
				return {}

			# Extract By Attribute
			alg_params = {
				'FIELD': self.ID_FIELD,
				'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
				'OPERATOR': 0,  # =
				'VALUE': str(fid),
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['single_point'] = processing.run(
				'native:extractbyattribute', alg_params, context=context, feedback=None, is_child_algorithm=True)

			if model_feedback.isCanceled():
				return {}

			# Watershed
			alg_params = {
				'd8_pntr': parameters['D8'],
				'esri_pntr': False,
				'pour_pts': outputs['single_point']['OUTPUT'],
				'output': tmp['mainWatershed'].name
			}
			outputs['mainWatershed'] = processing.run(
				'wbt:Watershed', alg_params, context=context, feedback=None, is_child_algorithm=True)

			# Polygonize watershed (raster to vector)
			alg_params = {
				'BAND': 1,
				'EIGHT_CONNECTEDNESS': False,
				'EXTRA': '',
				'FIELD': 'DN',
				'INPUT': outputs['mainWatershed']['output'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['mainWatershedPoly'] = processing.run(
				'gdal:polygonize', alg_params, context=context, feedback=None, is_child_algorithm=True)

			# Compute watershed total area
			mainWatershedPoly = QgsVectorLayer(
				outputs['mainWatershedPoly']['OUTPUT'], 'vector main watershed', 'ogr')
			main_area = sum([feat.geometry().area()
						   for feat in mainWatershedPoly.getFeatures()])

			# Clip Dams
			alg_params = {
				'INPUT': outputs['SnappedDams']['OUTPUT'],
				'INTERSECT': outputs['mainWatershedPoly']['OUTPUT'],
				'PREDICATE': [6],  # are within
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['ClipDams'] = processing.run('native:extractbylocation', alg_params, context=context, feedback=None, is_child_algorithm=True)

			 # Watershed
			alg_params = {
				'd8_pntr': parameters['D8'],
				'esri_pntr': False,
				'pour_pts': outputs['ClipDams']['OUTPUT'],
				'output': tmp['subWatershed'].name
			}
			outputs['subWatershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=None, is_child_algorithm=True)

			if model_feedback.isCanceled():
				return {}

			# Vectorized Sub-watersheds
			alg_params = {
				'BAND': 1,
				'EIGHT_CONNECTEDNESS': False,
				'EXTRA': '',
				'FIELD': 'DN',
				'INPUT': outputs['subWatershed']['output'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['subWatershedPoly'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=None, is_child_algorithm=True)

			# Compute watershed total area
			subWatershedPoly = QgsVectorLayer(
				outputs['subWatershedPoly']['OUTPUT'], 'vector sub watershed', 'ogr')
			sub_area = sum([feat.geometry().area()
						   for feat in subWatershedPoly.getFeatures()])

			indiceA2 = 0

			if main_area != 0 and sub_area != 0:
				# get dams sub watersheds area ration
				ratio = sub_area / main_area
				if ratio < 0.05:
					indiceA2 = 0
				elif 0.05 <= ratio < 0.33:
					indiceA2 = 2
				elif 0.33 <= ratio < 0.66:
					indiceA2 = 3
				elif 0.66 <= ratio:
					indiceA2 = 4


			# Add forest area to new featuer
			feature.setAttributes(
				feature.attributes() + [indiceA2]
			)

			# Add modifed feature to sink
			sink.addFeature(feature, QgsFeatureSink.FastInsert)

			#print(f'{fid}/{total_features}')

			# Increments the progress bar
			if total_features != 0:
				progress = int(100*(current/total_features))
			else:
				progress = 0
			model_feedback.setProgress(progress)
			model_feedback.setProgressText(self.tr(f"Traitement de {current} segments sur {total_features}"))


		# Clear temporary files
		for tempfile in tmp.values():
			tempfile.close()

		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé et fichiers temporaire nettoyés'))

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
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"WBT D8 Pointer: Matriciel\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice A2 calculé pour chaque UEA."
		)
