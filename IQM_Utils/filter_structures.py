"""
Model exported as python.
Name : Add structures
Group :
With QGIS : 33000
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsCoordinateReferenceSystem,
)
import processing


class AddStructures(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('cours_eau', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('routes', self.tr('Réseau routier (OSM)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('structures', self.tr('Structures (MTMD)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('New_structures', self.tr('Couche de sortie (New_structures)'), type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        outputs = {}

        # Finding intersections between the road and the river network
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

        # Merging MTMD structures and river/road intersections
        alg_params = {
            'CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
            'LAYERS': [parameters['structures'],outputs['LineIntersections']['OUTPUT']],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['MergedStructures'] = processing.run('native:mergevectorlayers', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Buffer around each structures
        alg_params = {
            'DISSOLVE': False,
            'DISTANCE': 2,
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

        # Dissolving buffers into one shape (if multiple points are nearby)
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

        # Finding the centroid of the shape to get the mean coordinates for points close to one another
        alg_params = {
            'ALL_PARTS': False,
            'INPUT': outputs['Dissolve']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Centroids'] = processing.run('native:centroids', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        # Extract structures within distance of the river network
        alg_params = {
            'DISTANCE': 100,
            'INPUT': outputs['Centroids']['OUTPUT'],
            'REFERENCE': parameters['cours_eau'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractWithinDistance'] = processing.run('native:extractwithindistance', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(6)
        if feedback.isCanceled():
            return {}

        # Add a unique id field with an incremental value
        alg_params = {
            'FIELD_NAME': 'fid',
            'FIELD_TYPE': 1,  # Integer
            'FIELD_LENGTH': 10,
            'FIELD_PRECISION': 0,
            'NEW_FIELD': False,
            'FORMULA': ' @row_number ',
            'INPUT': outputs['ExtractWithinDistance']['OUTPUT'],
            'OUTPUT': parameters['New_structures']
        }
        outputs['AddUniqueId'] = processing.run('qgis:fieldcalculator', alg_params, context=context, feedback=None, is_child_algorithm=True)

        feedback.setCurrentStep(7)

        return {'OUTPUT' : outputs['AddUniqueId']['OUTPUT']}

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
            "Sort les structures et les infrastructures routières qui coincide ou qui sont proche du cours d'eau.\n" \
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