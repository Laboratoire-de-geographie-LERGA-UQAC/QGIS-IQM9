from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterFeatureSink
import processing


class Renewed_compute_iqm(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('bande_riv', 'Bande riveraine', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('barrages', 'Barrages', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('cours_eau', 'Réseau hydrographique', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'MNT', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('ptref__largeur', 'PtRef - Largeur', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('routes', 'Routes', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('structures', 'Structures', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('utilisation_du_territoir', 'Utilisation du territoir', defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Iqm', 'Output', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(9, model_feedback)
        results = {}
        outputs = {}

        # Calcul pointeur D8
        alg_params = {
            'dem': parameters['dem'],
            'stream_network': parameters['cours_eau'],
            'D8pointer': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CalculPointeurD8'] = processing.run('script:computed8', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Filtrer structures
        alg_params = {
            'cours_eau': parameters['cours_eau'],
            'routes': parameters['routes'],
            'structures': parameters['structures'],
            'New_structures': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FiltrerStructures'] = processing.run('script:filterstructures', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}
        # A1 A2 A3 F1
        alg_params = {
            'd8': outputs['CalculPointeurD8']['D8pointer'],
            'dams': parameters['barrages'],
            'landuse': parameters['utilisation_du_territoir'],
            'ptrefs_largeur': parameters['ptref__largeur'],
            'stream_network': parameters['cours_eau'],
            'structures': outputs['FiltrerStructures']['New_structures'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['A1A2A3F1'] = processing.run('script:calculA123', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        # outputs["A1A2A3F1"] = {"OUTPUT": parameters["cours_eau"]}

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Indice A4
        alg_params = {
            'INPUT': outputs['A1A2A3F1']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IndiceA4'] = processing.run('script:indicea4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Indice F2
        alg_params = {
            'antropic_layers': parameters['routes'],
            'landuse': parameters['utilisation_du_territoir'],
            'ptref_widths': parameters['ptref__largeur'],
            'rivnet': outputs['IndiceA4']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IndiceF2'] = processing.run('script:indicef2', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Indice F3
        alg_params = {
            'antropic_layers': parameters['routes'],
            'landuse': parameters['utilisation_du_territoir'],
            'ptref_widths': parameters['ptref__largeur'],
            'rivnet': outputs['IndiceF2']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IndiceF3'] = processing.run('script:indicef3', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Indice F4
        alg_params = {
            'ptref_widths': parameters['ptref__largeur'],
            'ratio': 2.5,
            'rivnet': outputs['IndiceF3']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IndiceF4'] = processing.run('script:indicef4', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(7)
        if feedback.isCanceled():
            return {}

        # Indice F5
        alg_params = {
            'bande_riveraine_polly': parameters['bande_riv'],
            'ptref_widths': parameters['ptref__largeur'],
            'ratio': 2.5,
            'rivnet': outputs['IndiceF4']['OUTPUT'],
            'transectsegment': 25,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['IndiceF5'] = processing.run('script:indicef5', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(8)
        if feedback.isCanceled():
            return {}

        # Field calculator
        alg_params = {
            'FIELD_LENGTH': 2,
            'FIELD_NAME': 'Score IQM',
            'FIELD_PRECISION': 2,
            'FIELD_TYPE': 0,  # Décimal (double)
            'FORMULA': '1 - (array_sum(array( "Indice A1",  "Indice A2" ,  "Indice A3" ,  "Indice A4" ,  "Indice F1" ,  "Indice F2" ,  "Indice F3" ,  "Indice F4" ,  "Indice F5"))) / 38',
            'INPUT': outputs['IndiceF5']['OUTPUT'],
            'OUTPUT': parameters['Iqm']
        }
        outputs['FieldCalculator'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Iqm'] = outputs['FieldCalculator']['OUTPUT']
        return results

    def name(self):
        return 'calculiqm'

    def displayName(self):
        return 'Calcul IQM'

    def group(self):
        return 'IQM Automatique'

    def groupId(self):
        return 'iqm_auto'

    def createInstance(self):
        return Renewed_compute_iqm()
