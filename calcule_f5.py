"""
Model exported as python.
Name : IQM indice F5
Group : 
With QGIS : 32802
Author : Karim Mehour
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProperty
import processing

from tempfile import NamedTemporaryFile as Ntf
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProcessing,
                       QgsField,
                       QgsFeatureSink,
                       QgsVectorLayer,
                       QgsFeatureRequest,
                       QgsExpression,
                       QgsExpressionContext
                      )



class IndiceF5(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        #self.addParameter(QgsProcessingParameterVectorLayer('bande_riveraine_polly', 'Bande_riveraine_polly', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        #self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
        self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('transectsegment', 'Transect/segment', optional=True, type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=100, defaultValue=10))
        #self.addParameter(QgsProcessingParameterFeatureSink('Norm', 'Norm', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('Points', 'Points', type=QgsProcessing.TypeVectorPoint, createByDefault=True, supportsAppend=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}
        tmp = {
            'points':Ntf(suffix="pts"),
            'normals':Ntf(suffix="normals"),
        }
        
        # Define source stream net
        source = self.parameterAsSource(parameters, 'rivnet', context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F5", QVariant.Int))
        """
        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            'Norm',
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )
        """
        # For each segment
        for segment in source.getFeatures():
            # Materialize river feature
            single_segment = source.materialize(QgsFeatureRequest().setFilterFids([segment.id()]))
            
            
            feat_context = QgsExpressionContext()
            feat_context.setFeature(segment)
            print("Transect/segment : ", type(parameters['transectsegment']))
            
            print("Evaluated Expression : ", exp.evaluate(feat_context))
            
            # Points along geometry
            alg_params = {
                'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {parameters['transectsegment']}"),
                'END_OFFSET': 0,
                'INPUT': single_segment,
                'START_OFFSET': 0,
                #'OUTPUT': tmp['points'].name
                'OUTPUT': parameters['Points']
            }
            outputs['PointsAlongGeometry'] = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            points = QgsVectorLayer(outputs['PointsAlongGeometry']['OUTPUT'], 'points', 'ogr')
            for point in points.getFeatures():
                print(f"    {point['angle']}")
            
        """
            # Geometry by expression
            alg_params = {
                'EXPRESSION': 'with_variable(\n\t\'len\',\n\toverlay_nearest(\n\t\t@ptref_widths,\n\t\tLargeur_mod\n\t)[0] *  @ratio ,\n\textend(\n\t\tmake_line(\n\t\t\t$geometry,\n\t\t\tproject(\n\t\t\t\t$geometry,\n\t\t\t\t@len,\n\t\t\t\tradians("angle" - 90)\n\t\t\t)\n\t\t),\n\t\t@len,\n\t\t0\n\t)\n)',
                'INPUT': outputs['PointsAlongGeometry']['OUTPUT'],
                'OUTPUT_GEOMETRY': 1,  # Line
                'WITH_M': False,
                'WITH_Z': False,
                'OUTPUT': tmp['normals'].name
            }
            outputs['GeometryByExpression'] = processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

            # Field calculator
            alg_params = {
                'FIELD_LENGTH': 9,
                'FIELD_NAME': 'intersect_length',
                'FIELD_PRECISION': 3,
                'FIELD_TYPE': 0,  # Decimal (double)
                'FORMULA': 'max(\n0,\nlength(\n\tsegments_to_lines(\n\t\tintersection(\n\t\t\t$geometry,\n\t\t\tcollect_geometries(\n\t\t\t\t overlay_intersects(\n\t\t\t\t\t@bande_riveraine_polly,\n\t\t\t\t\t$geometry\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n))',
                'INPUT': outputs['GeometryByExpression']['OUTPUT'],
                'OUTPUT': parameters['Norm']
            }
            outputs['FieldCalculator'] = processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            results['Norm'] = outputs['FieldCalculator']['OUTPUT']
        """
        
        results['PointsAlongGeometry'] = outputs['PointsAlongGeometry']['OUTPUT']
        #Clear temporary files
        for temp in tmp.values():
            temp.close()
        return results

    def name(self):
        return 'indicef5'

    def displayName(self):
        return 'Indice F5'

    def group(self):
        return 'IQM'

    def groupId(self):
        return 'iqm'

    def createInstance(self):
        return IndiceF5()
