import numpy as np
import processing
import gc
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProject,
    QgsField,
    QgsFeatureSink,
    QgsVectorLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingContext,
    QgsFeatureRequest,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProcessingUtils,
    QgsProcessingParameterRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)


class IndiceF2(QgsProcessingAlgorithm):

    OUTPUT = "OUTPUT"
    ID_FIELD = "fid"
    DIVISIONS = 10
    NORM_RATIO = 0

    tempDict = {
        name: QgsProcessingUtils.generateTempFilename(name)
        for name in [
            "points.shp",
            "reclass_landuse.tif",
            "vector_landuse.shp",
            "side_buffer.shp",
            "merged_layer.shp",
        ]
    }

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "antropic_layers",
                "Antropic layers",
                layerType=QgsProcessing.TypeVector,
                defaultValue=None,
                optional=True,
            )
        )
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
            QgsProcessingParameterRasterLayer(
                "landuse", "Utilisation du territoir", defaultValue=None
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

        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(1, model_feedback)

        # Define source stream net
        source = self.parameterAsVectorLayer(parameters, "rivnet", context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F2", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs(),
        )

        parameters["ratio"] = self.NORM_RATIO
        anthropic_layers = self.parameterAsLayerList(
            parameters, "antropic_layers", context
        )
        anthropic_layers = [layer.id() for layer in anthropic_layers]

        # Reclassify landUse
        vectorised_landuse = polygonize_landuse(parameters, context, feedback)
        QgsProject.instance().addMapLayer(vectorised_landuse, addToLegend=False)
        anthropic_layers.append(vectorised_landuse.id())

        # feature count for feedback
        feature_count = source.featureCount()
        fid_idx = max([source.fields().indexFromName(id) for id in ["id", "fid", "Id"]])

        expContext = QgsExpressionContext()
        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(source)
        expContext.appendScopes(scopes)
        parameters["expContext"] = expContext

        # try:
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        # Itteration over all river networ features
        for i, segment in enumerate(source.getFeatures()):

            if feedback.isCanceled():
                break

            # logging.info(f"\n\nworking on : {segment[fid_idx]=}, {segment.id()=}")

            # (.+)QgsProcessingUtils\.generateTempFilename\("([^"]*)"\)
            points = pointsAlongGeometry(
                segment,
                source,
                context=context,
                feedback=feedback,
                output=IndiceF2.tempDict["points.shp"],
            )
            segment_mean_width = get_segment_mean_width(
                segment, source, parameters, context=context, feedback=feedback
            )
            # logging.info(f"compute {segment_mean_width=}")

            normals = gen_split_normals(
                points,
                parameters,
                width=segment_mean_width,
                context=context,
                feedback=feedback,
            )
            # logging.info(f"normals created")

            scopeCount = len(
                QgsExpressionContextUtils.globalProjectLayerScopes(normals)
            )

            parameters["expContext"].appendScopes(
                QgsExpressionContextUtils.globalProjectLayerScopes(normals)
            )

            print(parameters["expContext"].scopeCount())
            mean_unrestricted_distance = get_mean_unrestricted_distance(
                normals, segment_mean_width, anthropic_layers, parameters
            )

            # Determin the IQM Score
            indiceF2 = computeF2(mean_unrestricted_distance)
            # Write Index
            segment.setAttributes(segment.attributes() + [indiceF2])
            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)

            for i in range(scopeCount):
                parameters["expContext"].popScope()

            QgsProject.instance().removeMapLayer(points.id())
            del (
                points,
                segment_mean_width,
                normals,
                mean_unrestricted_distance,
                indiceF2,
            )

            gc.collect()

            feedback.setProgress(int(i * total))

            # except Exception as e:
            #     feedback.reportError(str(e))
            #     QgsMessageLog.logMessage(f"Error processing feature {feature.id()}: {str(e)}", 'Indice F2', Qgis.Critical)

        QgsProject.instance().removeMapLayer(vectorised_landuse.id())

        return {self.OUTPUT: dest_id}

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return IndiceF2()

    def name(self):
        return "indicef2"

    def displayName(self):
        return self.tr("Indice F2")

    def group(self):
        return self.tr("Indicateurs IQM")

    def groupId(self):
        return "indicateurs_iqm"

    def shortHelpString(self):
        return self.tr("Clacul l'indice F2")


