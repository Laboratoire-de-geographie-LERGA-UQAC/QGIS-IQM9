import numpy as np
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsField,
    QgsProcessing,
    QgsProcessingUtils,
    QgsFeatureSink,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)


class IndiceF4(QgsProcessingAlgorithm):

    OUTPUT = "OUTPUT"
    ID_FIELD = "Id"
    DIVS = 100
    UTHRESH = 0.2
    LTHRESH = 0

    tempDict = {
        name: QgsProcessingUtils.generateTempFilename(name) for name in ["points.shp"]
    }

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "ptref_widths",
                "PtRef_widths",
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "rivnet",
                "RivNet",
                types=[QgsProcessing.TypeVectorLine],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.OUTPUT,
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
                supportsAppend=True,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        self.UTHRESH = self.parameterAsDouble(parameters, "thresh", context)

        def pointsAlongGeometry(feature):
            # Materialize segment feature
            feature = source.materialize(
                QgsFeatureRequest().setFilterFids([feature.id()])
            )

            # Points along geometry
            alg_params = {
                "DISTANCE": QgsProperty.fromExpression(
                    f"length($geometry) / {self.DIVS}"
                ),
                "END_OFFSET": 0,
                "INPUT": feature,
                "START_OFFSET": 0,
                "OUTPUT": IndiceF4.tempDict["points.shp"],
            }
            output = processing.run(
                "native:pointsalonglines",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )["OUTPUT"]
            return QgsVectorLayer(output, "points", "ogr")

        def evaluate_expression(expression_str, vlayer, feature=None):
            expression = QgsExpression(expression_str)
            context = QgsExpressionContext()
            if feature:
                context.setFeature(feature)
            scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
            context.appendScopes(scopes)
            res = expression.evaluate(context)
            return res

        def get_points_widths(vlayer, parameters):
            ptref_expr = f"""
                array_agg(overlay_nearest('{parameters['ptref_widths']}', largeur_mod)[0])
            """
            result = np.array(evaluate_expression(ptref_expr, vlayer))
            return result

        def natural_width_ratio(width_array, div_distance):
            # difs = (width_array[1:] / width_array[:-1]) / width_array[1:] / div_distance
            if not width_array.size:
                return 1
            difs_percent = (width_array[1:] - width_array[:-1]) / width_array[1:]
            difs_specific = difs_percent * 1000 / div_distance
            # print(f"{difs_specific=}")
            unnatural_widths = np.where(
                (difs_specific < self.LTHRESH) | (difs_specific > self.UTHRESH)
            )[0].size
            # print(f"{unnatural_widths=}")
            return 1 - (unnatural_widths / difs_percent.size)

        def computeF4(width_array, div_distance):
            # Compute F4 from width array
            ratio = natural_width_ratio(width_array, div_distance)
            if ratio >= 0.9:
                return 0
            if ratio >= 0.66:
                return 1
            if ratio >= 0.33:
                return 2
            return 3

        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}

        # Define source stream net
        source = self.parameterAsSource(parameters, "rivnet", context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F4", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs(),
        )
        results[self.OUTPUT] = dest_id

        total = 100.0 / source.featureCount() if source.featureCount() else 0
        # Itteration over all river networ features
        for i, segment in enumerate(source.getFeatures()):

            if feedback.isCanceled():
                return {}

            # gen points and normals along geometry
            points_along_line = pointsAlongGeometry(segment)
            div_distance = segment.geometry().length() / self.DIVS

            # Store normal length in numpy arrays
            width_array = get_points_widths(points_along_line, parameters)

            # Determin the IQM Score
            indiceF4 = computeF4(width_array, div_distance)
            # Write Index
            segment.setAttributes(segment.attributes() + [indiceF4])
            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(i * total))

            del points_along_line

        return results

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return IndiceF4()

    def name(self):
        return "indicef4"

    def displayName(self):
        return self.tr("Indice F4")

    def group(self):
        return self.tr("Indicateurs IQM")

    def groupId(self):
        return "indicateurs_iqm"

    def shortHelpString(self):
        return self.tr("Clacule l'indice F4")
