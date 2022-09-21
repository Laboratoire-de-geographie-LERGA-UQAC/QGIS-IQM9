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
from qgis.core import QgsVectorLayer , QgsRasterLayer, QgsCoordinateReferenceSystem
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
        #crs = QgsCoordinateReferenceSystem("EPSG:32198")
        
        crs = QgsRasterLayer( parameters['dem'], 'crslyr').crs().authid()
        print(crs)
        
        quit()
        
        tmp = {}
        #temporary WBT file
        tmp['d8'] = tempfile.NamedTemporaryFile(suffix=".tif")
        # Temporary shapefile for single points
        tmp['single_point'] = tempfile.NamedTemporaryFile(suffix=".gpkg")
        # Temporary verticies
        tmp['vertices'] = tempfile.NamedTemporaryFile(suffix=".gpkg")
        
        # FillBurn
        alg_params = {
            'dem': parameters['dem'],
            'streams': parameters['stream_network'],
            'output': tmp['d8'].name
        }
        outputs['Fillburn'] = processing.run('wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # BreachDepressions
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'fill_pits': False,
            'flat_increment': None,
            'max_depth': None,
            'max_length': None,
            'output': tmp['d8'].name
        }
        outputs['Breachdepressions'] = processing.run('wbt:BreachDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressions']['output'],
            'esri_pntr': False,
            'output': tmp['d8'].name
        }
        outputs['D8pointer'] = processing.run('wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Extract specific vertices
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-1',
            'OUTPUT': tmp['vertices'].name,
        }
        outputs['ExtractSpecificVertices'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}
            
            
        
        ## Loop through the elements
        
        #Create temporary path for watersheds
        tmp['watershed'] = tempfile.NamedTemporaryFile(suffix=".tif")
        # Watershed Parameters
        alg_params = {
            'd8_pntr': outputs['D8pointer']['output'],
            'esri_pntr': False,
            'pour_pts': tmp['single_point'].name,
            #'output': tmp['watershed'].name,
            'output': parameters['Networkwatersheds']
        }
        
        outlets = QgsVectorLayer(tmp['vertices'].name, 'vertices', 'ogr')
        
        for outlet in outlets.getFeatures([1,2,3]):
            # Get single point coordinates and CRS
            coordinates = f'{outlet.geometry().asPoint().toString()} [{crs.authid()}]'
            
            # Transform point to layer
            processing.run("native:pointtolayer", 
                            {'INPUT':coordinates
                            ,'OUTPUT': tmp['single_point'].name})
                            
            
            
            outputs['watershed'] = processing.runAndLoadResults('wbt:Watershed', alg_params)
            
            # TODO:
            # Faire en sort que chaque watershed calculé soit utilisé pour calculer le pourcentage
            # d
        
        #outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        #results['Networkwatersheds'] = outputs['Watershed']['output']
        
        # Closing temporary files
        for tempFile in tmp.values():
            tempFile.close()
        
        return 

    def name(self):
        return 'network-watershed'

    def displayName(self):
        return 'network-watershed'

    def group(self):
        return 'IQM'

    def groupId(self):
        return 'IQM'

    def createInstance(self):
        return Networkwatershed()
