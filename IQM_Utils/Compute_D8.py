"""
Model exported as python.
Name : compute_d8_GRHQ
Group :
With QGIS : 33000
"""

from qgis.core import (
    QgsProcessing,
    QgsProcessingUtils,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterRasterDestination,
)
import processing


class Compute_d8(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Stream Network', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        #self.addParameter(QgsProcessingParameterRasterDestination('D8pointer', 'D8Pointer', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}

        # FillBurn
        alg_params = {
            'dem': parameters['dem'],
            'streams': parameters['stream_network'],
            'output': QgsProcessingUtils.generateTempFilename("fill_burn.tif")
        }
        outputs['Fillburn'] = processing.run('wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # BreachDepressionsLeastCost
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'dist': 5,
            'fill': False,
            'flat_increment': None,
            'max_cost': None,
            'min_dist': True,
            'output': QgsProcessingUtils.generateTempFilename("breach_depression_lc.tif")
        }
        outputs['Breachdepressionsleastcost'] = processing.run('wbt:BreachDepressionsLeastCost', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # BreachDepressions
        alg_params = {
            'dem': outputs['Breachdepressionsleastcost']['output'],
            'fill_pits': True,
            'flat_increment': None,
            'max_depth': None,
            'max_length': None,
            'output': QgsProcessingUtils.generateTempFilename("breach_depression.tif")
        }
        outputs['Breachdepressions'] = processing.run('wbt:BreachDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressions']['output'],
            'esri_pntr': False,
            'output': QgsProcessingUtils.generateTempFilename("d8_pointer.tif")#parameters['D8pointer']
        }
        outputs['D8pointer'] = processing.run('wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['D8pointer'] = outputs['D8pointer']['output']
        return results

    def name(self):
        return 'computed8'

    def displayName(self):
        return 'Calcule pointeur D8'

    def group(self):
        return 'IQM_utils'

    def groupId(self):
        return 'iqmutils'

    def createInstance(self):
        return Compute_d8()
