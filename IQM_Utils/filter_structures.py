"""
Model exported as python.
Name : Add structures
Group :
With QGIS : 33000
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsCoordinateReferenceSystem
import processing


class AddStructures(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('cours_eau', 'Réseau hydrographique (CRHQ)', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('routes', 'Réseau routier (OSM)', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('structures', 'Structures (MTMD)', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('New_structures', 'Couche de sortie (New_structures)', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(6, model_feedback)
        results = {}
        outputs = {}

        # Line intersections
        alg_params = {
            'INPUT': parameters['cours_eau'],
            'INPUT_FIELDS': ['""'],
            'INTERSECT': parameters['routes'],
            'INTERSECT_FIELDS': [''],
            'INTERSECT_FIELDS_PREFIX': '',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['LineIntersections'] = processing.run('native:lineintersections', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Merged structures
        alg_params = {
            'CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
            'LAYERS': [parameters['structures'],outputs['LineIntersections']['OUTPUT']],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['MergedStructures'] = processing.run('native:mergevectorlayers', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Buffer
        alg_params = {
            'DISSOLVE': False,
            'DISTANCE': 50,
            'END_CAP_STYLE': 0,  # Rond
            'INPUT': outputs['MergedStructures']['OUTPUT'],
            'JOIN_STYLE': 0,  # Rond
            'MITER_LIMIT': 2,
            'SEGMENTS': 5,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Buffer'] = processing.run('native:buffer', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Dissolve
        alg_params = {
            'FIELD': [''],
            'INPUT': outputs['Buffer']['OUTPUT'],
            'SEPARATE_DISJOINT': True,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Dissolve'] = processing.run('native:dissolve', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Centroids
        alg_params = {
            'ALL_PARTS': False,
            'INPUT': outputs['Dissolve']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Centroids'] = processing.run('native:centroids', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Extract within distance
        alg_params = {
            'DISTANCE': 100,
            'INPUT': outputs['Centroids']['OUTPUT'],
            'REFERENCE': parameters['cours_eau'],
            'OUTPUT': parameters['New_structures']
        }
        outputs['ExtractWithinDistance'] = processing.run('native:extractwithindistance', alg_params, context=context, feedback=None, is_child_algorithm=True)
        results['New_structures'] = outputs['ExtractWithinDistance']['OUTPUT']
        return results

    def name(self):
        return 'filterstructures'

    def displayName(self):
        return 'Filtrer structures'

    def group(self):
        return self.tr('IQM utils')

    def groupId(self):
        return 'iqmutils'

    def shortHelpString(self):
        return self.tr(
            "Sort les structures et les infrastructures routières qui coincide ou qui sont proche du cours d'eau (vérif).\n" \
            "Paramètres\n" \
            "----------\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Réseau routier : Vectoriel (lignes)\n" \
            "-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
            "Structures : Vectoriel (points)\n" \
            "-> Ensemble de données vectorielles ponctuelles des structures sous la gestion du Ministère des Transports et de la Mobilité durable du Québec (MTMD) (pont, ponceau, portique, mur et tunnel). Source des données : MTMD. Structure, [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie (New_structure) : Vectoriel (points)\n" \
            "-> Couche vectorielle de données ponctuelles de structures filtrées"
        )

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return AddStructures()