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
import math

from qgis.PyQt.QtCore import QMetaType, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsGeometry,
	QgsPointXY,
	QgsProperty,
	QgsWkbTypes,
	QgsField,
	QgsUnitTypes,
	QgsProcessingParameterNumber,
	QgsFeatureSink,
	QgsFeatureRequest,
	QgsVectorLayer,
	QgsProcessingParameterString,
	QgsProcessingParameterBoolean,
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
	# Length of the transects
	TRANSECT_LENGTH = 50.0

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer("roads", self.tr("Réseau routier (OSM)"),  types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer("ptref_widths", self.tr("PtRef largeur (CRHQ)"), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer("rivnet", self.tr("Réseau hydrographique (CRHQ)"), types=[QgsProcessing.TypeVectorLine],defaultValue=None,))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('target_pts', self.tr('Nombre de points visés par segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=50))
		self.addParameter(QgsProcessingParameterNumber('step_min', self.tr('Longueur minimale entre les transects (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=10))
		self.addParameter(QgsProcessingParameterRasterLayer("landuse", self.tr("Utilisation du territoire (MELCCFP)"), defaultValue=None))
		self.addParameter(QgsProcessingParameterBoolean('use_agri', self.tr('Utiliser milieux agricoles ?'), defaultValue=True, optional=True))
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
		# Verify that the road layer passed through the preprocessing script
		if "demi_emp" not in [f.name() for f in roads_layer.fields()]:
			return False, self.tr("Le champ 'demi_emp' est absent de la couche du réseau routier! Veuillez vous assurer que la couche de réseau routier à préalablement passé par le script Extraction routes d'OSM (IQM utils).")
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
		use_agri = self.parameterAsBool(parameters, 'use_agri', context)
		# Define source stream net
		source = self.parameterAsVectorLayer(parameters, 'rivnet', context)

		# Define sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Larg_med_connect_lat", QMetaType.Double, prec=2))
		sink_fields.append(QgsField("Indice F2", QMetaType.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		# Group PtRef by segment (projected on each UEA line later)
		model_feedback.setProgressText(self.tr('Regroupement des PtRef par segment...'))
		#ptref_by_seg = group_ptref_by_segment(ptref_layer, seg_id_field)
		ptref_by_seg = group_ptref_by_segment(ptref_layer, seg_id_field, width_field)

		# Reclassify landUse
		model_feedback.setProgressText(self.tr("Polygonisation et reclassification de l'utilisation du territoire..."))
		# Zone of interest around the river network: transects never go further than
		# half the channel width + TRANSECT_LENGTH from the centerline (20 m safety margin)
		max_w = max_ptref_width(ptref_by_seg)
		zone_m = min(500.0, self.TRANSECT_LENGTH + max_w / 2.0 + 20.0)
		model_feedback.pushInfo(self.tr(f"Zone d'intérêt : buffer de {zone_m:.0f} m (largeur max du réseau actuel) autour du réseau hydrographique"))
		zone = processing.run("native:buffer", {
			'INPUT' : parameters['rivnet'],
			'DISTANCE' : zone_m,
			'SEGMENTS' : 5,
			'END_CAP_STYLE' : 0,
			'JOIN_STYLE' : 0,
			'MITER_LIMIT' : 2,
			'DISSOLVE' : True,
			'OUTPUT' : 'TEMPORARY_OUTPUT'
		}, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']

		try :
			vectorised_landuse = polygonize_landuse(use_agri, parameters, context, feedback=model_feedback, zone=zone)
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans polygonize_landuse : {str(e)}"))
			return {}
		if model_feedback.isCanceled():
			return {}

		# Making obstacle layers into one
		model_feedback.setProgressText(self.tr("Fusion des couches d'obstacles..."))
		try :
			# ----- (A) Convert roads (LineString) to polygons via buffer -----
			roads_poly = processing.run("native:buffer", {
				"INPUT": roads_layer,
				"DISTANCE": QgsProperty.fromField("demi_emp"),   # half width from side to sides
				"SEGMENTS": 5,
				"END_CAP_STYLE": 1,              # Round=0, Flat=1, Square=2
				"JOIN_STYLE": 0,
				"MITER_LIMIT": 2,
				"DISSOLVE": False,
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (B) Merge the two polygon layers (buffered roads + land use) -----
			landuse_simpl = simplify_layer_once(vectorised_landuse, tol=5.0, dissolve=False)
			all_obstacles_poly = processing.run("native:mergevectorlayers", {
				"LAYERS": [roads_poly, landuse_simpl],
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (C) Dissolve the merged obstacles (already in polygons) -----
			obstacles_dissolved = processing.run("native:dissolve", {
				"INPUT": all_obstacles_poly,
				"SEPARATE_DISJOINT": False,
				"FIELD": [],
				"OUTPUT": "memory:"
			}, context=context)["OUTPUT"]
			# ----- (D) Building the unified geometry -----
			global_obstacles_union = None
			for f in obstacles_dissolved.getFeatures():
				global_obstacles_union = f.geometry()
				break
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
		nb_null = 0

		# Iteration over all river network features
		model_feedback.setProgressText(self.tr('Itération sur les segments du réseau...'))
		for current, segment in enumerate(source.getFeatures()):
			if model_feedback.isCanceled():
				return {}
			seg_geom = segment.geometry()
			sid = segment[seg_id_field]
			seg_len = seg_geom.length()
			# Verify length of segment
			if seg_len <= 2 :
				model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale à deux mètres ! Veuillez vérifier si l'UEA est un artéfact de prétraitement."))
			line_geom = merged_line(seg_geom)
			# Calculate an appropriate step for the transect points
			step_m_local = max(step_min, seg_len / target_pts) # Makes bigger steps for long segments while keeping a set minimal resolution for smaller segments

			# Get points along segment based on given step_m_local for the segment
			dists, px, py, theta = sample_line(line_geom, step_m_local)
			# Width profile of the UEA, then width of the nearest PtRef along the line for each transect point
			ppos, pwidth = ptref_profile(line_geom, ptref_by_seg.get(sid, []))
			widths = widths_at_distances(dists, ppos, pwidth)
			# Half-width; 1 m (2 m channel) when no valid PtRef (NaN) or width <= 0
			offsets = np.where(widths > 0, widths / 2.0, 1.0)
			# Making the transects on both sides of the stream
			transect_list = make_transects(px, py, theta, offsets, self.TRANSECT_LENGTH)

			median_unrestricted_distance = None
			indiceF2 = None
			# If no transect pts are given for the segment the value for the index is Null
			if len(widths) == 0 :
				model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur nulle ou invalide et ne comporte pas de transects ! Indice F2 mis à NULL."))
			else :
				# Getting the distance (width) unobstructed
				median_unrestricted_distance = get_median_first_obstacle_distance(transect_list, prepared_engine, global_obstacles_union, no_hit_value=51.0, max_probe=self.TRANSECT_LENGTH)
				# Determine the IQM Score
				indiceF2 = computeF2(median_unrestricted_distance)

			if indiceF2 is None:
				nb_null += 1

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

		if nb_null:
			model_feedback.pushInfo(self.tr(f"\t {nb_null} UEA de longueur nulle) : Indice F2 mis à NULL."))
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
			"Calcule de l'indice F2 afin d'évaluer la connectivité latérale avec la plaine alluviale.\n L'outil prend en compte les éléments de déconnexion artificielle  présents sur la plaine alluviale (réseau routier, affectation urbaine et agricole à l'intérieur de la plaine) afin d'évaluer la connectivité latérale potentielle des deux rives (largeur médiane de la zone de connectivité latérale). La connectivité latérale est évaluée à partir d'une largeur minimale de 15 m jusqu'à une distance maximale de 50 m.\n" \
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
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes anthropique et agricole (optionnel), selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Utiliser milieux agricoles : Booléen (optionnel; valeur par défaut : Vrai) \n" \
			"-> Détermine si l'algorithme doit considérer les milieux agricoles comme obstacles supplémentaires dans la plaine alluviale pour la reclassification des classes d'utilisation du territoire.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F2 calculé pour chaque UEA."
		)


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters


def group_ptref_by_segment(ptref_layer, seg_id_field: str, width_field: str) -> dict:
	"""Returns {sid: [(QgsGeometry, width or None), ...]}; reads only the 2 needed fields."""
	request = QgsFeatureRequest().setSubsetOfAttributes([seg_id_field, width_field], ptref_layer.fields())
	seg_to_items = {}
	for pf in ptref_layer.getFeatures(request):
		g = pf.geometry()
		if not g or g.isEmpty():
			continue
		try:
			w = float(pf[width_field])
		except (TypeError, ValueError):
			w = None	# NULL / unreadable : ignored
		seg_to_items.setdefault(pf[seg_id_field], []).append((g, w))
	return seg_to_items


def merged_line(seg_geom: QgsGeometry) -> QgsGeometry:
	"""Single-part line when possible, so that distances along the line are unambiguous."""
	if seg_geom is not None and seg_geom.isMultipart():
		merged = seg_geom.mergeLines()
		if merged and not merged.isEmpty():
			return merged
	return seg_geom


def ptref_profile(line: QgsGeometry, ptref_items: list):
	"""
	Projects each PtRef on the line (lineLocatePoint) -> position in m from the line start.
	Returns (positions, widths) as numpy arrays sorted by position.
	Widths <= 0 / NaN are kept: the main loop turns them into the 1 m half-width fallback.
	"""
	pos_list, w_list = [], []
	for g, w in ptref_items:
		if w is None:
			continue
		pos = line.lineLocatePoint(g)
		if pos is None or pos < 0:
			continue
		pos_list.append(pos)
		w_list.append(w)
	pos = np.array(pos_list, dtype=float)
	w = np.array(w_list, dtype=float)
	order = np.argsort(pos)
	return pos[order], w[order]


def widths_at_distances(dists, pos, w):
	"""
	For each distance along the line, returns the width of the PtRef closest
	in along-line distance (NaN when the segment has no usable PtRef).
	"""
	dists = np.asarray(dists, dtype=float)
	if len(pos) == 0:
		return np.full(len(dists), np.nan)
	j = np.searchsorted(pos, dists)
	j_hi = np.clip(j, 0, len(pos) - 1)
	j_lo = np.clip(j - 1, 0, len(pos) - 1)
	use_lo = np.abs(dists - pos[j_lo]) <= np.abs(pos[j_hi] - dists)
	return w[np.where(use_lo, j_lo, j_hi)]


def max_ptref_width(ptref_by_seg: dict) -> float:
	vals = [w for items in ptref_by_seg.values() for _, w in items if w is not None and np.isfinite(w)]
	return max(vals) if vals else 0.0


def polygonize_landuse(use_agri, parameters, context, feedback, zone):
	alg_params = {
		'INPUT' : parameters['landuse'],
		'MASK' : zone,
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
	clip = processing.run("gdal:cliprasterbymasklayer", alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
	# Reclassify land use. Keep agricultural (optional) and anthropised land and drop other landuse classes.
	if use_agri == True :
		feedback.pushInfo("Utilisation des classes de milieux anthropiques et agricoles")
		CLASSES = ['101', '198', '1', #Agriculture from 101 to 198 are replaced by 1.
				'300', '360', '1' # Anthropised from 300 to 360 are replaced by 1.
		]
	else :
		feedback.pushInfo("Utilisation des classes de milieux anthropiques seulement")
		CLASSES = ['300', '360', '1' # Anthropised from 300 to 360 are replaced by 1.
		]
	alg_params = {
		'DATA_TYPE' : 0,  # Byte
		'INPUT_RASTER' : clip ,
		'NODATA_FOR_MISSING' : True,
		'NO_DATA' : 0,
		'RANGE_BOUNDARIES' : 2,  # min <= value <= max
		'RASTER_BAND': 1,
		'TABLE' : CLASSES,
		'OUTPUT' : QgsProcessingUtils.generateTempFilename("reclass_landuse.tif")
	}
	reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
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
	processing.run('gdal:polygonize', alg_params, context=context, feedback=None, is_child_algorithm=True)
	# Making the layer
	poly_layer = QgsVectorLayer(poly_path, "landuse", "ogr")
	if not poly_layer.isValid():
		raise RuntimeError("Échec de chargement de la couche polygonisée 'landuse'.")
	return poly_layer


def simplify_layer_once(layer, tol=2.0, dissolve=True):
	src = layer
	if dissolve :
		src = processing.run('native:dissolve', {
			'INPUT': layer, 'SEPARATE_DISJOINT': False, 'OUTPUT': 'memory:'
		})['OUTPUT']
	return processing.run('native:simplifygeometries', {
		'INPUT': src, 'METHOD': 0, 'TOLERANCE': tol, 'OUTPUT': 'memory:'
	})['OUTPUT']


def line_to_segments(line: QgsGeometry):
	"""
	Returns numpy arrays (x0, y0, dx, dy, length) for every non-degenerate
	sub-segment of the line (multipart handled, zero-length segments dropped).
	"""
	if QgsWkbTypes.isCurvedType(line.wkbType()):
		line = line.convertToStraightSegment()
	if QgsWkbTypes.isMultiType(line.wkbType()):
		parts = line.asMultiPolyline()
	else:
		parts = [line.asPolyline()]
	x0, y0, dx, dy = [], [], [], []
	for part in parts:
		if len(part) < 2:
			continue
		xy = np.array([(p.x(), p.y()) for p in part], dtype=float)
		d = np.diff(xy, axis=0)
		x0.append(xy[:-1, 0]); y0.append(xy[:-1, 1])
		dx.append(d[:, 0]);    dy.append(d[:, 1])
	if not x0:
		return (np.empty(0),) * 5
	x0, y0, dx, dy = map(np.concatenate, (x0, y0, dx, dy))
	slen = np.hypot(dx, dy)
	keep = slen > 0
	return x0[keep], y0[keep], dx[keep], dy[keep], slen[keep]


def sample_line(line: QgsGeometry, step_m: float):
	"""
	Samples the line every step_m meters (same rules as before: clamp to [0, L - eps],
	single midpoint if the line is shorter than the step).
	Returns (distances, x, y, theta) as numpy arrays; theta = local tangent angle (rad).
	"""
	empty = (np.empty(0),) * 4
	if line is None or line.isEmpty():
		return empty
	x0, y0, dx, dy, slen = line_to_segments(line)
	if len(slen) == 0:
		return empty
	cum = np.concatenate(([0.0], np.cumsum(slen)))
	L = cum[-1]
	eps = max(1e-6, min(0.001, 1e-3 * L))
	step_m = max(step_m, 1e-6)
	if L < step_m:
		d = np.array([max(0.0, min(L - eps, L * 0.5))])
	else:
		d = np.minimum(L - eps, np.arange(0.0, L, step_m))
	# Index of the sub-segment containing each distance
	i = np.clip(np.searchsorted(cum, d, side='right') - 1, 0, len(slen) - 1)
	t = (d - cum[i]) / slen[i]
	px = x0[i] + dx[i] * t
	py = y0[i] + dy[i] * t
	theta = np.arctan2(dy[i], dx[i])
	return d, px, py, theta


def make_transects(px, py, theta, offsets, length_m):
	"""
	Left transects (theta + 90°) then right transects (theta - 90°), each starting at
	'offset' m from the centerline and ending at offset + length_m.
	"""
	nx, ny = -np.sin(theta), np.cos(theta)	# left normal
	lines = []
	for sign in (1.0, -1.0):
		xs, ys = px + sign * nx * offsets, py + sign * ny * offsets
		xe, ye = px + sign * nx * (offsets + length_m), py + sign * ny * (offsets + length_m)
		lines.extend(
			QgsGeometry.fromPolylineXY([QgsPointXY(a, b), QgsPointXY(c, d)])
			for a, b, c, d in zip(xs, ys, xe, ye)
		)
	return lines


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
