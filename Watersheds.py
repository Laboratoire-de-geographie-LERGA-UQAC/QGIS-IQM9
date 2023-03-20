"""
Model exported as python.
Name : Network Watershed from DEM
Group :
With QGIS : 33000
"""

from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import (
    QgsVectorLayer,
    QgsRasterLayer,
    QgsWkbTypes,
    QgsProcessingUtils,
    QgsProject,
    QgsProcessingParameterFeatureSink,
    QgsField,
    QgsFeature,
    QgsFeatureSink,
    QgsFeatureRequest,
    QgsCoordinateReferenceSystem,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    )
import processing


import logging
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename="tmp/watershedsLog.log",
                                     level=logging.DEBUG,
                                     format=LOG_FORMAT,
                                     filemode='w')
logger = logging.getLogger()
logger.info("Algo start")


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
        self.addParameter(QgsProcessingParameterRasterLayer(self.D8, 'D8', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer(self.LANDUSE, 'LandUse', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(self.STREAM_NET, 'Cours d\'eau', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(self.DAMS, 'Barrages', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(self.STRUCTS, 'Structures', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(self.PTREFS, 'PtRefs - Largeur', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Output Layer', defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}


        source = self.parameterAsVectorLayer(parameters, self.STREAM_NET, context)
        # Define Sink fields
        new_fields = [
            QgsField("Indice A1", QVariant.Int),
            QgsField("Indice A2", QVariant.Int),
            QgsField("Indice A3", QVariant.Int),
            QgsField("Indice F1", QVariant.Int),
        ]
        sink_fields = source.fields()
        [sink_fields.append(field) for field in new_fields]

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}



        # Extract And Snap Outlets
        alg_params = {
            'dem': parameters[self.D8],
            'stream_network': parameters['stream_network'],
            'snapped_outlets': QgsProcessingUtils.generateTempFilename("outlets.shp"),
        }
        outputs['SnappedOutlets'] = processing.run('model:Extract And Snap Outlets', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['snapped_outlets']
        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}
        outlets = QgsVectorLayer(outputs['SnappedOutlets'], 'outlets', "ogr")


        # Reclassify Landuse
        outputs['ReclassifiedLanduse'] = self.reduce_landuse(parameters, context, feedback)


        for feature in source.getFeatures():
            logger.info(f"\n\n\nSegment : {feature['segment']} / {source.featureCount()}")

            logger.info("\n"*3+f"Started segment {feature['segment']}")
            # Get feature Id
            fid = feature[self.ID_FIELD]

            alg_params = {
                'FIELD': self.ID_FIELD,
                'INPUT': outputs['SnappedOutlets'],
                'OPERATOR': 0,  # =
                'VALUE': str(fid),
                'OUTPUT':  QgsProcessingUtils.generateTempFilename("outlet.shp")
            }
            outputs['SegmentOutlet'] = processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
            logger.info(f"Got the vertex")


            # comput segment Watershed
            alg_params = {
                #'d8_pntr': outputs['Compute_d8_grhq']['d8pointer'],
                'd8_pntr': parameters[self.D8],
                'esri_pntr': False,
                'pour_pts': outputs['SegmentOutlet'],
                'output': QgsProcessingUtils.generateTempFilename("watershed.tif")
            }
            outputs['SegmentWatershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['output']
            #Polygonize Watershed
            outputs['VectorWatershed'] = self.polygonize_raster(outputs['SegmentWatershed'], context, feedback, output=QgsProcessingUtils.generateTempFilename("vector1.shp"))


            logger.info(f"Got the watershed")


            # Compute watershed Area
            watershed_area = self.get_poly_area(outputs['VectorWatershed'], context, feedback)
            logger.info(f"Polygonized It")
            # A1 Specific Part
                #Clip landuse
                #Landuse unique values report
                # Function to parse unique value report
            (land_area, anthro_area, agri_area, forest_area) = self.compute_landuse_areas(outputs['ReclassifiedLanduse'], outputs['VectorWatershed'], context, feedback)
                #Compute A1
            indiceA1 = self.computeA1(land_area, anthro_area, agri_area, forest_area)
            logger.info(f"Computed A1")



            logger.info(f"\nA2 part: ")
            # A2 Specific Part
                # Clip DAMS
            segment_dams = self.clip_points_to_poly(parameters[self.DAMS],outputs['VectorWatershed'], context, feedback)
            logger.info(f"Cliped the points")

                # Compute Dam watershed
                #Compute dam_wshed area
            alg_params = {
                #'d8_pntr': outputs['Compute_d8_grhq']['d8pointer'],
                'd8_pntr': parameters[self.D8],
                'esri_pntr': False,
                'pour_pts': segment_dams,
                'output': QgsProcessingUtils.generateTempFilename("subwshed.tif"),
            }
            outputs['DamsWatershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['output']
            logger.info(f"Got dams watershed")

            #Polygonize Watershed
            outputs['VectorDamsWatershed'] = self.polygonize_raster(outputs['DamsWatershed'], context, feedback, QgsProcessingUtils.generateTempFilename("vector2.shp"),)
            logger.info(f"Polygonize dat too")

            #QgsProject.instance().addMapLayer(QgsVectorLayer(outputs['VectorDamsWatershed'], "Dams_Watershed", "ogr"))
            dams_area = self.get_poly_area(outputs['VectorDamsWatershed'], context, feedback)
            logger.info(f"computed dams area")
            indiceA2 = self.computeA2(watershed_area, dams_area)
            logger.info(f"Computed A2")


            logger.info(f"\nA3/F1 Part :")
            # A3 F1 join Part
                #Create 1km buffer
                # 1 Km buffer around river
            segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
            alg_params = {
                'INPUT': segment,
                'DISTANCE':1000,
                'SEGMENTS':5,'END_CAP_STYLE':0,
                'JOIN_STYLE':0,'MITER_LIMIT':2,
                'DISSOLVE':True,
                'OUTPUT': QgsProcessingUtils.generateTempFilename("Buffer_1km")
            }
            outputs['Buffer_1km'] = processing.run("native:buffer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
            logger.info(f"Got 1km buffer")
                # Clip watershed by buffer
            alg_params = {
                'INPUT': outputs['VectorWatershed'],
                'OVERLAY': outputs['Buffer_1km'],
                'OUTPUT': QgsProcessingUtils.generateTempFilename("buffer2.shp"),
                }
            outputs['Watershed_1km'] = processing.run("native:clip", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
            logger.info(f"Clipped it to watershed")
            #QgsProject.instance().addMapLayer(context.takeResultLayer(outputs['Watershed_1km']))
                # count number of dams -> A3 Penalty
            # Count number of dames in watershed
            dams = self.parameterAsVectorLayer(parameters, self.DAMS, context)
            alg_params = {
                'INPUT':dams,
                'PREDICATE':[6],
                'INTERSECT':outputs['Watershed_1km'],
                'METHOD':0
            }
            processing.run("native:selectbylocation", alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            dam_count_1km = dams.selectedFeatureCount()
            logger.info(f"Counted dams")

                # Count number of structurs -> Compute F1
            structs = self.parameterAsVectorLayer(parameters, self.STRUCTS, context)
            alg_params = {
                'INPUT':structs,
                'PREDICATE':[6],
                'INTERSECT':outputs['Watershed_1km'],
                'METHOD':0
            }
            processing.run("native:selectbylocation", alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            struct_count = structs.selectedFeatureCount()
            logger.info(f"Count structures")
            indiceF1 = self.computeF1(feature, struct_count)
            logger.info(f"Computed F1")


            logger.info(f"\nA3 Part :")
            #A3 specific part
                # Create 2x river Buffer
            feature_mean_width = self.ptrefs_mean_width(feature, source, parameters[self.PTREFS])
            logger.info(f"Computed mean width")
            params = {
                'INPUT':segment,
                'DISTANCE':feature_mean_width * 2.5,
                'SEGMENTS':5,'END_CAP_STYLE':1,'JOIN_STYLE':1,'MITER_LIMIT':2,'DISSOLVE':False,
                'OUTPUT' : QgsProcessingUtils.generateTempFilename("Buffer2.shp")
            }
            outputs['SegmentBuffer'] = processing.run("native:buffer", params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
            logger.info(f"Created buffer")
                # Landuse area report -> A3
            (land_area, anthro_area, agri_area, forest_area) = self.compute_landuse_areas(outputs['ReclassifiedLanduse'], outputs['SegmentBuffer'], context, feedback)

            indiceA3 = self.computeA3(land_area, anthro_area,agri_area,dam_count_1km)
            logger.info(f"Computed A3")
            logger.info(f"{indiceA1=}, {indiceA2=},{indiceA3=}, {indiceF1=}")

            # Add forest area to new featuer
            feature.setAttributes(
                    feature.attributes() + [indiceA1, indiceA2, indiceA3, indiceF1]
            )

            logger.info(f"\t\tFinished segment {feature['segment']}")
            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

        return {self.OUTPUT : dest_id}

    def name(self):
        return 'watershedrework'

    def displayName(self):
        return 'Watershed rework'

    def group(self):
        return 'testing'

    def groupId(self):
        return 'testing'

    def createInstance(self):
        return NetworkWatershedFromDem()

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
        reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
        return reclass

    def polygonize_raster(self, raster_id ,context, feedback, output=None):
        # Inputs : Raster ID
        # Output : layer_id
        alg_params = {
            'BAND': 1,
            'EIGHT_CONNECTEDNESS': False,
            'EXTRA': '',
            'FIELD': 'DN',
            'INPUT': raster_id,
            'OUTPUT': output
        }
        return processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    def clip_raster(self, raster_id, mask_id, context, feedback, output=None):

        alg_params = {
        'ALPHA_BAND': False,
        'CROP_TO_CUTLINE': True,
        'DATA_TYPE': 0,  # Use Input Layer Data Type
        'EXTRA': '',
        'INPUT': raster_id,
        'KEEP_RESOLUTION': True,
        'MASK': mask_id,
        'MULTITHREADING': False,
        'NODATA': None,
        'OPTIONS': '',
        'SET_RESOLUTION': False,
        'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
        'TARGET_CRS': 'ProjectCrs',
        'TARGET_EXTENT': None,
        'X_RESOLUTION': None,
        'Y_RESOLUTION': None,
        'OUTPUT' : QgsProcessingUtils.generateTempFilename("Raster_clip.tif")
        }
        return processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    def compute_landuse_areas(self, clipped_landuse_id, mask_id, context, feedback):
        # Clip Raster
        clipped = self.clip_raster(clipped_landuse_id, mask_id, context, feedback)

        alg_params = {
            'BAND': 1,
            'INPUT': clipped,
            'OUTPUT_TABLE': QgsProcessingUtils.generateTempFilename("table.shp"),
        }
        table = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT_TABLE']
        table = QgsVectorLayer(table, 'table', 'ogr')

        class_areas = {feat['value']:feat['m2'] for feat in table.getFeatures()}
        water_area = class_areas.get(4, 0)
        anthro_area = class_areas.get(3, 0)
        agri_area = class_areas.get(2, 0)
        forest_area = class_areas.get(1, 0)
        land_area = anthro_area + agri_area + forest_area
        return (land_area, anthro_area, agri_area, forest_area)

    def get_poly_area(self, vlayer_id, context, feedback):
        vlayer = QgsVectorLayer(vlayer_id, "Poly", "ogr")
        tot_area = sum([feat.geometry().area() for feat in vlayer.getFeatures()])
        return tot_area

    def clip_points_to_poly(self,points_id, polygon_id, context, feedback, output=None):
        # Clip Dams
        alg_params = {
            'INPUT': points_id,
            'INTERSECT': polygon_id,
            'PREDICATE': [6],  # are within
            'OUTPUT': QgsProcessingUtils.generateTempFilename("Dams_clip.shp")
        }

        extracted_dams = processing.run('native:extractbylocation', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
        return extracted_dams

    def computeA1(self, land_area, anthro_area, agri_area, forest_area):

        if land_area == 0:
            return 2
        forest_ratio = forest_area / land_area
        agri_ratio = agri_area / land_area
        logger.info(f"""
        Computing A1:
            {land_area=}
            {agri_area=}
            {forest_area=}

            {forest_ratio=}
            {agri_ratio=}
        """)
        if forest_ratio <= 0.1:
            return 5
        elif forest_ratio < 0.33:
            return 4
        elif forest_ratio <= 0.66:
            return 3 if agri_ratio < 0.33 else 2
        elif forest_ratio < 0.9:
            return 1
        else:
            return 0

    def computeA2(self, main_area, dams_area):
        if main_area == 0 :
            return 2
        ratio = dams_area / main_area

        logger.info(f"""
        Computing A2:
            {main_area=}
            {dams_area=}
            {ratio=}
        """)
        if ratio < 0.05:
            return 0
        elif 0.05 <= ratio < 0.33:
            return 2
        elif 0.33 <= ratio < 0.66:
            return 3
        elif 0.66 <= ratio:
            return 4

    def computeF1(self, feature, struct_count):
        length = feature.geometry().length()
        if not length or not struct_count:
            return 0

        ratio = struct_count / length * 1000
        logger.info(f"""
        Computing F1:
            {length=}
            {struct_count=}
            {ratio=}
        """)
        if ratio <= 1:
            return 2
        elif ratio > 1:
            return 4

    def ptrefs_mean_width(self, feature, source, PtRef_id, width_field='Largeur_mod', context=None, feedback=None):
        expr = QgsExpression(f"""
                array_mean(overlay_nearest('{PtRef_id}', {width_field}, limit:=-1, max_distance:=5))
                    """)
        feat_context = QgsExpressionContext()
        feat_context.setFeature(feature)

        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(source)
        feat_context.appendScopes(scopes)

        mean_width = expr.evaluate(feat_context)
        if not mean_width : mean_width = 5

        return mean_width

    def computeA3(self, land_area, anthro_area, agri_area, dam_count):

        dam_penality = 0
        if dam_count == 1:
            dam_penality = 2
        elif dam_count > 1:
            dam_penality = 4

        if land_area == 0:
            return dam_penality + 2

        ratio = (anthro_area + agri_area) / land_area
        logger.info(f"""
        Computing A3:
            {dam_count=}
            {anthro_area + agri_area=}
            {land_area=}
            {ratio=}

            if {agri_area=} was not computed :
            ratio={(anthro_area) / land_area}
        """)
        if ratio >= 0.9:
            return dam_penality + 4
        elif ratio >= 0.66:
            return dam_penality + 3
        elif ratio >= 0.33:
            return dam_penality + 2
        elif ratio >= 0.1:
            return dam_penality + 1
        return dam_penality
