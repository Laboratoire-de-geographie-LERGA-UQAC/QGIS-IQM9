
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsProcessingAlgorithm,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsCoordinateReferenceSystem)










class IndiceA1(QgsProcessingAlgorithm):
	ID_FIELD = 'fid'
	OUTPUT = 'OUTPUT'
	D8 = 'D8'
	LANDUSE = 'landuse'
	RIVNET = 'stream_network'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterRasterLayer(self.D8, self.tr('WBT D8 Pointer'), defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer(self.LANDUSE, self.tr('Utilisation du territoir'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer(self.RIVNET, self.tr('Cours d\'eau'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output Layer'), defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):
		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
		results = {}
		outputs = {}

		# Dictionnary that will contain all temporary file locations
		tmp = {}
		tmp['watershed'] = Ntf(suffix="watershed.tif")

		# Define source stream net
		source = self.parameterAsSource(parameters, 'stream_network', context)

		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Indice A1", QVariant.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)
		results[self.OUTPUT] = dest_id

		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# Reclassify land use
		alg_params = {
			'DATA_TYPE': 0,  # Byte
			'INPUT_RASTER': parameters['landuse'],
			'NODATA_FOR_MISSING': True,
			'NO_DATA': 0,
			'RANGE_BOUNDARIES': 2,  # min <= value <= max
			'RASTER_BAND': 1,
			'TABLE': [
				'50','56','1','210','235','1','501','735','1','101','199','2',
				'2050','2056','1','2210','2235','1','2501','2735','1','2101','2199','2',
				'4050','4056','1','4210','4235','1','4501','4735','1','4101','4199','2',
				'5050','5056','1','5210','5235','1','5501','5735','1','5101','5199','2',
				'6050','6056','1','6210','6235','1','6501','6735','1','6101','6199','2',
				'7050','7056','1','7210','7235','1','7501','7735','1','7101','7199','2',
				'8050','8056','1','8210','8235','1','8501','8735','1','8101','8199','2'
				],

			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		# Extract specific vertex
		alg_params = {
			'INPUT': parameters['stream_network'],
			'VERTICES': '-2',
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['ExtractSpecificVertex'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

		feedback.setCurrentStep(5)
		if feedback.isCanceled():
			return {}

		feature_count = source.featureCount()
		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for feature in source.getFeatures():
			fid = feature[fid_idx]
			# For each pour point
			# Compute the percentage of forests and agriculture lands in the draining area
			# Then compute index_A1 and add it in a new field to the river network
			if feedback.isCanceled():
				return {}

			# Extract By Attribute
			alg_params = {
			'FIELD': self.ID_FIELD,
			'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
			'OPERATOR': 0,  # =
			'VALUE': str(fid),
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['single_point']= processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

			# Watershed
			alg_params = {
				'd8_pntr': parameters['D8'],
				'esri_pntr': False,
				'pour_pts': outputs['single_point']['OUTPUT'],
				'output': tmp['watershed'].name
			}
			outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
			print(outputs['Watershed']['output'])

			# Polygonize (raster to vector)
			alg_params = {
				'BAND': 1,
				'EIGHT_CONNECTEDNESS': False,
				'EXTRA': '',
				'FIELD': 'DN',
				'INPUT': outputs['Watershed']['output'],
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

			# Drain_area Land_use
			alg_params = {
				'ALPHA_BAND': False,
				'CROP_TO_CUTLINE': True,
				'DATA_TYPE': 0,  # Use Input Layer Data Type
				'EXTRA': '',
				'INPUT': outputs['ReducedLanduse']['OUTPUT'],
				'KEEP_RESOLUTION': True,
				'MASK': outputs['PolygonizeRasterToVector']['OUTPUT'],
				'MULTITHREADING': False,
				'NODATA': None,
				'OPTIONS': '',
				'SET_RESOLUTION': False,
				'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
				'TARGET_CRS': 'ProjectCrs',
				'TARGET_EXTENT': None,
				'X_RESOLUTION': None,
				'Y_RESOLUTION': None,
				'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
			}
			outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

			# Landuse unique values report
			tmp['table'] = Ntf(suffix="table")
			alg_params = {
				'BAND': 1,
				'INPUT': outputs['Drain_areaLand_use']['OUTPUT'],
				'OUTPUT_TABLE': tmp['table'].name
			}
			outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

			# Create layers from source/path
			watershed_poly = QgsVectorLayer(outputs['PolygonizeRasterToVector']['OUTPUT'], 'poly', 'ogr')
			table = QgsVectorLayer(
				outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE'],
				'table', 'ogr'
			)

			# Here we compute watershed, forest and agri area, the add to new feture
			tot_area = sum([feat.geometry().area() for feat in watershed_poly.getFeatures()])
			forest_area = 0
			agri_area = 0

			if tot_area != 0:
				# Get forest and agri areas
				for feat in table.getFeatures():
					if feat['value'] == 1:
						forest_area = feat['m2']/tot_area
					elif feat['value'] == 2:
						agri_area = feat['m2']/tot_area


				# Assigne index A1
				if forest_area <= 0.1:
					indiceA1 = 5
				elif forest_area < 0.33:
					indiceA1 = 4
				elif forest_area <= 0.66:
					indiceA1 = 3 if agri_area < 0.33 else 2
				elif forest_area < 0.9:
					indiceA1 = 1
				else:
					indiceA1 = 0

			# Add forest area to new featuer
			feature.setAttributes(
					feature.attributes() + [indiceA1]
			)

			# Add modifed feature to sink
			sink.addFeature(feature, QgsFeatureSink.FastInsert)

			print(f'{fid}/{feature_count}')
			print(f'{tot_area=}\n{forest_area=}\n{agri_area=}\n{indiceA1=}\n\n')

		# Clear temporary files
		for tempfile in tmp.values():
			tempfile.close()

		return {self.OUTPUT : dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceA1()

	def name(self):
		return 'Indice A1'

	def displayName(self):
		return self.tr('Indice A1')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr("Clacule l'indice A1")
