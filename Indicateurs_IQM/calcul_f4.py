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
	QgsFeatureSink,
	QgsPointXY,
	QgsGeometry,
	QgsRectangle,
	QgsFeatureRequest,
	QgsSpatialIndex,
	QgsUnitTypes,
	QgsProcessingAlgorithm,
	QgsProcessingParameterNumber,
	QgsProcessingParameterString,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink
  )



class IndiceF4(QgsProcessingAlgorithm):

	OUTPUT = 'OUTPUT'
	DEFAULT_WIDTH_FIELD = 'Largeur_mod'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('target_pts', self.tr('Nombre de points visés par segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=200))
		self.addParameter(QgsProcessingParameterNumber('step_min', self.tr('Longueur minimale entre les transects (m)'), type=QgsProcessingParameterNumber.Double, defaultValue=10))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Check if the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
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
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		#self.UTHRESH = self.parameterAsDouble(parameters, 'thresh', context)
		# Define source stream net and other layers needed
		source = self.parameterAsSource(parameters, 'rivnet', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		target_pts = int(self.parameterAsDouble(parameters, 'target_pts', context))
		step_min = float(self.parameterAsDouble(parameters, 'step_min', context))
		# Verify the layers are created properly
		for layer, name in [[rivnet_layer, "Réseau hydrographique"], [ptref_layer, "PtRef largeur"]] :
			if layer is None or not layer.isValid() :
				raise RuntimeError(self.tr(f"Couche {name} invalide."))
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

		# Pre-indexation of PtRef per segment (for faster searching)
		model_feedback.pushInfo(self.tr('Indexation des PtRef par segment…'))
		ptref_indexes_by_seg = build_ptref_spatial_indexes(ptref_layer, seg_id_field, width_field)

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

		for current, segment in enumerate(source.getFeatures()):
			if model_feedback.isCanceled():
				return {}
			# Making geometry object of the river segment
			seg_geom = segment.geometry()
			seg_len = seg_geom.length()
			sid = segment[seg_id_field]
			# Adjusting the number of steps based on segment length
			if seg_len <= 0: # If segment length is lesser or equal to zero
				#warnings.warn("always",self.tr(f"L'UEA dont le {seg_id_field} est {sid} est de longueur inférieure ou égale à zéro ! Indice F5 mis à 4"), UserWarning)
				model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur inférieure ou égale zéro mètre ! Veuillez vérifier sa validité Indice F4 mis à 3."))
				segment.setAttributes(segment.attributes() + [0.0, 3])
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
			ptref_idx_entry = ptref_indexes_by_seg.get(sid)
			# Finding the nearest PtRef width
			if not ptref_idx_entry :
				widths = [0]
			else :
				widths = []
				for center_pt in pts :
					w = nearest_width_value_indexed(center_pt, ptref_idx_entry)
					widths.append(w)
			# Calculate relative variations
			div_distance = seg_len / len(pts)
			ratio = natural_width_ratio(widths, div_distance)
			# Compute F4
			indiceF4 = computeF4(ratio)
			#Write Index
			segment.setAttributes(segment.attributes() + [ratio, indiceF4])
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

		return {self.OUTPUT : dest_id}

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
			" Champ PtRef largeur : Chaine de caractère ('Largeur_mod' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant la largeur du chenal. Source des données : Couche PtRef largeur.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			" Nbr de points visés : nombre entier (int; 200 par défaut)\n" \
			"-> Nombre de points de transects visés par segment. Permet de meilleures performances pour réduire le nombre de transects pour les longs segments. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			" Longueur min entre transects (m) : double (10 m par défaut)\n" \
			"-> La distance minimale à avoir entre les transects (surtout utilisé pour les petits segments à la place d'utiliser le nombre des points visés). Tous les segments de longueur inférieure à long min intertransect*nbr de points visé, utiliserons cette distance entre les transects. L'augmenter augmentera la précision du calcul, mais ralentira l'exécution, en particulier pour les grands bassins versants.\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice F4 calculé pour chaque UEA."
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


def natural_width_ratio(widths, div_distance):
	# 1) Cas impossible à traiter → ratio = 1 (100% naturel)
	if len(widths) < 2:
		return 1.0
	# 2) Calcul des variations
	difs_percent = (np.array(widths[1:]) - np.array(widths[:-1])) / np.array(widths[1:])
	# 3) Cas limite : pas de variations → ratio = 1
	if difs_percent.size == 0:
		return 1.0
	# 4) Variation spécifique
	difs_specific = difs_percent * 1000 / div_distance
	# 5) Variations anormales
	unnatural_widths = np.where((difs_specific < 0) | (difs_specific > 0.2))[0].size
	# 6) Ratio final
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