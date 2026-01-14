
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
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsFeature,
	QgsPointXY,
	QgsVectorLayer,
	QgsFeatureRequest,
	QgsProcessingUtils,
	QgsUnitTypes,
	QgsSpatialIndex,
	QgsProcessingAlgorithm,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterString,
	QgsWkbTypes,
	QgsGeometry,
	QgsProcessingParameterNumber,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsProcessingMultiStepFeedback
)


class IndiceA3(QgsProcessingAlgorithm):
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'
	DEFAULT_WIDTH_FIELD = 'Largeur_mod'
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterNumber('dam_distance', self.tr('Distance max du barrage au segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=5,optional=True, minValue=1))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('ptref_width_field', self.tr('Nom du champ de largeur dans PtRef'), defaultValue=self.DEFAULT_WIDTH_FIELD))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Check if the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		ptref_layer  = self.parameterAsVectorLayer(parameters, 'ptref_widths', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		# Verify that the given segment ID is in the rivnet and PtRef layer
		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro ! Veuillez fournir un champ identifiant du segment commun aux deux couches.")
		if "Largeur_mod" not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ Largeur_mod est absent de la couche PtRef largeur! Veuillez vous assurer que la couche de points de références à préalablement passé par le script UEA_PtRef_join")
		if width_field not in [f.name() for f in ptref_layer.fields()]:
			return False, self.tr(f"Le champ '{width_field}' est absent de la couche PtRef largeur! Veuillez fournir un champ identifiant la largeur du segment qui se trouve dans cette couche.")
		if not is_metric_crs(rivnet_layer.crs()) :
			return False, self.tr(f"La couche de réseau hydro n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		if not is_metric_crs(ptref_layer.crs()) :
			return False, self.tr(f"La couche de PtRef n'est pas dans un CRS en mètres! Veuillez reprojeter la couche dans un CRS valide.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
		width_field  = self.parameterAsString(parameters, 'ptref_width_field', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)
		outputs = {}

		# Define stream network as source for data output
		source = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		# Gets the inputed dam distance parameter
		max_dam_distance = self.parameterAsInt(parameters, 'dam_distance', context)

		# Define sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("Nb_barrage_amont", QVariant.Int))
		sink_fields.append(QgsField("Indice A3", QVariant.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		if feedback.isCanceled():
			return {}

		# Initialising treatment layers
		dam_counts = {}
		dams_layer = self.parameterAsVectorLayer(parameters, 'dams', context)
		hydro_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)

		# Create spatial index to make the finding of the nearest segment faster
		hydro_index = QgsSpatialIndex(hydro_layer.getFeatures())
		id_to_feat = {f['Id_UEA']: f for f in hydro_layer.getFeatures()}

		# Gets the number of features (dams) to iterate over
		total_features = dams_layer.featureCount()
		feedback.pushInfo(self.tr(f"\t {total_features} features (barrages) à traiter"))

		feedback.setProgressText(self.tr(f"Compte des barrages"))
		try :
			for current, dam in enumerate(dams_layer.getFeatures()):
				current_feat = None
				try :
					# Finds the river segment of the current structure
					current_feat = find_segment_for_structure_fast(dam, hydro_layer, hydro_index, max_dist=max_dam_distance)
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur dans find_segment_for_structure : {str(e)}"))
					return {}
				if current_feat is None: # if no segment associated to the dam
					#feedback.pushInfo(self.tr(f"Pas de segment associé au barrage actuel. Prochain segment."))
					continue
				if feedback.isCanceled():
					return {}

				downstream_feat = None
				try :
					# Finds the downstream river segment
					downstream_id = current_feat['Id_UEA_aval']
					downstream_feat = id_to_feat.get(downstream_id)
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur dans get_downstream_segment : {str(e)}"))
					return {}
				if downstream_feat is None:
					#feedback.pushInfo(self.tr(f"Le segment d'aval ne fait pas partie du réseau hydrographique. Prochain segment."))
					continue

				cum_dist = 0
				prev_intersection = None
				step = 0
				visited = set()
				# Iterate over the next downstream segments while the cumulative distance from the dam to the downstream segment is less than 1000 meters
				while (cum_dist < 1000) and (downstream_feat is not None) :
					intersection_point = None
					if feedback.isCanceled():
						return {}
					try :
						# Find the intersecting point between the dam river segment and the downstream segment
						intersection_point = get_intersection_point(current_feat, downstream_feat, tol=5)
					except Exception as e :
						feedback.reportError(self.tr(f"Erreur dans get_intersection_point : {str(e)}"))
					if intersection_point is None or intersection_point.isEmpty():
						#feedback.pushInfo(self.tr(f"Le segment d'aval ne retourne pas d'intersection avec le segment courant. Prochain segment."))
						break

					try :
						# Calculates the distance along the network between the dam and this point
						if step == 0 : # If first time get distance between the dam and the intersection with downstream
							dist = line_distance_between_points(current_feat.geometry(), dam.geometry(), intersection_point)
						else : # Otherwise get the distance between the previous intersection and the current intersection
							dist = line_distance_between_points(current_feat.geometry(), prev_intersection, intersection_point)
					except Exception as e :
						feedback.reportError(self.tr(f"Erreur dans compute_shortest_path : {str(e)}"))
						return {}
					# If the distance is < 1000 m, increment the downstream segment dam counter.
					if dist is None or dist <= 0:
						# Null or invalid distance.
						break
					if (cum_dist + dist) < 1000:
						# Get the downstream UEA to increment the count of dams
						downstream_id = downstream_feat['Id_UEA']
						# Verify if we already counted this segment for this dam
						if downstream_id in visited:
							break
						dam_counts[downstream_id] = dam_counts.get(downstream_id, 0) + 1
						cum_dist += dist
						prev_intersection = intersection_point
						step += 1
						visited.add(downstream_id)
						# Get the downstream segment of the downstream segment to see if the dam is within range of another segment (for the next iteration of the while loop)
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
				feedback.setProgress(progress)

				if feedback.isCanceled():
					return {}
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la boucle de barrages : {str(e)}"))
		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# Adding dam count field
		feedback.setProgressText(self.tr(f"Ajout du champ de compte de barrage"))
		try :
			count_lyr = QgsVectorLayer("None", "dam_counts", "memory")
			prov = count_lyr.dataProvider()
			seg_field = source.fields().field(seg_id_field)
			prov.addAttributes([QgsField(seg_id_field, seg_field.type()), QgsField("Nb_barrage_amont", QVariant.Int)])
			count_lyr.updateFields()

			new_feats = []
			for f in source.getFeatures():
				seg = f[seg_id_field]
				c = int(dam_counts.get(seg, 0)) # Puts either the count found in dam_counts or 0
				nf = QgsFeature(count_lyr.fields())
				nf.setAttributes([seg, c])
				new_feats.append(nf)
			prov.addFeatures(new_feats)
			count_lyr.updateExtents()

		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans l'ajout du champ de compte des barrages : {str(e)}"))
		feedback.setCurrentStep(2)
		if feedback.isCanceled():
				return {}

		# Creating buffers for alluvial plain simulation
		feedback.setProgressText(self.tr(f"Création des tampons de 2x du lit mineur et calcul de l'util. du terr."))
		try :
			# Compute mean stream width for stream network segments
			ptref_id = parameters['ptref_widths']
			expr = f"coalesce(array_mean(overlay_nearest('{ptref_id}', '{width_field}', limit:=-1, max_distance:=5)), 5)"
			alg_params = {
				'INPUT': parameters['stream_network'],
				'FIELD_NAME': 'mean_width',
				'FIELD_TYPE': 0,  # 0 = float
				'FIELD_LENGTH': 10,
				'FIELD_PRECISION': 3,
				'NEW_FIELD': True,
				'FORMULA': expr,
				'OUTPUT': 'memory:stream_w_mean'
			}
			stream_w_mean = processing.run('native:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(3)
			# Create 'Mean width x 2' buffer
			expr = 'buffer($geometry, "mean_width" * 2, 30, \'round\', \'miter\', 2)'
			alg_params = {
				'INPUT': stream_w_mean,
				'EXPRESSION': expr,
				'OUTPUT': QgsProcessingUtils.generateTempFilename('buffer2x.shp')
			}
			outputs['buffer2x'] = processing.run('qgis:geometrybyexpression', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(4)
			# Reclassify land use
			outputs['reclassifiedlanduse'] = reduce_landuse(parameters['landuse'], context, feedback=None)
			feedback.setCurrentStep(5)
			# Compute land use within 2x mean width buffer
			stream2x = compute_landuse_areas(outputs['reclassifiedlanduse'], outputs['buffer2x'], context=context, feedback=None)
			feedback.setCurrentStep(6)
			# Join dam_count to stream2x
			alg_params = {
				'INPUT': stream2x,
				'FIELD': seg_id_field,
				'INPUT_2': count_lyr,
				'FIELD_2': seg_id_field,
				'FIELDS_TO_COPY': ['Nb_barrage_amont'],
				'METHOD': 1,  # 1 = one-to-one
				'DISCARD_NONMATCHING': False,
				'OUTPUT': 'memory:stream2x'
			}
			stream2x = processing.run('native:joinattributestable', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans création des tampons de lit mineur : {str(e)}"))
		feedback.setCurrentStep(7)
		if feedback.isCanceled():
			return {}

		# Compute A3 index
		feedback.setProgressText(self.tr(f"Calcul de l'indice A3"))
		try :
			outputs['streams2x'] = computeA3(stream2x, context, feedback=None)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de l'indice A3 : {str(e)}"))
		feedback.setCurrentStep(8)
		if feedback.isCanceled():
			return {}
		
		# Getting results ready to output 
		feedback.setProgressText(self.tr(f"Sortie des résultats."))
		try :
			# Convert stream features to vector layers
			streams2x_lyr = QgsVectorLayer(outputs['streams2x'], 'ws2x', 'ogr')
			# Map feature ID and index values for each watershed layer
			a3_map = {f[seg_id_field]: f['Indice A3'] for f in streams2x_lyr.getFeatures()}
			# Write final indices to sink using map
			for feat in source.getFeatures():
				seg = feat[seg_id_field]
				a3_vals = a3_map.get(seg, None)
				dam_count = dam_counts.get(feat[seg_id_field],0)
				# add both the dam count and A3 index score
				feat.setAttributes(feat.attributes() + [dam_count, a3_vals])
				sink.addFeature(feat, QgsFeatureSink.FastInsert)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la sortie des résultats : {str(e)}"))
		feedback.setCurrentStep(9)
		if feedback.isCanceled():
			return {}

		# Ending message
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT: dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceA3()

	def name(self):
		return 'indicea3'

	def displayName(self):
		return self.tr('Indice A3')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice A3 afin d'évaluer l’altération des régimes hydrologiques et sédimentaires ainsi que la présence de formes au niveau de la plaine alluviale à l’échelle du segment.\n Le niveau d’anthropisation du segment et la présence d’unités géomorphologiques sur la plaine sont évalués à l’intérieur du corridor fluvial sur une largeur respective de deux fois la largeur du lit mineur pour les milieux non-confinés, ou de 15 m pour les milieux confinés. Le niveau d’anthropisation correspond à la surface de recouvrement relative à l’intérieur du corridor fluvial liée aux affectations urbanisées et agricoles. Une pénalité est appliquée en fonction du nombre de barrages à l’intérieur d’une distance de 1000 m à l’amont du segment analysé. Ces entraves qui créent des discontinuités dans le transport par charge de fond affectent grandement les conditions hydrauliques influençant les processus hydrogéomorphologiques et les formes présentes dans le lit mineur en aval de celles-ci.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Distance max du barrage au segment : Chiffre (int)(optionnel; valeur par défaut : 15)\n" \
			"-> Distance maximale (en m) des barrages au segment. Parfois les points de barrages n'intersecte pas les lignes de réseau hydrographique. Cette distance est la distance maximale que l'algorithme vas chercher autour de chaque barrage pour trouver le segment de rivière le plus proche pour effectuer le compte du nombre de barrages.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			" Nbr de points visés : nombre entier (int; 200 par défaut)\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			" Champ PtRef largeur : Chaine de caractère ('Largeur_mod' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant la largeur du chenal. Source des données : Couche PtRef largeur.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le nombre de barrages en amont et le score de l'indice A3 calculé pour chaque UEA."
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


def get_downstream_segment(hydro_layer, current_feat):
	# Retrieves the ID of the downstream segment from the attribute field.
	downstream_id = current_feat['Id_UEA_aval']
	# Search for the corresponding segment in the layer
	request = QgsFeatureRequest().setFilterExpression(f'"Id_UEA" = \'{downstream_id}\'')
	return next(hydro_layer.getFeatures(request), None)


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


def reduce_landuse(landuse, context, feedback):
	# INPUT : parameters
	# OUTPUT : layer_id
	CLASSES = [
		'50','56','1','210','235','1','501','735','1', #Forestiers
		'60', '77', '1', '30', '31', '1', #Sols nues
		'250', '261', '1', '263', '280', '1', # Coupes de regeneration
		'101','199','2', #Agricoles
		'300', '360', '3', #Anthropisé
		'20', '27', '4',
		'2000', '9000', '1'#Milieux humides
	]

	# Reclassify land use
	alg_params = {
		'DATA_TYPE': 0,  # Byte
		'INPUT_RASTER': landuse,
		'NODATA_FOR_MISSING': True,
		'NO_DATA': 0,
		'RANGE_BOUNDARIES': 2,  # min <= value <= max
		'RASTER_BAND': 1,
		'TABLE': CLASSES,
		'OUTPUT': QgsProcessingUtils.generateTempFilename("landuse.tif"),
	}
	return processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']


def compute_landuse_areas(landuse_raster, basin_layer, context, feedback):
		# Inputs: Landuse raster, Basin polygon
		# Output: Landuse counts (m²)

		# Zonal histogram: produces pixel counts as fields lc_1, lc_2, lc_3, lc_4
		alg_params = {
			'INPUT_RASTER': landuse_raster,
			'RASTER_BAND': 1,
			'INPUT_VECTOR': basin_layer,
			'COLUMN_PREFIX': 'lc_',
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		zonalhist = processing.run('qgis:zonalhistogram', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

		# Multiply pixel counts for each land class by 100 to get area in m²
		lc_fields = ['lc_1', 'lc_2', 'lc_3', 'lc_4']
		area_fields = ['forest_area', 'agri_area', 'anthro_area', 'water_area']

		for i, field in enumerate(lc_fields):
			alg_params = {
				'INPUT': zonalhist,
				'FIELD_NAME': area_fields[i],
				'FIELD_TYPE': 0,  # Float
				'FIELD_LENGTH': 20,
				'FIELD_PRECISION': 2,
				'FORMULA': f'"{field}" * 100',
				'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
			}
			zonalhist = processing.run('qgis:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']

		# Compute total land area = forest + agri + anthro
		alg_params = {
			'INPUT': zonalhist,
			'FIELD_NAME': 'land_area',
			'FIELD_TYPE': 0,  # Float
			'FIELD_LENGTH': 20,
			"FIELD_PRECISION": 2,
			'FORMULA': '"forest_area" + "agri_area" + "anthro_area"',
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		return processing.run('qgis:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']


def computeA3(stream2x, context, feedback):
	a3_formula = """
		with_variable(
		'penalty',
		CASE
			WHEN "Nb_barrage_amont" = 1 THEN 2
			WHEN "Nb_barrage_amont" > 1 THEN 4
			ELSE 0
		END,
		CASE
			WHEN "land_area" = 0 THEN @penalty + 2
			WHEN (("anthro_area" + "agri_area")/"land_area") >= 0.9 THEN @penalty + 4
			WHEN (("anthro_area" + "agri_area")/"land_area") >= 0.66 THEN @penalty + 3
			WHEN (("anthro_area" + "agri_area")/"land_area") >= 0.33 THEN @penalty + 2
			WHEN (("anthro_area" + "agri_area")/"land_area") >= 0.1 THEN @penalty + 1
			ELSE @penalty
		END	
		)
		"""
	# Compute A3
	alg_params = {
		'INPUT': stream2x,
		'FIELD_NAME': 'Indice A3',
		'FIELD_TYPE': 2,  # 2 = integer
		'FIELD_LENGTH': 3,
		'FIELD_PRECISION': 0,
		'NEW_FIELD': True,
		'FORMULA': a3_formula,
		'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds2x.shp")
	}
	return processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']