def polygonize_landuse(parameters, context, feedback):

    alg_params = {
        "INPUT": parameters["rivnet"],
        "DISTANCE": 1000,
        "SEGMENTS": 5,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": True,
        "OUTPUT": "TEMPORARY_OUTPUT",
    }
    buffer = processing.run(
        "native:buffer",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]

    alg_params = {
        "INPUT": parameters["landuse"],
        "MASK": buffer,
        "SOURCE_CRS": None,
        "TARGET_CRS": None,
        "TARGET_EXTENT": None,
        "NODATA": None,
        "ALPHA_BAND": False,
        "CROP_TO_CUTLINE": True,
        "KEEP_RESOLUTION": False,
        "SET_RESOLUTION": False,
        "X_RESOLUTION": None,
        "Y_RESOLUTION": None,
        "MULTITHREADING": False,
        "OPTIONS": "",
        "DATA_TYPE": 0,
        "EXTRA": "",
        "OUTPUT": "TEMPORARY_OUTPUT",
    }
    clip = processing.run(
        "gdal:cliprasterbymasklayer", alg_params, context=context, feedback=feedback
    )["OUTPUT"]

    CLASSES = ["300", "360", "1"]

    # Reclassify land use
    alg_params = {
        "DATA_TYPE": 0,  # Byte
        "INPUT_RASTER": clip,  # parameters['landuse'],
        "NODATA_FOR_MISSING": True,
        "NO_DATA": 0,
        "RANGE_BOUNDARIES": 2,  # min <= value <= max
        "RASTER_BAND": 1,
        "TABLE": CLASSES,
        "OUTPUT": IndiceF2.tempDict["reclass_landuse.tif"],
    }
    reclass = processing.run(
        "native:reclassifybytable",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]

    alg_params = {
        "BAND": 1,
        "EIGHT_CONNECTEDNESS": False,
        "EXTRA": "",
        "FIELD": "DN",
        "INPUT": reclass,
        "OUTPUT": IndiceF2.tempDict["vector_landuse.shp"],
    }
    poly_path = processing.run(
        "gdal:polygonize",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]
    return QgsVectorLayer(poly_path, "landuse", "ogr")


def evaluate_expression(expression_str, vlayer, feature=None, context=None):
    # logging.info(f"\t\t Evaluating expression ...")

    expression = QgsExpression(expression_str)

    if not context:
        context = QgsExpressionContext()
        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
        context.appendScopes(scopes)
    print("In Eval Expr: context scope count = ", context.scopeCount())

    if feature:
        context.setFeature(feature)

    res = expression.evaluate(context)
    del context, expression

    return res


def pointsAlongGeometry(
    feature, source, context, feedback, output=QgsProcessing.TEMPORARY_OUTPUT
):

    NUMBER = 50
    # Materialize segment feature
    feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
    # Points along geometry
    alg_params = {
        "DISTANCE": QgsProperty.fromExpression(f"max(10, $length / {NUMBER})"),
        "END_OFFSET": 0,
        "INPUT": feature,
        "START_OFFSET": 0,
        "OUTPUT": output,
    }
    result_id = processing.run(
        "native:pointsalonglines",
        alg_params,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]
    return QgsVectorLayer(result_id, "points", "ogr")


def get_segment_mean_width(
    feature, source, parameters, width_field="Largeur_mod", context=None, feedback=None
):
    expr = QgsExpression(
        f"""
            max(5, array_mean(overlay_nearest('{parameters['ptref_widths']}', {width_field}, limit:=-1, max_distance:=5)))
                """
    )

    evaluate_expression(
        expr, source, feature=feature, context=parameters["expContext"]
    )

    return resg


def gen_split_normals(points, parameters, width=0, context=None, feedback=None):
    # Geometry by expression
    side_normals = []
    width = max(10, width)
    NORMALS_FLAT = 50
    for angle in [90, -90]:
        alg_params = {
            "EXPRESSION": f"with_variable('len',{width} * {0.5 + parameters['ratio']} + {NORMALS_FLAT}, make_line($geometry,project($geometry,@len,radians(\"angle\" + {angle}))))",
            "INPUT": points,
            "OUTPUT_GEOMETRY": 1,  # Line
            "WITH_M": False,
            "WITH_Z": False,
            "OUTPUT": IndiceF2.tempDict["side_buffer.shp"],
        }
        side_normals.append(
            processing.run(
                "native:geometrybyexpression",
                alg_params,
                feedback=feedback,
                is_child_algorithm=True,
            )["OUTPUT"]
        )

    res_id = processing.run(
        "native:mergevectorlayers",
        {
            "LAYERS": side_normals,
            "CRS": None,
            "OUTPUT": IndiceF2.tempDict["merged_layer.shp"],
        },
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]
    # logger.info(f"{res_id=}")

    return QgsVectorLayer(res_id, "normals", "ogr")


def get_mean_unrestricted_distance(
    normals, river_width, bounding_layer_ids, parameters
):
    # logging.info(f"\tComputing unrestricted distance")
    # Setting original normals lengths
    normals_length = river_width / 2 + 50
    diffs_array = 0

    for layer_id in bounding_layer_ids:
        expr_str = f"""
        array_agg(
            max( 0, distance(
                end_point($geometry),
                start_point(intersection(
                    $geometry,
                    collect_geometries(
                        overlay_nearest(
                            '{layer_id}',
                            $geometry
                        )
                    )
                ))
            ))
        )"""

        expr = evaluate_expression(expr_str, normals, context=parameters["expContext"])
        obstructed_distances = np.array(expr)
        # logging.info(f"{obstructed_distances=}\n")
        diffs_array = np.maximum(diffs_array, obstructed_distances)
        del obstructed_distances
        # logging.info(f"{obstructed_distances=}\n{diffs_array=}")
    unobstructed_lengths = normals_length - diffs_array - river_width / 2

    QgsProject.instance().removeMapLayer(normals.id())
    del diffs_array, normals

    return np.mean(unobstructed_lengths)


def computeF2(mean_length):
    # search for anthropisation in buffers
    barem = (
        (5, 15),
        (3, 30),
        (2, 49),
    )  # barem corresponds to (IQM score, buffer search scale) tuples
    for score, dist in barem:
        if mean_length <= dist:
            return score
    return 0
