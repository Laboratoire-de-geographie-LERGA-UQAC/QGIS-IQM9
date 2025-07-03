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
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)


class IndiceF3(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    ID_FIELD = 'fid'
    DIVISIONS = 10

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                'ptref_widths',
                self.tr('PtRef largeur (CRHQ)'),
                types=[QgsProcessing.TypeVectorPoint],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                'anthropic_layers',
                self.tr('Réseau routier (OSM)'),
                optional=True,
                layerType=QgsProcessing.TypeVector,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                'rivnet',
                self.tr('Réseau hydrographique (CRHQ)'),
                types=[QgsProcessing.TypeVectorLine],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                'landuse',
                self.tr('Utilisation du territoire (MELCCFP)'),
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
        source = self.parameterAsSource(parameters, 'rivnet', context)

        # Define Sink
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F3", QVariant.Int))
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        fid_idx = max([source.fields().indexFromName(id) for id in ["id", "fid", "Id"]])
        assert fid_idx >= 0, "field_index not found"
        anthropic_layers = [layer.id() for layer in self.parameterAsLayerList(parameters, 'anthropic_layers', context)]

        # Reclassify landUse
        vectorised_landuse = polygonize_landuse(parameters, context=context, feedback=None)
        QgsProject.instance().addMapLayer(vectorised_landuse, addToLegend=False)
        anthropic_layers.append(vectorised_landuse.id())


        # feature count for feedback
        total_features = source.featureCount()
        model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

        for current, segment in enumerate(source.getFeatures()):

            if model_feedback.isCanceled():
                return {}
            
            # Split segment into 100 sided buffers
            buffer_layer = split_buffer(segment, source, parameters, context, feedback=None)
            intersect_array = get_intersect_arr(buffer_layer, anthropic_layers, parameters, context)

            # Compute the IQM Score
            indiceF3 = computeF3(intersect_array)

            # Write to layer
            segment.setAttributes(segment.attributes() + [indiceF3])

            # Add a feature to sink
            sink.addFeature(segment, QgsFeatureSink.FastInsert)

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
        return IndiceF3()

    def name(self):
        return 'indicef3'

    def displayName(self):
        return self.tr('Indice F3')

    def group(self):
        return self.tr('IQM (indice solo)')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice F3 afin d'évaluer la capacité d'érosion du cours d'eau en évaluant la continuité de l'espace de mobilité sur l'ensemble du segment.\n L'outil calcul donc la continuité amont-aval en prenant compte de la somme des distances longitudinales dénuées de discontinuités de part et d'autre du chenal en fonction de la distance totale du segment. La continuité longitudinale de l'espace de mobilité s'exprime par la distance longitudinale relative (%). Les discontinuités utilisées par l'outil sont les infrastructures de transport (routes, voies ferrées) ainsi que les ponts et ponceaux présents à l'intérieur de l'espace de mobilité d'une largeur de 15 m. Dans le cas d'un cours d'eau anabranche ou divagant, la continuité longitudinale est évaluée en calculant la somme des distances sans discontinuités pour chaque chenal en fonction de la distance totale de tous les chenaux.\n" \
            "Paramètres\n" \
            "----------\n" \
            "PtRef largeur : Vectoriel (points)\n" \
            "-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Réseau routier : Vectoriel (lignes)\n" \
            "-> Réseau routier linéaire représentant les rues, les avenues, les autoroutes et les chemins de fer. Source des données : OpenStreetMap contributors. Dans OpenStreetMap.\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Utilisation du territoire : Matriciel\n" \
            "-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MELCCFP. Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice F3 calculé pour chaque UEA."
        )


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
    'INPUT': segment,
    'LENGTH': feature.geometry().length() / DIVISIONS,
    'OUTPUT': QgsProcessingUtils.generateTempFilename("split_line.shp"),
    }
    split = processing.run('native:splitlinesbylength', alg_param, context=context, is_child_algorithm=True)['OUTPUT']

    side_buffers = []
    for direction in [1, -1]:
        # Buffering subsegments
        alg_param = {
        'INPUT':split,
        'OUTPUT_GEOMETRY':0,'WITH_Z':False,
        'WITH_M':False,
        'EXPRESSION':f"single_sided_buffer( @geometry, {direction} * ({BUFF_FLAT} + {0.5 + BUFF_RATIO} * overlay_nearest('{parameters['ptref_widths']}', Largeur_Mod)[0]))",
        'OUTPUT': QgsProcessingUtils.generateTempFilename("side_buffers.shp")
        }
        side_buffers.append(processing.run("native:geometrybyexpression", alg_param, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT'])
    
    alg_params = {'LAYERS':side_buffers,'CRS':None,'OUTPUT': QgsProcessingUtils.generateTempFilename("Buffers.shp")}
    res_id = processing.run("native:mergevectorlayers", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
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
    alg_params = {'INPUT':parameters['rivnet'],'DISTANCE':1000,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':True,'OUTPUT':QgsProcessingUtils.generateTempFilename("Buffer.shp")}
    buffer = processing.run("native:buffer", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    alg_params = {'INPUT':parameters['landuse'],'MASK':buffer,'SOURCE_CRS':None,'TARGET_CRS':None,'TARGET_EXTENT':None,'NODATA':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':False,'OPTIONS':'','DATA_TYPE':0,'EXTRA':'','OUTPUT':QgsProcessingUtils.generateTempFilename("clip.tif")}
    clip = processing.run("gdal:cliprasterbymasklayer", alg_params,context=context, feedback=feedback)['OUTPUT']


    CLASSES = ['300', '360', '1']

    # Reclassify land use
    alg_params = {
        'DATA_TYPE': 0,  # Byte
        'INPUT_RASTER': clip,
        'NODATA_FOR_MISSING': True,
        'NO_DATA': 0,
        'RANGE_BOUNDARIES': 2,  # min <= value <= max
        'RASTER_BAND': 1,
        'TABLE': CLASSES,
        'OUTPUT': QgsProcessingUtils.generateTempFilename("reclass_and_use.tif")
    }
    reclass = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    alg_params = {
        'BAND': 1,
        'EIGHT_CONNECTEDNESS': False,
        'EXTRA': '',
        'FIELD': 'DN',
        'INPUT': reclass,
        'OUTPUT': QgsProcessingUtils.generateTempFilename("Vector_landuse.shp")
    }
    poly_path = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

    return QgsVectorLayer(poly_path, "landuse", "ogr")


def computeF3(intersect_arr):
    # Compute Iqm from sequence continuity
    ratio = np.mean(1 - intersect_arr) # Sum number of unrestricted segments

    if (ratio >= 0.9):
        return 0
    if (ratio >= 0.66):
        return 2
    if (ratio >= 0.33):
        return 3
    return 5
