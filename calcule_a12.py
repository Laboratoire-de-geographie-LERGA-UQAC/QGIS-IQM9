"""
Model exported as python.
Name : Indice A1 A2
Group : 
With QGIS : 32601
"""
from tempfile import NamedTemporaryFile as Ntf
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsCoordinateReferenceSystem
import processing


class IndiceA1A2(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'landuse', defaultValue=None))
        #self.addParameter(QgsProcessingParameterNumber('outlet_fid', 'outlet_FID', type=QgsProcessingParameterNumber.Integer, minValue=0, defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Stream Network', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        #self.addParameter(QgsProcessingParameterFeatureSink('Single_outlet', 'Single_outlet', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))
        #self.addParameter(QgsProcessingParameterFeatureSink('Report', 'report', optional=True, type=QgsProcessing.TypeVector, createByDefault=False, defaultValue=None))
        #self.addParameter(QgsProcessingParameterRasterDestination('Tmpreclassifiedtif', '/tmp/reclassified.tif', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        results = {}
        outputs = {}
        
        # Create temporary file locations
        tmp = {}
        
        # Create tmp File #1 for D8 Creation
        tmp['d8'] = Ntf(suffix="d8.tif")
        
        
        
        # WBT : Create D8 from dem
        # FillBurn
        alg_params = {
            'dem': parameters['dem'],
            'streams': parameters['stream_network'],
            'output': tmp['d8'].name
        }
        outputs['Fillburn'] = processing.run('wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
        
        print(outputs)
        quit()
        
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # FillDepressions
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'fix_flats': True,
            'flat_increment': None,
            'max_depth': None,
            'output': tmp['d8'].name
        }
        outputs['Filldepressions'] = processing.run('wbt:FillDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # BreachDepressionsLeastCost
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'dist': 10,
            'fill': True,
            'flat_increment': None,
            'max_cost': None,
            'min_dist': False,
            'output': tmp['d8'].name
        }
        outputs['Breachdepressionsleastcost'] = processing.run('wbt:BreachDepressionsLeastCost', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressionsleastcost']['output'],
            'esri_pntr': False,
            'output': tmp['d8'].name
        }
        outputs['D8pointer'] = processing.run('wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}
        
        # D8 Created #
        
        
        
        # Extract specific vertex
        # TODO : try and remove is_child_algorithm
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-2',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractSpecificVertex'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}
        
        ############ LOOP GOES HERE ############
        
        # Extract Single outlet
        alg_params = {
            'FIELD': 'fid',
            'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
            'OPERATOR': 0,  # =
            'VALUE': parameters['outlet_fid'],
            'OUTPUT': parameters['Single_outlet']
        }
        outputs['ExtractSingleOutlet'] = processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Single_outlet'] = outputs['ExtractSingleOutlet']['OUTPUT']

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}
        
        # Watershed
        alg_params = {
            'd8_pntr': outputs['D8pointer']['output'],
            'esri_pntr': False,
            'pour_pts': outputs['ExtractSingleOutlet']['OUTPUT'],
            'output': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Polygonize (raster to vector)
        alg_params = {
            'BAND': 1,
            'EIGHT_CONNECTEDNESS': False,
            'EXTRA': '',
            'FIELD': 'DN',
            'INPUT': outputs['Watershed']['output'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Drain_area Land_use
        alg_params = {
            'ALPHA_BAND': False,
            'CROP_TO_CUTLINE': True,
            'DATA_TYPE': 0,  # Use Input Layer Data Type
            'EXTRA': '',
            'INPUT': parameters['landuse'],
            'KEEP_RESOLUTION': True,
            'MASK': outputs['PolygonizeRasterToVector']['OUTPUT'],
            'MULTITHREADING': False,
            'NODATA': None,
            'OPTIONS': '',
            'SET_RESOLUTION': False,
            'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
            'TARGET_CRS': 'ProjectCrs',
            'TARGET_EXTENT': None,
            'X_RESOLUTION': None,
            'Y_RESOLUTION': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(9)
        if feedback.isCanceled():
            return {}

        # Reduced Landuse
        alg_params = {
            'DATA_TYPE': 0,  # Byte
            'INPUT_RASTER': outputs['Drain_areaLand_use']['OUTPUT'],
            'NODATA_FOR_MISSING': True,
            'NO_DATA': 0,
            'RANGE_BOUNDARIES': 2,  # min <= value <= max
            'RASTER_BAND': 1,
            'TABLE': ['50','56','1','210','235','1','501','735','1','101','199','2'],
            'OUTPUT': parameters['Tmpreclassifiedtif']
        }
        outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Tmpreclassifiedtif'] = outputs['ReducedLanduse']['OUTPUT']

        feedback.setCurrentStep(10)
        if feedback.isCanceled():
            return {}

        # Landuse unique values report
        alg_params = {
            'BAND': 1,
            'INPUT': outputs['ReducedLanduse']['OUTPUT'],
            'OUTPUT_TABLE': parameters['Report']
        }
        outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Report'] = outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE']
        
        # Clearing tem files
        for file in tmp.values():
            file.close()
        
        return results

    def name(self):
        return 'Indice A1 A2'

    def displayName(self):
        return 'Indice A1 A2'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return IndiceA1A2()
