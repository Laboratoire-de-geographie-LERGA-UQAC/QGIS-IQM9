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


from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
	QgsProcessing,
	QgsFeatureSink,
	QgsField,
	QgsProcessingException,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSource,
	QgsProcessingParameterFeatureSink,
)
from qgis import processing


class calculerIc(QgsProcessingAlgorithm):
	INPUT = 'INPUT'
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorAnyGeometry]))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie')))

	def processAlgorithm(self, parameters, context, feedback):
		# Retrieve the feature source and sink. The 'dest_id' variable is used
		# to uniquely identify the feature sink, and must be included in the
		# dictionary returned by the processAlgorithm function.
		source = self.parameterAsSource(
			parameters,
			self.INPUT,
			context
		)

		# If source was not found, throw an exception to indicate that the algorithm
		# encountered a fatal error. The exception text can be any string, but in this
		# case we use the pre-built invalidSourceError method to return a standard
		# helper text for when a source cannot be evaluated
		if source is None:
			raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

		#Adding new field to output
		sink_fields = source.fields()
		sink_fields.append(QgsField("Dist lineaire", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Indice sinuosite", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Indice A4", QVariant.Int))

		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		# Send some information to the user
		feedback.pushInfo(self.tr('CRS est {}'.format(source.sourceCrs().authid())))

		# If sink was not created, throw an exception to indicate that the algorithm
		# encountered a fatal error.
		if sink is None:
			raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

		# Compute the number of steps to display within the progress bar and
		# get features from source
		total_features = source.featureCount()
		feedback.pushInfo(self.tr(f"{total_features} features à traiter"))

		feedback.setProgressText(self.tr("Calcul de l'indice de sinuosité et de l'indice A4..."))
		try :
			for current, feature in enumerate(source.getFeatures()):
				# Stop the algorithm if cancel button has been clicked
				if feedback.isCanceled():
					break

				# Find start and endpoint vertices
				feature_vertices = list(feature.geometry().vertices())

				# Straight-line distance between the two ends
				dist_between_ends = max(p1.distance(p2) for p1 in feature_vertices for p2 in feature_vertices) # finds the max distance between vertices which is more robust to disjointed lines that can affect distance calculations

				if dist_between_ends == 0:
					# If start and endpoint are connected make 
					Is = 1
				else:
					# Is (sinuosity index) = length of the channel/length from both extremities
					Is = feature.geometry().length() / dist_between_ends

				# A4 index calculation where Is is the sinuosity index
				if Is >= 1.5:
					indice_A4 = 0
				elif Is >= 1.25:
					indice_A4 = 2
				elif Is >= 1.05:
					indice_A4 = 4
				else:
					indice_A4 = 6

				feature.setAttributes(
					feature.attributes() + [dist_between_ends, Is, indice_A4]
				)

				# Add a feature in the sink
				sink.addFeature(feature, QgsFeatureSink.FastInsert)

				# Increments the progress bar
				if total_features != 0:
					progress = int(100*(current/total_features))
				else:
					progress = 0
				feedback.setProgress(progress)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la boucle de structure : {str(e)}"))

		# Ending message
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT: dest_id}


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def createInstance(self):
		return calculerIc()


	def name(self):
		return 'indicea4'


	def displayName(self):
		return self.tr('Indice A4')


	def group(self):
		return self.tr('IQM (indice solo)')


	def groupId(self):
		return 'iqm'


	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice A4 afin d'évaluer le niveau d’altération par l’entremise d’un indice de sinuosité du tracé fluvial.\n Plus le segment possède un indice de sinuosité est faible (rectiligne), plus grandes sont les probabilités que les profils longitudinaux et transversaux soient homogènes et que les conditions hydrogéomorphologiques naturelles aient été perturbées par des interventions de nature anthropique.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec la distance linéaire entre les extrémités du segment, l'indice de sinuosité et le score de l'indice A4 calculé pour chaque UEA."
		)
