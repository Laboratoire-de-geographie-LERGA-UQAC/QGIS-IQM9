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
                       )
from qgis import processing


class calculerIc(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        # We add the input vector features source. It can have any kind of
        # geometry.
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Réseau hydrographique (CRHQ)'),
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )

        # We add a feature sink in which to store our processed features (this
        # usually takes the form of a newly created vector layer when the
        # algorithm is run in QGIS).
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Couche de sortie')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )

        # If source was not found, throw an exception to indicate that the algorithm
        # encountered a fatal error. The exception text can be any string, but in this
        # case we use the pre-built invalidSourceError method to return a standard
        # helper text for when a source cannot be evaluated
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        #Adding new field to output
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A4", QVariant.Int))

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

        if True:
            # Compute the number of steps to display within the progress bar and
            # get features from source
            total = 100.0 / source.featureCount() if source.featureCount() else 0
            features = [f for f in source.getFeatures()]
            print(len(features))
            for current, feature in enumerate(features):
                # Stop the algorithm if cancel button has been clicked
                if feedback.isCanceled():
                    break

                # Find start and endpoint vertices
                feature_vertices = feature.geometry().vertices()
                feature_vertices = list(feature_vertices)
                (start_point, end_point) = (feature_vertices[0],feature_vertices[-1])

                distance = start_point.distance(end_point)

                if distance ==0:
                    # If start and endpoint are connected
                    IC = 1
                else:
                    IC = feature.geometry().length() / distance
                    # IC maxed at 2.5, subject to chage.
                    IC = min(IC, 2.5)

                if IC >= 1.5:
                    indice_A4 = 0
                elif IC >= 1.25:
                    indice_A4 = 2
                elif IC >= 1.05:
                    indice_A4 = 4
                else:
                    indice_A4 = 6

                feature.setAttributes(
                    feature.attributes() + [indice_A4]
                )

                # Add a feature in the sink
                sink.addFeature(feature, QgsFeatureSink.FastInsert)

                # Update the progress bar
                feedback.setProgress(int(current * total))

        return {self.OUTPUT: dest_id}




    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return calculerIc()

    def name(self):
        return 'indicea4'

    def displayName(self):
        return self.tr('Indice A4')

    def group(self):
        return self.tr('IQM')

    def groupId(self):
        return 'iqm'

    def shortHelpString(self):
        return self.tr(
            "Calcule de l'indice A4 afin d'évaluer le niveau d’altération par l’entremise d’un indice de complexité du tracé fluvial.\n L'indice de complexité du tracé fluvial correspond à l'indice de sinuosité moyen de l’ensemble des chenaux à l’intérieur du segment. La somme des indices de sinuosité est par la suite divisé par le nombre de chenaux pour obtenir l'indice de complexité. Ainsi, plus le segment possède un indice de complexité faible, plus grandes sont les probabilités que les profils longitudinaux et transversaux soient homogènes et que les conditions hydrogéomorphologiques naturelles aient été perturbées par des interventions de nature anthropique\n" \
            "Paramètres\n" \
            "----------\n" \
            "Réseau hydrographique : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
            "Retourne\n" \
            "----------\n" \
            "Couche de sortie : Vectoriel (lignes)\n" \
            "-> Réseau hydrographique du bassin versant avec le score de l'indice A4 calculé pour chaque UEA."
        )
