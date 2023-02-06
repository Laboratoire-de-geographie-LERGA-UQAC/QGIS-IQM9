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
from collections import Counter
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
    STRUCTURES_PATH = '/home/karim/uqac/indice_F1/data/Structure_tq_shp/gsq_v_desc_strct_tri_rpr.shp'
    FID = "Id"
    

    def initAlgorithm(self, config=None):
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input layer'),
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        
        outputs = dict()
        
        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )
        
        # Create a QgsVectorLayer from source
        source_vl = QgsVectorLayer(parameters[self.INPUT],'hihi','memory')        
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

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # Send some information to the user
        feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))
        
        # find and read the structures shp file
        structures = QgsVectorLayer(self.STRUCTURES_PATH, 'structures','ogr')        
        
        prefix = "segment_"
        parameters = {
            "INPUT": structures,
            "INPUT_2": source.sourceName(),
            "DISCARD_NONMATCHING": True, 
            "FIELDS_TO_COPY": [self.FID],
            "MAX_DISTANCE": 8,
            "PREFIX": prefix,
            "NEIGHBORS": 2,
            "OUTPUT": "TEMPORARY_OUTPUT",
            #"area_units": "m2",
            #"distance_units": "meters",
            #"ellipsoid": "EPSG:7019",           
        }
        outputs['nearest'] = processing.run(
            "native:joinbynearest",
            parameters,
            context=context,feedback=feedback
        )
        
        QgsProject.instance().addMapLayer(outputs['nearest']['OUTPUT'])
        
        obstructed_ids = [feature[prefix + self.FID] for feature in outputs['nearest']['OUTPUT'].getFeatures()]
        obstructed_ids = Counter(obstructed_ids)
        
        print(obstructed_ids)
        
        # Compute the number of steps to display within the progress bar and
        # get features from source
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        features = [f for f in source.getFeatures()]
        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break
            id = feature.id()
            if id in obstructed_ids:
                if obstructed_ids[id] == 1:
                    indx_f1 = 2
                elif obstructed_ids[id] > 1:
                    indx_f1 = 4
            else:
                indx_f1 = 0
            
            feature.setAttributes(
                feature.attributes() + [indx_f1]
            )
            
            # Add a feature in the sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            # Update the progress bar
            feedback.setProgress(int(current * total))

        return {self.OUTPUT: dest_id}
    
    
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return calculerF1()

    def name(self):
        return 'calculerf1'

    def displayName(self):
        return self.tr('Indice F1')

    def group(self):
        return self.tr('IQM')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr("""Calcule de l'indice F1, à partire de la base de donnée des structures issue de \n
        https://www.donneesquebec.ca/recherche/dataset/structure#""")
