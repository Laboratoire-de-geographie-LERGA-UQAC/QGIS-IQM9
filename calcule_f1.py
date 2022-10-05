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
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsVectorLayer,
                       QgsProject,
                       QgsFeatureRequest,
                       QgsSpatialIndex
                       )
from qgis import processing


class calculerF1(QgsProcessingAlgorithm):
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

    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return calculerF1()

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'calculerf1'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Calcule F1')

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
        return self.tr("""Calcule de l'indice F1, à partire de la base de donnée des structures issue de \n
        https://www.donneesquebec.ca/recherche/dataset/structure#""")

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """

        # We add the input vector features source. It can have any kind of
        # geometry.
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input layer'),
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )

        # We add a feature sink in which to store our processed features (this
        # usually takes the form of a newly created vector layer when the
        # algorithm is run in QGIS).
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )
######################################################################################################
    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """

        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )
        # Create a QgsVectorLayer from source
        source_vl = QgsVectorLayer(parameters[self.INPUT],'hihi','memory')
        
        # If source was not found, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSourceError method to return a standard
        # helper text for when a source cannot be evaluated
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
            
        #Adding new field to output
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice F1", QVariant.Int))
        
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        # Send some information to the user
        feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))

        # If sink was not created, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSinkError method to return a standard
        # helper text for when a sink cannot be evaluated
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        
        # find and read the structures shp file
        structures_path = '/home/karim/uqac/indice_F1/data/Structure_tq_shp/gsq_v_desc_strct_tri_rpr.shp'
        structure = QgsVectorLayer(structures_path, 'structures','ogr')

        # clip to current extent
        req = QgsFeatureRequest().setFilterRect(source.sourceExtent())
        cliped = structure.materialize(req)
        QgsProject.instance().addMapLayer(cliped)
        
        # find source features closest to structures
        # by constructing spatial index
        index = QgsSpatialIndex(source.getFeatures())
        
        # Seek obstructed rivers
        obstructed_ids = []
        # nearest neighbore threshold distance
        minDistance = 2000
        for point in cliped.getFeatures():
            pointGeo = point.geometry()
            nearest_neighbor_id = index.nearestNeighbor(pointGeo,1)[0]
            nearest_neighbor = source_vl.getFeature(nearest_neighbor_id)
            nearest_neighbor_distance = nearest_neighbor.geometry().distance(pointGeo)
            if nearest_neighbor_distance < minDistance:
                obstructed_ids.append(nearest_neighbor_id)        
        
        # Seek up and downstream segments (1km)
        
        #add new field to streams and output
        
        
    ######################################################################################################
        if True:
            # Compute the number of steps to display within the progress bar and
            # get features from source
            total = 100.0 / cliped.featureCount() if cliped.featureCount() else 0
            features = [f for f in source.getFeatures()]
            print(len(features))
            for current, feature in enumerate(features):
                # Stop the algorithm if cancel button has been clicked
                if feedback.isCanceled():
                    break
                if feature.id() in obstructed_ids:
                    indx_f1 = 2
                else:
                    indx_f1 = 0
                
                feature.setAttributes(
                    feature.attributes() + [indx_f1]
                )
                
                # Add a feature in the sink
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

                # Update the progress bar
                feedback.setProgress(int(current * total))



        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.
        return {self.OUTPUT: dest_id}
