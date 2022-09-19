"""
Model exported as python.
Name : network-watershed
Group : 
With QGIS : 32601
"""
import tempfile
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterRasterDestination
import processing


class Networkwatershed(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Stream Network', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Networkwatersheds', 'network-watersheds', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(5, model_feedback)
        results = {}
        outputs = {}
        #tmpout = 'tmp/yopyop.tif'
        tmpFile = tempfile.NamedTemporaryFile(suffix=".tif")
        tmpout = tmpFile.name
        print(tmpout)

        # FillBurn
        alg_params = {
            'dem': parameters['dem'],
            'streams': parameters['stream_network'],
            'output': tmpout
        }
        outputs['Fillburn'] = processing.run('wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Extract specific vertices
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-1',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractSpecificVertices'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # BreachDepressions
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'fill_pits': False,
            'flat_increment': None,
            'max_depth': None,
            'max_length': None,
            'output': tmpout
        }
        outputs['Breachdepressions'] = processing.run('wbt:BreachDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressions']['output'],
            'esri_pntr': False,
            'output': tmpout
        }
        outputs['D8pointer'] = processing.run('wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Watershed
        ## Loop through the elements
        alg_params = {
            'd8_pntr': outputs['D8pointer']['output'],
            'esri_pntr': False,
            'pour_pts': outputs['ExtractSpecificVertices']['OUTPUT'],
            'output': parameters['Networkwatersheds']
        }
        outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Networkwatersheds'] = outputs['Watershed']['output']
        
        tmpFile.close()
        
        return results

    def name(self):
        return 'network-watershed2'

    def displayName(self):
        return 'network-watershed2'

    def group(self):
        return ''

    def groupId(self):
        return ''

    def createInstance(self):
        return Networkwatershed()
