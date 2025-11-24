
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsFeature,
	QgsVectorLayer,
	QgsFeatureRequest,
	QgsProcessingUtils,
	QgsProcessingAlgorithm,
	QgsProcessingParameterRasterLayer,
	QgsWkbTypes,
	QgsProcessingParameterNumber,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsProcessingMultiStepFeedback
)


class IndiceA3(QgsProcessingAlgorithm):
	ID_FIELD = 'Id'
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterNumber('dam_distance', self.tr('Distance max du barrage au segment'), type=QgsProcessingParameterNumber.Integer, defaultValue=15,optional=True, minValue=1))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))


	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
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
		hydro_layer = source.clone()

		# Gets the number of features (dams) to iterate over
		total_features = dams_layer.featureCount()
		feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

		feedback.setProgressText(self.tr(f"Compte des barrages"))
		try :
			for current, dam in enumerate(dams_layer.getFeatures()):
				current_feat = None
				try :
					# Finds the river segment of the current dam
					current_feat = find_segment_for_structure(dam, hydro_layer, context, distance=max_dam_distance)
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur dans find_segment_for_structure : {str(e)}"))
				if current_feat is None:
					continue

				downstream_feat = None
				try :
					# Finds the downstream river segment
					downstream_feat = get_downstream_segment(hydro_layer, current_feat)
				except Exception as e :
					feedback.reportError(self.tr(f"Erreur dans get_downstream_segment : {str(e)}"))
				if downstream_feat is None:
					continue

				cost = 0
				# Iterate over the next downstream segments if the distance of the structure is less than 1000 meters
				while (cost < 1000) and (downstream_feat is not None) :
					intersection_point = None
					try :
						# Find the intersecting point between the dam's river segment and the downstream segment
						intersection_point = get_intersection_point(current_feat, downstream_feat)
					except Exception as e :
						feedback.reportError(self.tr(f"Erreur dans get_intersection_point : {str(e)}"))
					if intersection_point is None:
						break

					try :
						# Calculates the distance along the network between the structure and this point
						cost = compute_shortest_path(dam, intersection_point, hydro_layer, feedback, context)
					except Exception as e :
						feedback.reportError(self.tr(f"Erreur dans compute_shortest_path : {str(e)}"))

					# If the distance is < 1000 m, increment the downstream segment dam counter.
					if cost is None :
						break
					if cost < 1000:
						downstream_id = downstream_feat['Id_UEA']
						dam_counts[downstream_id] = dam_counts.get(downstream_id, 0) + 1
						# Get the downstream segment of the downstream segment to see if the dam is within range of another segment (for the next iteration of the while loop)
						current_feat = downstream_feat
						downstream_feat = None
						try :
							# Finds the downstream river segment
							downstream_feat = get_downstream_segment(hydro_layer, current_feat)
						except Exception as e :
							feedback.reportError(self.tr(f"Erreur dans get_downstream_segment du segment en aval du segment d'aval du barrage : {str(e)}"))
						if downstream_feat is None:
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
			feedback.reportError(self.tr(f"Erreur dans la boucle de structure : {str(e)}"))
		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# Adding dam count field
		feedback.setProgressText(self.tr(f"Ajout du champ de compte de barrage"))
		try :
			hydro_layer.startEditing()
			hydro_layer.dataProvider().addAttributes([
				QgsField("Nb_barrage_amont", QVariant.Int)
			])
			hydro_layer.updateFields()

			for feat in source.getFeatures():
				seg_id = feat['Id_UEA']
				dam_count = dam_counts.get(seg_id, 0)

				# add the structure count to the attributes table
				new_feat = QgsFeature(hydro_layer.fields())
				new_feat.setGeometry(feat.geometry())
				new_feat.setAttributes(feat.attributes() + [dam_count])
				hydro_layer.addFeature(new_feat)
			hydro_layer.commitChanges()
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
			expr = f"coalesce(array_mean(overlay_nearest('{ptref_id}', \"Largeur_mod\", limit:=-1, max_distance:=5)), 5)"
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
				'FIELD': 'Id',
				'INPUT_2': hydro_layer,
				'FIELD_2': 'Id',
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
		feedback.setProgressText(self.tr(f"Calcul de l'indice A2"))
		try :
			outputs['streams2x'] = computeA3(stream2x, context, feedback=None)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de l'indice A2 : {str(e)}"))
		feedback.setCurrentStep(8)
		if feedback.isCanceled():
			return {}
		
		# Getting results ready to output 
		feedback.setProgressText(self.tr(f"Sortie des résultats."))
		try :
			# Convert stream features to vector layers
			streams2x_lyr = QgsVectorLayer(outputs['streams2x'], 'ws2x', 'ogr')
			# Map feature ID and index values for each watershed layer
			a3_map = {f['Segment']: f['Indice A3'] for f in streams2x_lyr.getFeatures()}
			# Write final indices to sink using map
			for feat in source.getFeatures():
				seg = feat['Segment']
				a3_vals = a3_map.get(seg, None)
				dam_count = dam_counts.get(feat['Id_UEA'],0)
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
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"PtRef largeur : Vectoriel (points)\n" \
			"-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le nombre de barrages en amont et le score de l'indice A3 calculé pour chaque UEA."
		)


