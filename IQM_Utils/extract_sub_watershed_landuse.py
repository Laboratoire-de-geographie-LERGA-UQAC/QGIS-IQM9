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
*	any later version.															*
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


import math
import time
import numpy as np
import processing
from osgeo import gdal
from qgis.PyQt.QtCore import QCoreApplication, QMetaType
from qgis.core import (
	NULL,
	Qgis,
	QgsProcessing,
	QgsProcessingUtils,
	QgsProcessingException,
	QgsProcessingAlgorithm,
	QgsProcessingContext,
	QgsProcessingMultiStepFeedback,
	QgsProcessingOutputVectorLayer,
	QgsProcessingParameterBoolean,
	QgsProcessingParameterString,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterFeatureSink,
	QgsFeature,
	QgsFeatureSink,
	QgsField,
	QgsFields,
	QgsGeometry,
	QgsPointXY,
	QgsRectangle,
	QgsCoordinateTransform,
	QgsVectorLayer
)


# Codes du pointeur D8 de WhiteboxTools (esri_pntr = False) -> (décalage ligne, décalage colonne)
#  64  128  1      NO  N  NE
#  32   x   2      O   x   E
#  16   8   4      SO  S  SE

# D8 pointer : every cell of the raster holds ONE code that tells toward which of its 8 neighbours the water flows.
# The codes are powers of 2 (WhiteboxTools default, esri_pntr = False). Example : a cell holding 2 drains to the cell
# on its right (east), a cell holding 8 drains to the cell just below it (south).
# Necessary to find the downstream segment
# OFFSETS : each code translated into a move inside the array, as (row change, column change).
# Rows increase going DOWN (south) and columns increase going RIGHT (east), so north is -1 row and east is +1 column.
# Used in _link_nodes() : the cell at (row + dr, col + dc) is the next cell downstream.
D8_OFFSETS = {
	1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0),
	16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0)
}

# Reclassification de l'utilisation du territoire : (valeur min, valeur max, classe), bornes incluses
# Classes : 1 = forestier, 2 = agricole, 3 = anthropique, 4 = aquatique, 0 = non classé
LANDUSE_RANGES = [
	(50, 56, 1), (210, 235, 1), (501, 735, 1),		# Forestiers
	(60, 77, 1), (30, 31, 1),						# Sols nus
	(250, 261, 1), (263, 280, 1),					# Coupes de régénération
	(101, 199, 2),									# Agricoles
	(300, 360, 3),									# Anthropisé
	(20, 27, 4),									# Aquatique
	(2000, 9000, 1)									# Milieux humides
]
# The land-use codes of the raster are translated into 5 classes (see _build_landuse_lut) :
# 0 = not classified, 1 = forest, 2 = agriculture, 3 = anthropic, 4 = water. Cells of class 0 still count in the basin area.
N_CLASSES = 5				# classes 0 à 4
# The rasters are read in 'strips' of rows holding about 16 million cells each, so memory use stays bounded
# whatever the size of the watershed.
STRIP_CELLS = 2 ** 24		# nombre de cellules lues par bloc (borne la consommation de mémoire)

ATTRIBUTE_NAMES = ['watershed_area', 'forest_area', 'agri_area', 'anthro_area', 'water_area', 'land_area', 'dam_area_sum']


