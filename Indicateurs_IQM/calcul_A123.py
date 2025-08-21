"""
Model exported as python.
Name : Network Watershed from DEM
Group :
With QGIS : 33000
"""

import processing
from pathlib import Path
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsVectorLayer,
	QgsProject,
	QgsProcessingUtils,
	QgsProcessingParameterFeatureSink,
	QgsField,
	QgsFeatureSink,
	QgsFeatureRequest,
	QgsCoordinateReferenceSystem,
	QgsExpression,
	QgsExpressionContext,
	QgsExpressionContextUtils,
	QgsProcessing,
	QgsProcessingAlgorithm,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterVectorLayer,
	)


class NetworkWatershedFromDem(QgsProcessingAlgorithm):

	D8 = 'd8'
	STREAM_NET = 'stream_network'
	OUTPUT = 'OUTPUT'
	ID_FIELD = "Id"
	LANDUSE = 'landuse'
	DAMS = 'dams'
	STRUCTS = 'structures'
	PTREFS = 'ptrefs_largeur'

	TMP_WATERSHED = 'watershed'
	TMP_OUTLETS = 'outlets'
	TMP_OUTLET = 'outlet'
	TMP_SUBWSHED = 'soubwshed'
	TMP_BUFFER1 = 'buffer1'
	TMP_BUFFER2 = 'buffer2'
	TMP_LANDUSE = 'landuse'
	TMP_VECTOR1 = 'vector1'
	TMP_VECTOR2 = 'vector2'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterRasterLayer(self.D8, self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer(self.LANDUSE, self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer(self.STREAM_NET, self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer(self.DAMS, self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer(self.STRUCTS, self.tr('Structures (MTMD)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer(self.PTREFS, self.tr('PtRef largeur cours d\'eau (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):
		outputs = {}

		# Source definition
		source = self.parameterAsVectorLayer(parameters, self.STREAM_NET, context)
		# Sink (output) définition
		new_fields = [
			QgsField("Indice A1", QVariant.Int),
			QgsField("Indice A2", QVariant.Int),
			QgsField("Indice A3", QVariant.Int),
			QgsField("Indice F1", QVariant.Int),
		]
		sink_fields = source.fields()
		[sink_fields.append(field) for field in new_fields]

		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		if model_feedback.isCanceled():
			return {}

		# Extract and snap outlets
		alg_params = {
			'dem': parameters[self.D8],
			'stream_network': parameters['stream_network'],
			'snapped_outlets': QgsProcessingUtils.generateTempFilename("snappedoutlets.shp"),
		}
		outputs['snappedoutlets'] = processing.run('script:extractandsnapoutlets', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']

		if model_feedback.isCanceled():
			return {}

		# Reclassify landuse
		outputs['reclassifiedlanduse'] = self.reduce_landuse(parameters, context, feedback=None)

		# Generate watershed polygon
		watersheds = self.generate_basin_polygons(parameters[self.D8], outputs['snappedoutlets'], temp_prefix="watersheds", context=context, feedback=model_feedback)

		if model_feedback.isCanceled():
			return {}

		# Compute area for all watersheds under "watersheds_area" field
		alg_params = {
			'INPUT': watersheds,
			'FIELD_NAME': 'watershed_area',
			'FIELD_TYPE': 0,  # 0 = float
			'FIELD_LENGTH': 10,
			'FIELD_PRECISION': 3,
			'NEW_FIELD': True,
			'FORMULA': '$area',
			'OUTPUT': 'memory:watersheds'
		}
		watersheds = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		if model_feedback.isCanceled():
			return {}

		# Compute landuse area for each watershed
		watersheds = self.compute_landuse_areas(outputs['reclassifiedlanduse'], watersheds, context=context, feedback=model_feedback)

		if model_feedback.isCanceled():
			return {}

		# Remove duplicate dam points
		alg_params = {
			'INPUT': parameters[self.DAMS],
			'OUTPUT': 'memory:dams_edited'
		}
		dams_edited = processing.run('native:deleteduplicategeometries', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Add index to edited dam points
		alg_params = {
			'INPUT': dams_edited,
			'FIELD_NAME': 'row_index',
			'FIELD_TYPE': 1,  # 1 = integer
			'FIELD_LENGTH': 10,
			'NEW_FIELD': True,
			'FORMULA': '@row_number + 1',  # Start at 1
			'OUTPUT': QgsProcessingUtils.generateTempFilename("dams_edited.shp")
		}
		outputs['dams_edited'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		if model_feedback.isCanceled():
			return {}

		# Generate dam watershed polygon
		damsheds = self.generate_basin_polygons(parameters[self.D8], outputs['dams_edited'], temp_prefix="damwatersheds", context=context, feedback=model_feedback)

		if model_feedback.isCanceled():
			return {}

		# Compute area for dam watersheds
		alg_params = {
			'INPUT': damsheds,
			'FIELD_NAME': 'dam_area',
			'FIELD_TYPE': 0,  # 0 = float
			'FIELD_LENGTH': 10,
			'FIELD_PRECISION': 3,
			'NEW_FIELD': True,
			'FORMULA': '$area',
			'OUTPUT': QgsProcessingUtils.generateTempFilename("damsheds_area.shp")
		}
		outputs['damsheds_area'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Attach 'dam_area' back to dam points
		alg_params = {
			'INPUT': outputs['dams_edited'],
			'FIELD': 'row_index',
			'INPUT_2': outputs['damsheds_area'],
			'FIELD_2': 'DN',
			'FIELDS_TO_COPY': ['dam_area'],
			'METHOD': 1,  # 1 = one-to-one
			'DISCARD_NONMATCHING': False,
			'OUTPUT': 'memory:dams_points_area'
		}
		dams_points_area = processing.run('native:joinattributestable', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']
		processing.run('native:createspatialindex', {'INPUT': dams_points_area}, context=context, feedback=None, is_child_algorithm=True)

		# Locate dam points in watersheds and sum total dam area per watershed
		alg_params = {
			'INPUT': watersheds,
			'PREDICATE': [1],  # 1 = contains
			'JOIN': dams_points_area,
			'JOIN_FIELDS': ['dam_area'],
			'SUMMARIES': [5],  # 5 = sum
			'PREFIX': '',
			'DISCARD_NONMATCHING': False,
			'OUTPUT': 'memory:watersheds'
		}
		watersheds = processing.run("qgis:joinbylocationsummary", alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		if model_feedback.isCanceled():
			return {}

		# Create 1km buffer on stream network
		alg_params = {
			'INPUT': parameters[self.STREAM_NET],
			'DISTANCE': 1000,
			'SEGMENTS': 5,
			'END_CAP_STYLE': 0,  # 0 = Round
			'JOIN_STYLE': 0,  # 0 = Round
			'MITER_LIMIT': 2,
			'DISSOLVE': False,
			'OUTPUT': QgsProcessingUtils.generateTempFilename("buffer1km.shp")
		}
		outputs['buffer1km'] = processing.run("native:buffer", alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']
		processing.run('native:createspatialindex', {'INPUT': outputs['buffer1km']}, context=context, feedback=model_feedback, is_child_algorithm=True)

		# Intersect and dissolve watershed and buffer layers to generate 1km watershed buffer
		watersheds1km = self.buffer_streams(outputs['buffer1km'], watersheds, context=context, feedback=model_feedback)

		# Count number of dams in 1km watershed buffer
		alg_params = {
			'POLYGONS': watersheds1km,
			'POINTS': parameters[self.DAMS],
			'FIELD': 'dam_count1km',
			'OUTPUT': 'memory:watersheds1km'
		}
		watersheds1km = processing.run("native:countpointsinpolygon", alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Count number structures in 1km watershed buffer
		alg_params = {
			'POLYGONS': watersheds1km,
			'POINTS': parameters[self.STRUCTS],
			'FIELD': 'struct_count1km',
			'OUTPUT': 'memory:watersheds1km'
		}
		watersheds1km = processing.run("native:countpointsinpolygon", alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Join stream network river length ('Long_km') to watersheds1km for F1 calculation
		alg_params = {
			'INPUT': watersheds1km,
			'FIELD': 'DN',
			'INPUT_2': parameters[self.STREAM_NET],
			'FIELD_2': 'fid',
			'FIELDS_TO_COPY': ['Long_km'],
			'METHOD': 1,  # 1 = one-to-one
			'DISCARD_NONMATCHING': False,
			'OUTPUT': 'memory:watersheds1km'
		}
		watersheds1km = processing.run('native:joinattributestable', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		if model_feedback.isCanceled():
			return {}

		# Compute mena stream width for stream network segments
		ptref_id = parameters[self.PTREFS]
		expr = f"coalesce(array_mean(overlay_nearest('{ptref_id}', \"Largeur_mod\", limit:=-1, max_distance:=5)), 5)"
		alg_params = {
			'INPUT': parameters[self.STREAM_NET],
			'FIELD_NAME': 'mean_width',
			'FIELD_TYPE': 0,  # 0 = float
			'FIELD_LENGTH': 10,
			'FIELD_PRECISION': 3,
			'NEW_FIELD': True,
			'FORMULA': expr,
			'OUTPUT': 'memory:stream_w_mean'
		}
		stream_w_mean = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Create 'Mean width x 2.5' buffer
		expr = 'buffer($geometry, "mean_width" * 2.5, 30, \'round\', \'miter\', 2)'
		alg_params = {
			'INPUT': stream_w_mean,
			'EXPRESSION': expr,
			'OUTPUT': QgsProcessingUtils.generateTempFilename('buffer2x.shp')
		}
		outputs['buffer2x'] = processing.run('qgis:geometrybyexpression', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Compute landuse within 2.5x mean width buffer
		watersheds2x = self.compute_landuse_areas(outputs['reclassifiedlanduse'], outputs['buffer2x'], context=context, feedback=model_feedback)

		# Join dam_count1km to watersheds2x
		alg_params = {
			'INPUT': watersheds2x,
			'FIELD': 'Id',
			'INPUT_2': watersheds1km,
			'FIELD_2': 'Id',
			'FIELDS_TO_COPY': ['dam_count1km'],
			'METHOD': 1,  # 1 = one-to-one
			'DISCARD_NONMATCHING': False,
			'OUTPUT': 'memory:watersheds2x'
		}
		watersheds2x = processing.run('native:joinattributestable', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Store formula expressions for Indices A1, A2, A3, and F1
		# Indice A1 formula
		a1_formula = """
		CASE
			WHEN "watershed_area" = 0 THEN 2
			WHEN ("forest_area"/"watershed_area") <= 0.1 THEN 5
			WHEN ("forest_area"/"watershed_area") < 0.33 THEN 4
			WHEN ("forest_area"/"watershed_area") <= 0.66 AND ("agri_area"/"watershed_area") < 0.33 THEN 3
			WHEN ("forest_area"/"watershed_area") <= 0.66 AND ("agri_area"/"watershed_area") >= 0.33 THEN 2
			WHEN ("forest_area"/"watershed_area") < 0.9 THEN 1
			ELSE 0
		END
		"""

		# Indice A2 formula. Treat null dam areas as 0.
		a2_formula = """
		CASE
			WHEN "watershed_area" = 0 THEN 2
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.05 THEN 0
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.33 THEN 2
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.66 THEN 3
			ELSE 4
		END
		"""

		# Indice A3 formula
		a3_formula = """
			with_variable(
			'penalty',
			CASE
				WHEN "dam_count1km" = 1 THEN 2
				WHEN "dam_count1km" > 1 THEN 4
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

		# Indice F1 formula
		f1_formula = """
		CASE
			WHEN "Long_km" IS NULL OR "Long_km" = 0 OR "struct_count1km" IS NULL OR "struct_count1km" = 0 THEN 0
			WHEN ("struct_count1km"/"Long_km") <= 1 THEN 2
			ELSE 4
		END
		"""

		# Compute A1
		alg_params = {
			'INPUT': watersheds,
			'FIELD_NAME': 'Indice A1',
			'FIELD_TYPE': 2,  # 2 = Integer
			'FIELD_LENGTH': 3,
			'FIELD_PRECISION': 0,
			'NEW_FIELD': True,
			'FORMULA': a1_formula,
			'OUTPUT': 'memory:watersheds'
		}
		watersheds = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Compute A2
		alg_params = {
			'INPUT': watersheds,
			'FIELD_NAME': 'Indice A2',
			'FIELD_TYPE': 2,  # 2 = integer
			'FIELD_LENGTH': 3,
			'FIELD_PRECISION': 0,
			'NEW_FIELD': True,
			'FORMULA': a2_formula,
			'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds.shp")
		}
		outputs['watersheds'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Compute A3
		alg_params = {
			'INPUT': watersheds2x,
			'FIELD_NAME': 'Indice A3',
			'FIELD_TYPE': 2,  # 2 = integer
			'FIELD_LENGTH': 3,
			'FIELD_PRECISION': 0,
			'NEW_FIELD': True,
			'FORMULA': a3_formula,
			'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds2x.shp")
		}
		outputs['watersheds2x'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Compute F1
		alg_params = {
			'INPUT': watersheds1km,
			'FIELD_NAME': 'Indice F1',
			'FIELD_TYPE': 2,  # 2 = integer
			'FIELD_LENGTH': 3,
			'FIELD_PRECISION': 0,
			'NEW_FIELD': True,
			'FORMULA': f1_formula,
			'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds1km.shp")
		}
		outputs['watersheds1km'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=model_feedback, is_child_algorithm=True)['OUTPUT']

		# Convert watershed features to vector layers
		watersheds_lyr = QgsVectorLayer(outputs['watersheds'], 'ws', 'ogr')
		watersheds2x_lyr = QgsVectorLayer(outputs['watersheds2x'], 'ws2x', 'ogr')
		watersheds1km_lyr = QgsVectorLayer(outputs['watersheds1km'], 'ws1km', 'ogr')

		# Map feature ID and index values for each watershed layer
		a1_map = {f.id(): f['Indice A1'] for f in watersheds_lyr.getFeatures()}
		a2_map = {f.id(): f['Indice A2'] for f in watersheds_lyr.getFeatures()}
		a3_map = {f.id(): f['Indice A3'] for f in watersheds2x_lyr.getFeatures()}
		f1_map = {f.id(): f['Indice F1'] for f in watersheds1km_lyr.getFeatures()}

		# Write final indices to sink using map
		for feat in source.getFeatures():
			fid = feat.id()
			vals = feat.attributes()

			vals += [
				a1_map.get(fid, None),
				a2_map.get(fid, None),
				a3_map.get(fid, None),
				f1_map.get(fid, None),
			]

			feat.setAttributes(vals)
			sink.addFeature(feat, QgsFeatureSink.FastInsert)

		# Gets the number of features to iterate over for the progress bar
		total_features = source.featureCount()
		model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

		# Ending message
		model_feedback.setProgressText(self.tr('\tProcessus terminé pour calcul de A1, A2, A3 et F1 !'))

		return {self.OUTPUT : dest_id}

	def name(self):
		return 'calculA123'

	def displayName(self):
		return 'Calcul A1 A2 A3 et F1'

	def group(self):
		return self.tr('IQM (multi-indice)')

	def groupId(self):
		return 'IQM'

	def shortHelpString(self):
		return self.tr(
			"Calcule les indices A1, A2, A3 et F1.\n Script appelé par le script de calcul automatique Calcul IQM. Voir les descriptions des indices individuels pour plus d'informations sur chacun.\n" \
			"Paramètres\n" \
			"----------\n" \
			"WBT D8 Pointer: Matriciel\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Structures : Vectoriel (points)\n" \
			"-> Ensemble de données vectorielles ponctuelles des structures sous la gestion du Ministère des Transports et de la Mobilité durable du Québec (MTMD) (pont, ponceau, portique, mur et tunnel). Source des données : MTMD. Structure, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score des indices A1, A2, A3 et F1 calculé pour chaque UEA."
			)

	def createInstance(self):
		return NetworkWatershedFromDem()

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def reduce_landuse(self, parameters, context, feedback):
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
			'INPUT_RASTER': parameters[self.LANDUSE],
			'NODATA_FOR_MISSING': True,
			'NO_DATA': 0,
			'RANGE_BOUNDARIES': 2,  # min <= value <= max
			'RASTER_BAND': 1,
			'TABLE': CLASSES,
			'OUTPUT': QgsProcessingUtils.generateTempFilename("landuse.tif"),
		}
		reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		return reclass

	def polygonize_raster(self, raster_id ,context, feedback, output=None):
		# Inputs : Raster ID
		# Output : layer_id
		alg_params = {
			'BAND': 1,
			'EIGHT_CONNECTEDNESS': True,
			'EXTRA': '',
			'FIELD': 'DN',
			'INPUT': raster_id,
			'OUTPUT': output
		}
		return processing.run('gdal:polygonize', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']

	def generate_basin_polygons(self, d8_pointer, pour_points, temp_prefix, context, feedback):
		# Inputs: d8 pointer, Pour points, Temp prefix
		# Output: Merged watershed polygon

		# Unnest basins into multiple raster layers
		prefix = QgsProcessingUtils.generateTempFilename(temp_prefix)
		alg_params = {
			'd8_pntr': d8_pointer,
			'pour_pts': pour_points,
			'esri_pntr': False,
			'output': prefix + '.tif'
		}
		output_tif = processing.run('wbt:UnnestBasins', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['output']

		# Find all watershed rasters and sort them by index
		base = Path(output_tif).with_suffix('')
		rasters = sorted(
			base.parent.glob(f"{base.stem}_*.tif"),
			key=lambda p: int(p.stem.rsplit('_', 1)[-1])
		)

		# Polygonize each raster layer
		vecs = []
		for ras in rasters:
			shp = QgsProcessingUtils.generateTempFilename(f"{temp_prefix}_poly.shp")
			poly = self.polygonize_raster(raster_id=str(ras), context=context, feedback=feedback, output=shp)

			# Fix geometries and return layer
			alg_params = {
				'INPUT': poly,
				'OUTPUT': f'memory:{Path(shp).stem}_fixed'
			}
			fixed = processing.run('native:fixgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			vecs.append(fixed)

		# Merge the basin polygons into one layer
		merge_shp = QgsProcessingUtils.generateTempFilename(f"{temp_prefix}.shp")
		alg_params = {
			'LAYERS': vecs,
			'CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
			'OUTPUT': merge_shp
		}
		merged = processing.run('native:mergevectorlayers', alg_params, context=context, feedback=feedback,	is_child_algorithm=True)['OUTPUT']

		# Load merged result as QgsVectorLayer
		merged_layer = QgsVectorLayer(merged, f"{temp_prefix}_merged", "ogr")

		# Create spatial index
		processing.run('native:createspatialindex', {'INPUT': merged_layer}, context=context, feedback=None, is_child_algorithm=True)
		return merged_layer

	def compute_landuse_areas(self, landuse_raster, basin_layer, context, feedback):
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
			zonalhist = processing.run('qgis:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			return zonalhist

	def buffer_streams(self, buffer, watershed, context, feedback):
			# Input: Buffer layer, watershed layer
			# Output: Buffered watershed layer

			# Intersect watershed and buffer layers
			alg_params = {
				'INPUT': watershed,
				'OVERLAY': buffer,
				'OUTPUT': 'memory:ws_buff'
			}
			ws_buff = processing.run('qgis:intersection', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

			# Dissolve intersected layer by buffer fid
			alg_params = {
				'INPUT': ws_buff,
				'FIELD': ['fid'],
				'OUTPUT': 'memory:ws_dissolved'
			}
			ws_dissolved = processing.run('native:dissolve', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
			return ws_dissolved