def find_segment_for_structure(structure, hydro_layer, context, distance=15):
	# Use the QGIS processing to select river segments located within `distance` meters of the structure point.
	# Create a temporary layer with the structure point
	point_layer = QgsVectorLayer("Point?crs=" + hydro_layer.crs().authid(), "structure_point", "memory")
	provider = point_layer.dataProvider()
	feat = QgsFeature()
	feat.setGeometry(structure.geometry())
	provider.addFeatures([feat])
	point_layer.updateExtents

	alg_params = {
		'INPUT': hydro_layer,
		'REFERENCE': point_layer,
		'DISTANCE': distance,
		'METHOD': 0 # 0, create a new selection
	}
	processing.run("native:selectwithindistance", alg_params, context=context, is_child_algorithm=True)
	selected_feats = list(hydro_layer.getSelectedFeatures())
	# Returns the first segment found (the closest one)
	return selected_feats[0] if selected_feats else None


def get_downstream_segment(hydro_layer, current_feat):
	# Retrieves the ID of the downstream segment from the attribute field.
	downstream_id = current_feat['Id_UEA_aval']
	# Search for the corresponding segment in the layer
	request = QgsFeatureRequest().setFilterExpression(f'"Id_UEA" = \'{downstream_id}\'')
	return next(hydro_layer.getFeatures(request), None)


def get_intersection_point(feat1, feat2):
	# Calculates the geometric intersection between the two segments
	intersection = feat1.geometry().intersection(feat2.geometry())
	# If the intersection is a point, return it
	if intersection and intersection.type() == QgsWkbTypes.PointGeometry:
		return intersection
	# If it's a multipoint, we take the first one.
	elif intersection and intersection.type() == QgsWkbTypes.MultiPointGeometry:
		return intersection.asMultiPoint()[0]
	# Otherwise, we return None
	return None


def compute_shortest_path(structure_point, target_point, hydro_layer, feedback, context):
	# Extract the coordinates for the points
	start_coords = structure_point.geometry().asPoint()
	end_coords = target_point.asPoint()

	# Find the shortest path on the river network between the downstream segment and the given structure to get the distance between the two
	alg_params = {
		'INPUT': hydro_layer,
		'STRATEGY': 0,  # 0 = shortest path
		'START_POINT': f"{start_coords.x()},{start_coords.y()}",
		'END_POINT': f"{end_coords.x()},{end_coords.y()}",
		'DEFAULT_DIRECTION': 2,
		'DEFAULT_SPEED': 1,
		'TOLERANCE': 5,
		'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
	}
	result = processing.run("native:shortestpathpointtopoint", alg_params, context=context, is_child_algorithm=True)
	temp_layer = context.takeResultLayer(result['OUTPUT'])

	if not temp_layer.isValid():
		feedback.reportError("La couche temporaire n'est pas valide.")
		return None
	if 'cost' not in temp_layer.fields().names():
		feedback.reportError("Le champ 'cost' est introuvable dans la couche de chemin.")
		return None

	path_feat = next(temp_layer.getFeatures(), None)
	# Return the length of the shortest path on the river network ('cost' field)
	return path_feat['cost'] if path_feat else None


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
