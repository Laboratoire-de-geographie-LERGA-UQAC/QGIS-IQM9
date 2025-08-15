
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsProcessingContext,
                       QgsFeatureSink,
                       QgsField,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterFeatureSink,
                       QgsWkbTypes,
                       QgsVectorLayer,
                       QgsFeature,
                       QgsFeatureRequest,
                       QgsGeometry
                       )
from qgis import processing


class IndiceF1(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, self.tr('Réseau hydrographique (CRHQ)'), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer('structs', self.tr('Structures filtrées (sortant de Filter structures; MTMD)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie')))

    def processAlgorithm(self, parameters, context, model_feedback):
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
        sink_fields.append(QgsField("Nb_struct_amont", QVariant.Int))

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
 
        structure_counts = {}
        struct_layer = self.parameterAsVectorLayer(parameters, 'structs', context)
        hydro_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)


        # Gets the number of features to iterate over for the progress bar
        total_features = struct_layer.featureCount()
        model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

        try :
            for current, struct in enumerate(struct_layer.getFeatures()):
                current_feat = None
                try :
                    # Finds the river segment of the current structure
                    current_feat = find_segment_for_structure(struct, hydro_layer, context)
                except Exception as e :
                    model_feedback.reportError(self.tr(f"Erreur dans find_segment_for_structure : {str(e)}"))
                if current_feat is None:
                    continue

                downstream_feat = None
                try :
                    # Finds the downstream river segment
                    downstream_feat = get_downstream_segment(hydro_layer, current_feat)
                except Exception as e :
                    model_feedback.reportError(self.tr(f"Erreur dans get_downstream_segment : {str(e)}"))
                if downstream_feat is None:
                    continue

                intersection_point = None
                try :
                    # Find the intersecting point between the structure river segment and the downstream segment
                    intersection_point = get_intersection_point(current_feat, downstream_feat)
                except Exception as e :
                    model_feedback.reportError(self.tr(f"Erreur dans get_intersection_point : {str(e)}"))
                if intersection_point is None:
                    continue

                try :
                    # Calculates the distance along the network between the structure and this point
                    cost = compute_shortest_path(struct, intersection_point, hydro_layer, model_feedback, context)
                except Exception as e :
                    model_feedback.reportError(self.tr(f"Erreur dans compute_shortest_path : {str(e)}"))

                # If the distance is < 1000 m, increment the downstream segment structure counter.
                if cost is None :
                    continue
                if cost < 1000:
                    downstream_id = downstream_feat['Id_UEA']
                    structure_counts[downstream_id] = structure_counts.get(downstream_id, 0) + 1

                # Updating the progress bar
                if total_features != 0:
                    progress = int(100*(current/total_features))
                else:
                    progress = 0
                model_feedback.setProgress(progress)

                if model_feedback.isCanceled():
                    return {}
        except Exception as e :
            model_feedback.reportError(self.tr(f"Erreur dans la boucle de structure : {str(e)}"))

        model_feedback.setProgressText(self.tr(f"Compte des structures terminé."))
        if model_feedback.isCanceled():
            return {}

        # Computing the F1 score for each river segment
        try :
            for feat in source.getFeatures():
                seg_id = feat['Id_UEA']
                struct_count = structure_counts.get(seg_id, 0)
                f1_score = computeF1(struct_count)

                # add both the structure count and the f1_score to the attributes table
                feat.setAttributes(feat.attributes() + [f1_score, struct_count])
                sink.addFeature(feat, QgsFeatureSink.FastInsert)
        except Exception as e :
            model_feedback.reportError(self.tr(f"Erreur dans le calcul de F1 et le sink des features : {str(e)}"))

        model_feedback.setProgressText(self.tr(f"Calcul du score de F1 terminé."))
        if model_feedback.isCanceled():
                return {}

        # Ending message
        model_feedback.setProgressText(self.tr('\tProcessus terminé !'))

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


def find_segment_for_structure(structure, hydro_layer, context, distance=5):
    # Use the QGIS processing to select river segments located within `distance` meters of the structure point.
    # Create a temporary layer with the structure point
    point_layer = QgsVectorLayer("Point?crs=" + hydro_layer.crs().authid(), "structure_point", "memory")
    provider = point_layer.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(structure.geometry())
    provider.addFeatures([feat])
    point_layer.updateExtents

    alg_params = {
        'INPUT': hydro_layer,
        'REFERENCE': point_layer,
        'DISTANCE': distance,
        'METHOD': 0 # 0, create a new selection
    }
    processing.run("native:selectwithindistance", alg_params, context=context, is_child_algorithm=True)
    selected_feats = list(hydro_layer.getSelectedFeatures())
    # Returns the first segment found (the closest one)
    return selected_feats[0] if selected_feats else None


def get_downstream_segment(hydro_layer, current_feat):
    # Retrieves the ID of the downstream segment from the attribute field.
    downstream_id = current_feat['Id_UEA_aval']
    # Search for the corresponding segment in the layer
    request = QgsFeatureRequest().setFilterExpression(f'"Id_UEA" = \'{downstream_id}\'')
    return next(hydro_layer.getFeatures(request), None)


def get_intersection_point(feat1, feat2):
    # Calculates the geometric intersection between the two segments
    intersection = feat1.geometry().intersection(feat2.geometry())
    # If the intersection is a point, return it
    if intersection and intersection.type() == QgsWkbTypes.PointGeometry:
        return intersection
    # If it's a multipoint, we take the first one.
    elif intersection and intersection.type() == QgsWkbTypes.MultiPointGeometry:
        return intersection.asMultiPoint()[0]
    # Otherwise, we return None
    return None


def compute_shortest_path(structure_point, target_point, hydro_layer, feedback, context):
    # Extract the coordinates for the points
    start_coords = structure_point.geometry().asPoint()
    end_coords = target_point.asPoint()

    # Find the shortest path on the river network between the downstream segment and the given structure to get the distance between the two
    alg_params = {
        'INPUT': hydro_layer,
        'STRATEGY': 0,  # 0 = shortest path
        'START_POINT': f"{start_coords.x()},{start_coords.y()}",
        'END_POINT': f"{end_coords.x()},{end_coords.y()}",
        'DEFAULT_DIRECTION': 2,
        'DEFAULT_SPEED': 1,
        'TOLERANCE': 5,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    }
    result = processing.run("native:shortestpathpointtopoint", alg_params, context=context, is_child_algorithm=True)
    temp_layer = context.takeResultLayer(result['OUTPUT'])

    if not temp_layer.isValid():
        feedback.reportError("La couche temporaire n'est pas valide.")
        return None
    if 'cost' not in temp_layer.fields().names():
        feedback.reportError("Le champ 'cost' est introuvable dans la couche de chemin.")
        return None

    path_feat = next(temp_layer.getFeatures(), None)
    # Return the length of the shortest path on the river network ('cost' field)
    return path_feat['cost'] if path_feat else None


def computeF1(struct_count):
    if struct_count == 0:
        # No obstruction or alteration in the continuity of sediment and wood transport upstream of the segment
        return 0
    if struct_count <= 1:
        # Presence of at least one obstacle to the continuous flow of sediment and wood upstream of the segment
        return 2
    elif struct_count > 1:
        # Presence of more than one obstacle to the continuous flow of sediment and wood upstream of the segment
        return 4
