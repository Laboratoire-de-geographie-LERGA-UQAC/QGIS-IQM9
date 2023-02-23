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
					   QgsFeatureRequest,
					   QgsExpression,
					   QgsExpressionContext,
					   QgsExpressionContextUtils,
					  )



class IndiceF3(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVISIONS = 100

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('roads', 'roads', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

		def split_buffer(feature, source):
			# Spliting river segment into a 100 subsegments.
			segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
			params = {
			'INPUT':segment,
			'LENGTH':feature.geometry().length() / self.DIVISIONS,
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
			}
			split = processing.run('native:splitlinesbylength', params, context=context, is_child_algorithm=True)['OUTPUT']
			# Buffering subsegments
			params = {
			'INPUT':split,
			'OUTPUT_GEOMETRY':0,'WITH_Z':False,
			'WITH_M':False,
			'EXPRESSION':f"buffer( $geometry, 2.5 * overlay_nearest('{parameters['ptref_widths']}', Largeur_Mod)[0])",
			'OUTPUT':'TEMPORARY_OUTPUT'
			}
			buffer = processing.run("native:geometrybyexpression", params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			return context.takeResultLayer(buffer)

		def intersects_road(feat, layer):
			#Evaluating intersection
			expr = QgsExpression(f"""
				to_int(overlay_intersects('{parameters['roads']}'))
			""")
			feat_context = QgsExpressionContext()
			feat_context.setFeature(feat)
			scopes = QgsExpressionContextUtils.globalProjectLayerScopes(layer)
			feat_context.appendScopes(scopes)
			intersect_bool = expr.evaluate(feat_context)
			return intersect_bool

		def computeF3(intersect_arr):
			# Compute Iqm from sequence continuity
			unrestricted_segments = numpy.sum(1 - intersect_arr) # Sum number of unrestricted segments
			segment_count = intersect_arr.size
			ratio = unrestricted_segments / segment_count
			if (ratio >= 0.9):
				return 0
			if (ratio >= 0.66):
				return 2
			if (ratio >= 0.33):
				return 3
			return 5

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
		sink_fields.append(QgsField("Indice F3", QVariant.Int))

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

		# feature count for feedback
		feature_count = source.featureCount()
		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for segment in source.getFeatures():
			# Split segment into 100 buffers
			buffers = split_buffer(segment, source)
			# List for storing normal lenght and intersection
			intersect_bool = []
			# Store normal length and intersection in numpy arrays
			for buffer in buffers.getFeatures():
				intersect_bool.append(intersects_road(buffer, buffers))

			intersect_bool = numpy.array(intersect_bool)
			print("arr_len : ", intersect_bool.size,"\narr_sum", numpy.sum(intersect_bool))
			print(intersect_bool)
			# Determin the IQM Score

			indiceF3 = computeF3(intersect_bool)
			#Write Index
			segment.setAttributes(
				segment.attributes() + [indiceF3]
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
		return IndiceF3()

	def name(self):
		return 'indicef3'

	def displayName(self):
		return self.tr('Indice F3')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr("Clacule l'indice F3")

