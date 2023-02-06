# Algorithm from the autogis-site tutorial
# Source : https://autogis-site.readthedocs.io/en/2018_/lessons/L7/processing-script.html

import processing
import string

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterField,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterVectorLayer
)

RIV_NET = "rivers"
id_field = "id_field"
output = "output"


class autoGisAlg(QgsProcessingAlgorithm):
    
    def __init__(self):
        super().__init__()
        
    def createInstance(self):
        return type(self)()
        
    def displayName(self):
        return "autoGisAlg"
        
    def name(self):
        return "autogisalg"
        
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                name=RIV_NET,
                description="Cours d'eau",
                types=[QgsProcessing.SourceType.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                name = id_field,
                description = "Parametre d'identification unique",
                parentLayerParameterName=RIV_NET,
                type=QgsProcessingParameterField.Numeric
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                name=output,
                description="Output"
            )
        )
        
        
    def processingAlgorithm(self, parameters, context, feedback):
        
        os.makedirs(
            parameters[ouput],
            exits_ok=True
        )
        
        
        
        return {}
    
        