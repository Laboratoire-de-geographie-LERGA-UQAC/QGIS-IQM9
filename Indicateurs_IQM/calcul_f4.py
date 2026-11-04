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
from qgis.PyQt.QtCore import QMetaType, QCoreApplication
from qgis.core import (
	QgsField,
	QgsProcessing,
	QgsFeatureSink,
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
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None, optional=False))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None, optional=False))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterNumber('seuil_km', self.tr('Seuil de variation spécifique de largeur (fraction par km)'), type=QgsProcessingParameterNumber.Double, defaultValue=0.2, minValue=0.0))
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
		if rivnet_layer.crs() != ptref_layer.crs():
			return False, self.tr("Les couches de réseau hydro et de PtRef doivent être dans le même CRS! Veuillez reprojeter l'une des deux couches.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		# Define source stream net and other layers needed
		source = self.parameterAsSource(parameters, 'rivnet', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'rivnet', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		seuil_km = float(self.parameterAsDouble(parameters, 'seuil_km', context))
		# Verify the layers are created properly
		for layer, name in [[rivnet_layer, "Réseau hydrographique"], [ptref_layer, "PtRef largeur"]] :
			if layer is None or not layer.isValid() :
				raise RuntimeError(self.tr(f"Couche {name} invalide."))
		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Nb_PtRef", QMetaType.Int))
		sink_fields.append(QgsField("Pourc_long_alt", QMetaType.Double, len=10, prec=2))
		sink_fields.append(QgsField("Indice F4", QMetaType.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		# Group PtRef by segment (only the PtRef of the UEA itself are used)
		model_feedback.pushInfo(self.tr('Regroupement des PtRef par segment…'))
		ptref_by_seg = group_ptref_by_segment(ptref_layer, seg_id_field)
 
		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))
		nb_null = 0
 
		for current, segment in enumerate(source.getFeatures()):
			if model_feedback.isCanceled():
				return {}
			seg_geom = segment.geometry()
			sid = segment[seg_id_field]
			seg_len = seg_geom.length() if seg_geom and not seg_geom.isEmpty() else 0.0
 
			nb_ptref = 0
			pourc_alt = None
			indiceF4 = None
 
			if seg_len <= 0:
				model_feedback.pushInfo(self.tr(f"ATTENTION : Le segment ({seg_id_field} : {sid}) est de longueur nulle ou invalide ! Indice F4 mis à NULL."))
			else:
				# Width profile along the UEA (position in m, width), ordered upstream -> downstream
				profile = ptref_profile(seg_geom, ptref_by_seg.get(sid, []), width_field)
				nb_ptref = len(profile)
				ratio = altered_length_ratio(profile, seuil_km)
				if ratio is not None:
					pourc_alt = round(100.0 * ratio, 2)
					indiceF4 = computeF4(ratio)
 
			if indiceF4 is None:
				nb_null += 1
 
			# Write attributes (None -> NULL)
			segment.setAttributes(segment.attributes() + [nb_ptref, pourc_alt, indiceF4])
			sink.addFeature(segment, QgsFeatureSink.FastInsert)
 
			# Increments the progress bar
			model_feedback.setProgress(int(100 * (current + 1) / max(1, total_features)))
 
		if nb_null:
			model_feedback.pushInfo(self.tr(f"\t {nb_null} UEA avec moins de 2 PtRef valides (ou de longueur nulle) : Indice F4 mis à NULL."))
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
			"Calcule de l'indice F4 afin d'évaluer l’hétérogénéité naturelle des unités géomorphologiques liée à ces processus présents dans le lit mineur en mesurant la continuité dans la variabilité naturelle de la largeur du lit mineur.\n" \
			"Les points de référence (PtRef) de chaque UEA sont ordonnés de l'amont vers l'aval. Pour chaque paire de PtRef consécutifs, la variation relative de largeur est ramenée au kilomètre à l'aide de la distance réelle entre les deux points. Un intervalle est jugé anormal si la largeur diminue vers l'aval ou si son augmentation dépasse le seuil donné. L'indice est déterminé par la proportion de la longueur de l'UEA couverte par des intervalles anormaux : 0 = altération sur 10 % ou moins de la longueur; 1 = 10 à 34 %; 2 = 34 à 67 %; 3 = plus de 67 %.\n" \
			"Les UEA ayant moins de deux PtRef valides ne peuvent pas être évalués : l'indice F4 y est mis à NULL.\n" \
			"Paramètres\n" \
			"----------\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ PtRef largeur : Chaine de caractère ('Largeur_mod' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant la largeur du chenal. Source des données : Couche PtRef largeur.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Les lignes doivent être orientées de l'amont vers l'aval. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			" Seuil de variation spécifique : double (0,2 par défaut)\n" \
			"-> Augmentation relative maximale de la largeur par kilomètre considérée comme naturelle (0,2 = 20 % par km).\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec, pour chaque UEA, le nombre de PtRef valides (Nb_PtRef), le pourcentage de longueur altérée (Pourc_long_alt) et le score de l'indice F4 (NULL si non évaluable)."
		)


def is_metric_crs(crs):
	# True if the distance unit of the CRS is the meter
	return crs.mapUnits() == QgsUnitTypes.DistanceMeters
 
 
def group_ptref_by_segment(ptref_layer, seg_id_field: str) -> dict:
	"""Returns {sid: [QgsFeature, ...]} for all PtRef of the layer."""
	seg_to_features = {}
	for pf in ptref_layer.getFeatures():
		seg_to_features.setdefault(pf[seg_id_field], []).append(pf)
	return seg_to_features
 
 
def ptref_profile(seg_geom, ptref_feats, width_field: str) -> list:
	"""
	Builds the width profile of a UEA.
	Each PtRef is projected on the line (lineLocatePoint) to get its position
	in meters from the start of the line (upstream).
	Returns [(position_m, width)] sorted upstream -> downstream.
	PtRef with an invalid, null or non-positive width are ignored.
	"""
	if not ptref_feats:
		return []
	line = seg_geom
	if seg_geom.isMultipart():
		merged = seg_geom.mergeLines()
		if merged and not merged.isEmpty():
			line = merged
	profile = []
	for pf in ptref_feats:
		g = pf.geometry()
		if not g or g.isEmpty():
			continue
		try:
			w = float(pf[width_field])
		except (TypeError, ValueError):
			continue
		if not np.isfinite(w) or w <= 0:
			continue
		pos = line.lineLocatePoint(g)
		if pos is None or pos < 0:
			continue
		profile.append((pos, w))
	profile.sort(key=lambda p: p[0])
	return profile
 
 
def altered_length_ratio(profile: list, seuil_km: float):
	"""
	Proportion (0-1) of the length covered by the PtRef that shows an abnormal
	width variation. Returns None if fewer than 2 PtRef (not assessable).
	For each pair of consecutive PtRef :
		var_km = (w_aval - w_amont) / w_amont * 1000 / distance_m
	The interval is abnormal if var_km < 0 (narrowing downstream)
	or var_km > seuil_km.
	"""
	if len(profile) < 2:
		return None
	pos = np.array([p for p, _ in profile], dtype=float)
	w = np.array([v for _, v in profile], dtype=float)
	dist = np.diff(pos)
	ok = dist > 0	# ignores PtRef located at the same position
	if not np.any(ok):
		return None
	dist = dist[ok]
	w_up = w[:-1][ok]
	w_down = w[1:][ok]
	var_km = (w_down - w_up) / w_up * 1000.0 / dist
	abnormal = (var_km < 0) | (var_km > seuil_km)
	return float(dist[abnormal].sum() / dist.sum())
 
 
def computeF4(ratio):
	# Compute F4 from the proportion of altered length (previous weighting)
	if ratio is None:
		return None
	natural = 1.0 - ratio
	if natural >= 0.90: #   naturel >= 90 %  (altéré <= 10 %)
		return 0
	if natural >= 0.66: #   naturel >= 66 %  (altéré 10 à 34 %) 
		return 1
	if natural >= 0.33: #   naturel >= 33 %  (altéré 34 à 67 %)
		return 2
	return 3            #   naturel <  33 %  (altéré > 67 %) 