from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
	QgsProcessing,
	QgsFeatureSink,
	QgsField,
	QgsProcessingException,
	QgsProcessingAlgorithm,
	QgsProcessingParameterFeatureSource,
	QgsProcessingParameterFeatureSink)
from qgis import processing


class calculerIc(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

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

        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )

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

        feedback.pushInfo('CRS is {}'.format(source.sourceCrs().authid()))

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        if True:
            # Compute the number of steps to display within the progress bar and
            # get features from source
            total = 100.0 / source.featureCount() if source.featureCount() else 0
            features = [f for f in source.getFeatures()]

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
        return self.tr("Clacule l'indice A4 de l'IQM (sinuosité)")
