# -*- coding: utf-8 -*-

"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


import logging
import numpy
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProperty
import processing

from tempfile import NamedTemporaryFile
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
						QgsProject,
						QgsField,
						QgsFeatureSink,
						QgsVectorLayer,
						QgsProcessingContext,
						QgsFeatureRequest,
						QgsExpression,
						QgsExpressionContext,
						QgsExpressionContextUtils,
						QgsProcessingParameterRasterLayer,
						QgsCoordinateReferenceSystem,
						)

# LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
# logging.basicConfig(filename="/tmp/F2Log.log",
# 					level=logging.DEBUG,
# 					format=LOG_FORMAT,
# 					filemode='w')

# logger = logging.getLogger()
# logger.info("Our First Message")


class IndiceF2(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVISIONS = 10

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('roads', 'roads', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('structs', 'Structures', defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'Utilisation du territoir', defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

		def gen_buffer(feature, source, scale=2.5):
			# logger.info("Generatign buffer")
			feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
			# Buffering subsegment
			params = {
			'INPUT':feature,
			'OUTPUT_GEOMETRY':0,'WITH_Z':False,
			'WITH_M':False,
			'EXPRESSION':f"buffer( $geometry, {scale + 0.5	} * overlay_nearest('{parameters['ptref_widths']}', Largeur_Mod)[0])",
			'OUTPUT':'TEMPORARY_OUTPUT'
			}
			buffer = processing.run("native:geometrybyexpression", params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			return context.takeResultLayer(buffer)

		def intersects_structs(feat, base_layer, struct_lay_sources):
			# logger.info("checking vector intersection")
			for layer_source in struct_lay_sources:
				#Evaluating intersection
				expr = QgsExpression(f"""
					to_int(overlay_intersects('{layer_source}'))
				""")
				feat_context = QgsExpressionContext()
				feat_context.setFeature(feat)
				scopes = QgsExpressionContextUtils.globalProjectLayerScopes(base_layer)
				feat_context.appendScopes(scopes)
				eval = expr.evaluate(feat_context)
				if eval:
					return True
			return False

		def computeF2(feature, source, land_use):
			# logger.info("Computing F2")
			# search for anthropisation in buffers
			barem = ((5, 1), (3, 2), (2, 4)) # barem corresponds to (IQM score, buffer search scale) tuples
			for result, scale in barem:
				# Create buffer
				buffer_layer = gen_buffer(feature, source, scale)
				#QgsProject.instance().addMapLayer(buffer_layer)
				print(f"{result=}, {scale=}")
				buffer_feature = next(buffer_layer.getFeatures())

				# # Check vector data intersection
				intersection = intersects_structs(buffer_feature, buffer_layer, [parameters['roads'], parameters['structs']])
				if intersection:
					print(f"INTERSECTION : {result=}, {scale=}")
					return result

				#check landuse  antropisation data
				if check_raster(buffer_layer, land_use):
					return result

			return 0

		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
		results = {}
		tmp = {
			'points':NamedTemporaryFile(suffix="pts.gpkg"),
			'normals':NamedTemporaryFile(suffix="normals.gpkg"),
		}

		# Define source stream net
		source = self.parameterAsSource(parameters, 'rivnet', context)

		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Indice F2", QVariant.Int))

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

		# Reclassify landUse
		reclassified_landuse = reclassify_landuse(parameters['landuse'], context=context, feedback=feedback)

		# feature count for feedback
		feature_count = source.featureCount()
		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for segment in source.getFeatures():
			"""
			# Split segment into 100 buffers
			buffer_layer = split_buffer(segment, source)
			# List for storing normal lenght and intersection
			intersect_bool = []
			# Store normal length and intersection in numpy arrays
			for buffer in buffer_layer.getFeatures():
				intersect_bool.append(intersects_structs(buffer, buffer_layer, [parameters['roads'], parameters['structs']]))

			intersect_bool = numpy.array(intersect_bool)
			print("arr_len : ", intersect_bool.size,"\narr_sum", numpy.sum(intersect_bool))
			print(intersect_bool)
			"""
			# Determin the IQM Score
			indiceF2 = computeF2(segment, source, reclassified_landuse)
			#Write Index
			segment.setAttributes(
				segment.attributes() + [indiceF2]
			)
			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)
			print(f"{segment[fid_idx]} / {feature_count}")

		#Clear temporary files
		for temp in tmp.values():
			temp.close()
		return results

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF2()

	def name(self):
		return 'indicef2'

	def displayName(self):
		return self.tr('Indice F2')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr("Clacule l'indice F2")

def reclassify_landuse(raster_source, context=None, feedback=None):
    if context == None:
        context = QgsProcessingContext()

    CLASSES = ['101','199','2', '300', '360', '3', '20', '27', '4']
    # Extend classe table to other environments
    table = CLASSES.copy()
    for i in [2, 4, 5, 6, 7, 8]:
        for j in range(len(CLASSES)):
            c = int(CLASSES[j])
            if (j + 1) % 3 != 0:
                c += i * 1000
            table.append(str(c))

    # Reclassify land use
    alg_params = {
        'DATA_TYPE': 0,  # Byte
        'INPUT_RASTER': raster_source,
        'NODATA_FOR_MISSING': True,
        'NO_DATA': 0,
        'RANGE_BOUNDARIES': 2,  # min <= value <= max
        'RASTER_BAND': 1,
        'TABLE': table,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }
    result = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return result

def unique_values_report(mask_vlayer, raster_path, context=None, feedback=None):
    #logger.info("Computing unique values report")
    if not context:
        context = QgsProcessingContext()
    #Clip raster by mask
    alg_params = {
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'DATA_TYPE': 0,  # Use Input Layer Data Type
        'EXTRA': '',
        'INPUT': raster_path,
        'KEEP_RESOLUTION': True,
        'MASK': mask_vlayer,
        'MULTITHREADING': False,
        'NODATA': None,
        'OPTIONS': '',
        'SET_RESOLUTION': False,
        'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
        'TARGET_CRS': 'ProjectCrs',
        'TARGET_EXTENT': None,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT#f"tmp/land_use_clip_{fid}.tif"#
    }
    clipped_raster = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    # Landuse unique values report
    alg_params = {
        'BAND': 1,
        'INPUT': clipped_raster,
        'OUTPUT_TABLE': QgsProcessing.TEMPORARY_OUTPUT
    }
    output = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT_TABLE']
    print(output)
    return context.takeResultLayer(output)

def check_raster(mask_vlayer, raster_path):
	#logger.info("Checking raster anthro")
	val_report = unique_values_report(mask_vlayer, raster_path)
	anthro_class_id = 3
	values = [feat['value'] for feat in val_report.getFeatures()]
	return anthro_class_id in values
