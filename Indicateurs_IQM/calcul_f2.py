# -*- coding: utf-8 -*-

"""
*********************************************************************************
*																				*
*		QGIS-IQM9 is a program developed for QGIS as a tool to automatically	*
*	calculate the Morphological Quality Index (MQI) of river systems			*
*	Copyright (C) 2025 Laboratoire d'expertise et de recherche en géographie	*
*	appliquée (LERGA) de l'Université du Québec à Chicoutimi (UQAC)				*
*																				*
*	This program is free software: you can redistribute it and/or modify		*
*	it under the terms of the GNU Affero General Public License as published	*
*	by the Free Software Foundation, either version 3 of the License, or		*
*	(at your option) any later version.											*
*																				*
*	This program is distributed in the hope that it will be useful,				*
*	but WITHOUT ANY WARRANTY; without even the implied warranty of				*
*	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the				*
*	GNU Affero General Public License for more details.							*
*																				*
*	You should have received a copy of the GNU Affero General Public License	*
*	along with this program.  If not, see <https://www.gnu.org/licenses/>.		*
*																				*
*********************************************************************************
"""


import numpy as np
import processing
import logging

from tempfile import NamedTemporaryFile
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
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)

import sys
LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format=LOG_FORMAT,
    filemode='w')

logger = logging.getLogger()
logger.info("Algo start")

class IndiceF2(QgsProcessingAlgorithm):

    OUTPUT = "OUTPUT"
    ID_FIELD = "fid"
    DIVISIONS = 10
    NORM_RATIO = 0

    tempDict = {
        name: QgsProcessingUtils.generateTempFilename(name)
        for name in [
            "reclass_landuse.tif",
            "vector_landuse.shp",
            "side_buffer.shp",
        ]
    }

    tempDict.update({
        name: 'TEMPORARY_OUTPUT'
        for name in [
            "points.shp",
            "merged_layer.shp",
        ]
    })

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                "anthropic_layers",
                self.tr("Réseau routier (OSM)"),
                layerType=QgsProcessing.TypeVector,
                defaultValue=None,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "ptref_widths",
                self.tr("PtRef largeur (CRHQ)"),
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "rivnet",
                self.tr("Réseau hydrographique (CRHQ)"),
                types=[QgsProcessing.TypeVectorLine],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "landuse",
                self.tr("Utilisation du territoire (MELCCFP)"),
                defaultValue=None
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Couche de sortie'),
                type=QgsProcessing.TypeVectorAnyGeometry,
                createByDefault=True,
                supportsAppend=True,
                defaultValue=None,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        if model_feedback.isCanceled():
            return {}

        # Define source stream net
        source = self.parameterAsVectorLayer(parameters, 'rivnet', context)

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
            source.sourceCrs()
        )

        parameters['ratio'] = self.NORM_RATIO
        anthropic_layers = self.parameterAsLayerList(parameters, 'anthropic_layers', context)
        anthropic_layers = [layer.id() for layer in anthropic_layers]

        # Reclassify landUse
        vectorised_landuse = polygonize_landuse(parameters, context, feedback=None)
        QgsProject.instance().addMapLayer(vectorised_landuse, addToLegend=False)
        anthropic_layers.append(vectorised_landuse.id())

        # Gets the number of features to iterate over for the progress bar
        total_features = source.featureCount()
        model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

        fid_idx = max([source.fields().indexFromName(id) for id in ["id", "fid", "Id"]])

        expContext = QgsExpressionContext()
        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(source)
        expContext.appendScopes(scopes)
        parameters['expContext'] = expContext

        # Itteration over all river network features
        for current, segment in enumerate(source.getFeatures()):

            if model_feedback.isCanceled():
                return {}

            logging.info(f"\n\nworking on : {segment[fid_idx]=}, {segment.id()=}")

            points = pointsAlongGeometry(segment, source, context=context, feedback=None, output=QgsProcessingUtils.generateTempFilename("points.shp"))
            segment_mean_width = get_segment_mean_width(segment, source, parameters, context=context, feedback=None)
            logging.info(f"compute {segment_mean_width=}")

            normals = gen_split_normals(points, parameters, width=segment_mean_width,context=context, feedback=None)
            logging.info(f"normals created")

            parameters['expContext'].appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(normals))

            mean_unrestricted_distance = get_mean_unrestricted_distance(normals, segment_mean_width, anthropic_layers, parameters)
            logging.info(f"mean_unrestricted_distance computed")
            logging.info(f"Segment : {segment.id()} => {mean_unrestricted_distance=}")

            # Determin the IQM Score
            indiceF2 = computeF2(mean_unrestricted_distance)
            #Write Index
            segment.setAttributes(
                segment.attributes() + [indiceF2]
            )
            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)
            logging.info(f"{indiceF2=}")
            logging.info(f"{segment.id()} / {total_features}\n\n")
            logging.info(f"segment{segment[fid_idx]} done !")

            # Increments the progress bar
            if total_features != 0:
                progress = int(100*(current/total_features))
            else:
                progress = 0
            model_feedback.setProgress(progress)
            model_feedback.setProgressText(self.tr(f"Traitement de {current} segments sur {total_features}"))

        # Ending message
        model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

        return {self.OUTPUT : dest_id}

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return IndiceF2()

    def name(self):
        return 'indicef2'

    def displayName(self):
        return self.tr('Indice F2')

    def group(self):
        return self.tr('IQM (indice solo)')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice F2 afin d'évaluer la connectivité latérale avec la plaine alluviale.\n L'outil prend en compte les éléments de déconnexion artificielle  présents sur la plaine alluviale (réseau routier et affectation urbaine à l'intérieur de la plaine) afin d'évaluer la connectivité latérale potentielle des deux rives. La connectivité latérale est évaluée à partir d'une largeur minimale de 15 m jusqu'à une distance maximale de 50 m.\n" \
            "Paramètres\n" \
            "----------\n" \
            "Réseau routier : Vectoriel (lignes)\n" \
            "-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
            "PtRef largeur : Vectoriel (points)\n" \
            "-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Utilisation du territoire : Matriciel\n" \
            "-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice F2 calculé pour chaque UEA."
        )

