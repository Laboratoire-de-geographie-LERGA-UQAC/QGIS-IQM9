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
	QgsProcessingParameterString,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
)
from qgis import processing


class calculerIc(QgsProcessingAlgorithm):
	INPUT = 'INPUT'
	OUTPUT = 'OUTPUT'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie')))


	def checkParameterValues(self, parameters, context):
		# Check if the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		# Verify that the given segment ID is in the rivnet and PtRef layer
		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro ! Veuillez fournir un champ identifiant du segment qui se trouve dans la couche de réseau hydrographique.")
		return True, ''


	def processAlgorithm(self, parameters, context, feedback):
		# Retrieve the feature source and sink. The 'dest_id' variable is used
		# to uniquely identify the feature sink, and must be included in the
		# dictionary returned by the processAlgorithm function.
		source = self.parameterAsSource(parameters, self.INPUT, context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)

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

		# Get boundaries of all river segments
		feedback.setProgressText(self.tr("Extraction des extrémités avec native:boundary..."))
		try :
			rivnet_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
			boundary_layer = processing.run("native:boundary", {
				'INPUT': rivnet_layer,
				'OUTPUT': 'memory:'
			}, context=context)['OUTPUT']
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la création des points d'extrémités : {str(e)}"))
			return {}

		# Regroup the points per segments (Id_UEA)
		extremities = {}
		for point_feat in boundary_layer.getFeatures():
			fid = point_feat[seg_id_field]
			if fid not in extremities:
				extremities[fid] = []
			geom = point_feat.geometry()
			# Gérer Point et MultiPoint
			if geom.isMultipart():
				pts = geom.asMultiPoint()
			else:
				pts = [geom.asPoint()]
			for pt in pts:
				extremities[fid].append(pt)
		
		# Compute the number of steps to display within the progress bar and
		# get features from source
		total_features = source.featureCount()
		feedback.pushInfo(self.tr(f"{total_features} features (segments) à traiter"))

		# Calculate sinuosity index and A4 for each river segment
		feedback.setProgressText(self.tr("Calcul de l'indice de sinuosité et de l'indice A4..."))
		try :
			for current, feature in enumerate(source.getFeatures()):
				# Stop the algorithm if cancel button has been clicked
				if feedback.isCanceled():
					break

				# Extract boundary points for the current segment
				sid = feature[seg_id_field]
				geom = feature.geometry()
				points = extremities.get(sid, [])

				if len(points) == 2:
					# Normal case, 2 extremities
					distance = points[0].distance(points[1])
				# If more than two points (non continuous line), removes vertices of disjoint lines until only the two extremities of the segment remains
				elif len(points) > 2:
					try:
						# Initialise the list of remaining points
						remaining_points = points.copy()
						while len(remaining_points) > 2 : 
							# Finds disjoint vertices pairs (those closest to each others)
							min_dist = float('inf')
							p_close1, p_close2 = None, None
							# Iterates over the boundary points and finds those furthest from each others (the extremities)
							for i in range(len(remaining_points)):
								for j in range(i+1, len(remaining_points)):
									d = remaining_points[i].distance(remaining_points[j])
									if d < min_dist:
										min_dist = d
										p_close1, p_close2 = remaining_points[i], remaining_points[j]
							# Verify that we found a pair
							if p_close1 is None or p_close2 is None:
								feedback.reportError(self.tr(f"Impossible de trouver une paire de points pour le segment {sid}"))
								distance = 0
								break
							remaining_points.remove(p_close1)
							remaining_points.remove(p_close2)
						# The last two points are the extremities of the segment
						if len(remaining_points) == 2 :
							distance = remaining_points[0].distance(remaining_points[1])
						else : 
							feedback.reportError(self.tr(f"Nombre de points restants incorrect ({len(remaining_points)}) pour le segment {sid}"))
							distance = 0
					except Exception as e :
						feedback.reportError(self.tr(f"Erreur dans la recherche des points d'extremites : {str(e)}"))
				else:
					distance = 0  # Edge case
				if distance <= 2 :
					feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale à deux mètres ! Veuillez vérifier si l'UEA est un artéfact de prétraitement."))
				# Calculate the sinuosity index (Is)
				if distance > 0:
					# Is = length of the channel/length from both extremities
					Is = geom.length() / distance
				else:
					# If start and endpoint are connected make 
					Is = 1

				# A4 index calculation where Is is the sinuosity index
				if Is >= 1.5:      # Sinuosity greater or equal than 1.5 (High sinuosity)
					indice_A4 = 0
				elif Is >= 1.25:   # Sinuosity between [1.25-1.5[ (Medium sinuosity)
					indice_A4 = 2
				elif Is >= 1.05:   # Sinuosity between [1.05-1.25[ (Low sinuosity)
					indice_A4 = 4
				else:              # Suniosity < 1.05 (linear)
					indice_A4 = 6

				feature.setAttributes(feature.attributes() + [distance, Is, indice_A4])

				# Add a feature in the sink
				sink.addFeature(feature, QgsFeatureSink.FastInsert)

				# Increments the progress bar
				if total_features != 0:
					progress = int(100*(current/total_features))
				else:
					progress = 0
				feedback.setProgress(progress)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la boucle de segments : {str(e)}"))

		# Ending message
		feedback.setProgressText(self.tr('Processus terminé !'))

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
			"Calcule de l'indice A4 afin d'évaluer le niveau d’altération par l’entremise d’un indice de sinuosité du tracé fluvial.\n Plus le segment possède un indice de sinuosité faible (rectiligne), plus grandes sont les probabilités que les profils longitudinaux et transversaux soient homogènes et que les conditions hydrogéomorphologiques naturelles aient été perturbées par des interventions de nature anthropique.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec la distance linéaire entre les extrémités du segment, l'indice de sinuosité et le score de l'indice A4 calculé pour chaque UEA."
		)
