"""
Model exported as python.
Name : TEST_vector_watershed
Group :
With QGIS : 33000
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsProcessingUtils
import processing


class Test_vector_watershed(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('d8_pointer', 'D8 Pointer', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('points', 'Points', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Vectorized', 'Vectorized', type=QgsProcessing.TypeVectorPolygon, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(2, model_feedback)
        results = {}
        outputs = {}

        # Watershed
        alg_params = {
            'd8_pntr': parameters['d8_pointer'],
            'esri_pntr': False,
            'pour_pts': parameters['points'],
            'output': QgsProcessingUtils.generateTempFilename("watershed.tif")
        }
        outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        print(outputs['Watershed'])

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Polygonize (raster to vector)
        alg_params = {
            'BAND': 1,
            'EIGHT_CONNECTEDNESS': False,
            'EXTRA': '',
            'FIELD': 'DN',
            'INPUT': outputs['Watershed']['output'],
            'OUTPUT': parameters['Vectorized']
        }
        outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        print(outputs['PolygonizeRasterToVector'])
        results['Vectorized'] = outputs['PolygonizeRasterToVector']['OUTPUT']
        return results

    def name(self):
        return 'TEST_vector_watershed'

    def displayName(self):
        return 'TEST_vector_watershed'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return Test_vector_watershed()
