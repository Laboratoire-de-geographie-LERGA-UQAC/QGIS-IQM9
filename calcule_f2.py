# -*- coding: utf-8 -*-

"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""


import numpy as np
import processing

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
    QgsProcessingParameterRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)

class IndiceF2(QgsProcessingAlgorithm):

    OUTPUT = 'OUTPUT'
    ID_FIELD = 'Id'
    DIVISIONS = 10
    normals_ratio = 5

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers('antropic_layers', 'Antropic layers', layerType=QgsProcessing.TypeVector, defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        #self.addParameter(QgsProcessingParameterNumber('ratio', 'Ratio', optional=True, type=QgsProcessingParameterNumber.Double, minValue=1, maxValue=5, defaultValue=2.5))
        self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'Utilisation du territoir', defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):



        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)

        # Define source stream net
        source = self.parameterAsSource(parameters, 'rivnet', context)

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

        parameters['ratio'] = self.normals_ratio

        # Reclassify landUse
        vectorized_landuse = polygonize_landuse(parameters['landuse'], context=context, feedback=feedback)

        anthropic_layers = []#[layer.id() for layer in self.parameterAsLayerList(parameters, 'antropic_layers', context)]
        anthropic_layers.append(vectorized_landuse.id())
        QgsProject.instance().addMapLayer(vectorized_landuse)


        # feature count for feedback
        feature_count = source.featureCount()
        fid_idx = source.fields().indexFromName(self.ID_FIELD)

        for segment in source.getFeatures():

            print(f"working on : {segment[fid_idx]=}, {segment['Segment']=}")

            points = pointsAlongGeometry(segment, source, context, feedback=feedback)
            normals = gen_split_normals(points, parameters, context, feedback= feedback)
            mean_unrestricted_distance = get_mean_unrestricted_distance(normals, anthropic_layers, parameters)
            #print(f"{mean_unrestricted_distance=}")


            # Determin the IQM Score
            indiceF2 = computeF2(mean_unrestricted_distance)
            #Write Index
            segment.setAttributes(
                segment.attributes() + [indiceF2]
            )
            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)
            print(f"{segment[fid_idx]} / {feature_count}")

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
        return self.tr('IQM')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr("Clacule l'indice F2")

def polygonize_landuse(raster_source, context, feedback):

    CLASSES = ['300', '360', '1']
    # Extend classe table to other environments
    table = CLASSES.copy()
    for i in [2, 4, 5, 6, 7, 8]:
        for j in range(len(CLASSES)):
            c = int(CLASSES[j])
            if (j + 1) % 3 != 0:
                c += i * 1000
            table.append(str(c))

    # Reclassify land use
    alg_params = {
        'DATA_TYPE': 0,  # Byte
        'INPUT_RASTER': raster_source,
        'NODATA_FOR_MISSING': True,
        'NO_DATA': 0,
        'RANGE_BOUNDARIES': 2,  # min <= value <= max
        'RASTER_BAND': 1,
        'TABLE': table,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }
    raster = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    alg_params = {
        'BAND': 1,
        'EIGHT_CONNECTEDNESS': False,
        'EXTRA': '',
        'FIELD': 'DN',
        'INPUT': raster,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }
    poly_path = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    return QgsVectorLayer(poly_path, 'poly_landuse', "ogr")

def evaluate_expression(expression_str, vlayer, feature=None ):
    expression = QgsExpression(expression_str)
    context = QgsExpressionContext()
    if feature:
        context.setFeature(feature)
    scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
    context.appendScopes(scopes)
    res = expression.evaluate(context)
    return res

def intersects_structs(feature, base_layer, struct_lay_sources):
    # logger.info("checking vector intersection")
    for layer_source in struct_lay_sources:
        #Evaluating intersection
        expr = f"""
            to_int(overlay_intersects('{layer_source}'))
        """
        eval = evaluate_expression(expr, base_layer, feature=feature)
        if eval:
            return True
    return False

def pointsAlongGeometry(feature, source, context, feedback, output=QgsProcessing.TEMPORARY_OUTPUT):

    NUMBER = 15
    # Materialize segment feature
    feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
    # Points along geometry
    alg_params = {
        'DISTANCE': QgsProperty.fromExpression(f"length($geometry) / {NUMBER}"),
        'END_OFFSET': 0,
        'INPUT': feature,
        'START_OFFSET': 0,
        'OUTPUT': output,
    }
    # points = QgsVectorLayer(tmp['points'].name, 'points', 'ogr')
    # outputs['PointsAlongGeometry']['OUTPUT'] = points
    result_id = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return context.takeResultLayer(result_id)

def gen_split_normals(points, parameters, context, feedback, output=QgsProcessing.TEMPORARY_OUTPUT,):
    # Geometry by expression
    side_normals = []
    for angle in [90, -90]:
        alg_params = {
            'EXPRESSION':f"with_variable('len',overlay_nearest('{parameters['ptref_widths']}',Largeur_mod)[0] * {parameters['ratio']},make_line($geometry,project($geometry,@len,radians(\"angle\" + {angle}))))",
            'INPUT': points,
            'OUTPUT_GEOMETRY': 1,  # Line
            'WITH_M': False,
            'WITH_Z': False,
            'OUTPUT': output
        }
        side_normals.append(processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT'])

    res_id = processing.run("native:mergevectorlayers", {'LAYERS':side_normals,'CRS':None,'OUTPUT':'TEMPORARY_OUTPUT'}, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return context.takeResultLayer(res_id)

def get_mean_unrestricted_distance(normals, bounding_layer_ids, parameters):
    # Setting original normals lengths
    normals_lengths = np.array(evaluate_expression("array_agg(length(@geometry))" ,normals))
    river_widths = normals_lengths / parameters['ratio']
    diffs_array = np.zeros(normals_lengths.shape)

    for layer_id in bounding_layer_ids:
        expr_str = f"""
        array_agg(
            max( 0, distance(
                end_point(@geometry),
                start_point(intersection(
                $geometry,
                collect_geometries(
                    overlay_nearest(
                        '{layer_id}',
                        $geometry
                    )
                )
        )))))
        """
        obstructed_distances = np.nan_to_num(np.array(evaluate_expression(expr_str, normals)))
        #print(layer_id)
        #print(obstructed_distances)
        diffs_array = np.maximum(diffs_array, obstructed_distances)

    unobstructed_len_ratio = (normals_lengths - diffs_array - river_widths) / river_widths
    return np.mean(unobstructed_len_ratio)

def computeF2(mean_ratio):
    # search for anthropisation in buffers
    barem = ((5, 1), (3, 2), (2, 4)) # barem corresponds to (IQM score, buffer search scale) tuples
    for score, ratio in barem:
        if mean_ratio <= ratio:
            return score
    return 0
