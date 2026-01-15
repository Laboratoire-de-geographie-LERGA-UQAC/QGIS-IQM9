
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

import processing
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
	QgsProcessing,
	QgsProcessingUtils,
	QgsPointXY,
	QgsFeatureSink,
	QgsField,
	QgsProcessingException,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSource,
	QgsProcessingParameterBoolean,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsSpatialIndex,
	QgsWkbTypes,
	QgsUnitTypes,
	QgsFeatureRequest,
	QgsGeometry
)


class IndiceF1(QgsProcessingAlgorithm):
	INPUT = 'INPUT'
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterBoolean('structs_are_filtered', self.tr('La couche de structures fournie est elle filtrée (sortant de Filtrer structures) ?'), defaultValue=False))
		self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Réseau hydrographique (CRHQ)'), [QgsProcessing.TypeVectorLine]))
		self.addParameter(QgsProcessingParameterVectorLayer('structs', self.tr('Structures (MTMD) (filtrées ou non)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('routes', self.tr('Réseau routier (OSM)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie')))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		structs_are_filtered = self.parameterAsBool(parameters, 'structs_are_filtered', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
		struct_layer = self.parameterAsVectorLayer(parameters, 'structs', context)
		if not struct_layer or not struct_layer.isValid() :
			return False, self.tr("La couche de structures n'est pas valide ! Vérifiez que vous fournissez bien une couche.")
		if structs_are_filtered: # If the structure layer is already filtered
			if 'highway' not in [field.name() for field in struct_layer.fields()]:
				return False, self.tr("Vous avez indiqué fournir la couche structure filtrée, mais elle n'est pas filtrée ! Veuillez soit fournir la couche de structure filtrée (sortant du script IQM utils Filtrer structures) ou fournir la couche non filtrée ainsi que la couche de réseau routier.")
		else :
			if parameters['routes'] is None :
				return False, self.tr('Vous devez fournir la couche nécessaire (Réseau routier) pour créer la couche de structures filtrées.')
			road_layer = self.parameterAsVectorLayer(parameters, "routes", context)
			if not is_metric_crs(road_layer.crs()) :
				return False, self.tr(f"La couche de réseau routier n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(rivnet_layer.crs()) :
			return False, self.tr(f"La couche de réseau hydro n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(struct_layer.crs()) :
			return False, self.tr(f"La couche de structures n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		source = self.parameterAsSource(
			parameters,
			self.INPUT,
			context
		)

		# Create a QgsVectorLayer from source
		if source is None:
			raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

		#Adding new field to output
		sink_fields = source.fields()
		sink_fields.append(QgsField("Nb_struct_amont", QVariant.Int))
		sink_fields.append(QgsField("Indice F1", QVariant.Int))

		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		if sink is None:
			raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

		# Send some information to the user
		model_feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))
 
		#  Opening the layer we need for the process
		hydro_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)

		# Create spatial index to make the finding of the nearest segment faster
		hydro_index = QgsSpatialIndex(hydro_layer.getFeatures())
		id_to_feat = {f['Id_UEA']: f for f in hydro_layer.getFeatures()}

		# Make the filtered structure df if its not given
		structs_are_filtered = self.parameterAsBool(parameters, 'structs_are_filtered', context)
		if structs_are_filtered == False :
			# If the sub watershed layer is not given
			model_feedback.setProgressText(self.tr(f"Filtre des structures"))
			try :
				# Create the filtered structures
				alg_params = {
					'cours_eau' : parameters[self.INPUT],
					'routes' : parameters['routes'],
					'structures' : parameters['structs'],
					'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
				}
				structs_data = processing.run('script:filterstructures', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']
				struct_layer = QgsProcessingUtils.mapLayerFromString(structs_data, context)
				if not struct_layer or not struct_layer.isValid() :
					# Verify if the created layer is valid
					model_feedback.reportError(self.tr("La couche structures filtrée est invalide."))
					return {}
			except Exception as e :
				model_feedback.reportError(self.tr(f"Erreur dans la création de la couche de structures filtrées : {str(e)}"))
		else : # If its already filtered makes the layer from what is given as a parameter
			struct_layer = self.parameterAsVectorLayer(parameters, 'structs', context)

		structure_counts = {}
		# Gets the number of features to iterate over for the progress bar
		total_features = struct_layer.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features (structures) à traiter"))

		try :
			for current, struct in enumerate(struct_layer.getFeatures()):
				current_feat = None
				try :
					# Finds the river segment of the current structure
					current_feat = find_segment_for_structure_fast(struct, hydro_layer, hydro_index)
				except Exception as e :
					model_feedback.reportError(self.tr(f"Erreur dans find_segment_for_structure : {str(e)}"))
					return {}
				if current_feat is None: # if no segment associated to the structure
					#model_feedback.pushInfo(self.tr(f"Pas de segment associé à la structure actuelle. Prochain segment."))
					continue
				if model_feedback.isCanceled():
					return {}

				downstream_feat = None
				try :
					# Finds the downstream river segment
					downstream_id = current_feat['Id_UEA_aval']
					downstream_feat = id_to_feat.get(downstream_id)
				except Exception as e :
					model_feedback.reportError(self.tr(f"Erreur dans get_downstream_segment : {str(e)}"))
					return {}
				if downstream_feat is None:
					#model_feedback.pushInfo(self.tr(f"Le segment d'aval ne fait pas partie du réseau hydrographique. Prochain segment."))
					continue

				cum_dist = 0
				prev_intersection = None
				step = 0
				visited = set()
				# Iterate over the next downstream segments while the cumulative distance from the structure to the downstream segment is less than 1000 meters
				while (cum_dist < 1000) and (downstream_feat is not None) :
					intersection_point = None
					if model_feedback.isCanceled():
						return {}
					try :
						# Find the intersecting point between the structure river segment and the downstream segment
						intersection_point = get_intersection_point(current_feat, downstream_feat, tol=5)
					except Exception as e :
						model_feedback.reportError(self.tr(f"Erreur dans get_intersection_point : {str(e)}"))
					if intersection_point is None or intersection_point.isEmpty():
						#model_feedback.pushInfo(self.tr(f"Le segment d'aval ne retourne pas d'intersection avec le segment courant. Prochain segment."))
						break

					try :
						# Calculates the distance along the network between the structure and this point
						if step == 0 : # If first time get distance between the structure and the intersection with downstream
							dist = line_distance_between_points(current_feat.geometry(), struct.geometry(), intersection_point)
						else : # Otherwise get the distance between the previous intersection and the current intersection
							dist = line_distance_between_points(current_feat.geometry(), prev_intersection, intersection_point)
					except Exception as e :
						model_feedback.reportError(self.tr(f"Erreur dans compute_shortest_path : {str(e)}"))
						return {}
					# If the distance is < 1000 m, increment the downstream segment structure counter.
					if dist is None or dist <= 0:
						# Null or invalid distance.
						break
					if (cum_dist + dist) < 1000:
						# Get the downstream UEA to increment the count of structures
						downstream_id = downstream_feat['Id_UEA']
						# Verify if we already counted this segment for this structure
						if downstream_id in visited:
							break
						structure_counts[downstream_id] = structure_counts.get(downstream_id, 0) + 1
						cum_dist += dist
						prev_intersection = intersection_point
						step += 1
						visited.add(downstream_id)
						# Get the downstream segment of the downstream segment to see if the structure is within range of another segment (for the next iteration of the while loop)
						current_feat = downstream_feat
						downstream_feat = None
						downstream_id = current_feat['Id_UEA_aval']
						#downstream_feat = get_downstream_segment(hydro_layer, current_feat)
						if not downstream_id:
							# No downstream segment. We get out of the loop
							break
						downstream_feat = id_to_feat.get(downstream_id)
					else:
						# 1000 m limit reached. We get out of the loop
						break

				# Updating the progress bar
				if total_features != 0:
					progress = int(100*(current/total_features))
				else:
					progress = 0
				model_feedback.setProgress(progress)

				if model_feedback.isCanceled():
					return {}
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans la boucle de structure : {str(e)}"))

		model_feedback.setProgressText(self.tr(f"Compte des structures terminé."))
		if model_feedback.isCanceled():
			return {}

		# Computing the F1 score for each river segment
		try :
			for feat in source.getFeatures():
				seg_id = feat['Id_UEA']
				struct_count = structure_counts.get(seg_id, 0)
				f1_score = computeF1(struct_count)
				# Add both the structure count and the f1_score to the attributes table
				feat.setAttributes(feat.attributes() + [struct_count, f1_score])
				sink.addFeature(feat, QgsFeatureSink.FastInsert)
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans le calcul de F1 et le sink des features : {str(e)}"))

		model_feedback.setProgressText(self.tr(f"Calcul du score de F1 terminé."))
		if model_feedback.isCanceled():
				return {}

		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT: dest_id}


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def createInstance(self):
		return IndiceF1()


	def name(self):
		return 'indicef1'


	def displayName(self):
		return self.tr('Indice F1')


	def group(self):
		return self.tr('IQM (indice solo)')


	def groupId(self):
		return 'iqm'


	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice F1 afin d'évaluer la continuité du transit longitudinal du transit de sédiments et de bois.\n L'outil évalue la présence d\'obstacles (traverses, ponts, ponceaux, intersections etc.) du réseau routier ou ferroviaire qui pourraient entraver ou nuire au transport de sédiments et de bois. Il prend en compte la densité linéaire des entraves sur 1000 m de rivière. Puisque les effets des entraves affectent la portion en aval de l'infrastructure, l'outil considère seulement les éléments artificiels situés à une distance maximale de 1000 m à l'amont du segment.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Couche de structures déjà filtrée fournise: Booléen (optionnel; valeur par défaut : Faux)\n" \
			"-> Détermine si la couche de structures fournise à déjà été filtrée (préalablement produite par Filtrer structures).\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Structures : Vectoriel (points)\n" \
			"-> Ensemble de données vectorielles ponctuelles des structures sous la gestion du Ministère des Transports et de la Mobilité durable du Québec (MTMD) (pont, ponceau, portique, mur et tunnel) ayant été préalablement filtrées par le script Filtrer structures ou non. Source des données : MTMD. Structure, [Jeu de données], dans Données Québec.\n" \
			"Réseau routier : Vectoriel (lignes; optionnel)\n" \
			"-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Doit avoir préalablement avoir passé par le script Extraction routes d'OSM. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F1 calculé pour chaque UEA."
		)


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters


def find_segment_for_structure_fast(struct, hydro_layer, hydro_index, max_dist=5):
	pt = struct.geometry().asPoint()
	candidate_ids = hydro_index.nearestNeighbor(pt, 5)
	best = None
	best_d = float('inf')
	for fid in candidate_ids:
		feat = next(hydro_layer.getFeatures(QgsFeatureRequest(fid)))
		d = feat.geometry().distance(struct.geometry())
		if d < best_d:
			best_d = d
			best = feat
	return best if best and best_d <= max_dist else None


def endpoints_as_points(geom: QgsGeometry):
	# Return (p0, p1) as QgsPointXY, by taking the longuest point if MultiLine
	if geom.isMultipart():
		lines = geom.asMultiPolyline()
		line = max(lines, key=lambda l: QgsGeometry.fromPolylineXY(l).length())
	else:
		line = geom.asPolyline()
	if not line:
		return None, None
	return QgsPointXY(line[0]), QgsPointXY(line[-1])


def nearest_endpoint_to_geom(p0: QgsPointXY, p1: QgsPointXY, other_geom: QgsGeometry):
	gp0 = QgsGeometry.fromPointXY(p0)
	gp1 = QgsGeometry.fromPointXY(p1)
	d0 = gp0.distance(other_geom)
	d1 = gp1.distance(other_geom)
	return (gp0, d0) if d0 <= d1 else (gp1, d1)


def get_intersection_point(upstream_feat, downstream_feat, tol=1.0):
	"""
	Returns a QgsGeometry point belonging to upstream_feat (current segment),
	representing the “junction” with downstream_feat.
	Cases
	1) explicit intersction -> point
	2) close endpoints -> upstream enpoint as intersection
	3) fallback nearestPoints -> nearest upstream enpoint 
	4) Safeguard against parallele segments (distance at endpoints >> nearestPoints)
	"""
	g_up = upstream_feat.geometry()
	g_dw = downstream_feat.geometry()
	# 1) Explicit intersection
	inter = g_up.intersection(g_dw)
	if inter and not inter.isEmpty():
		if inter.type() == QgsWkbTypes.PointGeometry:
			if inter.isMultipart():
				pts = inter.asMultiPoint()
				return QgsGeometry.fromPointXY(pts[0]) if pts else None
			else:
				return inter
		elif inter.type() == QgsWkbTypes.LineGeometry:
			# Overlap : we take the upstream end closest to the downstream segment
			p0, p1 = endpoints_as_points(g_up)
			if p0 is None: 
				return None
			cand, distc = nearest_endpoint_to_geom(p0, p1, g_dw)
			if distc <= tol:
				return cand
			# Otherwise fallback
		# If PolygonGeometry or other, goes to fallback
	# 2) Proximal endpoints (tol): the upstream end closest to the downstream segment is selected
	p0, p1 = endpoints_as_points(g_up)
	if p0 is None:
		return None
	cand, distc = nearest_endpoint_to_geom(p0, p1, g_dw)
	if distc <= tol:
		return cand  # point on upstream
	# 3) Fallback nearestPoints
	n_up = g_up.nearestPoint(g_dw)
	n_dw = g_dw.nearestPoint(g_up)
	if (n_up is None) or n_up.isEmpty() or (n_dw is None) or n_dw.isEmpty():
		return None
	# Minimum Euclidean distance between geometries (on potential internal points)
	d_np = n_up.distance(n_dw)  # distance between the 2 points
	# The junction is constrained to the upstream end closest to g_dw (not an interior point).
	# (makes sure that lineLocatePoint() applies correctly to upstream)
	cand, distc = nearest_endpoint_to_geom(p0, p1, g_dw)
	# 4) Parallelism safeguard: if dist endpoint >> dist nearestPoints (on interior point), we doubt
	if d_np > 0 and distc > 3.0 * d_np:
		return None
	# Otherwise, the most plausible upstream end is used as the junction
	return cand


def line_distance_between_points(line_geom: QgsGeometry, ptA_geom: QgsGeometry, ptB_geom: QgsGeometry) -> float:
	"""
	Returns the curvilinear distance along line_geom between ptA and ptB,
	in meters (assumes metric CRS).
	Uses lineLocatePoint to project points onto the polyline.
	"""
	a = line_geom.lineLocatePoint(ptA_geom)
	b = line_geom.lineLocatePoint(ptB_geom)
	# a and b are distances from the start of the line
	return abs(b - a)


def computeF1(struct_count):
	if struct_count == 0:
		# No obstruction or alteration in the continuity of sediment and wood transport upstream of the segment
		return 0
	if struct_count <= 1:
		# Presence of at least one obstacle to the continuous flow of sediment and wood upstream of the segment
		return 2
	elif struct_count > 1:
		# Presence of more than one obstacle to the continuous flow of sediment and wood upstream of the segment
		return 4
