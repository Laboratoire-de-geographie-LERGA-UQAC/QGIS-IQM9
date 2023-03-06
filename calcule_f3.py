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

import numpy as np

import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProject,
	QgsField,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsProcessingParameterMultipleLayers,
	QgsFeatureRequest,
	QgsExpression,
	QgsExpressionContext,
	QgsExpressionContextUtils,
	QgsProcessingAlgorithm,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterNumber,
	QgsProcessingParameterFeatureSink,
	QgsProperty,
)


class IndiceF3(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVISIONS = 10

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterMultipleLayers('antropic_layers', 'Antropic layers', layerType=QgsProcessing.TypeVector, defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

		# Use a multi-step feedback
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)

		# Define source stream net
		source = self.parameterAsSource(parameters, 'rivnet', context)

		# Define Sink
		sink_fields = source.fields()
		sink_fields.append(QgsField("Indice F3", QVariant.Int))
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		anthropic_layers = [layer.id() for layer in
			self.parameterAsLayerList(parameters, 'antropic_layers', context)]

		# feature count for feedback
		feature_count = source.featureCount()
		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for segment in source.getFeatures():
			# Split segment into 100 sided buffers
			buffer_layer = split_buffer(segment, source, parameters, context, feedback=feedback)

			intersect_bool = []
			for buffer in buffer_layer.getFeatures():
				intersect_bool.append(intersects_structs(buffer, buffer_layer, anthropic_layers, parameters))
			intersect_bool = np.array(intersect_bool)

			# Compute the IQM Score
			indiceF3 = computeF3(intersect_bool)

			#Write to layer
			segment.setAttributes(segment.attributes() + [indiceF3])

			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)
			print(f"{segment[fid_idx]} / {feature_count}")
			print(f"arr_len : {intersect_bool.size}\narr_sum : {np.sum(intersect_bool)}")

		return {self.OUTPUT : dest_id}

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


def evaluate_expression(expression_str, vlayer, feature=None ):
	expression = QgsExpression(expression_str)
	context = QgsExpressionContext()
	if feature:
		context.setFeature(feature)
	scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
	context.appendScopes(scopes)
	res = expression.evaluate(context)
	return res

def split_buffer(feature, source, parameters, context, feedback=None):
	DIVISIONS = 100
	# Spliting river segment into a fixed number of subsegments.
	segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
	alg_param = {
	'INPUT':segment,
	'LENGTH':feature.geometry().length() / DIVISIONS,
	'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
	}
	split = processing.run('native:splitlinesbylength', alg_param, context=context, is_child_algorithm=True)['OUTPUT']

	side_buffers = []
	for direction in [1, -1]:
		# Buffering subsegments
		alg_param = {
		'INPUT':split,
		'OUTPUT_GEOMETRY':0,'WITH_Z':False,
		'WITH_M':False,
		'EXPRESSION':f"single_sided_buffer( $geometry, {direction} * 2.5 * overlay_nearest('{parameters['ptref_widths']}', Largeur_Mod)[0])",
		'OUTPUT':'TEMPORARY_OUTPUT'
		}
		side_buffers.append(processing.run("native:geometrybyexpression", alg_param, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT'])
	res_id = processing.run("native:mergevectorlayers", {'LAYERS':side_buffers,'CRS':None,'OUTPUT':'TEMPORARY_OUTPUT'}, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	return context.takeResultLayer(res_id)

def intersects_structs(feature, base_layer, struct_lay_ids, parameters):
	for layer_source in struct_lay_ids:
		expr = f"""
			to_int(overlay_intersects('{layer_source}'))
		"""
		eval = evaluate_expression(expr, base_layer, feature=feature)
		if eval:
			return True
	return False

def computeF3(intersect_arr):
	# Compute Iqm from sequence continuity
	unrestricted_segments = np.sum(1 - intersect_arr) # Sum number of unrestricted segments
	segment_count = intersect_arr.size
	ratio = unrestricted_segments / segment_count
	if (ratio >= 0.9):
		return 0
	if (ratio >= 0.66):
		return 2
	if (ratio >= 0.33):
		return 3
	return 5