class Extract_sub_watershed_landuse(QgsProcessingAlgorithm):
	# Parameter identification constants
	OUTPUT = 'OUTPUT'
	OUTPUT_POLYGONS = 'OUTPUT_POLYGONS'
	EXPORT_POLYGONS = 'EXPORT_POLYGONS'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		# Main output : attribute table without geometry (one row per segment)
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Tableau de sortie (sous-BV et util. terr.)'), type=QgsProcessing.TypeVector, createByDefault=False, defaultValue=None))
		# Optional : cumulative sub-watershed polygons (slower, for quality control), written to a temporary layer
		self.addParameter(QgsProcessingParameterBoolean(self.EXPORT_POLYGONS, self.tr('Produire aussi les polygones des sous-BV (couche temporaire, plus lent)'), defaultValue=False))
		self.addOutput(QgsProcessingOutputVectorLayer(self.OUTPUT_POLYGONS, self.tr('Polygones des sous-BV'), QgsProcessing.TypeVectorPolygon))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		d8_layer = self.parameterAsRasterLayer(parameters, 'D8', context)
		landuse_layer = self.parameterAsRasterLayer(parameters, 'landuse', context)
		dams_layer = self.parameterAsVectorLayer(parameters, 'dams', context)

		# Check if the segment identifier given is present in the river network layer
		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro. ! Veuillez fournir un champ identifiant du segment présent comme attribut de la couche.")
		# Verify the type of CRS of the landuse layer
		if landuse_layer.crs().isGeographic():
			return False, self.tr("Le raster d'utilisation du territoire est en coordonnées géographiques : un SCR projeté (mètres) est requis pour calculer des superficies ! Veuillez fournir une couche un SCR adéquat.")
		# Verify if the layers are all in the same CRS
		layers_crs = [lyr.crs().authid() for lyr in [rivnet_layer, d8_layer, landuse_layer, dams_layer]]
		if len(set(layers_crs)) > 1 : # If there's a different CRS between the three layers
			return False, self.tr(f"Les SCR des couches fournises ne sont pas identiques ! Veuillez fournir des couches qui ont le même SCR.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		# Overview of the algorithm :
		#   1. Create one outlet point per stream segment and snap it onto the stream.
		#   2. Put the outlets and the dams on D8 cells. Each distinct cell is a "node".
		#   3. Run WhiteboxTools Watershed ONCE : it gives a raster of non-overlapping sub-basins, labelled by node.
		#   4. Find which node is directly downstream of each node (the upstream/downstream tree).
		#   5. Count the cells of each land-use class inside each sub-basin (numpy, one pass over the rasters).
		#   6. Add the values of the upstream nodes to each node : this gives the whole upstream basin. Write the table.
		#   7. (Optional) Build the cumulative basin polygons, for quality control only.
		feedback = QgsProcessingMultiStepFeedback(7, model_feedback)

		# Making layers and parameters needed for processing
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		d8_layer = self.parameterAsRasterLayer(parameters, 'D8', context)
		landuse_layer = self.parameterAsRasterLayer(parameters, 'landuse', context)
		dams_layer = self.parameterAsVectorLayer(parameters, 'dams', context)
		want_polygons = self.parameterAsBool(parameters, self.EXPORT_POLYGONS, context)

		if landuse_layer.crs().isGeographic():
			raise QgsProcessingException(self.tr("Le raster d'utilisation du territoire est en coordonnées géographiques : un SCR projeté (mètres) est requis pour calculer des superficies."))

		# Outputs are created first so that a bad output setting fails immediately, not after the heavy processing
		fields = _make_fields(rivnet_layer, seg_id_field)
		(sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context, fields, Qgis.WkbType.NoGeometry, rivnet_layer.sourceCrs())
		poly_sink, poly_dest_id = None, None
		if want_polygons:
			# Temporary layer created here (no output parameter to fill), loaded in the project when the algorithm ends
			poly_path = QgsProcessingUtils.generateTempFilename("sous_bv_polygones.gpkg")
			(poly_sink, poly_dest_id) = QgsProcessingUtils.createFeatureSink(poly_path, context, fields, Qgis.WkbType.MultiPolygon, d8_layer.crs())
			if poly_sink is None:
				raise QgsProcessingException(self.tr("Impossible de créer la couche temporaire des polygones."))
			context.addLayerToLoadOnCompletion(poly_dest_id, QgsProcessingContext.LayerDetails(self.tr('Polygones des sous-BV'), context.project(), self.OUTPUT_POLYGONS))

		# ------------------------------------------------------------------
		# Step 1 : extract and snap the outlets of each segment
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Extraction et mise en place des embouchures de bassin..."))
		alg_params = {
			'dem': parameters['D8'],
			'stream_network': parameters['stream_network'],
			'segment_id_field': seg_id_field,
			'snapped_outlets': QgsProcessingUtils.generateTempFilename("snappedoutlets.shp")
		}
		# Result : one point per segment (attribute = segment id), moved onto the rasterized stream so that it lies on a stream cell.
		snapped_path = processing.run('script:extractandsnapoutlets', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		snapped_layer = QgsProcessingUtils.mapLayerFromString(snapped_path, context)
		if snapped_layer is None or not snapped_layer.isValid():
			raise QgsProcessingException(self.tr("La couche des embouchures est invalide."))
		_log_time(feedback, "Embouchures", t0)
		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 2 : convert outlets and dams to D8 cells (one "node" per distinct cell)
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Association des embouchures et des barrages aux cellules du D8..."))
		# The D8 raster is read with GDAL. Its geotransform (gt) converts map coordinates into (row, col) :
		# gt[0], gt[3] = x, y of the upper-left corner ; gt[1] = pixel width ; gt[5] = pixel height (negative).
		d8_ds = gdal.Open(d8_layer.source())
		if d8_ds is None:
			raise QgsProcessingException(self.tr("Impossible d'ouvrir le raster D8."))
		gt = d8_ds.GetGeoTransform()
		ncols, nrows = d8_ds.RasterXSize, d8_ds.RasterYSize
		if gt[2] != 0 or gt[4] != 0:
			raise QgsProcessingException(self.tr("Les rasters avec rotation ne sont pas supportés."))

		# A "node" is a D8 cell that holds at least one outlet and/or one dam. Several segments or dams can fall in the same cell :
		# they then share the same node (and therefore the same result). Everything downstream works on nodes, not on points.
		nodes = _NodeSet()

		# Outlets (the shapefile may truncate long field names to 10 characters)
		snapped_names = [f.name() for f in snapped_layer.fields()]
		id_field = seg_id_field if seg_id_field in snapped_names else next((nm for nm in snapped_names if nm == seg_id_field[:10]), None)
		if id_field is None:
			raise QgsProcessingException(self.tr(f"Le champ '{seg_id_field}' est absent de la couche des embouchures."))
		# Transformation from the CRS of the outlets to the CRS of the D8 raster (None when they are the same)
		to_d8 = _make_transform(snapped_layer.crs(), d8_layer.crs(), context)
		n_outlets_skipped = 0
		# Each outlet point -> (row, col) of its D8 cell -> node. The segment id is recorded on that node.
		for feat in snapped_layer.getFeatures():
			seg = feat[id_field]
			pt = _first_point(feat.geometry())
			if pt is None or seg is None or seg == NULL:
				n_outlets_skipped += 1
				continue
			if to_d8 is not None:
				pt = to_d8.transform(pt)
			cell = _xy_to_cell(pt.x(), pt.y(), gt, ncols, nrows)
			if cell is None:
				n_outlets_skipped += 1
				continue
			nodes.seg_ids[nodes.get(*cell)].append(seg)

		# Dams : exact duplicate points are removed (as before); distinct dams in the same cell are each counted
		n_dams = 0
		n_dams_skipped = 0
		if dams_layer is not None and dams_layer.featureCount() > 0:
			to_d8_dams = _make_transform(dams_layer.crs(), d8_layer.crs(), context)
			seen_xy = set()
			# Dams are counted per node. Two dams at exactly the same x, y are the same dam listed twice and are counted once.
			for feat in dams_layer.getFeatures():
				pt = _first_point(feat.geometry())
				if pt is None:
					continue
				key = (pt.x(), pt.y())
				if key in seen_xy:
					continue
				seen_xy.add(key)
				if to_d8_dams is not None:
					pt = to_d8_dams.transform(pt)
				cell = _xy_to_cell(pt.x(), pt.y(), gt, ncols, nrows)
				if cell is None:
					n_dams_skipped += 1
					continue
				nodes.dam_count[nodes.get(*cell)] += 1
				n_dams += 1
			feedback.pushInfo(self.tr(f"{n_dams} barrage(s) retenu(s), {n_dams_skipped} hors du raster D8."))
		else:
			feedback.pushInfo(self.tr("Aucun barrage dans la couche de barrages. Aire des barrages par BV (dam_area_sum) mise à zéro (0)."))
		if n_outlets_skipped:
			feedback.pushInfo(self.tr(f"{n_outlets_skipped} embouchure(s) ignorée(s) (géométrie ou identifiant absent, ou hors du raster D8)."))
		# Diagnostic : the same segment id appearing on several outlet points gives several output rows
		id_count = {}
		for ids in nodes.seg_ids:
			for s in ids:
				id_count[s] = id_count.get(s, 0) + 1
		duplicated = {s: c for s, c in id_count.items() if c > 1}
		feedback.pushInfo(self.tr(f"{snapped_layer.featureCount()} point(s) d'embouchure lus, {len(id_count)} identifiant(s) distinct(s)."))
		if duplicated:
			shown = ', '.join(f"{s} (x{c})" for s, c in list(duplicated.items())[:10])
			feedback.reportError(self.tr(f"{len(duplicated)} identifiant(s) de segment présent(s) sur plusieurs embouchures : {shown}. Ils produiront plusieurs lignes en sortie."), False)
		if not nodes.cells:
			raise QgsProcessingException(self.tr("Aucune embouchure ou barrage n'a pu être placé sur le raster D8."))
		_log_time(feedback, f"{len(nodes.cells)} cellules d'exutoire", t0)
		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 3 : ONE watershed run for all outlets and dams (non-nested inter-basins)
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Délimitation des sous-bassins..."))
		# Pour points are written at the centre of their D8 cell so they always fall in the intended cell
		# Build the pour points of the watershed tool : one point per node, placed at the CENTRE of its D8 cell.
		# The attribute "node" (node index + 1) becomes the label, i.e. the pixel value, of the sub-basin in the output raster.
		pp_layer = QgsVectorLayer('Point?field=node:integer', 'pour_points', 'memory')
		pp_layer.setCrs(d8_layer.crs())
		pp_feats = []
		for i, (row, col) in enumerate(nodes.cells):
			f = QgsFeature(pp_layer.fields())
			f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(gt[0] + (col + 0.5) * gt[1], gt[3] + (row + 0.5) * gt[5])))
			f.setAttributes([i + 1])
			pp_feats.append(f)
		pp_layer.dataProvider().addFeatures(pp_feats)
		pp_path = QgsProcessingUtils.generateTempFilename("pour_points.shp")
		processing.run('native:savefeatures', {'INPUT': pp_layer, 'OUTPUT': pp_path}, context=context, feedback=None, is_child_algorithm=True)

		# wbt:Watershed gives each cell the label of the node it drains to FIRST (the nearest outlet downstream).
		# The labelled areas therefore do NOT overlap : each one is only the part of the basin between a node and the nodes just
		# upstream of it (an "inter-basin"). The complete upstream basin of a node is rebuilt later by adding up the
		# upstream inter-basins (steps 4 and 6).
		label_path = QgsProcessingUtils.generateTempFilename("interbasins.tif")
		alg_params = {
			'd8_pntr': parameters['D8'],
			'pour_pts': pp_path,
			'esri_pntr': False,
			'output': label_path
		}
		label_path = processing.run('wbt:Watershed', alg_params, context=context, feedback=None, is_child_algorithm=True).get('output', label_path)
		label_ds = gdal.Open(label_path)
		if label_ds is None:
			raise QgsProcessingException(self.tr("Impossible d'ouvrir le raster de sous-bassins produit par WhiteboxTools."))
		if (label_ds.RasterXSize, label_ds.RasterYSize) != (ncols, nrows):
			raise QgsProcessingException(self.tr("Le raster de sous-bassins n'a pas la même taille que le D8."))
		_log_time(feedback, "Watershed (WBT)", t0)
		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 4 : upstream/downstream topology between nodes
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Détermination de la topologie amont-aval..."))
		# node_label[i] : label of node i in the raster ; parent[i] : index of the node directly downstream of i (-1 if none).
		# n_bad : nodes whose downstream cell still belongs to their own basin (suggests a wrong D8 encoding).
		node_label, parent, n_bad = _link_nodes(d8_ds.GetRasterBand(1), label_ds.GetRasterBand(1), ncols, nrows, nodes.cells)
		valid = node_label > 0
		n_valid = int(valid.sum())
		if n_valid == 0:
			raise QgsProcessingException(self.tr("Aucun exutoire n'a obtenu de bassin : vérifier que les points sont sur le réseau et dans l'emprise du D8."))
		if n_valid < len(valid):
			feedback.reportError(self.tr(f"{len(valid) - n_valid} exutoire(s) sans bassin (hors domaine du D8) : ignoré(s)."), False)
		if n_bad:
			msg = self.tr(f"{n_bad} exutoire(s) dont la cellule aval appartient à leur propre bassin : l'encodage du pointeur D8 est-il bien celui de WhiteboxTools (esri_pntr = False) ?")
			if n_bad > 0.05 * n_valid:
				raise QgsProcessingException(msg)
			feedback.reportError(msg, False)
		# order : the nodes sorted so that every node comes AFTER all of the nodes upstream of it (headwaters first).
		order = _topological_order(parent, valid)
		_log_time(feedback, "Topologie", t0)
		feedback.setCurrentStep(4)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 5 : land-use histogram per inter-basin (one pass over the rasters, by strips)
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Calcul de l'aire d'utilisation du territoire par sous-bassin..."))
		# The sub-basin raster and the land-use raster do not always share the same grid. If they differ, the labels are resampled
		# (nearest neighbour) onto the land-use grid, restricted to the window that overlaps the basin.
		lu_ds = gdal.Open(landuse_layer.source())
		if lu_ds is None:
			raise QgsProcessingException(self.tr("Impossible d'ouvrir le raster d'utilisation du territoire."))
		same_crs = d8_layer.crs() == landuse_layer.crs()
		if same_crs:
			rect_to_landuse_crs = lambda r: r
		else:
			xform = QgsCoordinateTransform(d8_layer.crs(), landuse_layer.crs(), context.transformContext())
			def rect_to_landuse_crs(r):
				b = xform.transformBoundingBox(QgsRectangle(r[0], r[1], r[2], r[3]))
				return (b.xMinimum(), b.yMinimum(), b.xMaximum(), b.yMaximum())
		aligned_ds, col0, row0, width, height, same_grid = _align_labels_to_landuse(
			label_ds, lu_ds, d8_layer.crs().toWkt(), landuse_layer.crs().toWkt(), same_crs, rect_to_landuse_crs
		)
		lu_gt = lu_ds.GetGeoTransform()
		# Area of one land-use cell in m2 (e.g. 10 m x 10 m = 100 m2)
		cell_area = abs(lu_gt[1] * lu_gt[5])
		# Sanity check : warn if the land-use raster covers less than 99 % of the basin area
		if not same_grid and same_crs:
			# Warn if the land-use raster does not cover the whole basin
			area_d8 = _count_labeled_cells(label_ds.GetRasterBand(1), ncols, nrows) * abs(gt[1] * gt[5])
			area_lu = _count_labeled_cells(aligned_ds.GetRasterBand(1), width, height) * cell_area
			if area_d8 > 0 and (area_d8 - area_lu) / area_d8 > 0.01:
				feedback.reportError(self.tr(f"Le raster d'utilisation du territoire ne couvre pas tout le bassin ({100 * (area_d8 - area_lu) / area_d8:.1f} % de la superficie manquante). Les superficies seront sous-estimées."), False)
		# hist[label, class] = number of cells of that land-use class inside that sub-basin (see _label_class_histogram).
		hist = _label_class_histogram(
			aligned_ds.GetRasterBand(1), lu_ds.GetRasterBand(1), col0, row0, width, height,
			int(node_label.max()), _build_landuse_lut(), feedback
		)
		_log_time(feedback, "Histogramme d'utilisation du territoire", t0)
		feedback.setCurrentStep(5)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 6 : accumulate downstream and write the table
		# ------------------------------------------------------------------
		t0 = time.perf_counter()
		feedback.setProgressText(self.tr("Cumul vers l'aval et écriture du tableau..."))
		# Add the values of every upstream node to each node : the result is, for each node, the total over its WHOLE upstream basin.
		# Cell counts are converted to m2 (x cell area) and the dam areas are accumulated the same way.
		stats = _node_statistics(hist, node_label, parent, order, nodes.dam_count, cell_area)
		# One output row per segment. Segments that share a node get identical values.
		n_rows = 0
		for i in order:
			for seg in nodes.seg_ids[i]:
				feat = QgsFeature(fields)
				feat.setAttributes(_attribute_row(seg, i, stats, cell_area))
				sink.addFeature(feat, QgsFeatureSink.FastInsert)
				n_rows += 1
		feedback.pushInfo(self.tr(f"{n_rows} segment(s) écrits sur {rivnet_layer.featureCount()} dans le réseau hydrographique."))
		_log_time(feedback, "Cumul et écriture", t0)
		feedback.setCurrentStep(6)
		if feedback.isCanceled():
			return {}

		# ------------------------------------------------------------------
		# Step 7 (optional) : cumulative polygons for quality control
		# ------------------------------------------------------------------
		if want_polygons:
			t0 = time.perf_counter()
			feedback.setProgressText(self.tr("Construction des polygones cumulatifs (optionnel)..."))
			# Polygons are built only on request (slow) : see _cumulative_polygons().
			geoms = _cumulative_polygons(label_path, node_label, parent, order, context, feedback)
			for i in order:
				if geoms.get(i) is None:
					continue
				for seg in nodes.seg_ids[i]:
					feat = QgsFeature(fields)
					feat.setAttributes(_attribute_row(seg, i, stats, cell_area))
					feat.setGeometry(geoms[i])
					poly_sink.addFeature(feat, QgsFeatureSink.FastInsert)
			_log_time(feedback, "Polygones", t0)
		feedback.setCurrentStep(7)

		# Closing datasets
		d8_ds = label_ds = lu_ds = aligned_ds = None

		feedback.setProgressText(self.tr('\tProcessus terminé !'))
		results = {self.OUTPUT: dest_id}
		if want_polygons:
			results[self.OUTPUT_POLYGONS] = poly_dest_id
		return results


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def name(self):
		return 'extract_subwatershed'


	def displayName(self):
		return self.tr("Extract sous-BV et landuse (A1 et A2)")


	def group(self):
		return self.tr('IQM utils')


	def groupId(self):
		return 'iqmutils'


	def shortHelpString(self):
		return self.tr(
			"Extraction des sous bassins versants et utilisation du territoire\n Script préparatoire pour les indices A1 et A2 qui calcule, pour chaque segment du réseau hydrographique, la superficie de son bassin versant cumulatif (tout ce qui draine vers son exutoire), la superficie de chaque classe d'utilisation du territoire et la somme des superficies de drainage des barrages situés dans ce bassin.\n" \
			"Les bassins sont délimités en une seule passe (sous-bassins), puis cumulés vers l'aval selon la topologie du pointeur D8. Les polygones ne sont produits que sur demande.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. Source des données : Couche réseau hydrographique.\n" \
			"WBT D8 Pointer: Matriciel\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools, encodage par défaut). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire qui seront reclassées pour les classes forestière, agricole, anthropique et aquatique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Tableau de sortie : Table sans géométrie\n" \
			"-> Une ligne par segment : watershed_area, forest_area, agri_area, anthro_area, water_area, land_area, dam_area_sum (m²).\n" \
			"Produire aussi les polygones des sous-BV : Booléen (décoché par défaut)\n" \
			"-> Si coché, ajoute une couche temporaire de polygones (bassins cumulatifs de chaque segment) pour le contrôle de la qualité. Plus lent : à n'activer que si nécessaire. Pour la conserver, l'exporter depuis le projet."
		)


	def createInstance(self):
		return Extract_sub_watershed_landuse()


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
class _NodeSet:
	"""Distinct D8 cells that act as outlets (segment outlets and/or dams)."""
	def __init__(self):
		self.index = {}			# (row, col) -> node index
		self.cells = []			# node index -> (row, col)
		self.seg_ids = []		# node index -> list of segment ids that share this cell
		self.dam_count = []		# node index -> number of dams in this cell

	def get(self, row, col):
		i = self.index.get((row, col))
		if i is None:
			i = len(self.cells)
			self.index[(row, col)] = i
			self.cells.append((row, col))
			self.seg_ids.append([])
			self.dam_count.append(0)
		return i


