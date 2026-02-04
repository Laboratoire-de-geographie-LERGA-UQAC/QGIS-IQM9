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

import sys
import numpy as np
import processing
import math

from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsRectangle,
	QgsGeometry,
	QgsPointXY,
	QgsWkbTypes,
	QgsField,
	QgsUnitTypes,
	QgsProcessingParameterNumber,
	QgsFeatureSink,
	QgsSpatialIndex,
	QgsVectorLayer,
	QgsProcessingParameterString,
	QgsProcessingUtils,
	QgsProcessingParameterRasterLayer,
	QgsProcessingAlgorithm,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink
)

class IndiceF2(QgsProcessingAlgorithm):
	OUTPUT = "OUTPUT"
	DEFAULT_WIDTH_FIELD = 'Largeur_mod'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer("roads", self.tr("Réseau routier (OSM)"),  types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer("ptref_widths", self.tr("PtRef largeur (CRHQ)"), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer("rivnet", self.tr("Réseau hydrographique (CRHQ)"), types=[QgsProcessing.TypeVectorLine],defaultValue=None,))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('target_pts', self.tr('Nombre de points visés par segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=50))
		self.addParameter(QgsProcessingParameterNumber('step_min', self.tr('Longueur minimale entre les transects (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=10))
		self.addParameter(QgsProcessingParameterRasterLayer("landuse", self.tr("Utilisation du territoire (MELCCFP)"), defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Check if the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		roads_layer = self.parameterAsVectorLayer(parameters, 'roads', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		# Verify that the given segment ID is in the rivnet and PtRef layer
		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro ! Veuillez fournir un champ identifiant du segment commun aux deux couches (res. hydro. et PtRef largeur).")
		if seg_id_field not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche PtRef largeur! Veuillez fournir un champ identifiant du segment commun aux deux couches (res. hydro. et PtRef largeur).")
		# Verify that the given width attribute is in the PtRef layer
		if width_field not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ '{width_field}' est absent de la couche PtRef largeur! Veuillez fournir un champ identifiant la largeur du segment qui se trouve dans cette couche.")
		if not is_metric_crs(rivnet_layer.crs()) :
			return False, self.tr(f"La couche de réseau hydro n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(ptref_layer.crs()) :
			return False, self.tr(f"La couche de PtRef n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(roads_layer.crs()) :
			return False, self.tr(f"La couche de bande riveraine n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		if model_feedback.isCanceled():
			return {}
		# Making layers and parameters needed for processing
		roads_layer = self.parameterAsVectorLayer(parameters, 'roads', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		target_pts = int(self.parameterAsDouble(parameters, 'target_pts', context))
		step_min = float(self.parameterAsDouble(parameters, 'step_min', context))
		# Define source stream net
		source = self.parameterAsVectorLayer(parameters, 'rivnet', context)

		# Define sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Larg_med_connect_lat", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Indice F2", QVariant.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		# Pre-indexation of PtRef per segment (for faster searching)
		model_feedback.pushInfo(self.tr('Indexation des PtRef par segment…'))
		ptref_indexes_by_seg = build_ptref_spatial_indexes(ptref_layer, seg_id_field, width_field)

		# Reclassify landUse
		model_feedback.setProgressText(self.tr("Polygonisation et reclassification de l'utilisation du territoire..."))
		try :
			vectorised_landuse = polygonize_landuse(parameters, context, feedback=None)
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans polygonize_landuse : {str(e)}"))
			return {}
		if model_feedback.isCanceled():
			return {}

		# Making obstacle layers into one
		model_feedback.setProgressText(self.tr("Fusion des couches d'obstacles..."))
		try :
			roads_simpl = simplify_layer_once(roads_layer, tol=5.0)
			landuse_simpl = simplify_layer_once(vectorised_landuse, tol=5.0)
			# ----- (A) Convert roads (LineString) to polygons via buffer -----
			# Choose a realistic width in meters to represent the blocking right-of-way.
			# E.g., 20 m (10 m on each side). Adjust according to your data context.
			ROAD_BUFFER = 20
			roads_poly = processing.run("native:buffer", {
				"INPUT": roads_simpl,
				"DISTANCE": ROAD_BUFFER / 2.0,   # half width from side to sides
				"SEGMENTS": 5,
				"END_CAP_STYLE": 1,              # Round=0, Flat=1, Square=2
				"JOIN_STYLE": 0,
				"MITER_LIMIT": 2,
				"DISSOLVE": True,                # important for reducing the number of parts
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (B) Dissolve the polygonized land cover (already in polygons) -----
			landuse_diss = processing.run("native:dissolve", {
				"INPUT": landuse_simpl,
				"SEPARATE_DISJOINT": False,
				"FIELD": [],
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (C) Merge the two polygon layers (buffered roads + land use) -----
			all_obstacles_poly = processing.run("native:mergevectorlayers", {
				"LAYERS": [roads_poly, landuse_diss],
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (D) Dissolve to obtain few features -----
			obstacles_dissolved = processing.run("native:dissolve", {
				"INPUT": all_obstacles_poly,
				"SEPARATE_DISJOINT": False,
				"FIELD": [],
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (E) Building the unified geometry (there should be very little left after the dissolve) and a prepared GEOS engine -----
			union_parts = [f.geometry() for f in obstacles_dissolved.getFeatures()]
			if union_parts:
				global_obstacles_union = QgsGeometry.unaryUnion(union_parts)
			else:
				global_obstacles_union = None
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans fusion des couches d'obstacles : {str(e)}"))
			return {}
		if model_feedback.isCanceled():
			return {}

		# Prepare the GEOS engine for fast intersection tests
		prepared_engine = None
		if global_obstacles_union and not global_obstacles_union.isEmpty():
			prepared_engine = QgsGeometry.createGeometryEngine(global_obstacles_union.constGet())
			prepared_engine.prepareGeometry()

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"{total_features} features (segments) à traiter"))

		# Iteration over all river network features
		model_feedback.setProgressText(self.tr('Itération sur les segments du réseau...'))
		for current, segment in enumerate(source.getFeatures()):
			if model_feedback.isCanceled():
				return {}
			seg_geom = segment.geometry()
			sid = segment[seg_id_field]
			seg_len = seg_geom.length()
			# # Get mean width of the segment
			# ptref_idx_entry = ptref_indexes_by_seg.get(sid)
			# # Mean width of the segment otherwise the max (5 m)
			# w_values = [float(pf[width_field]) for pf in (ptref_idx_entry.get('features', []) if ptref_idx_entry else []) if pf[width_field] is not None]
			# segment_mean_width = max(5.0, np.mean(w_values)) if w_values else 10
			# Verify length of segment
			if seg_len <= 2 :
				model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale à deux mètres ! Veuillez vérifier si l'UEA est un artéfact de prétraitement."))
			# Calculate an appropriate step for the transect points
			step_m_local = max(step_min, seg_len / target_pts) # Makes bigger steps for long segments while keeping a set minimal resolution for smaller segments
			# Get points along segment based on given step_m_local for the segment
			center_pts = safe_points_along_line(seg_geom, step_m_local)
			# Making the transects on both sides of the stream
			# Length of the transects
			TRANSECT_LENGTH = 50.0
			left_lines  = []
			right_lines = []
			# Get the PtRef for the segment
			ptref_idx_entry = ptref_indexes_by_seg.get(sid)
			for pt in center_pts:
				# Find the nearest PtRef to the transect pt to get the width of the channel otherwise set the width to 2 m
				w = nearest_width_value_indexed(pt, ptref_idx_entry)
				offset = (float(w) / 2.0) if (w and w > 0) else 2/2
				pt_xy = QgsPointXY(pt.x(), pt.y())
				theta = direction_angle_at_point_fast(seg_geom, pt_xy)
				if theta == 0.0:
					theta = direction_angle_at_point(seg_geom, pt_xy)
				left_lines.append(make_transect_line(pt_xy,  theta + math.pi/2.0, offset, TRANSECT_LENGTH))
				right_lines.append(make_transect_line(pt_xy, theta - math.pi/2.0, offset, TRANSECT_LENGTH))
			# Getting the distance (width) unobstructed
			transect_list = left_lines + right_lines
			median_unrestricted_distance = get_median_first_obstacle_distance(transect_list, prepared_engine, global_obstacles_union, no_hit_value=51.0, max_probe=TRANSECT_LENGTH)
			# Determine the IQM Score
			indiceF2 = computeF2(median_unrestricted_distance)
			# Write score to sink
			segment.setAttributes(
				segment.attributes() + [median_unrestricted_distance, indiceF2]
			)
			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)
			# Increments the progress bar
			if total_features != 0:
				progress = int(100*(current/total_features))
			else:
				progress = 0
			model_feedback.setProgress(progress)

		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT : dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF2()

	def name(self):
		return 'indicef2'

	def displayName(self):
		return self.tr('Indice F2')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice F2 afin d'évaluer la connectivité latérale avec la plaine alluviale.\n L'outil prend en compte les éléments de déconnexion artificielle  présents sur la plaine alluviale (réseau routier et affectation urbaine à l'intérieur de la plaine) afin d'évaluer la connectivité latérale potentielle des deux rives (largeur médiane de la zone de connectivité latérale). La connectivité latérale est évaluée à partir d'une largeur minimale de 15 m jusqu'à une distance maximale de 50 m.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau routier : Vectoriel (lignes)\n" \
			"-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ PtRef largeur : Chaine de caractère ('Largeur_mod' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant la largeur du chenal. Source des données : Couche PtRef largeur.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			" Nbr de points visés : nombre entier (int; 50 par défaut)\n" \
			"-> Nombre de points de transects visés par segment. Permet de meilleures performances pour réduire le nombre de transects pour les longs segments. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			" Longueur min entre transects (m) : double (10 m par défaut)\n" \
			"-> La distance minimale à avoir entre les transects (surtout utilisé pour les petits segments à la place d'utiliser le nombre des points visés). Tous les segments de longueur inférieure à long min intertransect*nbr de points visé, utiliserons cette distance entre les transects. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F2 calculé pour chaque UEA."
		)


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters


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


def polygonize_landuse(parameters, context, feedback):
	# River network buffer
	alg_params = {
		'INPUT' : parameters['rivnet'],
		'DISTANCE' : 500,
		'SEGMENTS' : 5,
		'END_CAP_STYLE' : 0,
		'JOIN_STYLE' : 0,
		'MITER_LIMIT' : 2,
		'DISSOLVE' : True,
		'OUTPUT' : 'TEMPORARY_OUTPUT'
	}
	buffer = processing.run("native:buffer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	# Clip raster by mask
	alg_params = {
		'INPUT' : parameters['landuse'],
		'MASK' : buffer,
		'SOURCE_CRS' : None,
		'TARGET_CRS' : None,
		'TARGET_EXTENT' : None,
		'NODATA' : None,
		'ALPHA_BAND' : False,
		'CROP_TO_CUTLINE' : True,
		'KEEP_RESOLUTION' : False,
		'SET_RESOLUTION' : False,
		'X_RESOLUTION' : None,
		'Y_RESOLUTION' : None,
		'MULTITHREADING' : False,
		'OPTIONS' : '',
		'DATA_TYPE' : 0,
		'EXTRA' : '',
		'OUTPUT' : 'TEMPORARY_OUTPUT'
	}
	clip = processing.run("gdal:cliprasterbymasklayer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	# Reclassify land use. Keep agriculture and anthropised and drop other landuse classes.
	CLASSES = ['101', '198', '1', #Agriculture from 101 to 198 are replaced by 1.
        '300', '360', '1' # Anthropised from 300 to 360 are replaced by 1.
    ]
	alg_params = {
		'DATA_TYPE' : 0,  # Byte
		'INPUT_RASTER' : clip ,#parameters['landuse'],
		'NODATA_FOR_MISSING' : True,
		'NO_DATA' : 0,
		'RANGE_BOUNDARIES' : 2,  # min <= value <= max
		'RASTER_BAND': 1,
		'TABLE' : CLASSES,
		'OUTPUT' : QgsProcessingUtils.generateTempFilename("reclass_landuse.tif")
	}
	reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	# Polygonize the reclassification
	poly_path = QgsProcessingUtils.generateTempFilename("vector_landuse.gpkg") # higher performance with gpkg than shp
	alg_params = {
		'BAND' : 1,
		'EIGHT_CONNECTEDNESS' : False,
		'EXTRA' : '',
		'FIELD' : 'DN',
		'INPUT' : reclass,
		'OUTPUT' : poly_path
	}
	processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
	# Making the layer
	poly_layer = QgsVectorLayer(poly_path, "landuse", "ogr")
	if not poly_layer.isValid():
		raise RuntimeError("Échec de chargement de la couche polygonisée 'landuse'.")
	return poly_layer


def simplify_layer_once(layer, tol=2.0):
	dissolved = processing.run('native:dissolve', {
		'INPUT': layer, 'SEPARATE_DISJOINT': False, 'OUTPUT': 'memory:'
	})['OUTPUT']
	simplified = processing.run('native:simplifygeometries', {
		'INPUT': dissolved, 'METHOD': 0, 'TOLERANCE': tol, 'OUTPUT': 'memory:'
	})['OUTPUT']
	return simplified


def safe_points_along_line(seg_geom: QgsGeometry, step_m: float) -> list:
	"""
	Robustly sample points along a (multi)line geometry every step_m meters.
	- Clamps interpolation distances to [0, length - eps] to avoid null geometries.
	- Skips empty/invalid interp results defensively.
	- Falls back to a single midpoint when the segment is shorter than the step.
	"""
	pts = []
	if seg_geom is None or seg_geom.isEmpty():
		return pts
	seg_len = seg_geom.length()
	if not np.isfinite(seg_len) or seg_len <= 0.0:
		return pts
	# Tiny epsilon to stay strictly inside [0, length)
	eps = max(1e-6, min(0.001, 1e-3 * seg_len))
	def _interp_point_at(dist_m: float):
		"""Interpolate and safely convert to QgsPointXY if a point geometry is returned."""
		g = seg_geom.interpolate(dist_m)
		if not g or g.isEmpty() or g.type() != QgsWkbTypes.PointGeometry:
			return None
		# Handle Point vs MultiPoint
		try:
			p = g.asPoint()
		except Exception:
			mp = g.asMultiPoint()
			if not mp:
				return None
			p = mp[0]
		return QgsPointXY(p.x(), p.y())
	# If the line is shorter than the step -> single midpoint (clamped)
	if seg_len < step_m:
		mid = max(0.0, min(seg_len - eps, seg_len * 0.5))
		p = _interp_point_at(mid)
		return [p] if p is not None else []
	# Regular sampling
	d = 0.0
	while d < seg_len:
		# Clamp d to [0, seg_len - eps] to avoid "null geometry" from interpolate()
		dd = min(seg_len - eps, max(0.0, d))
		p = _interp_point_at(dd)
		if p is not None:
			pts.append(p)
		d += step_m
	# Safety: if nothing has been collected (rare degenerate cases), try the midpoint
	if not pts:
		mid = max(0.0, min(seg_len - eps, seg_len * 0.5))
		p = _interp_point_at(mid)
		if p is not None:
			pts.append(p)

	return pts


def nearest_width_value_indexed(center_pt: QgsPointXY, seg_ptref_idx_entry) -> float or None:
	"""
	Find the closest width via spatial index for this segment.
	seg_ptref_idx_entry = {'index': QgsSpatialIndex, 'features': [QgsFeature], 'width_field': 'Width_mod'}
	"""
	if not seg_ptref_idx_entry:
		return None
	idx = seg_ptref_idx_entry['index']
	feats = seg_ptref_idx_entry['features']
	width_field = seg_ptref_idx_entry['width_field']
	# small search box (~100 m around the point) to limit candidates
	# (you can adjust the radius according to the density of PtRef)
	r = 100
	rect = QgsRectangle(center_pt.x() - r, center_pt.y() - r, center_pt.x() + r, center_pt.y() + r)
	candidate_ids = idx.intersects(rect)
	best_w = None
	best_d = float('inf')
	center_g = QgsGeometry.fromPointXY(center_pt)
	# if there are no candidates in the bbox, we try them all (rare)
	if not candidate_ids:
		candidate_ids = [f.id() for f in feats]
	# Direct access to features by FID via a query; otherwise local loop
	# (here, we go through the ‘feats’ list, which is simpler and faster in memory)
	id_to_feat = {f.id(): f for f in feats}
	for fid in candidate_ids:
		pf = id_to_feat.get(fid)
		if pf is None:
			continue
		g = pf.geometry()
		if not g or g.isEmpty():
			continue
		d = g.distance(center_g)
		# Read width
		try:
			val = pf[width_field]
			w = float(val) if val is not None else None
		except Exception:
			w = None
		if w is not None and d < best_d:
			best_d, best_w = d, w
	return best_w


def direction_angle_at_point_fast(seg_geom: QgsGeometry, pt_xy: QgsPointXY) -> float:
	"""
	Angle (radians) de la tangente locale au segment au voisinage de pt_xy,
	via QgsGeometry.closestSegmentWithContext (C++ -> rapide).
	Retourne 0.0 si non applicable.
	"""
	if (seg_geom is None) or seg_geom.isEmpty():
		return 0.0
	try:
		center_g = QgsGeometry.fromPointXY(pt_xy)
		res = seg_geom.closestSegmentWithContext(center_g)
		if not res or len(res) < 5:
			return 0.0
		pt_on_seg, v_after, v_before, dist, left_of = res
		ax, ay = v_before.x(), v_before.y()
		bx, by = v_after.x(), v_after.y()
		dx, dy = (bx - ax), (by - ay)
		if dx == 0.0 and dy == 0.0:
			return 0.0
		return math.atan2(dy, dx)
	except Exception:
		return 0.0


def direction_angle_at_point(seg_geom: QgsGeometry, pt_xy: QgsPointXY) -> float:
	"""
	Angle (radians) of the local tangent to the segment at point 'pt_xy'.
	Robust method: find the closest small polyline segment, then find the angle of that segment.
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


def make_transect_line(center_pt: QgsPointXY, normal_angle: float, offset: float, length_m: float) -> QgsGeometry:
	"""
	Construct a perpendicular line:
	- starting at offset meters from the center,
	- ending at offset + length_m meters.
	"""
	start = QgsPointXY(center_pt.x() + offset * math.cos(normal_angle),
					center_pt.y() + offset * math.sin(normal_angle))
	end   = QgsPointXY(center_pt.x() + (offset + length_m) * math.cos(normal_angle),
					center_pt.y() + (offset + length_m) * math.sin(normal_angle))
	return QgsGeometry.fromPolylineXY([start, end])


def first_hit_distance_bsearch(
	prepared_engine,
	sx: float, sy: float,
	ux: float, uy: float,
	lo: float, hi: float,
	tol: float = 0.5,
	start_epsilon: float = 0.05
) -> float | None:
	"""
	Binary search the smallest t in (lo, hi] such that the subsegment
	[start+epsilon, start+t] intersects the prepared polygonal union.

	Precondition: prepared_engine.intersects(seg(hi)) is True and
				prepared_engine.intersects(seg(lo)) is False.

	Returns hi at the end (first hit) within ±tol.
	"""
	# Helper to test intersection up to distance t
	def _hit(t: float) -> bool:
		p0 = QgsPointXY(sx + start_epsilon * ux, sy + start_epsilon * uy)
		p1 = QgsPointXY(sx + t * ux, sy + t * uy)
		g = QgsGeometry.fromPolylineXY([p0, p1])
		return prepared_engine.intersects(g.constGet())
	# Standard binary search
	while (hi - lo) > tol:
		mid = 0.5 * (lo + hi)
		if _hit(mid):
			hi = mid  # hit occurs, move left
		else:
			lo = mid  # no hit yet, move right
	# 'hi' approximates the first hit distance
	return hi


def get_median_first_obstacle_distance(
	transects_lines,
	prepared_engine,           # Prepared GEOS engine on the global union (can be None)
	global_obstacles_union,    # Unified obstacles geometry (can be None)
	no_hit_value: float = 51.0,
	max_probe: float = 50.0,
	tol: float = 0.5,          # Binary-search tolerance in meters
	b1: float = 5.0,           # First quick bracket threshold
	b2: float = 15.0           # Second quick bracket threshold (around F2 class breakpoints)
):
	"""
	Fast path version: find the first hit distance using only prepared 'intersects' calls.
	We avoid building the full intersection geometry and vertex iteration.

	For each transect:
	1) BBOX + prepared-engine quick rejects
	2) If no intersection up to max_probe -> return no_hit_value
	3) Otherwise, bracket the hit in [0, b1], [b1, b2], or [b2, max_probe]
	4) Binary search within the bracket down to 'tol'
	"""
	if (prepared_engine is None) or (global_obstacles_union is None) or global_obstacles_union.isEmpty():
		return float(no_hit_value)
	union_bbox = global_obstacles_union.boundingBox()
	distances = []
	for line in transects_lines:
		if line is None or line.isEmpty():
			continue
		# 0) Broad phase: bbox reject
		if not line.boundingBox().intersects(union_bbox):
			distances.append(no_hit_value)
			continue
		# Extract start and unit direction once per line
		poly = line.asPolyline()
		if not poly or len(poly) < 2:
			distances.append(no_hit_value)
			continue
		sx, sy = poly[0].x(), poly[0].y()
		ex, ey = poly[-1].x(), poly[-1].y()
		dx, dy = ex - sx, ey - sy
		seg_len = math.hypot(dx, dy)
		if seg_len <= 0.0:
			distances.append(no_hit_value)
			continue
		ux, uy = dx / seg_len, dy / seg_len  # unit direction vector
		# Helper to build a tiny subsegment [start+eps, start+t]
		def _seg_to(t: float, start_epsilon: float = 0.05) -> QgsGeometry:
			# Using a tiny epsilon avoids pathological cases (touching at t=0)
			p0 = QgsPointXY(sx + start_epsilon * ux, sy + start_epsilon * uy)
			p1 = QgsPointXY(sx + t * ux, sy + t * uy)
			return QgsGeometry.fromPolylineXY([p0, p1])
		# 1) Quick reject with prepared intersects on the full probe length
		full = _seg_to(max_probe)
		if not prepared_engine.intersects(full.constGet()):
			distances.append(no_hit_value)
			continue
		# 2) Quick bracketing (0–b1, b1–b2, b2–max_probe)
		#    We ensure lo is "no hit" and hi is "hit" before binary search.
		def _hit(t: float) -> bool:
			g = _seg_to(t)
			return prepared_engine.intersects(g.constGet())
		lo, hi = 0.0, None
		if _hit(b1):
			lo, hi = 0.0, b1
			# Edge case: if even a tiny epsilon hits, return b1 directly (fast)
			# We could binary-search [0,b1] but it's often negligible vs classes
		elif _hit(b2):
			lo, hi = b1, b2
		else:
			# Must hit in (b2, max_probe] because full already hits
			lo, hi = b2, max_probe
		# Safety: if lo already hits (very rare), return minimal plausible value
		if _hit(lo):
			distances.append(lo)
			continue
		# 3) Binary search for first-hit distance within [lo, hi]
		d = first_hit_distance_bsearch(prepared_engine, sx, sy, ux, uy, lo, hi, tol)
		distances.append(d if d is not None else no_hit_value)
	return float(np.median(distances)) if distances else float(no_hit_value)


def computeF2(median_length):
	# search for anthropisation in buffers
	if median_length > 50: # Lateral connectivity with the alluvial plain over a width of more than 50m
		return 0
	elif median_length >= 30 and median_length <= 50 : # Lateral connectivity with the alluvial plain over a width between [30m, 50m]
		return 2
	elif median_length >= 15 and median_length < 30 : # Lateral connectivity with the alluvial plain over a width between [15m, 30m[
		return 3
	elif median_length < 15 : # Lateral connectivity with the alluvial plain over a width less than 15m
		return 5
