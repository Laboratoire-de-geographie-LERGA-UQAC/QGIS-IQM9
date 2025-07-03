"""
Model exported as python.
Name : IQM indice F5
Group :
With QGIS : 32802
Author : Karim Mehour
"""

import numpy as np
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingUtils,
    QgsField,
    QgsFeatureSink,
    QgsFeatureRequest,
    QgsExpression,
    QgsVectorLayer,
    QgsExpressionContext,
    QgsProcessingAlgorithm,
    QgsExpressionContextUtils,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProperty,
)
import sys

class IndiceF5(QgsProcessingAlgorithm):
    OUTPUT = 'OUTPUT'
    ID_FIELD = 'Id'
    TRANSECT_RATIO = 3

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                'bande_riveraine_polly',
                self.tr('Bande riveraine (peuplement forestier; MELCCFP)'),
                types=[QgsProcessing.TypeVectorPolygon],
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                'ptref_widths',
                self.tr('PtRef largeur (CRHQ)'),
                types=[QgsProcessing.TypeVectorPoint],
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

        # Define source stream net
        source = self.parameterAsSource(parameters, 'rivnet', context)

        # Define Sink
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F5", QVariant.Int))
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        # Gets the number of features to iterate over for the progress bar
        total_features = source.featureCount()
        model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

        for current, segment in enumerate(source.getFeatures()):

            if model_feedback.isCanceled():
                return {}
    
            # gen transects, and analyse intersection with 'Bande riv'
            points_along_line = pointsAlongLines(segment, source, context, feedback=None)
            normals = gen_split_normals(points_along_line, parameters, context, feedback=None)
            br_widths_arr = get_bandriv_width_arr(normals, parameters)

            # Compute the IQM Score
            indiceF5 = computeF5(br_widths_arr)

            # Write Index to layer
            segment.setAttributes(
                segment.attributes() + [indiceF5]
            )
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
        return IndiceF5()

    def name(self):
        return 'indicef5'

    def displayName(self):
        return self.tr('Indice F5')

    def group(self):
        return self.tr('IQM (indice solo)')

    def groupId(self):
        return self.tr('iqm')

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice F5 afin d'évaluer la largeur et la continuité longitudinale de la bande riveraine fonctionnelle de part et d’autre du lit mineur à l’intérieur du corridor fluvial.\n La bande riveraine fonctionnelle consiste à la portion végétale ligneuse dont la hauteur moyenne au-dessus de 1 m est susceptible de contribuer à l’apport en bois. La continuité de la végétation est évaluée par la distance longitudinale relative en contact avec une bande riveraine d’une largeur donnée. La qualité morphologique du segment varie en fonction de la largeur de la bande riveraine (pour une largeur prédéterminée de 50, 30 ou 15 m à partir de la limite du lit mineur) et la continuité à l’intérieur du segment qui s’exprime en pourcentage (%). Dans le cas de la présence de plusieurs chenaux (p.ex. style divagant ou anabranche), les îlots végétalisés sont comptabilisés dans le calcul de la largeur de bande riveraine.\n" \
            "Paramètres\n" \
            "----------\n" \
            "Bande riveraine : Vectoriel (polygones)\n" \
            "-> Données vectorielles surfacique des peuplements écoforestiers pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Carte écoforestière à jour, [Jeu de données], dans Données Québec.\n" \
            "PtRef largeur : Vectoriel (points)\n" \
            "-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie :  Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice F5 calculé pour chaque UEA."
        )


def pointsAlongLines(feature, source, context, feedback=None, output=None):
    NUMBER = 50

    feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))

    # Points along lines
    alg_params = {
        'DISTANCE': QgsProperty.fromExpression(f"length(@geometry) / {NUMBER}"),
        'END_OFFSET': 0,
        'INPUT': feature,
        'START_OFFSET': 0,
        'OUTPUT': QgsProcessingUtils.generateTempFilename("points.shp"),
    }
    result_id = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return QgsVectorLayer(result_id, 'points', "ogr")


def gen_split_normals(points, parameters, context, feedback=None, output=None):
    # Geometry by expression
    TRANSECT_RATIO = 1.5
    TRANSECT_FLAT = 30

    side_normals = []
    for angle in [90, -90]:
        alg_params = {
            'EXPRESSION':f"""with_variable(
                'len',overlay_nearest('{parameters['ptref_widths']}',Largeur_mod)[0] * {0.5 + TRANSECT_RATIO} + {TRANSECT_FLAT},
                make_line(@geometry,project(@geometry,@len,radians(\"angle\" + {angle}))))
            """,
            'INPUT': points,
            'OUTPUT_GEOMETRY': 1,  # Line
            'WITH_M': False,
            'WITH_Z': False,
            'OUTPUT': QgsProcessingUtils.generateTempFilename("split_normals.shp")
        }
        side_normals.append(processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT'])
    
    alg_params = {'LAYERS':side_normals, 'CRS':None, 'OUTPUT':QgsProcessingUtils.generateTempFilename("normals.shp")}
    res_id = processing.run("native:mergevectorlayers", alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
    return QgsVectorLayer(res_id, 'normals', "ogr")


def evaluate_expression(expression_str, vlayer, feature=None ):
    expression = QgsExpression(expression_str)
    context = QgsExpressionContext()
    if feature:
        context.setFeature(feature)
    scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
    context.appendScopes(scopes)
    res = expression.evaluate(context)
    return res


def get_bandriv_width_arr(vlayer, parameters):
    #Evaluating intersection distance
    intersection_expr = f"""
        max(
            0,
            length(
                segments_to_lines(
                    intersection(
                        @geometry,collect_geometries(
                            overlay_intersects('{parameters['bande_riveraine_polly']}',@geometry)
                        )
                    )
                )
            )
        )
    """
    expr = QgsExpression(f"array_agg({intersection_expr})")
    result = np.array(evaluate_expression(expr, vlayer))
    return result


def computeF5(br_widths_arr):
    # Compute Iqm from sequence continuity
    if (np.mean(br_widths_arr >= 30)  >= 0.9):
        return 0
    if (np.mean(br_widths_arr >= 30) >= 0.66):
        return 1
    if (np.mean(br_widths_arr >= 15) >= 0.66):
        return 2
    if (np.mean(br_widths_arr >= 30) >= 0.33):
        return 2
    if (np.mean(br_widths_arr >= 15) >= 0.33):
        return 3
    return 4