def _log_time(feedback, label, t0):
	feedback.pushInfo(f"[TEMPS EXECUTION] {label} : {time.perf_counter() - t0:.1f} s")


def _make_fields(rivnet_layer, seg_id_field):
	fields = QgsFields()
	fields.append(QgsField(rivnet_layer.fields().field(seg_id_field)))
	for name in ATTRIBUTE_NAMES:
		fields.append(QgsField(name, QMetaType.Double))
	return fields


def _make_transform(src_crs, dst_crs, context):
	if src_crs == dst_crs:
		return None
	return QgsCoordinateTransform(src_crs, dst_crs, context.transformContext())


def _first_point(geom):
	if geom is None or geom.isNull() or geom.isEmpty():
		return None
	if geom.isMultipart():
		pts = geom.asMultiPoint()
		return pts[0] if pts else None
	return geom.asPoint()


def _xy_to_cell(x, y, gt, ncols, nrows):
	# Map coordinates -> pixel indices : distance from the upper-left corner divided by the pixel size, rounded down.
	# gt[5] is negative (y decreases going down the raster), so the division gives a positive row index.
	col = int(math.floor((x - gt[0]) / gt[1]))
	row = int(math.floor((y - gt[3]) / gt[5]))
	if 0 <= col < ncols and 0 <= row < nrows:
		return row, col
	return None


