
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
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
                       QgsProject,
                       QgsFeatureRequest,
                       QgsSpatialIndex
                       )
from qgis import processing


class IndiceF1(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'
    STRUCTURES_PATH = '/home/karim/uqac/indice_F1/data/Structure_tq_shp/gsq_v_desc_strct_tri_rpr.shp'
    FID = "Id"

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Réseau hydrographique (CRHQ)'), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer('structs', self.tr('Structures filtrées (sortant de Filter structures; MTMD)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie')))

    def processAlgorithm(self, parameters, context, model_feedback):
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
        model_feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))
        # Gets the number of features to iterate over for the progress bar
        total_features = source.featureCount()

        for current, feature in enumerate(source.getFeatures()):

            if model_feedback.isCanceled():
                return {}

            buffer = gen_buffer(feature, source, context=context)
            struct_count = count_structures(buffer, parameters)

            indiceF1 = computeF1(feature, struct_count)

            feature.setAttributes(
                feature.attributes() + [indiceF1]
            )

            # Increments the progress bar
            if total_features != 0:
                progress = int(100*(current/total_features))
            else:
                progress = 0
            model_feedback.setProgress(progress)

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
        return self.tr('IQM (indice solo)')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice F1 afin d'évaluer la continuité du transit longitudinal du transit de sédiments et de bois.\n L'outil évalue la présence d\'obstacles (barrages, traverses, ponts, etc.) qui pourraient entraver ou nuire au transport de sédiments et de bois. Il prend en compte la densité linéaire des entraves sur 1000 m de rivière. Puisque les effets des entraves affectent la portion en aval de l'infrastructure, l'outil considère seulement les éléments artificiels situés à une distance maximale de 1000 m à l'amont du segment. Dans le cas d'un style fluvial à plusieurs chenaux (divagant, anabranche), une seule entrave est comptabilisée lorsque plusieurs structures sont localisées à la même distance amont-aval dans les divers chenaux.\n" \
            "Paramètres\n" \
            "----------\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Structures filtrées : Vectoriel (points)\n" \
            "-> Ensemble de données vectorielles ponctuelles des structures sous la gestion du Ministère des Transports et de la Mobilité durable du Québec (MTMD) (pont, ponceau, portique, mur et tunnel) ayant été préalablement filtrées par le script Filter structures. Source des données : MTMD. Structure, [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice F1 calculé pour chaque UEA."
        )

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
    #print(count)
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
