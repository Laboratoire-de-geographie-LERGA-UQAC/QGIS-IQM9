import numpy as np
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProject,
    QgsField,
    QgsFeatureSink,
    QgsVectorLayer,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterMultipleLayers,
    QgsFeatureRequest,
    QgsExpression,
    QgsProcessingUtils,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProcessingAlgorithm,
    QgsCoordinateReferenceSystem,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)


class IndiceF3(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"
    ID_FIELD = "fid"
    DIVISIONS = 10

    tempDict = {
        name: QgsProcessingUtils.generateTempFilename(name)
        for name in [
            "clip.tif",
            "reclass_and_use.tif",
            "Vector_landuse.shp",
        ]
    }

    tempDict.update({
        name: 'TEMPORARY_OUTPUT'
        for name in [
            "split_line.shp",
            "side_buffers.shp",
            "Buffers.shp",
            "Buffer.shp",
        ]
    })

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
            QgsProcessingParameterMultipleLayers(
                "antropic_layers",
                "Antropic layers",
                optional=True,
                layerType=QgsProcessing.TypeVector,
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

        # Use a multi-step feedback
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)

        # Define source stream net
        source = self.parameterAsSource(parameters, "rivnet", context)

        # Define Sink
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F3", QVariant.Int))
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs(),
        )

        fid_idx = max([source.fields().indexFromName(id) for id in ["id", "fid", "Id"]])
        assert fid_idx >= 0, "field_index not found"
        anthropic_layers = [
            layer.id()
            for layer in self.parameterAsLayerList(
                parameters, "antropic_layers", context
            )
        ]

        # Reclassify landUse
        vectorised_landuse = polygonize_landuse(
            parameters, context=context, feedback=feedback
        )
        QgsProject.instance().addMapLayer(vectorised_landuse, addToLegend=False)
        anthropic_layers.append(vectorised_landuse.id())

        # feature count for feedback
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        # Itteration over all river networ features
        for i, segment in enumerate(source.getFeatures()):

            if feedback.isCanceled():
                return {}

            # Split segment into 100 sided buffers
            buffer_layer = split_buffer(
                segment, source, parameters, context, feedback=feedback
            )
            intersect_array = get_intersect_arr(
                buffer_layer, anthropic_layers, parameters, context
            )

            # Compute the IQM Score
            indiceF3 = computeF3(intersect_array)

            # Write to layer
            segment.setAttributes(segment.attributes() + [indiceF3])

            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)

            feedback.setProgress(int(i * total))

        return {self.OUTPUT: dest_id}

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return IndiceF3()

    def name(self):
        return "indicef3"

    def displayName(self):
        return self.tr("Indice F3")

    def group(self):
        return self.tr("Indicateurs IQM")

    def groupId(self):
        return "indicateurs_iqm"

    def shortHelpString(self):
        return self.tr("Clacule l'indice F3")


def evaluate_expression(expression_str, vlayer, feature=None):
    expression = QgsExpression(expression_str)
    context = QgsExpressionContext()
    if feature:
        context.setFeature(feature)
    scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
    context.appendScopes(scopes)
    res = expression.evaluate(context)
    return res


def split_buffer(feature, source, parameters, context, feedback=None):
    DIVISIONS = 50
    BUFF_RATIO = 1
    BUFF_FLAT = 15

    # Spliting river segment into a fixed number of subsegments.
    segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
    alg_param = {
        "INPUT": segment,
        "LENGTH": feature.geometry().length() / DIVISIONS,
        "OUTPUT": IndiceF3.tempDict["split_line.shp"],
    }
    split = processing.run(
        "native:splitlinesbylength", alg_param, context=context, is_child_algorithm=True
    )["OUTPUT"]

    side_buffers = []
    for direction in [1, -1]:
        # Buffering subsegments
        alg_param = {
            "INPUT": split,
            "OUTPUT_GEOMETRY": 0,
            "WITH_Z": False,
            "WITH_M": False,
            "EXPRESSION": f"single_sided_buffer( @geometry, {direction} * ({BUFF_FLAT} + {0.5 + BUFF_RATIO} * overlay_nearest('{parameters['ptref_widths']}', Largeur_Mod)[0]))",
            "OUTPUT": IndiceF3.tempDict["side_buffers.shp"],
        }
        side_buffers.append(
            processing.run(
                "native:geometrybyexpression",
                alg_param,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )["OUTPUT"]
        )

    alg_params = {
        "LAYERS": side_buffers,
        "CRS": None,
        "OUTPUT": IndiceF3.tempDict["Buffers.shp"],
    }
    res_id = processing.run(
        "native:mergevectorlayers",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]
    return context.takeResultLayer(res_id)


def get_intersect_arr(vlayer, struct_lay_ids, parameters, context):
    obstructed_arr = False

    for layer_source in struct_lay_ids:
        expr = f"""
            array_agg(to_int(overlay_intersects('{layer_source}')))
        """
        eval = np.array(evaluate_expression(expr, vlayer), dtype=bool)
        obstructed_arr += eval
    return obstructed_arr


def polygonize_landuse(parameters, context, feedback):
    alg_params = {
        "INPUT": parameters["rivnet"],
        "DISTANCE": 1000,
        "SEGMENTS": 5,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": True,
        "OUTPUT": IndiceF3.tempDict["Buffer.shp"],
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
        "OUTPUT": IndiceF3.tempDict["clip.tif"],
    }
    clip = processing.run(
        "gdal:cliprasterbymasklayer", alg_params, context=context, feedback=feedback
    )["OUTPUT"]

    CLASSES = ["300", "360", "1"]

    # Reclassify land use
    alg_params = {
        "DATA_TYPE": 0,  # Byte
        "INPUT_RASTER": clip,
        "NODATA_FOR_MISSING": True,
        "NO_DATA": 0,
        "RANGE_BOUNDARIES": 2,  # min <= value <= max
        "RASTER_BAND": 1,
        "TABLE": CLASSES,
        "OUTPUT": IndiceF3.tempDict["reclass_and_use.tif"],
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
        "OUTPUT": IndiceF3.tempDict["Vector_landuse.shp"],
    }
    poly_path = processing.run(
        "gdal:polygonize",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )["OUTPUT"]
    return QgsVectorLayer(poly_path, "landuse", "ogr")


def computeF3(intersect_arr):
    # Compute Iqm from sequence continuity
    ratio = np.mean(1 - intersect_arr)  # Sum number of unrestricted segments
    if ratio >= 0.9:
        return 0
    if ratio >= 0.66:
        return 2
    if ratio >= 0.33:
        return 3
    return 5