def _build_landuse_lut():
	# Lookup table : raw land-use value -> class (0 when not listed in LANDUSE_RANGES)
	# lut[code] = class. The array is as long as the largest code, so a raw land-use code can be used directly as an index.
	# Example : lut[120] == 2 (agriculture). Codes that are not in any range stay 0.
	lut = np.zeros(max(hi for _, hi, _ in LANDUSE_RANGES) + 1, dtype=np.uint8)
	# Fill every code of each range (bounds included) with its class
	for lo, hi, cls in LANDUSE_RANGES:
		lut[lo:hi + 1] = cls
	return lut


def _read_window3(band, row, col, ncols, nrows):
	# Reads the 3x3 window centred on (row, col); cells outside the raster are -1
	# 3x3 window initialised to -1 ("outside the raster"), then filled with the part that really exists
	# (cells on the edge of the raster have fewer than 8 neighbours). This reads a cell and its neighbours without loading the raster.
	out = np.full((3, 3), -1.0)
	r0, c0 = row - 1, col - 1
	rs, cs = max(r0, 0), max(c0, 0)
	re, ce = min(r0 + 3, nrows), min(c0 + 3, ncols)
	if re <= rs or ce <= cs:
		return out
	data = band.ReadAsArray(cs, rs, ce - cs, re - rs)
	out[rs - r0:re - r0, cs - c0:ce - c0] = data
	return out


