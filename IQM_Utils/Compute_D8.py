"""
Model exported as python.
Name : compute_d8_GRHQ
Group :
With QGIS : 33000
"""

from qgis.PyQt.QtCore import QCoreApplication
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
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'MNT LiDAR (10 m)', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Réseau hydrographique (CRHQ)', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
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
        return self.tr('Calcule pointeur D8')

    def group(self):
        return 'IQM_utils'

    def groupId(self):
        return 'iqmutils'

    def shortHelpString(self):
        return self.tr(
            "Extrait une grille de pointeurs de flux pour le bassin versant donné à l'aide d'un modèle numérique de terrain\n" \
            "Paramètres\n" \
            "----------\n" \
            "MNT LiDAR (10 m) : Matriciel\n" \
            "-> Modèle numérique de terrain par levés aériennes LiDAR de résolution de 1 m rééchantilloné à 10 m pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Lidar - Modèles numériques (terrain, canopée, pente, courbe de niveau), [Jeu de données], dans Données Québec.\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "WBT D8 Pointer: Matriciel\n" \
            "-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools)."
        )

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return Compute_d8()
