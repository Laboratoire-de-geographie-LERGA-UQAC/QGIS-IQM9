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
        self.addParameter(QgsProcessingParameterVectorLayer('bande_riveraine_polly', 'Bande_riveraine_polly', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
        self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('transectsegment', 'Transect/segment', optional=True, type=QgsProcessingParameterNumber.Integer, minValue=1, maxValue=100, defaultValue=10))
        self.addParameter(QgsProcessingParameterFeatureSink('sink', 'Sink', type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))
        #self.addParameter(QgsProcessingParameterFeatureSink('Points', 'Points', type=QgsProcessing.TypeVectorPoint, createByDefault=True, supportsAppend=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}
        tmp = {
            'points':Ntf(suffix="pts.gpkg"),
            'normals':Ntf(suffix="normals.gpkg"),
        }
        
        # Define source stream net
        source = self.parameterAsSource(parameters, 'rivnet', context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F5", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            'sink',
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        # feature count for feedback
        feature_count = source.featureCount()
        
        for segment in source.getFeatures():
            # Materialize segment feature
            single_segment = source.materialize(QgsFeatureRequest().setFilterFids([segment.id()]))
            
            # Points along geometry
            alg_params = {
                'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {parameters['transectsegment']}"),
                'END_OFFSET': 0,
                'INPUT': single_segment,
                'START_OFFSET': 0,
                #'OUTPUT':QgsProcessing.TEMPORARY_OUTPUT
                'OUTPUT': tmp['points'].name,
                #'OUTPUT': parameters['Points']
            }
            outputs['PointsAlongGeometry'] = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Take ownership of child temporary layer
            #points = context.takeResultLayer(outputs['PointsAlongGeometry']['OUTPUT'])
            points = QgsVectorLayer(tmp['points'].name, 'points', 'ogr')
            outputs['PointsAlongGeometry']['OUTPUT'] = points            

            # Geometry by expression
            alg_params = {
                'EXPRESSION':f"with_variable('len',overlay_nearest(\'{parameters['ptref_widths']}\',Largeur_mod)[0] *  {parameters['ratio']},extend(make_line($geometry,project($geometry,@len,radians(\"angle\" - 90))),@len,0))",
                #'EXPRESSION':"
                #'INPUT': outputs['PointsAlongGeometry']['OUTPUT'],
                'INPUT': points,
                'OUTPUT_GEOMETRY': 1,  # Line
                'WITH_M': False,
                'WITH_Z': False,
                'OUTPUT': tmp['normals'].name
                #'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                #'OUTPUT':parameters['Norm']
            }
            outputs['GeometryByExpression'] = processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            # Take ownership of child temporary layer
            #normals = context.takeResultLayer(outputs['GeometryByExpression']['OUTPUT'])
            normals = QgsVectorLayer(tmp['normals'].name, 'normals', 'ogr')
            outputs['GeometryByExpression']['OUTPUT'] = normals
            
            occurence = dict.fromkeys([0, 2, 3, 4, 5], 0)
            division_num = 0
            
            for normal in normals.getFeatures():
                # retreive segment width
                section_width= normal.geometry().length() / parameters['ratio']
                
                #Evaluating intersection distance
                expr = QgsExpression(
                f"max(0,length(segments_to_lines(intersection($geometry,collect_geometries(overlay_intersects('{parameters['bande_riveraine_polly']}',$geometry))))))",
                )
                feat_context = QgsExpressionContext()
                feat_context.setFeature(normal)
                intersect_len = expr.evaluate(feat_context)
                
                if intersect_len >= 2 * section_width:
                    occurence[0] += 1
                if intersect_len >= section_width:
                    occurence[2] += 1
                if intersect_len >= 0.5 * section_width:
                    occurence[3] += 1
                if intersect_len >= 0.5 * section_width:
                    occurence[4] += 1
                if intersect_len < 0.5 * section_width:
                    occurence[5] += 1
                
                division_num += 1
                
            # Determin the IQM Score
            if occurence[0] / division_num >= 0.9:
                indiceF5 = 0
            elif occurence[2] / division_num >= 0.66:
                indiceF5 = 2
            elif occurence[3] / division_num >= 0.66:
                indiceF5 = 3
            elif occurence[4] / division_num >= 0.33:
                indiceF5 = 4
            else:
                indiceF5 = 5
        
            #Write Index
            segment.setAttributes(
                segment.attributes() + [indiceF5]
            )
            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)
            print(f"{segment.id()} / {feature_count}")
        
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