def _link_nodes(d8_band, label_band, ncols, nrows, cells):
	"""
	For each node, finds its label in the inter-basin raster and its downstream node.
	The downstream node is the label found one D8 step downstream of the node's cell:
	inter-basin labels are assigned by the nearest outlet downstream, so that label IS the next node.
	Returns (node_label, parent, n_bad) ; parent[i] = -1 for a root, node_label[i] = 0 when the node has no basin.
	"""
	n = len(cells)
	# node_label[i] : sub-basin label found at the node's own cell
	# down_label[i] : sub-basin label found ONE D8 step downstream of that cell
	node_label = np.zeros(n, dtype=np.int64)
	down_label = np.zeros(n, dtype=np.int64)
	for i, (row, col) in enumerate(cells):
		# Sub-basin labels around the node's cell : lw[1, 1] is the cell itself, the 8 others are its neighbours
		lw = _read_window3(label_band, row, col, ncols, nrows)
		lab = lw[1, 1]
		if not lab > 0:
			continue
		node_label[i] = int(lab)
		# D8 code of the cell : toward which neighbour does the water flow?
		ptr = _read_window3(d8_band, row, col, ncols, nrows)[1, 1]
		if np.isfinite(ptr) and int(ptr) in D8_OFFSETS:
			# Offset of that neighbour. The centre of the 3x3 window is (1, 1), so the downstream cell is at (1 + dr, 1 + dc).
			# The label found there is the next node downstream : the label of an inter-basin IS the node it drains to.
			dr, dc = D8_OFFSETS[int(ptr)]
			nl = lw[1 + dr, 1 + dc]
			if nl > 0:
				down_label[i] = int(nl)

	# Reverse lookup (label -> node index) to turn a downstream label into a node
	label_to_node = {}
	for i in range(n):
		lab = int(node_label[i])
		if lab > 0:
			if lab in label_to_node:
				raise QgsProcessingException(f"Deux exutoires partagent la même étiquette de bassin ({lab}).")
			label_to_node[lab] = i

	# parent[i] = node directly downstream of node i (-1 for an outlet of the whole network).
	# A node whose downstream label is its own label is counted in n_bad and left without parent.
	parent = [-1] * n
	n_bad = 0
	for i in range(n):
		dl = int(down_label[i])
		if dl > 0:
			p = label_to_node.get(dl, -1)
			if p == i:
				n_bad += 1
				p = -1
			parent[i] = p
	return node_label, parent, n_bad


