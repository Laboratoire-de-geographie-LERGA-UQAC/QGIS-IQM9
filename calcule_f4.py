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
					   QgsField,
					   QgsFeatureSink,
					   QgsVectorLayer,
					   QgsFeatureRequest,
					   QgsExpression,
					   QgsExpressionContext,
					   QgsExpressionContextUtils,
					  )



class IndiceF4(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVS = 100
	UTHRESH = 0.2
	LTHRESH = 0
	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('thresh', 'Threshold', optional=True, type=QgsProcessingParameterNumber.Double, minValue=0, maxValue=5, defaultValue=0.1))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):
		self.UTHRESH = self.parameterAsDouble(parameters, 'thresh', context)
		def pointsAlongGeometry(feature):
			# Materialize segment feature
			feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))

			# Points along geometry
			alg_params = {
				'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {self.DIVS}"),
				'END_OFFSET': 0,
				'INPUT': feature,
				'START_OFFSET': 0,
				#'OUTPUT':QgsProcessing.TEMPORARY_OUTPUT
				'OUTPUT': tmp['points'].name,
				#'OUTPUT': parameters['Points']
			}
			# points = QgsVectorLayer(tmp['points'].name, 'points', 'ogr')
			# outputs['PointsAlongGeometry']['OUTPUT'] = points
			processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			return QgsVectorLayer(tmp['points'].name, 'points', 'ogr')

		def gen_normals(points, context):
			# Geometry by expression
			alg_params = {
				'EXPRESSION':f"with_variable('len',overlay_nearest(\'{parameters['ptref_widths']}\',Largeur_mod)[0] * {parameters['ratio']},extend(make_line($geometry,project($geometry,@len,radians(\"angle\" - 90))),@len,0))",
				#'EXPRESSION':"
				#'INPUT': outputs['PointsAlongGeometry']['OUTPUT'],
				'INPUT': points,
				'OUTPUT_GEOMETRY': 1,  # Line
				'WITH_M': False,
				'WITH_Z': False,
				'OUTPUT': tmp['normals'].name
				#'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
				#'OUTPUT':parameters['Norm']
			}
			processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
			return QgsVectorLayer(tmp['normals'].name, 'normals', 'ogr')

		def evaluate_expression(expression_str, vlayer, feature=None ):
			expression = QgsExpression(expression_str)
			context = QgsExpressionContext()
			if feature:
				context.setFeature(feature)
			scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
			context.appendScopes(scopes)
			res = expression.evaluate(context)
			return res

		def get_points_widths(vlayer, parameters):
			ptref_expr = f"""
				array_agg(overlay_nearest('{parameters['ptref_widths']}', largeur_mod)[0])
			"""
			result = np.array(evaluate_expression(ptref_expr, vlayer))
			return result

		def natural_width_ratio(width_array, div_distance):
			# difs = (width_array[1:] / width_array[:-1]) / width_array[1:] / div_distance
			difs_percent = (width_array[1:] - width_array[:-1])/ width_array[1:]
			difs_specific = difs_percent * 1000 / div_distance
			print(f"{difs_specific=}")
			unnatural_widths = np.where((difs_specific < self.LTHRESH) | (difs_specific > self.UTHRESH))[0].size
			print(f"{unnatural_widths=}")
			return 1 - (unnatural_widths / difs_percent.size)

		def computeF4(width_array, div_distance):
			# Compute F4 from width array
			ratio = natural_width_ratio(width_array, div_distance)
			if (ratio >= 0.9):
				return 0
			if (ratio >= 0.66):
				return 1
			if (ratio >= 0.33):
				return 2
			return 3

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
		sink_fields.append(QgsField("Indice F4", QVariant.Int))

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
			#gen points and normals along geometry
			points_along_line = pointsAlongGeometry(segment)

			div_distance = segment.geometry().length() / self.DIVS

			# Store normal length in numpy arrays
			width_array = get_points_widths(points_along_line, parameters)
			print(f"{width_array=}")
			# Determin the IQM Score
			indiceF4 = computeF4(width_array, div_distance)
			#Write Index
			segment.setAttributes(
				segment.attributes() + [indiceF4]
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
		return IndiceF4()

	def name(self):
		return 'indicef4'

	def displayName(self):
		return self.tr('Indice F4')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr("Clacule l'indice F4")
