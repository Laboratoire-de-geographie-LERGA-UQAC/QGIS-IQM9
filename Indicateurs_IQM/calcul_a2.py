from tempfile import NamedTemporaryFile as Ntf
import processing
from tempfile import NamedTemporaryFile as Ntf
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsField,
    QgsFeatureSink,
    QgsVectorLayer,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterRasterDestination,
    QgsCoordinateReferenceSystem,
)


class IndiceA2(QgsProcessingAlgorithm):
    ID_FIELD = "fid"
    OUTPUT = "OUTPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "stream_network",
                "Cours d'eau",
                types=[QgsProcessing.TypeVectorLine],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer("D8", "WBT D8", defaultValue=None)
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "dams", "Dams", types=[QgsProcessing.TypeVectorPoint], defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, self.tr("Output Layer"), defaultValue=None
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):

        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        outputs = {}

        # Create temporary file locations
        tmp = {
            "mainWatershed": Ntf(suffix="watershed.tif"),
            "subWatershed": Ntf(suffix="sub-watershed.tif"),
        }

        # Define source stream net
        source = self.parameterAsSource(parameters, "stream_network", context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A2", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs(),
        )

        # Snap dams to river network
        alg_params = {
            "BEHAVIOR": 1,  # Prefer closest point, insert extra vertices where required
            "INPUT": parameters["dams"],
            "REFERENCE_LAYER": parameters["stream_network"],
            "TOLERANCE": 75,
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["SnappedDams"] = processing.run(
            "native:snapgeometries",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        # Extract specific vertex
        alg_params = {
            "INPUT": parameters["stream_network"],
            "VERTICES": "-2",
            "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        }
        outputs["ExtractSpecificVertex"] = processing.run(
            "native:extractspecificvertices",
            alg_params,
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        feature_count = source.featureCount()
        fid_idx = source.fields().indexFromName(self.ID_FIELD)

        for feature in source.getFeatures():

            fid = feature[fid_idx]
            if feedback.isCanceled():
                return {}

            # Extract By Attribute
            alg_params = {
                "FIELD": self.ID_FIELD,
                "INPUT": outputs["ExtractSpecificVertex"]["OUTPUT"],
                "OPERATOR": 0,  # =
                "VALUE": str(fid),
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }

            outputs["single_point"] = processing.run(
                "native:extractbyattribute",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            # Watershed
            alg_params = {
                "d8_pntr": parameters["D8"],
                "esri_pntr": False,
                "pour_pts": outputs["single_point"]["OUTPUT"],
                "output": tmp["mainWatershed"].name,
            }
            outputs["mainWatershed"] = processing.run(
                "wbt:Watershed",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            # Polygonize watershed (raster to vector)
            alg_params = {
                "BAND": 1,
                "EIGHT_CONNECTEDNESS": False,
                "EXTRA": "",
                "FIELD": "DN",
                "INPUT": outputs["mainWatershed"]["output"],
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["mainWatershedPoly"] = processing.run(
                "gdal:polygonize",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            # Compute watershed total area
            mainWatershedPoly = QgsVectorLayer(
                outputs["mainWatershedPoly"]["OUTPUT"], "vector main watershed", "ogr"
            )
            main_area = sum(
                [feat.geometry().area() for feat in mainWatershedPoly.getFeatures()]
            )

            # Clip Dams
            alg_params = {
                "INPUT": outputs["SnappedDams"]["OUTPUT"],
                "INTERSECT": outputs["mainWatershedPoly"]["OUTPUT"],
                "PREDICATE": [6],  # are within
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ClipDams"] = processing.run(
                "native:extractbylocation",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            # Watershed
            alg_params = {
                "d8_pntr": parameters["D8"],
                "esri_pntr": False,
                "pour_pts": outputs["ClipDams"]["OUTPUT"],
                "output": tmp["subWatershed"].name,
            }
            outputs["subWatershed"] = processing.run(
                "wbt:Watershed",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(10)
            if feedback.isCanceled():
                return {}

            # Vectorized Sub-watersheds
            alg_params = {
                "BAND": 1,
                "EIGHT_CONNECTEDNESS": False,
                "EXTRA": "",
                "FIELD": "DN",
                "INPUT": outputs["subWatershed"]["output"],
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["subWatershedPoly"] = processing.run(
                "gdal:polygonize",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            # Compute watershed total area
            subWatershedPoly = QgsVectorLayer(
                outputs["subWatershedPoly"]["OUTPUT"], "vector sub watershed", "ogr"
            )
            sub_area = sum(
                [feat.geometry().area() for feat in subWatershedPoly.getFeatures()]
            )

            indiceA2 = 0

            if main_area != 0 and sub_area != 0:
                # get dams sub watersheds area ration
                ratio = sub_area / main_area
                if ratio < 0.05:
                    indiceA2 = 0
                elif 0.05 <= ratio < 0.33:
                    indiceA2 = 2
                elif 0.33 <= ratio < 0.66:
                    indiceA2 = 3
                elif 0.66 <= ratio:
                    indiceA2 = 4

            # Add forest area to new featuer
            feature.setAttributes(feature.attributes() + [indiceA2])

            # Clear temporary files
            for tempfile in tmp.values():
                tempfile.close()

            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            print(f"{fid}/{feature_count}")
            del mainWatershedPoly, subWatershedPoly

        return {self.OUTPUT: dest_id}

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return IndiceA2()

    def name(self):
        return "Indice A2"

    def displayName(self):
        return self.tr("Indice A2")

    def group(self):
        return self.tr("Indicateurs IQM")

    def groupId(self):
        return "indicateurs_iqm"

    def shortHelpString(self):
        return self.tr("Clacule l'indice A2")