def _topological_order(parent, valid):
	# Order in which every node comes after all of its upstream nodes (leaves first)
	n = len(parent)
	# pending[p] = number of upstream nodes of p that are not yet placed in the order
	pending = [0] * n
	for i in range(n):
		if valid[i] and parent[i] >= 0:
			pending[parent[i]] += 1
	# Start with the headwater nodes (nothing upstream). A node is released once ALL of its upstream nodes have been placed.
	stack = [i for i in range(n) if valid[i] and pending[i] == 0]
	order = []
	while stack:
		i = stack.pop()
		order.append(i)
		p = parent[i]
		if p >= 0:
			pending[p] -= 1
			if pending[p] == 0:
				stack.append(p)
	if len(order) != int(np.count_nonzero(valid)):
		raise QgsProcessingException("La topologie amont-aval contient un cycle : le pointeur D8 est incohérent.")
	return order


def _accumulate(order, parent, own):
	# Adds each node's total to its downstream node (order guarantees upstream nodes are processed first)
	# cum starts as each node's own values. Going from the headwaters toward the outlet, each node hands its running total
	# to its downstream node. Example A -> B -> C : cum[B] += cum[A], then cum[C] += cum[B], so C ends up with A + B + C.
	cum = own.copy()
	for i in order:
		p = parent[i]
		if p >= 0:
			cum[p] += cum[i]
	return cum


