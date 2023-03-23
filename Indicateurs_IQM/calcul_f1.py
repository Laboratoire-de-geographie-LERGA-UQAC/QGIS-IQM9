
from qgis import processing
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
	QgsProcessing,
	QgsFeatureSink,
	QgsField,
	QgsProcessingException,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSource,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsExpression,
	QgsExpressionContext,
	QgsExpressionContextUtils,
	QgsVectorLayer,
	QgsProcessingMultiStepFeedback,
	QgsProject,
	QgsFeatureRequest,
	QgsSpatialIndex)


class IndiceF1(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    STRUCTURES_PATH = '/home/karim/uqac/indice_F1/data/Structure_tq_shp/gsq_v_desc_strct_tri_rpr.shp'
    FID = "Id"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Reseau hydrologique'), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer('structs', self.tr('Structures'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Output layer')))

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        outputs = {}
        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )

        # Create a QgsVectorLayer from source
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        #Adding new field to output
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F1", QVariant.Int))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # Send some information to the user
        feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))

        for feature in source.getFeatures():

            if feedback.isCanceled():
                break

            buffer = gen_buffer(feature, source, context=context)
            struct_count = count_structures(buffer, parameters)

            indiceF1 = computeF1(feature, struct_count)

            feature.setAttributes(
                feature.attributes() + [indiceF1]
            )

            # Add a feature in the sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)


        return {self.OUTPUT: dest_id}


    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return IndiceF1()

    def name(self):
        return 'indicef1'

    def displayName(self):
        return self.tr('Indice F1')

    def group(self):
        return self.tr('Indicateurs IQM')

    def groupId(self):
        return 'indicateurs_iqm'

    def shortHelpString(self):
        return self.tr("""Calcule de l'indice F1, à partire de la base de donnée des structures issue de \n
        https://www.donneesquebec.ca/recherche/dataset/structure#""")

def evaluate_expression(expression_str, vlayer, feature=None ):
    expression = QgsExpression(expression_str)
    context = QgsExpressionContext()
    if feature:
        context.setFeature(feature)
    scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
    context.appendScopes(scopes)
    res = expression.evaluate(context)
    return res

def gen_buffer(feature, vlayer, context, feedback=None, parameters={}):
    segment = vlayer.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
    # Buffering subsegments
    alg_params = {'INPUT':segment,'DISTANCE':1000 ,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':True,'OUTPUT':'TEMPORARY_OUTPUT'}
    buffer = processing.run("native:buffer", alg_params, context=context, is_child_algorithm=True)['OUTPUT']
    return context.takeResultLayer(buffer)

def count_structures(buffer, parameters):
    expr_str = f"""
    array_length(overlay_intersects('{parameters['structs']}', @geometry))
    """
    feature = next(buffer.getFeatures())
    count = evaluate_expression(expr_str, buffer, feature=feature)
    print(count)
    return count

def computeF1(feature, struct_count):
    length = feature.geometry().length()
    if not length or not struct_count:
        return 0

    ratio = struct_count / length
    if ratio <= 1:
        return 2
    elif ratio > 1:
        return 4
