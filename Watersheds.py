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
    QgsProcessingParameterFeatureSink,
    QgsField,
    QgsFeature,
    QgsFeatureSink,
    QgsFeatureRequest,
    QgsProject,
    )
import processing
from tempfile import NamedTemporaryFile

class NetworkWatershedFromDem(QgsProcessingAlgorithm):
    
    D8 = 'd8'
    WATERSHED = 'watershed'
    OUTLETS = 'outlets'
    STREAM_NET = 'stream_network'
    OUTPUT = 'OUTPUT'
    ID_FIELD = "Id"
    
    def initAlgorithm(self, config=None):
        #self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer(self.D8, 'D8', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(self.STREAM_NET, 'stream_network', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        #self.addParameter(QgsProcessingParameterRasterDestination('Poly_watershed', 'polywatershed', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Output Layer', defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}
        tmp = {
            self.D8 : NamedTemporaryFile(suffix="-D8.tif"),
            self.WATERSHED : NamedTemporaryFile(suffix="-watershed.tif"),
            self.OUTLETS : NamedTemporaryFile(suffix="-outlets.shp"),
        }
        
        
        source = self.parameterAsVectorLayer(parameters, self.STREAM_NET, context)
        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A3", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            QgsWkbTypes.Polygon,
            source.sourceCrs()
        )
        
        """
        # compute_d8_GRHQ
        alg_params = {
            'dem': parameters['dem'],
            'stream_network': parameters['stream_network'],
            'd8pointer': tmp[self.D8].name
        }
        outputs['Compute_d8_grhq'] = processing.run('model:compute_d8_GRHQ', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        """
        
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Extract And Snap Outlets
        alg_params = {
            'dem': parameters[self.D8],
            'stream_network': parameters['stream_network'],
            'snapped_outlets': tmp[self.OUTLETS].name
        }
        outputs['ExtractAndSnapOutlets'] = processing.run('model:Extract And Snap Outlets', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}
        
        outlets = QgsVectorLayer(outputs['ExtractAndSnapOutlets']['snapped_outlets'], 'outlets', "ogr")
        
        for feature in source.getFeatures():
            # Get feature Id
            fid = feature[self.ID_FIELD]
            segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
            
            alg_params = {
                'FIELD': self.ID_FIELD,
                'INPUT': outputs['ExtractAndSnapOutlets']['snapped_outlets'],
                'OPERATOR': 0,  # =
                'VALUE': str(fid),
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }

            outputs['SegmentOutlet'] = processing.run(
                'native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            QgsProject.instance().addMapLayer(context.takeResultLayer(outputs['single_outlet']['OUTPUT']))
            
            # comput segment Watershed
            alg_params = {
                #'d8_pntr': outputs['Compute_d8_grhq']['d8pointer'],
                'd8_pntr': parameters[self.D8],
                'esri_pntr': False,
                'pour_pts': outputs['SegmentOutlet']['OUTPUT'],
                'output': tmp[self.WATERSHED].name
            }
            outputs['SegmentWatershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Polygonize Segment watershed(raster to vector)
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['SegmentWatershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            watershed_poly = QgsVectorLayer(outputs['PolygonizeRasterToVector']['OUTPUT'], 'watershed poly', 'ogr')
            QgsProject.instance().addMapLayer(watershed_poly)
            

        for file in tmp.values():
            file.close()
        
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