def _node_statistics(hist, node_label, parent, order, dam_count, cell_area):
	n = len(parent)
	# own[i] = cell counts of the node's own inter-basin only (copied from the histogram row of its label)
	own = np.zeros((n, N_CLASSES), dtype=np.int64)
	idx = np.flatnonzero(node_label > 0)
	own[idx] = hist[node_label[idx]]
	# cum[i] = cell counts over the whole upstream basin of node i, for each class
	cum = _accumulate(order, parent, own)
	# Total basin area in m2 = all the cells (every class, including class 0) x area of one cell
	area_total = cum.sum(axis=1) * cell_area
	# Each dam contributes the drainage area of its own basin ; the sum is taken over all dams upstream (and in) each basin
	# The drainage area of a dam is the full basin area of its node. dam_own[i] = (dams in node i) x (basin area of node i).
	# Accumulating it downstream gives, for each node, the SUM of the drainage areas of all the dams upstream (nested dams add up).
	dam_own = (np.asarray(dam_count, dtype=np.float64) * area_total)[:, None]
	dam_sum = _accumulate(order, parent, dam_own)[:, 0]
	return {'cum': cum, 'area_total': area_total, 'dam_sum': dam_sum}


def _attribute_row(seg, i, stats, cell_area):
	cum = stats['cum'][i]
	# Classes : 1 = forest, 2 = agriculture, 3 = anthropic, 4 = water. land_area = forest + agri + anthro (water excluded).
	forest = float(cum[1]) * cell_area
	agri = float(cum[2]) * cell_area
	anthro = float(cum[3]) * cell_area
	water = float(cum[4]) * cell_area
	return [seg, float(stats['area_total'][i]), forest, agri, anthro, water, forest + agri + anthro, float(stats['dam_sum'][i])]


