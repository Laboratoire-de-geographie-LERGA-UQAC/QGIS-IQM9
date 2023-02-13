"""
Model exported as python.
Name : IQM indice F5
Group :
With QGIS : 32802
Author : Karim Mehour
"""

from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProperty
import processing
import numpy
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



class IndiceF5(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('bande_riveraine_polly', 'Bande_riveraine_polly', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterNumber('transectsegment', 'Transect/segment', optional=True, type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=100, defaultValue=10))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))
		#self.addParameter(QgsProcessingParameterFeatureSink('Points', 'Points', type=QgsProcessing.TypeVectorPoint, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

		def pointsAlongGeometry(feature):
			# Materialize segment feature
			feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))

			# Points along geometry
			alg_params = {
				'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {parameters['transectsegment']}"),
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

		def intersection_len_band_riv(normal):
			section_width= normal.geometry().length() / parameters['ratio']
			#Evaluating intersection distance
			expr = QgsExpression(f"""
				max(
					0,
					length(
						segments_to_lines(
							intersection(
								$geometry,collect_geometries(
									overlay_intersects('{parameters['bande_riveraine_polly']}',$geometry)
								)
							)
						)
					)
				)
			""")
			feat_context = QgsExpressionContext()
			feat_context.setFeature(normal)
			intersect_len = expr.evaluate(feat_context)
			return intersect_len

		def longest_seq(bits):
			# make sure all runs of ones are well-bounded
			bounded = numpy.hstack(([0], bits, [0]))
			print(bounded)
			# get 1 at run starts and -1 at run ends
			difs = numpy.diff(bounded)
			run_starts, = numpy.where(difs > 0)
			run_ends, = numpy.where(difs < 0)
			if run_starts.size and run_ends.size:
				return (run_ends - run_starts).max()
			return 0


		def computeF5(intersect_arr, lengths_arr, div):
			# Compute Iqm from sequence continuity
			if (longest_seq(intersect_arr > 2 * lengths_arr) / div >= 0.9):
				return 0
			if (longest_seq(intersect_arr > lengths_arr) / div >= 0.66):
				return 2
			if (longest_seq(intersect_arr > 0.5 * lengths_arr) / div >= 0.66):
				return 3
			if (longest_seq(intersect_arr > 0.5 * lengths_arr) / div >= 0.33):
				return 4
			return 5

		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
		results = {}
		outputs = {}
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
			normals = gen_normals(points_along_line)

			# List for storing normal lenght and intersection
			intersect_lengths = []
			normal_lengths = []
			division_num = 0

			# Store normal length and intersection len in numpy arrays
			for normal in normals.getFeatures():
				normal_lengths.append(normal.geometry().length() / parameters['ratio'])
				intersect_lengths.append(intersection_len_band_riv(normal))
				division_num += 1
			intersect_lengths = numpy.array(intersect_lengths)
			normal_lengths = numpy.array(normal_lengths)

			# Determin the IQM Score

			indiceF5 = computeF5(intersect_lengths, normal_lengths, division_num)
			#Write Index
			segment.setAttributes(
				segment.attributes() + [indiceF5]
			)
			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)
			print(f"{segment[1]} / {feature_count}")

		#Clear temporary files
		for temp in tmp.values():
			temp.close()
		return results

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF5()

	def name(self):
		return 'indicef5'

	def displayName(self):
		return self.tr('Indice F5')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return self.tr('iqm')

	def shortHelpString(self):
		return self.tr("Clacule l'indice A4 de l'IQM (sinuosité)")
