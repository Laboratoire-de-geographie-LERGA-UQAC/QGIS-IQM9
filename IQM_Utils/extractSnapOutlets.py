
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
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingAlgorithm,
	QgsProcessingException,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterString,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterVectorDestination,
	QgsProperty,
	QgsProcessingUtils,
	QgsVectorLayer,
	QgsFeature,
	QgsField
)
import processing

SNAP_DISTANCE = 40		# Maximum snap distance (m) given to JensonSnapPourPoints

class ExtractAndSnapOutlets(QgsProcessingAlgorithm):
	DEFAULT_SEG_ID_FIELD= 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterRasterLayer('dem', self.tr('MNT LiDAR (10 m)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterVectorDestination('snapped_outlets', self.tr('Couche de sortie (Snapped_outlets)'), type=QgsProcessing.TypeVectorPoint, createByDefault=True, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		dem_layer = self.parameterAsRasterLayer(parameters, 'dem', context)

		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro. ! Veuillez fournir un champ identifiant du segment présent comme attribut de la couche.")
		# Verify if the layers are all in the same CRS
		layers_crs = [lyr.crs().authid() for lyr in [rivnet_layer, dem_layer]]
		if len(set(layers_crs)) > 1 : # If there's a different CRS between the layers
			return False, self.tr(f"Les SCR des couches fournises ne sont pas identiques ! Veuillez fournir des couches qui ont le même SCR.")
		return True, ''
	

	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
		results = {}

		# Making layers and parameters needed for processing
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		dem_layer = self.parameterAsRasterLayer(parameters, 'dem', context)
		output_path = self.parameterAsOutputLayer(parameters, 'snapped_outlets', context)

		# Interpolate point on line (each point inherits the attributes of its own segment)
		alg_params = {
			'DISTANCE': QgsProperty.fromExpression('if(length($geometry) > 100, length($geometry) - 30, length($geometry) * 0.9)'),
			'INPUT': parameters['stream_network'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		interp = processing.run('native:interpolatepoint', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# RasterizeStreams
		alg_params = {
			'base': parameters['dem'],
			'feature_id': False,
			'nodata': True,
			'streams': parameters['stream_network'],
			'output': QgsProcessingUtils.generateTempFilename("snapped_tmp.tif")
		}
		Rasterizestreams = processing.run('wbt:RasterizeStreams', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# JensonSnapPourPoints
		snapped_tmp = QgsProcessingUtils.generateTempFilename("snapped_tmp.shp")
		alg_params = {
			'pour_pts': interp['OUTPUT'],
			'snap_dist': SNAP_DISTANCE,
			'streams': Rasterizestreams['output'],
			'output': snapped_tmp
		}
		snapped = processing.run('wbt:JensonSnapPourPoints', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}

		# Copy the segment ID onto the snapped points BY POSITION (not by proximity).
		# WhiteboxTools writes the snapped points in the same order as the interpolated points, so the
		# n-th snapped point belongs to the n-th interpolated point, i.e. to the segment it was interpolated on.
		interp_layer = QgsProcessingUtils.mapLayerFromString(interp['OUTPUT'], context)
		snapped_layer = QgsVectorLayer(snapped['output'], 'snapped', 'ogr')
		if interp_layer is None or not interp_layer.isValid() or not snapped_layer.isValid():
			raise QgsProcessingException(self.tr("Impossible de lire les points interpolés ou les points snappés."))

		interp_feats = sorted(interp_layer.getFeatures(), key=lambda f: f.id())
		snapped_feats = sorted(snapped_layer.getFeatures(), key=lambda f: f.id())
		if len(interp_feats) != len(snapped_feats):
			raise QgsProcessingException(self.tr(
				f"Le nombre de points snappés ({len(snapped_feats)}) diffère du nombre de points interpolés ({len(interp_feats)}) : "
				"le rattachement par ordre est impossible."
			))

		# A point can only have moved by at most the snap distance (plus a cell diagonal of tolerance for the cell centre)
		pixel = max(dem_layer.rasterUnitsPerPixelX(), dem_layer.rasterUnitsPerPixelY())
		max_move = SNAP_DISTANCE + 2 * pixel
		interp_xy = [_point_xy(f.geometry()) for f in interp_feats]
		snapped_xy = [_point_xy(f.geometry()) for f in snapped_feats]
		bad = check_order(interp_xy, snapped_xy, max_move)
		if bad:
			raise QgsProcessingException(self.tr(
				f"{len(bad)} point(s) snappé(s) se trouvent à plus de {max_move:.0f} m du point interpolé de même rang (ex. rang {bad[0] + 1}). "
				"L'ordre des points n'est pas conservé par WhiteboxTools, ou les SCR du MNT et du réseau diffèrent."
			))

		# Output layer : one point per segment, geometry from the snapped point, segment ID from the interpolated point
		out_layer = QgsVectorLayer('Point', 'snapped_outlets', 'memory')
		out_layer.setCrs(rivnet_layer.crs())
		out_layer.dataProvider().addAttributes([QgsField(rivnet_layer.fields().field(seg_id_field))])
		out_layer.updateFields()
		out_feats = []
		for src, snp in zip(interp_feats, snapped_feats):
			f = QgsFeature(out_layer.fields())
			f.setGeometry(snp.geometry())
			f.setAttributes([src[seg_id_field]])
			out_feats.append(f)
		out_layer.dataProvider().addFeatures(out_feats)

		joined = processing.run('native:savefeatures', {'INPUT': out_layer, 'OUTPUT': output_path},
								context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		results['OUTPUT'] = joined
		results['snapped_outlets'] = joined

		feedback.setCurrentStep(4)
		if feedback.isCanceled():
			return {}
		return results


	def name(self):
		return 'extractandsnapoutlets'


	def displayName(self):
		return self.tr('Extraction And Snap Outlets')


	def shortHelpString(self):
		return self.tr(
			"Extrait et met ensemble les embouchures des segments.\n" \
			"Chaque point est interpolé sur son segment puis déplacé sur le cours d'eau rastérisé; l'identifiant du segment est conservé par position (un point par segment), et non par proximité, ce qui évite les doublons et les erreurs d'attribution près des confluences.\n" \
			"Paramètres\n" \
			"----------\n" \
			"MNT LiDAR (10 m) : Matriciel\n" \
			"-> Modèle numérique de terrain par levés aériennes LiDAR de résolution de 1 m rééchantilloné à 10 m pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Lidar - Modèles numériques (terrain, canopée, pente, courbe de niveau), [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie (Snapped_outlets) : Vectoriel (points)\n" \
			"-> Couche vectorielle de données ponctuelles de l'embouchure de chaque UEA (un point par segment)"
		)


	def group(self):
		return self.tr('IQM utils')


	def groupId(self):
		return 'iqmutils'


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def createInstance(self):
		return ExtractAndSnapOutlets()


# Helper functions
def _point_xy(geom):
	# First vertex of a point or multipoint geometry as (x, y); None if the geometry is empty
	if geom is None or geom.isNull() or geom.isEmpty():
		return None
	p = geom.asMultiPoint()[0] if geom.isMultipart() else geom.asPoint()
	return (p.x(), p.y())


def check_order(interp_xy, snapped_xy, max_move):
	# Returns the ranks whose snapped point is farther than max_move from the interpolated point of the same rank
	bad = []
	for i, (a, b) in enumerate(zip(interp_xy, snapped_xy)):
		if a is None or b is None or math.hypot(a[0] - b[0], a[1] - b[1]) > max_move:
			bad.append(i)
	return bad