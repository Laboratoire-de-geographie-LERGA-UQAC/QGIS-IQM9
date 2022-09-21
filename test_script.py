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

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsField,
                       QgsFields,
                       QgsFeature,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterRasterLayer,
                       QgsCoordinateReferenceSystem)
from qgis import processing


class ExampleProcessingAlgorithm(QgsProcessingAlgorithm):
    """
    This is an example algorithm that takes a vector layer and
    creates a new identical one.

    It is meant to be used as an example of how to create your own
    algorithms and explain methods and variables used to do it. An
    algorithm like this will be available in all elements, and there
    is not need for additional work.

    All Processing algorithms should extend the QgsProcessingAlgorithm
    class.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    INPUT = 'INPUTs'
    OUTPUT = 'OUTPUT'



    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                self.tr('Cours d\'eau'),
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )
        
        self.addParameter(QgsProcessingParameterRasterLayer('d8', 'D8 Pointer'))
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'LandUse'))
        
        
        # We add a feature sink in which to store our processed features (this
        # usually takes the form of a newly created vector layer when the
        # algorithm is run in QGIS).
        #self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT,self.tr('Output layer')))

    def processAlgorithm(self, parameters, context, feedback):
        
        #outputs dict
        outputs = {}
        results = {}
        
        # add rlayer as source
        v_layer = self.parameterAsVectorLayer( parameters, self.INPUT, context)
        
        
        fields = QgsFields()
        fields.append(QgsField('fid',QVariant.String))
        # Extract specific vertex
        alg_params = {
            'INPUT': parameters[self.INPUT],
            'VERTICES': '-2',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['vertices'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback)
        results['single'] = "tmp/single_outlet1337.shp"

        fid_index = outputs['vertices']['OUTPUT'].fields().indexFromName('fid')
        fid_ids = outputs['vertices']['OUTPUT'].uniqueValues(fid_index)
        
        
        for fid in list(fid_ids)[189:195]:
            # Extract By Attribute
            alg_params = {
            'FIELD': 'fid',
            'INPUT': outputs['vertices']['OUTPUT'],
            'OPERATOR': 0,  # =
            'VALUE': str(fid),
            'OUTPUT': results['single']
            }
            
            outputs['single_point']= processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback)
                        
            results['watershed'] = 'tmp/watershed1337.tif'
            alg_params = {
                'd8_pntr': parameters['d8'],
                'esri_pntr': False,
                'pour_pts': outputs['single_point']['OUTPUT'],
                'output': results['watershed']#"tmp/watershed_{}.tif".format(fid)
            }
            outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback)
            
            # Polygonize (raster to vector)
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['Watershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Drain_area Land_use
            alg_params = {
                'ALPHA_BAND': False,
                'CROP_TO_CUTLINE': True,
                'DATA_TYPE': 0,  # Use Input Layer Data Type
                'EXTRA': '',
                'INPUT': parameters['landuse'],
                'KEEP_RESOLUTION': True,
                'MASK': outputs['PolygonizeRasterToVector']['OUTPUT'],
                'MULTITHREADING': False,
                'NODATA': None,
                'OPTIONS': '',
                'SET_RESOLUTION': False,
                'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
                'TARGET_CRS': 'ProjectCrs',
                'TARGET_EXTENT': None,
                'X_RESOLUTION': None,
                'Y_RESOLUTION': None,
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

            # Reduced Landuse
            alg_params = {
                'DATA_TYPE': 0,  # Byte
                'INPUT_RASTER': outputs['Drain_areaLand_use']['OUTPUT'],
                'NODATA_FOR_MISSING': True,
                'NO_DATA': 0,
                'RANGE_BOUNDARIES': 2,  # min <= value <= max
                'RASTER_BAND': 1,
                'TABLE': ['50','56','1','210','235','1','501','735','1','101','199','2'],
                'OUTPUT': "tmp/reduced_landuse_{}.tif".format(fid)#QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            results['Tmpreclassifiedtif'] = outputs['ReducedLanduse']['OUTPUT']
            
            # Landuse unique values report
            alg_params = {
                'BAND': 1,
                'INPUT': outputs['ReducedLanduse']['OUTPUT'],
                'OUTPUT_TABLE': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
            #results['Report'] = outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE'].id()
            
            table = outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE']
            for feat in table.getFeatures():
                print(feat.fields().names(), feat.attributes(), sep="\n")
            print()
            
        return results   
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ExampleProcessingAlgorithm()

    def name(self):
        return 'myscript'

    def displayName(self):
        return self.tr('My Script')

    def group(self):
        return self.tr('Example scripts')

    def groupId(self):
        return 'examplescripts'

    def shortHelpString(self):
        return self.tr("Example algorithm short description")
