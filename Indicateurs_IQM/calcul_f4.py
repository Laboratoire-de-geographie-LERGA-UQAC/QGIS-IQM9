# -*- coding: utf-8 -*-

"""
*********************************************************************************
*																				*
*		QGIS-IQM9 is a program developed for QGIS as a tool to automatically	*
*	calculate the Morphological Quality Index (MQI) of river systems			*
*	Copyright (C) 2025 Laboratoire d'expertise et de recherche en géographie	*
*	appliquée (LERGA) de l'Université du Québec à Chicoutimi (UQAC)				*
*																				*
*	This program is free software: you can redistribute it and/or modify		*
*	it under the terms of the GNU Affero General Public License as published	*
*	by the Free Software Foundation, either version 3 of the License, or		*
*	(at your option) any later version.											*
*																				*
*	This program is distributed in the hope that it will be useful,				*
*	but WITHOUT ANY WARRANTY; without even the implied warranty of				*
*	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the				*
*	GNU Affero General Public License for more details.							*
*																				*
*	You should have received a copy of the GNU Affero General Public License	*
*	along with this program.  If not, see <https://www.gnu.org/licenses/>.		*
*																				*
*********************************************************************************
"""


import numpy as np
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsField,
	QgsProcessing,
	QgsProcessingUtils,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsFeatureRequest,
	QgsExpression,
	QgsExpressionContext,
	QgsExpressionContextUtils,
	QgsProcessingAlgorithm,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsProperty,
  )



class IndiceF4(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	DIVS = 100
	UTHRESH = 0.2
	LTHRESH = 0
	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):
		self.UTHRESH = self.parameterAsDouble(parameters, 'thresh', context)
		def pointsAlongGeometry(feature, feedback):
			# Materialize segment feature
			feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))

			# Points along geometry
			alg_params = {
				'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {self.DIVS}"),
				'END_OFFSET': 0,
				'INPUT': feature,
				'START_OFFSET': 0,
				'OUTPUT': QgsProcessingUtils.generateTempFilename("points.shp"),
			}
			output = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			return QgsVectorLayer(output, 'points', 'ogr')

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
			if not width_array.size:
				return 1
			difs_percent = (width_array[1:] - width_array[:-1])/ width_array[1:]
			difs_specific = difs_percent * 1000 / div_distance
			# print(f"{difs_specific=}")
			unnatural_widths = np.where((difs_specific < self.LTHRESH) | (difs_specific > self.UTHRESH))[0].size
			# print(f"{unnatural_widths=}")
			return 1 - (unnatural_widths / difs_percent.size)

		def computeF4(ratio):
			# Compute F4
			if (ratio >= 0.9):
				return 0
			if (ratio >= 0.66):
				return 1
			if (ratio >= 0.33):
				return 2
			return 3

		results = {}

		# Define source stream net
		source = self.parameterAsSource(parameters, 'rivnet', context)

		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Pourc_var_long", QVariant.Double, prec=2))
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

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

		for current, segment in enumerate(source.getFeatures()):

			if model_feedback.isCanceled():
				return {}
	
			#gen points and normals along geometry
			points_along_line = pointsAlongGeometry(segment, feedback=None)
			div_distance = segment.geometry().length() / self.DIVS

			# Store normal length in numpy arrays
			width_array = get_points_widths(points_along_line, parameters)

			# Determine the IQM Score
			ratio = natural_width_ratio(width_array, div_distance)
			indiceF4 = computeF4(ratio)
			#Write Index
			segment.setAttributes(
				segment.attributes() + [ratio, indiceF4]
			)
			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)

			# Increments the progress bar
			if total_features != 0:
				progress = int(100*(current/total_features))
			else:
				progress = 0
			model_feedback.setProgress(progress)
			#model_feedback.setProgressText(self.tr(f"Traitement de {current} segments sur {total_features}"))

		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

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
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice F4 afin d'évaluer l’hétérogénéité naturelle des unités géomorphologiques liée à ces processus présents dans le lit mineur en mesurant la continuité dans la variabilité naturelle de la largeur du lit mineur.\n L'outil compare la largeur de deux points de référence ainsi que la distance entre eux. Une augmentation de plus de 10% indique une discontinuité dans la variation longitudinale naturelle.\n" \
			"Paramètres\n" \
			"----------\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F4 calculé pour chaque UEA."
		)