def polygonize_landuse(parameters, context, feedback):

    alg_params = {'INPUT':parameters['rivnet'],'DISTANCE':1000,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':True,'OUTPUT':'TEMPORARY_OUTPUT'}
    buffer = processing.run("native:buffer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    alg_params = {'INPUT':parameters['landuse'],'MASK':buffer,'SOURCE_CRS':None,'TARGET_CRS':None,'TARGET_EXTENT':None,'NODATA':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':False,'OPTIONS':'','DATA_TYPE':0,'EXTRA':'','OUTPUT':'TEMPORARY_OUTPUT'}
    clip = processing.run("gdal:cliprasterbymasklayer", alg_params,context=context, feedback=feedback)['OUTPUT']

    CLASSES = ['300', '360', '1']

    # Reclassify land use
    alg_params = {
        'DATA_TYPE': 0,  # Byte
        'INPUT_RASTER': clip ,#parameters['landuse'],
        'NODATA_FOR_MISSING': True,
        'NO_DATA': 0,
        'RANGE_BOUNDARIES': 2,  # min <= value <= max
        'RASTER_BAND': 1,
        'TABLE': CLASSES,
        'OUTPUT': QgsProcessingUtils.generateTempFilename("reclass_landuse.tif")
    }
    reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    alg_params = {
        'BAND': 1,
        'EIGHT_CONNECTEDNESS': False,
        'EXTRA': '',
        'FIELD': 'DN',
        'INPUT': reclass,
        'OUTPUT': QgsProcessingUtils.generateTempFilename("vector_landuse.shp")
    }
    poly_path = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return QgsVectorLayer(poly_path, "landuse", "ogr")


def evaluate_expression(expression_str, vlayer, feature=None, context=None):
    logging.info(f"\t\t Evaluating expression ...")

    expression = QgsExpression(expression_str)

    if not context:
        context = QgsExpressionContext()
        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
        context.appendScopes(scopes)

    if feature:
        context.setFeature(feature)
    #feature = next(vlayer.getFeatures())

    return expression.evaluate(context)


def pointsAlongGeometry(feature, source, context, feedback, output=QgsProcessing.TEMPORARY_OUTPUT):

    NUMBER = 50
    # Materialize segment feature
    feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
    # Points along geometry
    alg_params = {
        'DISTANCE': QgsProperty.fromExpression(f"max(10, $length / {NUMBER})"),
        'END_OFFSET': 0,
        'INPUT': feature,
        'START_OFFSET': 0,
        'OUTPUT': output,
    }
    result_id = processing.run('native:pointsalonglines', alg_params, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return QgsVectorLayer(result_id, "points", "ogr")

def get_segment_mean_width(feature, source, parameters, width_field='Largeur_mod', context=None, feedback=None):
    expr = QgsExpression(f"""
            max(5, array_mean(overlay_nearest('{parameters['ptref_widths']}', {width_field}, limit:=-1, max_distance:=5)))
                """)

    return evaluate_expression(expr, source, feature=feature, context=parameters['expContext'])

def gen_split_normals(points, parameters, width=0,context=None, feedback=None):
    # Geometry by expression
    side_normals = []
    width = max(10, width)
    NORMALS_FLAT = 50
    for angle in [90, -90]:
        alg_params = {
            'EXPRESSION':f"with_variable('len',{width} * {0.5 + parameters['ratio']} + {NORMALS_FLAT}, make_line($geometry,project($geometry,@len,radians(\"angle\" + {angle}))))",
            'INPUT': points,
            'OUTPUT_GEOMETRY': 1,  # Line
            'WITH_M': False,
            'WITH_Z': False,
            'OUTPUT': QgsProcessingUtils.generateTempFilename("side_buffer.shp")
        }
        side_normals.append(processing.run('native:geometrybyexpression', alg_params, feedback=feedback, is_child_algorithm=True)['OUTPUT'])

    res_id = processing.run("native:mergevectorlayers", {'LAYERS':side_normals,'CRS':None,'OUTPUT':QgsProcessingUtils.generateTempFilename("merged_layer.shp")}, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    logger.info(f"{res_id=}")
    #return context.takeResultLayer(res_id)
    return QgsVectorLayer(res_id, 'normals', "ogr" )

def get_mean_unrestricted_distance(normals, river_width, bounding_layer_ids, parameters):
    logging.info(f"\tComputing unrestricted distance")
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


        obstructed_distances = np.array(evaluate_expression(expr_str, normals, context=parameters['expContext']))
        logging.info(f"{obstructed_distances=}\n")
        diffs_array = np.maximum(diffs_array, obstructed_distances)
        logging.info(f"{obstructed_distances=}\n{diffs_array=}")
    unobstructed_lengths = (normals_length - diffs_array - river_width / 2)
    logging.info(f"{unobstructed_lengths=}, mean= {np.mean(unobstructed_lengths)}")
    return np.mean(unobstructed_lengths)

def computeF2(mean_length):
    # search for anthropisation in buffers
    if mean_length > 50: # Lateral connectivity with the alluvial plain over a width of more than 50m
         return 0
    elif mean_length >= 30 and mean_length <= 50 : # Lateral connectivity with the alluvial plain over a width between [30m, 50m]
        return 2
    elif mean_length >= 15 and mean_length < 30 : # Lateral connectivity with the alluvial plain over a width between [15m, 30m[
        return 3
    elif mean_length < 15 : # Lateral connectivity with the alluvial plain over a width less than 15m
        return 5