def _label_class_histogram(label_band, lu_band, col0, row0, width, height, max_label, lut, feedback):
	"""
	Counts cells per (inter-basin label, land-use class) in ONE pass over both rasters, by strips.
	label_band and lu_band must be aligned ; (col0, row0) is the window origin in the land-use raster.
	Returns an array [max_label + 1, N_CLASSES] of cell counts.
	"""
	# One counter per (label, class) pair, stored in a flat 1-D array. The pair is encoded in ONE integer key :
	#   key = label * N_CLASSES + class        e.g. label 3, class 2 -> key 17
	# and can be decoded with  label = key // 5,  class = key % 5.
	size = (max_label + 1) * N_CLASSES
	hist = np.zeros(size, dtype=np.int64)
	# Largest raw code the lookup table can translate ; larger codes are treated as class 0
	lut_max = len(lut) - 1
	rows_per_strip = max(1, STRIP_CELLS // width)
	for y in range(0, height, rows_per_strip):
		if feedback.isCanceled():
			break
		h = min(rows_per_strip, height - y)
		# Read one strip (h rows over the full width) of the sub-basin labels instead of the whole raster
		lab = label_band.ReadAsArray(0, y, width, h)
		# Only the cells that belong to a sub-basin matter (label 0 = outside every basin)
		valid = lab > 0
		if valid.any():
			# Land-use codes of the same cells (same strip, shifted by the window origin col0, row0).
			# Indexing with the boolean mask flattens them to a 1-D array aligned with lab[valid].
			lu_v = lu_band.ReadAsArray(col0, row0 + y, width, h)[valid]
			# Translate raw codes into classes with the lookup table, for ALL the cells at once (no Python loop).
			# Codes that are unknown or out of range stay class 0.
			cls_v = np.zeros(lu_v.shape, dtype=np.uint8)
			ok = (lu_v >= 0) & (lu_v <= lut_max)
			cls_v[ok] = lut[lu_v[ok].astype(np.int64)]
			# One key per cell : (sub-basin label, class) packed in a single integer
			keys = lab[valid].astype(np.int64) * N_CLASSES + cls_v
			keys = keys[keys < size]
			# bincount counts how many times each key appears = number of cells per (label, class). Summed over all strips.
			hist += np.bincount(keys, minlength=size)
		feedback.setProgress(100.0 * (y + h) / height)
	# Back to a 2-D table : one row per label, one column per class (hist[3, 2] = cells of class 2 inside sub-basin 3)
	return hist.reshape(max_label + 1, N_CLASSES)


def _count_labeled_cells(band, width, height):
	total = 0
	rows_per_strip = max(1, STRIP_CELLS // width)
	for y in range(0, height, rows_per_strip):
		h = min(rows_per_strip, height - y)
		total += int(np.count_nonzero(band.ReadAsArray(0, y, width, h) > 0))
	return total


def _align_labels_to_landuse(label_ds, lu_ds, label_srs_wkt, lu_srs_wkt, same_crs, rect_to_landuse_crs):
	"""
	Puts the inter-basin raster on the land-use grid (nearest neighbour), restricted to the window of the
	land-use raster that overlaps the basin. If the grids are already identical, nothing is resampled.
	Returns (aligned dataset, col0, row0, width, height, same_grid), where (col0, row0, width, height) is the window in the land-use raster.
	"""
	lgt = label_ds.GetGeoTransform()
	lw, lh = label_ds.RasterXSize, label_ds.RasterYSize
	ugt = lu_ds.GetGeoTransform()
	uw, uh = lu_ds.RasterXSize, lu_ds.RasterYSize

	# Same grid = same CRS, same size and same geotransform (within a tiny tolerance) : no resampling needed
	tol = 1e-6 * abs(ugt[1])
	same_grid = same_crs and (lw, lh) == (uw, uh) and all(abs(a - b) <= tol for a, b in zip(lgt, ugt))
	if same_grid:
		return label_ds, 0, 0, uw, uh, True

	# Basin raster extent expressed in the land-use CRS, then converted to a pixel window of the land-use raster
	xmin, ymax = lgt[0], lgt[3]
	xmax, ymin = lgt[0] + lw * lgt[1], lgt[3] + lh * lgt[5]
	xmin, ymin, xmax, ymax = rect_to_landuse_crs((xmin, ymin, xmax, ymax))
	px, py = ugt[1], ugt[5]		# py is negative for north-up rasters
	col0 = max(0, int(math.floor((xmin - ugt[0]) / px)))
	col1 = min(uw, int(math.ceil((xmax - ugt[0]) / px)))
	row0 = max(0, int(math.floor((ymax - ugt[3]) / py)))
	row1 = min(uh, int(math.ceil((ymin - ugt[3]) / py)))
	if col1 <= col0 or row1 <= row0:
		raise QgsProcessingException("Le raster d'utilisation du territoire ne recouvre pas le bassin versant.")
	width, height = col1 - col0, row1 - row0
	bounds = (ugt[0] + col0 * px, ugt[3] + row1 * py, ugt[0] + col1 * px, ugt[3] + row0 * py)
	src_nodata = label_ds.GetRasterBand(1).GetNoDataValue()
	# gdal.Warp into an in-memory VRT : resamples the labels onto the land-use grid. Nearest neighbour keeps the labels whole numbers.
	warp_kwargs = dict(
		format='VRT', outputBounds=bounds, xRes=abs(px), yRes=abs(py), resampleAlg='near',
		srcSRS=label_srs_wkt, dstSRS=lu_srs_wkt, dstNodata=0
	)
	if src_nodata is not None:
		warp_kwargs['srcNodata'] = src_nodata
	aligned = gdal.Warp('', label_ds, **warp_kwargs)
	if aligned is None or (aligned.RasterXSize, aligned.RasterYSize) != (width, height):
		raise QgsProcessingException("Échec de l'alignement du raster d'inter-bassins sur la grille d'utilisation du territoire.")
	return aligned, col0, row0, width, height, False


def _cumulative_polygons(label_path, node_label, parent, order, context, feedback):
	"""
	Builds the cumulative basin polygon of each node : polygonizes the inter-basin raster ONCE, then
	unions each node's polygon with the cumulative polygons of its upstream nodes (leaves first).
	Returns {node index: QgsGeometry (multipart)}.
	"""
	poly_path = QgsProcessingUtils.generateTempFilename("interbasins_poly.gpkg")
	processing.run('gdal:polygonize', {
		'BAND': 1,
		'EIGHT_CONNECTEDNESS': True,
		'EXTRA': '',
		'FIELD': 'DN',
		'INPUT': label_path,
		'OUTPUT': poly_path
	}, context=context, feedback=None, is_child_algorithm=True)
	layer = QgsVectorLayer(poly_path, 'interbasins', 'ogr')
	# parts[label] = polygons of that inter-basin (one label can give several polygons)
	parts = {}
	for feat in layer.getFeatures():
		parts.setdefault(int(feat['DN']), []).append(QgsGeometry(feat.geometry()))

	pending = {}		# node index -> cumulative geometries of its upstream nodes
	geoms = {}
	total = len(order)
	for k, i in enumerate(order):
		if feedback.isCanceled():
			break
		# Cumulative polygon of a node = its own inter-basin polygons + the cumulative polygons of its upstream nodes, merged (union)
		pieces = parts.get(int(node_label[i]), []) + pending.pop(i, [])
		g = QgsGeometry.unaryUnion(pieces) if pieces else None
		if g is not None and not g.isNull():
			g.convertToMultiType()
			geoms[i] = g
			if parent[i] >= 0:
				pending.setdefault(parent[i], []).append(g)
		feedback.setProgress(100.0 * (k + 1) / total)
	return geoms