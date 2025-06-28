"""
Model exported as python.
Name : Extract And Snap Outlets
Group :
With QGIS : 33000
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProperty
from qgis.core import QgsProcessingUtils
import processing


class ExtractAndSnapOutlets(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'MNT LiDAR (10 m)', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Réseau hydrologique (CRHQ)', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('snapped_outlets', 'Couche de sortie (Snapped_outlets)', type=QgsProcessing.TypeVectorPoint, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        # Interpolate point on line
        interpolated_points_output = QgsProcessingUtils.generateTempFilename("interpolatedPoints.gpkg")
        alg_params = {
            'DISTANCE': QgsProperty.fromExpression('if(length($geometry) > 100, length($geometry) - 30, length($geometry) * 0.9)'),
            'INPUT': parameters['stream_network'],
            'OUTPUT': interpolated_points_output
        }
        outputs['InterpolatePointOnLine'] = processing.run('native:interpolatepoint', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # RasterizeStreams
        rasterized_streams_output = QgsProcessingUtils.generateTempFilename("rasterizedStreams.tif")
        alg_params = {
            'base': parameters['dem'],
            'feature_id': False,
            'nodata': True,
            'streams': parameters['stream_network'],
            'output': rasterized_streams_output
        }
        outputs['Rasterizestreams'] = processing.run('wbt:RasterizeStreams', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # JensonSnapPourPoints
        alg_params = {
            'pour_pts': outputs['InterpolatePointOnLine']['OUTPUT'],
            'snap_dist': 40,
            'streams': outputs['Rasterizestreams']['output'],
            'output': parameters['snapped_outlets']
        }
        outputs['Jensonsnappourpoints'] = processing.run('wbt:JensonSnapPourPoints', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['OUTPUT'] = outputs['Jensonsnappourpoints']['output']
        return results

    def name(self):
        return 'extractandsnapoutlets'

    def displayName(self):
        return 'Extraction And Snap Outlets'

    def group(self):
        return 'IQM_utils'

    def groupId(self):
        return 'iqmutils'

    def createInstance(self):
        return ExtractAndSnapOutlets()
