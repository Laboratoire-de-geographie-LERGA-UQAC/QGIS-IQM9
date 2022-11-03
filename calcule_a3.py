"""
Model exported as python.
Name : Indice A3
Group : 
With QGIS : 32601
"""
from tempfile import NamedTemporaryFile as Ntf
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProcessing,
                       QgsField,
                       QgsFeatureSink,
                       QgsVectorLayer,
                       QgsFeatureRequest,
                      )
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsCoordinateReferenceSystem, QgsProcessingFeatureSourceDefinition
import processing


class IndiceA3(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'Utilisation du territoir', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Cours d\'eau', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('sink', 'Output', defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        results = {}
        outputs = {}
        
        # Create temporary file locations
        tmp = {
            'table':Ntf(suffix="table"),
            'buffer':Ntf(suffix="buffer")
        }
                
        # Define source stream net 
        source = self.parameterAsSource(parameters, 'stream_network', context)
        
        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A3", QVariant.Int))
        
        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            'sink',
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )
               
        # LandUse classes of interest
        # MELCC landuse classification
        # 1:Autres, 2:aggricole, 3:anthropique, 4:aquatique
        CLASSES = ['101','199','2', '300', '360', '3', '20', '27', '4']
        # Extend classes to other environments
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
            'INPUT_RASTER': parameters['landuse'],
            'NODATA_FOR_MISSING': False,
            'NO_DATA': 0,
            'RANGE_BOUNDARIES': 2,  # min <= value <= max
            'RASTER_BAND': 1,
            'TABLE': table,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
                    

        
        
        ############ LOOP GOES HERE ############
        # Looping through vertices
        #fid_index = outputs['ExtractSpecificVertex']['OUTPUT'].fields().indexFromName('fid')
        #fid_ids = outputs['ExtractSpecificVertex']['OUTPUT'].uniqueValues(fid_index)
                
        #for fid in list(fid_ids)[189:192]:
        features = [f for f in source.getFeatures()]
        feature_count = source.featureCount()
        id_field = 'Id'
        for current, feature in enumerate(features):
            fid = feature[id_field]
            
            # For each pour point
            # Compute the percentage of forests and agriculture lands in the draining area
            # Then compute index_A1 and add it in a new field to the river network
            if feedback.isCanceled():
                return {}
            
                    # Get segments buffers
            single_segment = source.materialize(QgsFeatureRequest().setFilterFids([fid]))
            buffer_width = max(
                feature['width'] * 2.5, # twice river width on each side
                feature['width'] * 0.5 + 15
            )
            params = {'INPUT':single_segment,
                'DISTANCE':buffer_width,
                'SEGMENTS':5,'END_CAP_STYLE':1,'JOIN_STYLE':1,'MITER_LIMIT':2,'DISSOLVE':False,
                'OUTPUT': tmp['buffer'].name
            }
            outputs['buffer'] = processing.run("native:buffer", params, context=context, feedback=feedback, is_child_algorithm=True)

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
                'OUTPUT': f"tmp/land_use_clip_{fid}.tif"#QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Landuse unique values report
            alg_params = {
                'BAND': 1,
                'INPUT': outputs['Drain_areaLand_use']['OUTPUT'],
                'OUTPUT_TABLE': tmp['table'].name
            }
            outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Here we compute forest and agri area, the add to new feture
            table = QgsVectorLayer(
                outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE'],            
                'table', 'ogr'
            )
            
            class_areas = {feat['value']:feat['m2'] for feat in table.getFeatures()}
            land_area = sum(class_areas.values()) - class_areas.get(4,0)
            anthro_area = class_areas.get(3, 0) + class_areas.get(2, 0)
            
            
            
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
            
            # Add forest area to new featuer
            feature.setAttributes(
                    feature.attributes() + [indiceA3]
            )
            
            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            print(f'{fid}/{feature_count}')
            print(f"{ratio=}\n{land_area=}\n{anthro_area=}\n\n")
        # Clear temporary files
        for tempfile in tmp.values():
            tempfile.close()
        
        return {'IQM': dest_id}

    def name(self):
        return 'Indice A3'

    def displayName(self):
        return 'Indice A3'

    def group(self):
        return 'IQM'

    def groupId(self):
        return 'iqm'

    def createInstance(self):
        return IndiceA3()
