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

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterRasterDestination
                       )
from qgis import processing


class drain_area_land_use(QgsProcessingAlgorithm):
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

    RIV_NETWORK = 'RIV_NETWORK'
    DEM = 'DEM'
    tmp_ras_out = "test_out_raster"
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return drain_area_land_use()

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'drainarealanduse'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Drain area land use')

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr('IQM')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'IQM'

    def shortHelpString(self):
        """
        Returns a localised short helper string for the algorithm. This string
        should provide a basic description about what the algorithm does and the
        parameters and outputs associated with it..
        """
        return self.tr("""
        Calcule de l'indice de qualité morphologique A1_A2.
        Prend en entrée le DEM et le reseau de cours d'eau d'une region.
        calcule l'utilisation de sols des aires de drenage pour chaque segment de riviere.
        """)

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        # Add DEM input
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.DEM,
                self.tr('DEM'),
            )
        )
        
        # disabled for dev testing
        """ 
        # Add river network input
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RIV_NETWORK,
                self.tr('Cours d\'eau'),
                [QgsProcessing.TypeVectorLine]
            )
        )"""

        self.addParameter(
            QgsProcessingParameterRasterDestination(
            self.tmp_ras_out,
            self.tr("test Raster output")
            )
        )
        
        # Disabled for dev testing
        """
        # Add feature sink
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )"""
        
        
        #

    def processAlgorithm(self, parameters, context, feedback):
                
        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsRasterLayer(
            parameters,
            self.DEM,
            context
        )
        

        # If source was not found, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSourceError method to return a standard
        # helper text for when a source cannot be evaluated
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
            
            
        #(a, b) = self.parameterAs
        """
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            source.fields(),
            source.wkbType(),
            source.sourceCrs()
        )
        """
        # Send some information to the user
        feedback.pushInfo('CRS is {}'.format(source.crs().authid()))

        # To run another Processing algorithm as part of this algorithm, you can use
        # processing.run(...). Make sure you pass the current context and feedback
        # to processing.run to ensure that all temporary layer outputs are available
        # to the executed algorithm, and that the executed algorithm can send feedback
        # reports to the user (and correctly handle cancellation and progress reports!)
        sobel_filter = processing.run("wbt:SobelFilter", {
        'input': parameters[self.DEM],
        'variant':0,
        'clip':0,
        'output':'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback)
        
        #print(type(sobel_filter), sobel_filter, sep="\n")
        #out = QgsProcessingUtils.mapLayerFromString('TEMPORARY_OUTPUT', context)
        print(qgis._core.QgsProcessingUtils)
    
        if False:
            buffered_layer = processing.run("native:buffer", {
                'INPUT': dest_id,
                'DISTANCE': 1.5,
                'SEGMENTS': 5,
                'END_CAP_STYLE': 0,
                'JOIN_STYLE': 0,
                'MITER_LIMIT': 2,
                'DISSOLVE': False,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
        
        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.
        return {self.OUTPUT: sobel_filter}
    
