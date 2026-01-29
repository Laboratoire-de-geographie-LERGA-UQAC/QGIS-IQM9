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
import math

import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsUnitTypes,
	QgsPointXY,
	QgsVectorLayer,
	QgsProcessingParameterString,
	QgsProcessingParameterRasterLayer,
	QgsSpatialIndex,
	QgsGeometry,
	QgsRectangle,
	QgsFeatureRequest,
	QgsProcessingUtils,
	QgsProcessingAlgorithm,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterNumber,
	QgsProcessingParameterFeatureSink
)


class IndiceF3(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'
	DEFAULT_WIDTH_FIELD = 'Largeur_mod'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer("roads", self.tr("Réseau routier (OSM)"),  types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer("ptref_widths", self.tr("PtRef largeur (CRHQ)"), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer("rivnet", self.tr("Réseau hydrographique (CRHQ)"), types=[QgsProcessing.TypeVectorLine],defaultValue=None,))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('target_pts', self.tr('Nombre de points visés par segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=200))
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
		# Define source as well as other layers and parameters needed for processing
		source = self.parameterAsSource(parameters, 'rivnet', context)
		roads_layer = self.parameterAsVectorLayer(parameters, 'roads', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		target_pts = int(self.parameterAsDouble(parameters, 'target_pts', context))
		step_min = float(self.parameterAsDouble(parameters, 'step_min', context))
		# Length of the transects and margin to use
		TRANSECT_LENGTH = 16
		MARGIN = 2.0
		# Verify the layers are created properly
		for layer, name in [[rivnet_layer, "Réseau hydrographique"], [roads_layer, "Réseau routier"], [ptref_layer, "PtRef largeur"]] :
			if layer is None or not layer.isValid() :
				raise RuntimeError(self.tr(f"Couche {name} invalide."))
		# Define sink
		sink_fields = source.fields()
		sink_fields.append(QgsField("Pourc_15m", QVariant.Double, prec=2))
		sink_fields.append(QgsField("Indice F3", QVariant.Int))
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
		# Length of the transects (m) and margin to use
		TRANSECT_LENGTH = 15 # Needs to stay the minimal with desired for the mobility space
		MARGIN = 2.0

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
		model_feedback.setProgressText(self.tr("Création de l'indice spatial des couches d'obstacles..."))
		roads_simpl = simplify_layer_once(roads_layer, tol=5.0)
		landuse_simpl = simplify_layer_once(vectorised_landuse, tol=5.0)
		obstacle_indexes = []
		for lyr in [roads_simpl, landuse_simpl]:
			idx = QgsSpatialIndex()
			for f in lyr.getFeatures():
				idx.addFeature(f)
			obstacle_indexes.append((lyr, idx))

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"{total_features} features (segments) à traiter"))

		# Iteration over all river network features
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
						#warnings.warn("always",self.tr(f"L'UEA dont le {seg_id_field} est {sid} est de longueur inférieure ou égale à zéro ! Indice F3 mis à 5"), UserWarning)
						model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale zéro mètre ! Veuillez vérifier sa validité Indice F3 mis à 5."))
						segment.setAttributes(segment.attributes() + [0.0, 5])
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
					# 3) Adaptive buffer and simplified dissolved riparian zone
					segment_buffer = seg_geom.buffer(R, 8)
					# Intersect the geometry of the riparian zone polygon with the segment max width buffer collect the obstacles intersecting this BBOX
					bbox = segment_buffer.boundingBox()
					bbox_g = QgsRectangle(
							bbox.xMinimum()-R, bbox.yMinimum()-R,
							bbox.xMaximum()+R, bbox.yMaximum()+R
					)
					local_parts = []
					for lyr, idx in obstacle_indexes:
						candidate_ids = idx.intersects(bbox_g)
						for fid in candidate_ids:
							f = lyr.getFeature(fid)
							g = f.geometry()
							if g and not g.isEmpty():
								# fast double check: bbox & intersects
								if not g.boundingBox().intersects(bbox_g):
									continue
								if not g.intersects(segment_buffer):
									continue
								# Local clip (only useful portion)
								c = g.intersection(segment_buffer)
								if c and not c.isEmpty():
									local_parts.append(c)
					union_geom = QgsGeometry.unaryUnion(local_parts)
					# If no local obstacle -> all free
					if not local_parts or not union_geom or union_geom.isEmpty():
						#model_feedback.pushInfo(self.tr(f"Pas d'obstacle. Passe au procahin"))
						perc15=1.0
						indiceF3 = computeF3(perc15)
						segment.setAttributes(segment.attributes() + [perc15*100, indiceF3])
						sink.addFeature(segment, QgsFeatureSink.FastInsert)
						model_feedback.setProgress(int(100 * (current) / max(1, total_features)))
						continue
					# Make bounding box of the clipped riparian zone polygon to verify if the transect intersects
					engine_prepared, band_bbox = make_prepared_engine_and_bbox(union_geom)
					# Verify if the obstacles union is empty (no obstacles around the segment)
					if (engine_prepared is None):
						# Nothing to intersect for this segment
						perc15=1.0
						indiceF3 = computeF3(perc15)
						segment.setAttributes(segment.attributes() + [perc15*100, indiceF3])
						sink.addFeature(segment, QgsFeatureSink.FastInsert)
						model_feedback.setProgress(int(100 * (current) / max(1, total_features)))
						continue
					# Counters of transect in intersection with the riparian zone
					count_15 = 0   # Number of shores (left+right) that have a riparian zone >= 15 m
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
						left_int_len  = fast_intersection_status(left_line, union_geom, engine_prepared, band_bbox)
						right_int_len = fast_intersection_status(right_line, union_geom, engine_prepared, band_bbox)
						# Tests if there is an obstacle within 15m in both sides, if its not the case we skip the count of the transect
						if (left_int_len == True) and (right_int_len == True):
							continue
						# 3) Counts the number of transects for which the intersect is within the width treshold (15m) (taking into account each sides)
						count_15 += (1 if left_int_len == False else 0) + (1 if right_int_len == False else 0)

					# Pourcentages
					den = 2.0 * float(n_pts) if n_pts else 1.0
					perc15 = count_15 / den

					# Compute the IQM Score
					indiceF3 = computeF3(perc15)

					# Write to layer
					segment.setAttributes(segment.attributes() + [perc15*100, indiceF3])
					# Add a feature to sink
					sink.addFeature(segment, QgsFeatureSink.FastInsert)

					# Increments the progress bar
					if total_features != 0:
						progress = int(100*(current/total_features))
					else:
						progress = 0
					model_feedback.setProgress(progress)
					#model_feedback.setProgressText(self.tr(f"Traitement de {current} segments sur {total_features}"))
		except Exception as e :
			model_feedback.reportError(self.tr(f"Erreur dans la boucle de segments : {str(e)}"))
			return {}
		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT : dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF3()

	def name(self):
		return 'indicef3'

	def displayName(self):
		return self.tr('Indice F3')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice F3 afin d'évaluer la capacité d'érosion du cours d'eau en évaluant la continuité de l'espace de mobilité sur l'ensemble du segment.\n L'outil calcul donc la continuité amont-aval en prenant compte de la somme des distances longitudinales dénuées de discontinuités de part et d'autre du chenal en fonction de la distance totale du segment. La continuité longitudinale de l'espace de mobilité s'exprime par la distance longitudinale relative (%). Les discontinuités utilisées par l'outil sont les infrastructures de transport (routes, voies ferrées) ainsi que les ponts et ponceaux présents à l'intérieur de l'espace de mobilité d'une largeur de 15 m. Dans le cas d'un cours d'eau anabranche ou divagant, la continuité longitudinale est évaluée en calculant la somme des distances sans discontinuités pour chaque chenal en fonction de la distance totale de tous les chenaux.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau routier : Vectoriel (lignes)\n" \
			"-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L'ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
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
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F3 calculé pour chaque UEA."
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
	clip = processing.run("gdal:cliprasterbymasklayer", alg_params, context=context, feedback=feedback)['OUTPUT']
	# Reclassify land use. Keep anthropised and drop other landuse classes.
	CLASSES = ['300', '360', '1' # Anthropised from 300 to 360 are replaced by 1.
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
	# small search box (~50 m around the point) to limit candidates
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


def make_transect_line(center_pt: QgsPointXY, normal_angle: float, offset: float, length_m: float) -> QgsGeometry:
	"""
	Construct a perpendicular line:
	- starting at 'offset' meters from the center,
	- ending at 'offset + length_m' meters.
	"""
	start = QgsPointXY(center_pt.x() + offset * math.cos(normal_angle),
						center_pt.y() + offset * math.sin(normal_angle))
	end   = QgsPointXY(center_pt.x() + (offset + length_m) * math.cos(normal_angle),
						center_pt.y() + (offset + length_m) * math.sin(normal_angle))
	return QgsGeometry.fromPolylineXY([start, end])


def fast_intersection_status(line: QgsGeometry, band_union: QgsGeometry, engine_prepared, band_bbox):
	"""
	Length of the intersection 'line ∩ band_union' with short circuits:
	1) BBOX (very inexpensive): if no intersection of envelopes -> 0
	2) Prepared predicate (accurate & fast): if no intersection -> 0
	3) Overlay (expensive): only if we know there is a real intersection.
	"""
	if (line is None) or line.isEmpty() or (band_union is None) or band_union.isEmpty():
		return False
	# 1) Broad-phase: BBOX
	if not line.boundingBox().intersects(band_bbox):
		return False
	# 2) Narrow-phase: exact predicate on prepared geometry
	if not engine_prepared.intersects(line.constGet()):
		return False
	# 3) Overlay: we finally calculate the actual (costly) intersection
	inter = line.intersection(band_union)
	return True if (inter and not inter.isEmpty()) else False


def computeF3(intersect_perc):
	# Compute Iqm from sequence continuity
	if (intersect_perc > 0.9): # Mobility space of at least 15m on >90% of the length of the segment
		return 0
	if (intersect_perc > 0.66) and (intersect_perc <= 0.9): # Mobility space of at least 15m on ]66%-90%] of the length of the segment
		return 2
	if (intersect_perc > 0.33) and (intersect_perc <= 0.66): # Mobility space of at least 15m on ]33%-66%] of the length of the segment
		return 3
	# Mobility space of at least 15m on less than 33% of the length of the segment
	return 5
