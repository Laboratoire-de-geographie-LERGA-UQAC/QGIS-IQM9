
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
import math
import warnings
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingUtils,
	QgsField,
	QgsPointXY,
	QgsUnitTypes,
	QgsGeometry,
	QgsFeatureSink,
	QgsFeatureRequest,
	QgsGeometry,
	QgsSpatialIndex,
	QgsRectangle,
	QgsVectorLayer,
	QgsProcessingAlgorithm,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterNumber,
	QgsProcessingParameterString,
	QgsProcessingParameterFeatureSink
)
import sys

class IndiceF5(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'
	DEFAULT_WIDTH_FIELD = 'Largeur_mod'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'
	TRANSECT_RATIO = 3

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('bande_riveraine_polly', self.tr('Bande riveraine (peuplement forestier; MELCCFP)'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine]))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('target_pts', self.tr('Nombre de points visés par segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=200))
		self.addParameter(QgsProcessingParameterNumber('step_min', self.tr('Longueur minimale entre les transects (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=10))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Check if the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		bande_layer = self.parameterAsVectorLayer(parameters, 'bande_riveraine_polly', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		# Verify that the given segment ID is in the rivnet and PtRef layer
		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro ! Veuillez fournir un champ identifiant du segment commun aux deux couches.")
		if seg_id_field not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche PtRef largeur! Veuillez fournir un champ identifiant du segment commun aux deux couches.")
		# Verify that the given width attribute is in the PtRef layer
		if width_field not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ '{width_field}' est absent de la couche PtRef largeur! Veuillez fournir un champ identifiant la largeur du segment qui se trouve dans cette couche.")
		if not is_metric_crs(rivnet_layer.crs()) :
			return False, self.tr(f"La couche de réseau hydro n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(ptref_layer.crs()) :
			return False, self.tr(f"La couche de PtRef n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(bande_layer.crs()) :
			return False, self.tr(f"La couche de bande riveraine n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		# Define source stream net and other layers needed
		source = self.parameterAsSource(parameters, 'rivnet', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		bande_layer = self.parameterAsVectorLayer(parameters, 'bande_riveraine_polly', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		target_pts = int(self.parameterAsDouble(parameters, 'target_pts', context))
		step_min = float(self.parameterAsDouble(parameters, 'step_min', context))
		# Length of the transects (m) and margin to use
		TRANSECT_LENGTH = 31.0
		MARGIN = 2.0
		# Verify the layers are created properly
		for layer, name in [[rivnet_layer, "Réseau hydrographique"], [bande_layer, "Bande riveraine"], [ptref_layer, "PtRef largeur"]] :
			if layer is None or not layer.isValid() :
				raise RuntimeError(self.tr(f"Couche {name} invalide."))
		# Define Sink
		sink_fields = source.fields()
		sink_fields.append(QgsField("Perc_15to30m", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Perc_gt30m", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Indice F5", QVariant.Int))
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)
		model_feedback.setProgressText(self.tr("Dissolve des polygones de bande riveraine..."))
		# Dissoudre puis simplifier la bande (une seule fois)
		bande_dissolved = processing.run('native:dissolve', {
			'INPUT': bande_layer,
			'SEPARATE_DISJOINT': False,
			'OUTPUT': 'memory:'
		}, context=context)['OUTPUT']
		if model_feedback.isCanceled():
			return {}
		model_feedback.setProgressText(self.tr("Simplification des polygones de bande riveraine..."))
		bande_simplified = processing.run('native:simplifygeometries', {
			'INPUT': bande_dissolved,
			'METHOD': 0,          # distance
			'TOLERANCE': 2.0,     # à ajuster (2–5 m selon ton besoin)
			'OUTPUT': 'memory:'
		}, context=context)['OUTPUT']
		if model_feedback.isCanceled():
			return {}
		# Make a vector layer of the simplified and dissolved riparian zone polygons
		bande_global = make_layer(bande_simplified, context, 'bande_global_dissolved_simplified')

		# Pre-indexation of PtRef per segment
		model_feedback.pushInfo(self.tr('Indexation des PtRef par segment…'))
		ptref_indexes_by_seg = build_ptref_spatial_indexes(ptref_layer, seg_id_field, width_field)

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"{total_features} features à traiter"))
		# Iteration over the network to find the pourcentage of length of riparian strip in the buffers
		model_feedback.setProgressText(self.tr('Itération sur les segments du réseau...'))
		try :
			for current, segment in enumerate(source.getFeatures()):
				if model_feedback.isCanceled():
					return {}
				# Making geometry object of the river segment
				seg_geom = segment.geometry()
				seg_len = seg_geom.length()
				sid = segment[seg_id_field]
				# Adjusting the number of steps based on segment length
				if seg_len <= 0: # If segment length is lesser or equal to zero
					warnings.warn("always",self.tr(f"L'UEA dont le {seg_id_field} est {sid} est de longueur inférieure ou égale à zéro ! Indice F5 mis à 4"), UserWarning)
					model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale zéro mètre ! Veuillez vérifier sa validité Indice F5 mis à 4."))
					segment.setAttributes(segment.attributes() + [0.0, 0.0, 4])
					sink.addFeature(segment, QgsFeatureSink.FastInsert)
					model_feedback.setProgress(int(100 * (current) / max(1, total_features)))
					continue
				else:
					if seg_len <= 2 :
						model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale à deux mètres ! Veuillez vérifier si l'UEA est un artéfact de prétraitement."))
					# Calculate an appropriate step for the transect points
					step_m_local = max(step_min, seg_len / target_pts) # Makes bigger steps for long segments while keeping a set minimal resolution for smaller segments
					if seg_len < step_m_local: # If segment length is smaller than the step we calculated
						# We make a single point in the middle of the segment
						pts = [seg_geom.interpolate(seg_len / 2.0).asPoint()]
					else:
						# Make the transect points for the segment
						feature = rivnet_layer.materialize(QgsFeatureRequest().setFilterFids([segment.id()]))
						points_local = processing.run('native:pointsalonglines', {
							'INPUT': feature,
							'DISTANCE': step_m_local,
							'START_OFFSET': 0,
							'END_OFFSET': 0,
							'OUTPUT': 'memory:'
						}, context=context)['OUTPUT']
						pts = [f.geometry().asPoint() for f in points_local.getFeatures()]
				# 1) Max river width on the segment
				ptref_idx_entry = ptref_indexes_by_seg.get(sid)
				w_max = max_width_for_segment(ptref_idx_entry)  # 0.0 if no PtRef
				# 2) Adaptative clip radius (max offset + L + margin)
				R = (w_max / 2.0) + TRANSECT_LENGTH + MARGIN
				# 3) Buffer adaptatif et clip de la bande dissoute simplifiée
				clip_buf = seg_geom.buffer(R, 8)
				# Intersect the geometry of the riparian zone polygon with the segment max width buffer
				band_clip = QgsGeometry()
				for bf in bande_global.getFeatures():
					g = bf.geometry()
					if g and not g.isEmpty() and g.intersects(clip_buf):
						inter = g.intersection(clip_buf)
						if inter and not inter.isEmpty():
							band_clip = band_clip.combine(inter) if not band_clip.isEmpty() else inter
				# Make bounding box of the clipped riparian zone polygon to verify if the transect intersects
				engine_prepared, band_bbox = make_prepared_engine_and_bbox(band_clip)
				# Verify if the riparian zone union is empty (no riparian zone around the segment)
				if (engine_prepared is None):
					# Nothing to intersect for this segment
					perc30 = 0.0
					perc15to30 = 0.0
					indiceF5 = computeF5_from_sides(perc30, perc15to30)
					segment.setAttributes(segment.attributes() + [perc30, perc15to30, indiceF5])
					sink.addFeature(segment, QgsFeatureSink.FastInsert)
					model_feedback.setProgress(int(100 * (current) / max(1, total_features)))
					continue
				# Counters of transect in intersection with the riparian zone
				count_30   = 0   # Number of shores (left+right) that have a riparian zone > 30 m
				count_15to30 = 0 # Number of shores that have a riparian zone >= 15 m and =< 30 m
				n_pts = len(pts)
				# Go over each transect points to calculate the intersection with the riparian zone
				for center_pt in pts:
					# 1) Angle of local tangent
					theta = direction_angle_at_point_fast(seg_geom, center_pt)
					# In case there's some weird geometries
					if theta == 0.0:
						theta = direction_angle_at_point(seg_geom, center_pt)
					# 2) Start offset = channel width/2 if PtRef exists, else 0
					# Get the PtRef points index for this segments
					ptref_idx_entry = ptref_indexes_by_seg.get(sid)
					w = nearest_width_value_indexed(center_pt, ptref_idx_entry)
					offset = (float(w) / 2.0) if (w and w > 0) else 0.0
					# Transects left/right of length of TRANSECT_LENGTH 
					left_line  = make_transect_line(center_pt, theta + math.pi/2.0, offset, TRANSECT_LENGTH)
					right_line = make_transect_line(center_pt, theta - math.pi/2.0, offset, TRANSECT_LENGTH)
					# Check the length of the transect intersection with riparian zone, if no riparian zone to intersect returns zero
					left_int_len  = fast_intersection_length(left_line, band_clip, engine_prepared, band_bbox)
					right_int_len = fast_intersection_length(right_line, band_clip, engine_prepared, band_bbox)
					# Tests if the intersection length is smaller than 15m, if its not the case we skip the count of the transect
					if (left_int_len < 15.0) and (right_int_len < 15.0):
						continue
					# 3) Counts the number of transects for which the intersect is greater or equal to each width treshold (15 and 30m)(taking into account each sides)
					count_30 += (1 if left_int_len > 30.0 else 0) + (1 if right_int_len > 30.0 else 0)
					count_15to30  += (1 if (15.0 <= left_int_len <= 30.0) else 0) + (1 if (15.0 <= right_int_len <= 30.0) else 0)

				# Pourcentages
				den = 2.0 * float(n_pts) if n_pts else 1.0
				perc30 = count_30 / den
				perc15to30 = count_15to30 / den

				# Compute the F5 index
				indiceF5 = computeF5_from_sides(perc30, perc15to30)

				# Adding results to the sink
				segment.setAttributes(segment.attributes() + [perc15to30*100, perc30*100,  indiceF5])
				sink.addFeature(segment, QgsFeatureSink.FastInsert)

				# Increments the progress bar
				if total_features != 0:
					progress = int(100*(current/total_features))
				else:
					progress = 0
				model_feedback.setProgress(progress)
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans la boucle de segments : {str(e)}"))
			return {}
		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT : dest_id}


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF5()

	def name(self):
		return 'indicef5'

	def displayName(self):
		return self.tr('Indice F5')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return self.tr('iqm')

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice F5 afin d'évaluer la largeur et la continuité longitudinale de la bande riveraine fonctionnelle de part et d’autre du lit mineur à l’intérieur du corridor fluvial.\n La bande riveraine fonctionnelle consiste à la portion végétale ligneuse dont la hauteur moyenne au-dessus de 1 m est susceptible de contribuer à l’apport en bois. La continuité de la végétation est évaluée par la distance longitudinale relative en contact avec une bande riveraine d’une largeur donnée. La qualité morphologique du segment varie en fonction de la largeur de la bande riveraine (pour une largeur prédéterminée de 30 ou 15 m à partir de la limite du lit mineur) et la continuité à l’intérieur du segment qui s’exprime en pourcentage (%).\n" \
			"Paramètres\n" \
			"----------\n" \
			"Bande riveraine : Vectoriel (polygones)\n" \
			"-> Données vectorielles surfacique des peuplements écoforestiers pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Carte écoforestière à jour, [Jeu de données], dans Données Québec.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ PtRef largeur : Chaine de caractère ('Largeur_mod' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant la largeur du chenal. Source des données : Couche PtRef largeur.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			" Nbr de points visés : nombre entier (int; 200 par défaut)\n" \
			"-> Nombre de points de transects visés par segment. Permet de meilleures performances pour réduire le nombre de transects pour les longs segments. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			" Longueur min entre transects (m) : double (10 m par défaut)\n" \
			"-> La distance minimale à avoir entre les transects (surtout utilisé pour les petits segments à la place d'utiliser le nombre des points visés). Tous les segments de longueur inférieure à long min intertransect*nbr de points visé, utiliserons cette distance entre les transects. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie :  Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le pourcentage de longueur de segment ayant une bande riveraine entre 15 et 30m [15,30] et le pourcentage pour une largeur de plus de 30m ainsi que le score de l'indice F5 calculé pour chaque UEA."
		)


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters


def make_layer(obj, context, name='layer'):
	"""
	Make sure we have a QgsVectorLayer.
	- If obj is already a layer it is returned
	- If obj is a string (path/ID), we convert is to a OGR layer.
	"""
	if isinstance(obj, QgsVectorLayer):
		return obj
	if isinstance(obj, str):
		lyr = QgsProcessingUtils.mapLayerFromString(obj, context)
		if lyr is None or not lyr.isValid():
			raise RuntimeError(f"Impossible de charger la couche '{name}' depuis: {obj}")
		return lyr
	raise TypeError(f"Type inattendu pour '{name}': {type(obj)}")


def build_ptref_spatial_indexes(ptref_layer, seg_id_field: str, width_field: str):
	"""
	Builds spatial indexes by segment.
	Returns a dict: {sid: {'index': QgsSpatialIndex, 'features': [QgsFeature], 'width_field': width_field}}
	"""
	seg_to_features = {}
	for pf in ptref_layer.getFeatures():
		sid = pf[seg_id_field]
		seg_to_features.setdefault(sid, []).append(pf)

	seg_to_index = {}
	for sid, feats in seg_to_features.items():
		idx = QgsSpatialIndex()
		for f in feats:
			idx.addFeature(f)
		seg_to_index[sid] = {'index': idx, 'features': feats, 'width_field': width_field}
	return seg_to_index


def max_width_for_segment(ptref_idx_entry) -> float:
	"""
	Returns the maximum width (Largeur_mod) on the PtRef of the segment.
	ptref_idx_entry = {'index': QgsSpatialIndex, 'features': [QgsFeature], width_field: 'Largeur_mod'}
	"""
	if not ptref_idx_entry:
		return 0.0
	feats = ptref_idx_entry.get('features', [])
	width_field = ptref_idx_entry.get('width_field', 'Largeur_mod')
	wmax = 0.0
	for pf in feats:
		try:
			val = pf[width_field]
			w = float(val) if val is not None else None
		except Exception:
			w = None
		if w is not None and w > wmax:
			wmax = w
	return wmax


def make_prepared_engine_and_bbox(geom: QgsGeometry):
	"""
	Returns (engine_prepared, bbox) for geom.
	- engine_prepared: GEOS engine prepared for fast predicates (intersects, contains, etc.).
	- bbox: axis-aligned bounding box (AABB) of geom for the broad-phase filter.
	"""
	if (geom is None) or geom.isEmpty():
		return None, None
	engine = QgsGeometry.createGeometryEngine(geom.constGet())
	engine.prepareGeometry()
	bbox = geom.boundingBox()
	return engine, bbox


def direction_angle_at_point_fast(seg_geom: QgsGeometry, pt_xy: QgsPointXY) -> float:
	"""
	Angle (radians) of the local tangent to the polyline seg_geom in the vicinity of pt_xy,
	obtained via QgsGeometry.closestSegmentWithContext (C++ -> faster).

	Returns 0.0 if not applicable (empty geometry, zero segment).
	"""
	if (seg_geom is None) or seg_geom.isEmpty():
		return 0.0
	try:
		center_g = QgsGeometry.fromPointXY(pt_xy)
		# Gives: (pt_on_seg, vertex_after, vertex_before, dist, left_of)
		res = seg_geom.closestSegmentWithContext(center_g)
		if not res or len(res) < 5:
			return 0.0
		pt_on_seg, v_after, v_before, dist, left_of = res
		# v_before and v_after are QgsPoint;
		ax, ay = v_before.x(), v_before.y()
		bx, by = v_after.x(),  v_after.y()
		dx = (bx - ax)
		dy = (by - ay)
		# If the segment is degenerate (dx=dy=0), we end up with 0.0.
		if dx == 0.0 and dy == 0.0:
			return 0.0
		return math.atan2(dy, dx)
	except Exception:
		# Silent Fallback (rare): return 0.0
		return 0.0


def direction_angle_at_point(seg_geom: QgsGeometry, pt_xy: QgsPointXY) -> float:
	"""
	Angle (radians) de la tangente locale au segment au point 'pt_xy'.
	Méthode robuste : trouver le petit segment de polyline le plus proche, puis angle de ce segment.
	"""
	parts = seg_geom.asMultiPolyline()
	if not parts:
		parts = [seg_geom.asPolyline()]
	best_seg = None
	best_dist = float('inf')
	for line in parts:
		for a, b in zip(line[:-1], line[1:]):
			dist = QgsGeometry.fromPolylineXY([a, b]).distance(QgsGeometry.fromPointXY(pt_xy))
			if dist < best_dist:
				best_dist = dist
				best_seg = (a, b)
	if best_seg is None:
		return 0.0
	a, b = best_seg
	dx = (b.x() - a.x())
	dy = (b.y() - a.y())
	return math.atan2(dy, dx)


def nearest_width_value_indexed(center_pt: QgsPointXY, seg_ptref_idx_entry) -> float or None:
	"""
	Cherche la largeur la plus proche via index spatial pour CE segment.
	seg_ptref_idx_entry = {'index': QgsSpatialIndex, 'features': [QgsFeature], 'width_field': 'Largeur_mod'}
	"""
	if not seg_ptref_idx_entry:
		return None
	idx = seg_ptref_idx_entry['index']
	feats = seg_ptref_idx_entry['features']
	width_field = seg_ptref_idx_entry['width_field']

	# petite boite de recherche (~50 m autour du point) pour limiter les candidats
	# (tu peux ajuster le rayon selon la densité des PtRef)
	r = 100
	rect = QgsRectangle(center_pt.x() - r, center_pt.y() - r, center_pt.x() + r, center_pt.y() + r)
	candidate_ids = idx.intersects(rect)

	best_w = None
	best_d = float('inf')
	center_g = QgsGeometry.fromPointXY(center_pt)

	# si aucun candidat dans la bbox, on essaie tous (rare)
	if not candidate_ids:
		candidate_ids = [f.id() for f in feats]

	# Accès direct aux features par FID via une requête; sinon boucle locale
	# (ici, on parcourt la liste 'feats', c'est plus simple et rapide en mémoire)
	id_to_feat = {f.id(): f for f in feats}
	for fid in candidate_ids:
		pf = id_to_feat.get(fid)
		if pf is None:
			continue
		g = pf.geometry()
		if not g or g.isEmpty():
			continue
		d = g.distance(center_g)
		# lecture de la largeur
		try:
			val = pf[width_field]
			w = float(val) if val is not None else None
		except Exception:
			w = None
		if w is not None and d < best_d:
			best_d, best_w = d, w

	return best_w


def make_transect_line(center_pt: QgsPointXY, normal_angle: float, offset: float, length_m: float) -> QgsGeometry:
	"""
	Construit une ligne perpendiculaire :
		- départ à 'offset' mètres du centre,
		- fin à 'offset + length_m' mètres.
	"""
	start = QgsPointXY(center_pt.x() + offset * math.cos(normal_angle),
						center_pt.y() + offset * math.sin(normal_angle))
	end   = QgsPointXY(center_pt.x() + (offset + length_m) * math.cos(normal_angle),
						center_pt.y() + (offset + length_m) * math.sin(normal_angle))
	return QgsGeometry.fromPolylineXY([start, end])


def fast_intersection_length(line: QgsGeometry, band_union: QgsGeometry, engine_prepared, band_bbox):
	"""
	Longueur de l'intersection 'line ∩ band_union' avec court-circuits :
	1) BBOX (très bon marché) : si pas d'intersection d'enveloppes -> 0
	2) Prédicat préparé (exact & rapide) : si pas d'intersection -> 0
	3) Overlay (coûteux) : seulement si on sait qu'il y a intersection réelle.
	"""
	if (line is None) or line.isEmpty() or (band_union is None) or band_union.isEmpty():
		return 0.0
	# 1) Broad-phase: BBOX
	if not line.boundingBox().intersects(band_bbox):
		return 0.0
	# 2) Narrow-phase: prédicat exact sur geometry préparée
	if not engine_prepared.intersects(line.constGet()):
		return 0.0
	# 3) Overlay: on calcule enfin l'intersection réelle (coûteuse)
	inter = line.intersection(band_union)
	return inter.length() if (inter and not inter.isEmpty()) else 0.0



def build_band_union_for_segment(seg_geom: QgsGeometry, bande_layer: QgsVectorLayer, band_index: QgsSpatialIndex) -> QgsGeometry:
	clip = seg_geom.buffer(31.0, 8)
	ids = band_index.intersects(clip.boundingBox())
	parts = []
	for fid in ids:
		g = bande_layer.getFeature(fid).geometry()
		if g and not g.isEmpty() and clip.intersects(g):
			c = clip.intersection(g)
			if c and not c.isEmpty():
				parts.append(c)
	return QgsGeometry.unaryUnion(parts) if parts else QgsGeometry()


def nearest_width_value(center_pt: QgsPointXY, ptrefs_for_seg, width_field: str):
	"""
	Retourne la largeur la plus proche parmi les PtRef du segment (sinon None).
	Pas de fallback global : tu as dit que tu vérifies les IDs en amont.
	"""
	if not ptrefs_for_seg:
		return None
	best_w = None
	best_d = float('inf')
	center_g = QgsGeometry.fromPointXY(center_pt)
	for pf in ptrefs_for_seg:
		g = pf.geometry()
		if not g or g.isEmpty():
			continue
		d = g.distance(center_g)
		try:
			val = pf[width_field]
			w = float(val) if val is not None else None
		except Exception:
			w = None
		if w is not None and d < best_d:
			best_d, best_w = d, w
	return best_w


def line_intersection_length_union(line_geom: QgsGeometry, band_union: QgsGeometry) -> float:
	if not band_union or band_union.isEmpty() or not line_geom or line_geom.isEmpty():
		return 0.0
	inter = line_geom.intersection(band_union)
	return inter.length() if (inter and not inter.isEmpty()) else 0.0


def computeF5_from_sides(p30, p15to30):
	"""  Classe F5 basée sur la proportion de rives conformes par seuil """
	# Classe 0 : ≥>30 m sur > 90% de la longueur
	if p30 > 0.90:
		return 0
	# Classe 1 : ≥>30 m sur > 66% de la longueur
	if p30 > 0.66:
		return 1
	# Classe 2 :
	# - 15-30 m sur > 66%   OU
	# - ≥>30 m sur 33-66%
	if (p15to30 > 0.66) or (0.33 <= p30 <= 0.66):
		return 2
	# Classe 3 : 15-30 m (discontinue) sur 33-66% et pas de ≥30 m significatif
	if (0.33 <= p15to30 <= 0.66) and (p30 < 0.33):
		return 3
	# Classe 4 : < 33% en tout
	return 4