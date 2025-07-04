"""
Model exported as python.
Name : Indice A3
Group :
With QGIS : 32601
"""
from tempfile import NamedTemporaryFile as Ntf
import os
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (QgsProcessing,
                        QgsField,
                        QgsFeatureSink,
                        QgsVectorLayer,
                        QgsFeatureRequest,
                        QgsProcessingAlgorithm,
                        QgsProcessingParameterRasterLayer,
                        QgsProcessingParameterNumber,
                        QgsProcessingParameterVectorLayer,
                        QgsProcessingParameterFeatureSink,
                        QgsProcessingParameterRasterDestination,
                        QgsCoordinateReferenceSystem,
                        QgsProcessingFeatureSourceDefinition,
                        QgsExpression,
                        QgsExpressionContext,
                        QgsExpressionContextUtils,
                    )
import processing


class IndiceA3(QgsProcessingAlgorithm):
    ID_FIELD = 'Id'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr("Réseau hydrographique (CRHQ)"), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', self.tr('PtRef largeur (CRHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))


    def processAlgorithm(self, parameters, context, model_feedback):

        outputs = {}

        # Create temporary file locations
        tmp = {
            'table':Ntf(suffix="table", delete=False),
            'buffer':Ntf(suffix="buffer", delete=False),
            'mainWatershed':Ntf(suffix="watershed.tif", delete=False),
        }

        # Define source stream net
        source = self.parameterAsSource(parameters, 'stream_network', context)
        source_vlayer = self.parameterAsVectorLayer(parameters, 'stream_network', context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A3", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        if model_feedback.isCanceled():
            return {}

        # Defin dams layer
        dams = self.parameterAsVectorLayer(parameters, 'dams', context)
        assert dams.isValid(), "dams not valid"

        # Reclassify land use
        # LandUse classes of interest
        # MELCC landuse classification
        CLASSES = ['101','199','2', '300', '360', '3', '20', '27', '4'] # 1:Autres, 2:aggricole, 3:anthropique, 4:aquatique
        # Extend classe table to other environments
        table = CLASSES.copy()
        for i in [2, 4, 5, 6, 7, 8]:
            for j in range(len(CLASSES)):
                c = int(CLASSES[j])
                if (j + 1) % 3 != 0:
                    c += i * 1000
                table.append(str(c))
        alg_params = {
            'DATA_TYPE': 0,  # Byte
            'INPUT_RASTER': parameters['landuse'],
            'NODATA_FOR_MISSING': False,
            'NO_DATA': 0,
            'RANGE_BOUNDARIES': 2,  # min <= value <= max
            'RASTER_BAND': 1,
            'TABLE': table,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=None, is_child_algorithm=True)

        # Snap dams to river network
        alg_params = {
            'BEHAVIOR': 1,  # Prefer closest point, insert extra vertices where required
            'INPUT': parameters['dams'],
            'REFERENCE_LAYER': parameters['stream_network'],
            'TOLERANCE': 75,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['SnappedDams'] = processing.run('native:snapgeometries', alg_params, context=context, feedback=None, is_child_algorithm=True)

        if model_feedback.isCanceled():
            return {}
        # Extract specific vertex
        # TODO : try and remove is_child_algorithm
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-2',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractSpecificVertex'] = processing.run(
            'native:extractspecificvertices', alg_params, context=context, feedback=None, is_child_algorithm=True)

        if model_feedback.isCanceled():
            return {}

        # Gets the number of features to iterate over for the progress bar
        total_features = source.featureCount()
        model_feedback.pushInfo(self.tr(f"\t {total_features} features à traiter"))

        fid_idx = source.fields().indexFromName(self.ID_FIELD)

        # Looping through vertices
        for current, feature in enumerate(source.getFeatures()):
            fid = feature[fid_idx]

            # For each pour point
            # Compute the percentage of forests and agriculture lands in the draining area
            # Then compute index_A1 and add it in a new field to the river network
            if model_feedback.isCanceled():
                return {}

            # Find number of dames in watershed
            # Get segment pour point
            # Extract By Attribute
            alg_params = {
                'FIELD': self.ID_FIELD,
                'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
                'OPERATOR': 0,  # =
                'VALUE': str(fid),
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }

            outputs['single_point'] = processing.run(
                'native:extractbyattribute', alg_params, context=context, feedback=None, is_child_algorithm=True)

            # Watershed
            alg_params = {
                'd8_pntr': parameters['D8'],
                'esri_pntr': False,
                'pour_pts': outputs['single_point']['OUTPUT'],
                'output': tmp['mainWatershed'].name
            }
            outputs['mainWatershed'] = processing.run(
                'wbt:Watershed', alg_params, context=context, feedback=None, is_child_algorithm=True)

            # Polygonize watershed (raster to vector)
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['mainWatershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                #'OUTPUT':tmp['mainWatershed'].name
            }
            outputs['mainWatershedPoly'] = processing.run(
                'gdal:polygonize', alg_params, context=context, feedback=None, is_child_algorithm=True)

            if model_feedback.isCanceled():
                return {}

            # materialize segment
            single_segment = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))
            # 1 Km buffer around river
            alg_params = {
                'INPUT': single_segment,
                'DISTANCE':1000,
                'SEGMENTS':5,'END_CAP_STYLE':0,
                'JOIN_STYLE':0,'MITER_LIMIT':2,
                'DISSOLVE':True,
                #'OUTPUT':f"tmp/buffer{fid}.gpkg"
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['damBuffer'] = processing.run("native:buffer", alg_params, context=context, feedback=None, is_child_algorithm=True)

            # Clip watershed by buffer
            alg_params = {
                'INPUT': outputs['mainWatershedPoly']['OUTPUT'],
                'OVERLAY': outputs['damBuffer']['OUTPUT'],
                #'OUTPUT': f"tmp/clipped_buffer_{fid}.gpkg"
                'OUTPUT':tmp['buffer'].name
                }
            outputs['buffer_clip'] = processing.run("native:clip", alg_params, context=context, feedback=None, is_child_algorithm=True)


            # Count number of dames in watershed
            alg_params = {
                'INPUT':dams,
                'PREDICATE':[6],
                'INTERSECT':outputs['buffer_clip']['OUTPUT'],
                'METHOD':0
            }
            processing.run("native:selectbylocation", alg_params, context=context, feedback=None, is_child_algorithm=True)
            dam_count = dams.selectedFeatureCount()


            #### LAND USE ANALYSIS
            # analyse land use on sides of stream
            # Get segments buffers
            feature_mean_width = ptrefs_mean_width(feature, source_vlayer, parameters['ptref_widths'])
            buffer_width = max(
                feature_mean_width * 2.5, # twice river width on each side
                feature_mean_width * 0.5 + 15
            )
            params = {
                'INPUT':single_segment,
                'DISTANCE':buffer_width,
                'SEGMENTS':5,'END_CAP_STYLE':1,'JOIN_STYLE':1,'MITER_LIMIT':2,'DISSOLVE':False,
                #'OUTPUT': tmp['buffer'].name,
                'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT,
                #'OUTPUT' : f"tmp/test_buffer{fid}.gpkg"
            }
            outputs['buffer'] = processing.run("native:buffer", params, context=context, feedback=None, is_child_algorithm=True)

            # Clip landuse by buffer
            alg_params = {
                'ALPHA_BAND': False,
                'CROP_TO_CUTLINE': True,
                'DATA_TYPE': 0,  # Use Input Layer Data Type
                'EXTRA': '',
                'INPUT': outputs['ReducedLanduse']['OUTPUT'],
                'KEEP_RESOLUTION': True,
                'MASK': outputs['buffer']['OUTPUT'],
                'MULTITHREADING': False,
                'NODATA': None,
                'OPTIONS': '',
                'SET_RESOLUTION': False,
                'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
                'TARGET_CRS': 'ProjectCrs',
                'TARGET_EXTENT': None,
                'X_RESOLUTION': None,
                'Y_RESOLUTION': None,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT#f"tmp/land_use_clip_{fid}.tif"#
            }
            outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=None, is_child_algorithm=True)

            # Landuse unique values report
            alg_params = {
                'BAND': 1,
                'INPUT': outputs['Drain_areaLand_use']['OUTPUT'],
                'OUTPUT_TABLE': tmp['table'].name
            }
            outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=None, is_child_algorithm=True)

            # Here we compute forest and agri area, the add to new feture
            table = QgsVectorLayer(
                outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE'],
                'table', 'ogr'
            )

            class_areas = {feat['value']:feat['m2'] for feat in table.getFeatures()}
            land_area = sum(class_areas.values()) - class_areas.get(4,0)
            anthro_area = class_areas.get(3, 0) + class_areas.get(2, 0)


            indiceA3 = computeA3(land_area, anthro_area, dam_count)

            # Add forest area to new featuer
            feature.setAttributes(
                    feature.attributes() + [indiceA3]
            )

            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            #print(f'{fid}/{total_features}')
            #print(f"{land_area=}\n{anthro_area=}\n{indiceA3=}\n\n")

            # Increments the progress bar
            if total_features != 0:
                progress = int(100*(current/total_features))
            else:
                progress = 0
            model_feedback.setProgress(progress)
            model_feedback.setProgressText(self.tr(f"Traitement de {current} segments sur {total_features}"))


        # Clear temporary files
        for tempfile in tmp.values():
            tempfile.close()
            os.remove(tempfile.name)

        # Ending message
        model_feedback.setProgressText(self.tr('\tProcessus terminé et fichiers temporaire nettoyés'))

        return {self.OUTPUT: dest_id}

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return IndiceA3()

    def name(self):
        return 'Indice A3'

    def displayName(self):
        return self.tr('Indice A3')

    def group(self):
        return self.tr('IQM (indice solo)')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice A3 afin d'évaluer l’altération des régimes hydrologiques et sédimentaires ainsi que la présence de formes au niveau de la plaine alluviale à l’échelle du segment.\n Le niveau d’anthropisation du segment et la présence d’unités géomorphologiques sur la plaine sont évalués à l’intérieur du corridor fluvial sur une largeur respective de deux fois la largeur du lit mineur pour les milieux non-confinés, ou de 15 m pour les milieux confinés. Le niveau d’anthropisation correspond à la surface de recouvrement relative à l’intérieur du corridor fluvial liée aux affectations urbanisées et agricoles. Une pénalité est appliquée en fonction du nombre de barrages à l’intérieur d’une distance de 1000 m à l’amont du segment analysé. Ces entraves qui créent des discontinuités dans le transport par charge de fond affectent grandement les conditions hydrauliques influençant les processus hydrogéomorphologiques et les formes présentes dans le lit mineur en aval de celles-ci.\n" \
            "Paramètres\n" \
            "----------\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "WBT D8 Pointer: Matriciel\n" \
            "-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
            "Barrages : Vectoriel (point)\n" \
            "-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
            "Utilisation du territoire : Matriciel\n" \
            "-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
            "PtRef largeur : Vectoriel (points)\n" \
            "-> Points de référence rapportant la largeur modélisée du segment contenant l'information de la couche PtRef et la table PtRef_mod_lotique provenant des données du CRHQ (couche sortante du script UEA_PtRef_join). Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice A3 calculé pour chaque UEA."
        )

def ptrefs_mean_width(feature, source, PtRef_id, width_field='Largeur_mod', context=None, feedback=None):
    expr = QgsExpression(f"""
            array_mean(overlay_nearest('{PtRef_id}', {width_field}, limit:=-1, max_distance:=5))
                """)
    feat_context = QgsExpressionContext()
    feat_context.setFeature(feature)

    scopes = QgsExpressionContextUtils.globalProjectLayerScopes(source)
    feat_context.appendScopes(scopes)

    mean_width = expr.evaluate(feat_context)
    if not mean_width : mean_width = 5

    return mean_width

def computeA3(land_area, anthro_area, dam_count):
    indiceA3 = 0
    if land_area != 0:
        ratio = anthro_area / land_area
        # Assigne index A3
        if ratio >= 0.9:
            indiceA3 = 4
        elif ratio >= 0.66:
            indiceA3 = 3
        elif ratio >= 0.33:
            indiceA3 = 2
        elif ratio >= 0.1:
            indiceA3 = 1
    # Add penality
    dam_penality = 0
    if dam_count == 1:
        dam_penality = 2
    elif dam_count > 1:
        dam_penality = 4
    indiceA3 += dam_penality
    return indiceA3
