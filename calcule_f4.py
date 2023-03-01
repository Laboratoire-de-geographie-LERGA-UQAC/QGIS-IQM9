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
					   QgsExpressionContext
					  )



class IndiceF4(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVS = 100
	CHANGE_THRESH = 0.66
	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

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

		def gen_normals(points):
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

		def get_ptref_width(feature):
			#Evaluating intersection distance
			expr = QgsExpression(f"""
				overlay_nearest(\'{parameters['ptref_widths']}\',Largeur_mod)[0]
			""")
			feat_context = QgsExpressionContext()
			feat_context.setFeature(point)
			width = expr.evaluate(feat_context)
			return width

		def natural_width_ratio(width_array):
			difs = width_array[1:] / width_array[:-1]
			unnatural_widths = np.where((difs > 1.33) | (difs < 1))[0].size
			return 1 - (unnatural_widths / difs.size)

		def computeF4(width_array):
			# Compute F4 from width array
			ratio = natural_width_ratio(width_array)
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
		sink_fields.append(QgsField("Indice F5", QVariant.Int))

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

			# get width at points
			width_array = []

			# Store normal length and intersection len in np arrays
			for point in points_along_line.getFeatures():
				width = get_ptref_width(point)
				width_array.append(width)
			width_array = np.array(width_array)
			print(width_array)
			# Determin the IQM Score
			indiceF4 = computeF4(width_array=width_array)
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
