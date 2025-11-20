
import processing
from pathlib import Path
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProject,
	QgsProcessingUtils,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterRasterLayer,
	QgsProcessingMultiStepFeedback,
	QgsProcessingAlgorithm,
	QgsVectorLayer,
	QgsFeatureSink,
	QgsProcessingParameterFeatureSink
)


class Extract_sub_watershed_landuse(QgsProcessingAlgorithm):
	# Parameter identification constants 
	OUTPUT = 'OUTPUT'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=False, defaultValue=None))


	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(12, model_feedback)
		outputs = {}

		feedback.setProgressText(self.tr(f"Polygonisation du bassin versant."))
		try :
			# Extract and snap outlets
			feedback.setProgressText(self.tr(f"Extraction and snap outlet."))
			alg_params = {
				'dem': parameters['D8'],
				'stream_network': parameters['stream_network'],
				'snapped_outlets': QgsProcessingUtils.generateTempFilename("snappedoutlets.shp"),
			}
			outputs['snappedoutlets'] = processing.run('script:extractandsnapoutlets', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(1)
			# Generate watershed polygon
			feedback.setProgressText(self.tr(f"Generate watershed polygon."))
			watersheds = generate_basin_polygons(parameters['D8'], outputs['snappedoutlets'], temp_prefix="watersheds", CRS=QgsProject.instance().crs(), context=context, feedback=None)
			feedback.setCurrentStep(2)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la polygonisation du bassin versant : {str(e)}"))

		if feedback.isCanceled():
			return {}

		feedback.setProgressText(self.tr(f"Traitement polygones pour les barrages."))
		try :
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
			watersheds = processing.run('native:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(4)
			# Reclassify landuse
			feedback.setProgressText(self.tr(f"Reclassify landuse."))
			outputs['reclassifiedlanduse'] = reduce_landuse(parameters['landuse'], context, feedback=None) # peut-être que ça me marcheras pas avec le changement de param
			feedback.setCurrentStep(3)
			# Compute landuse area for each watershed
			watersheds = compute_landuse_areas(outputs['reclassifiedlanduse'], watersheds, context=context, feedback=None)
			feedback.setCurrentStep(4)
			# Remove duplicate dam points
			alg_params = {
				'INPUT': parameters['dams'],
				'OUTPUT': 'memory:dams_edited'
			}
			dams_edited = processing.run('native:deleteduplicategeometries', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(5)
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
			outputs['dams_edited'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(6)
			# Generate dam watershed polygon
			damsheds = generate_basin_polygons(parameters['D8'], outputs['dams_edited'], temp_prefix="damwatersheds", CRS=QgsProject.instance().crs(), context=context, feedback=None)
			feedback.setCurrentStep(7)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans traitement polygones pour barrages : {str(e)}"))

		if feedback.isCanceled():
			return {}

		feedback.setProgressText(self.tr(f"Calcul superficie des barrages."))
		try :
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
			outputs['damsheds_area'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(8)
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
			dams_points_area = processing.run('native:joinattributestable', alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(9)
			processing.run('native:createspatialindex', {'INPUT': dams_points_area}, context=context, feedback=None, is_child_algorithm=True)
			feedback.setCurrentStep(10)
			# Locate dam points in watersheds and sum total dam area per watershed
			# 'memory:watersheds'
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
			watersheds = processing.run("qgis:joinbylocationsummary", alg_params, context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
			feedback.setCurrentStep(11)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans calcul superficie barrage : {str(e)}"))

		if feedback.isCanceled():
			return {}

		# Returning the processed watershed layer
		feedback.setProgressText(self.tr(f"Création de la couche de résultats"))
		try :
			watersheds_layer = QgsProcessingUtils.mapLayerFromString(watersheds, context)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la sortie des résultats : {str(e)}"))

		if watersheds_layer and watersheds_layer.isValid():
			(sink, dest_id) = self.parameterAsSink(
				parameters,
				self.OUTPUT,
				context,
				watersheds_layer.fields(),
				watersheds_layer.wkbType(),
				watersheds_layer.sourceCrs()
			)
			try :
				for feat in watersheds_layer.getFeatures():
					sink.addFeature(feat, QgsFeatureSink.FastInsert)
				# Ending message
				feedback.setProgressText(self.tr('\tProcessus terminé !'))
				return {self.OUTPUT: dest_id}
			except Exception as e :
				feedback.reportError(self.tr(f"Erreur dans sink des features finaux : {str(e)}"))
			return {self.OUTPUT: dest_id}
		else:
			feedback.reportError(self.tr("La couche watersheds est invalide."))
			return {}


	def tr(self, string):
		return QCoreApplication.translate('Processing', string)


	def name(self):
		return 'extract_subwatershed'


	def displayName(self):
		return self.tr("Extract sous-BV et landuse (A123)")


	def group(self):
		return self.tr('IQM utils')


	def groupId(self):
		return 'iqmutils'


	def shortHelpString(self):
		return self.tr(
			"Extraction des sous bassins versants et utilisation du territoire\n Script préparatoire pour les indices A1 et A2 qui extrait les sous bassin versant du réseau hydrographique et sur l'utilisation du territoire en une couche vectorielle\n" \
			"Paramètres\n" \
			"----------\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"WBT D8 Pointer: Matriciel\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Barrages : Vectoriel (point)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (polygones)\n" \
			"-> Bassin versant donné divisé en sous bassin versant."
		)


	def createInstance(self):
		return Extract_sub_watershed_landuse()

# Helper functions 
def generate_basin_polygons(d8_pointer, pour_points, temp_prefix, CRS, context, feedback):
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
		poly = processing.run('gdal:polygonize', {
			'BAND': 1,
			'EIGHT_CONNECTEDNESS': True,
			'EXTRA': '',
			'FIELD': 'DN',
			'INPUT': str(ras),
			'OUTPUT': shp
			}, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
		# Fix geometries and return layer
		# 
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
		'CRS': CRS,
		'OUTPUT': merge_shp
	}
	merged = processing.run('native:mergevectorlayers', alg_params, context=context, feedback=feedback,	is_child_algorithm=True)['OUTPUT']
	# Load merged result as QgsVectorLayer
	merged_layer = QgsVectorLayer(merged, f"{temp_prefix}_merged", "ogr")
	# Create spatial index
	processing.run('native:createspatialindex', {'INPUT': merged_layer}, context=context, feedback=None, is_child_algorithm=True)
	return merged_layer


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


def reduce_landuse(parameters, context, feedback):
	# INPUT : parameters
	# OUTPUT : layer_id
	CLASSES = [
		'50','56','1','210','235','1','501','735','1', #Forestiers
		'60', '77', '1', '30', '31', '1', #Sols nues
		'250', '261', '1', '263', '280', '1', # Coupes de regeneration
		'101','199','2', #Agricoles
		'300', '360', '3', #Anthropisé
		'20', '27', '4',
		'2000', '9000', '1' #Milieux humides
	]
	# Reclassify land use
	alg_params = {
		'DATA_TYPE': 0,  # Byte
		'INPUT_RASTER': parameters, # 'landuse'
		'NODATA_FOR_MISSING': True,
		'NO_DATA': 0,
		'RANGE_BOUNDARIES': 2,  # min <= value <= max
		'RASTER_BAND': 1,
		'TABLE': CLASSES,
		'OUTPUT': QgsProcessingUtils.generateTempFilename("landuse.tif"),
	}
	return processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']