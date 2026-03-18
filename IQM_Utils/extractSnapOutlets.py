
"""
*********************************************************************************
*																				*
*		QGIS-IQM9 is a program developed for QGIS as a tool to automatically	*
*	calculate the Morphological Quality Index (MQI) of river systems			*
*	Copyright (C) 2025 Laboratoire d'expertise et de recherche en géographie	*
*	appliquée (LERGA) de l'Université du Québec à Chicoutimi (UQAC)				*
*																				*
*	This program is free software: you can redistribute it and/or modify		*
*	it under the terms of the GNU Affero General Public License as published	*
*	by the Free Software Foundation, either version 3 of the License, or		*
*	(at your option) any later version.											*
*																				*
*	This program is distributed in the hope that it will be useful,				*
*	but WITHOUT ANY WARRANTY; without even the implied warranty of				*
*	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the				*
*	GNU Affero General Public License for more details.							*
*																				*
*	You should have received a copy of the GNU Affero General Public License	*
*	along with this program.  If not, see <https://www.gnu.org/licenses/>.		*
*																				*
*********************************************************************************
"""


from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsProcessingAlgorithm,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterString,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterVectorDestination,
	QgsProperty,
	QgsProcessingUtils
)
import processing


class ExtractAndSnapOutlets(QgsProcessingAlgorithm):
	DEFAULT_SEG_ID_FIELD= 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterRasterLayer('dem', self.tr('MNT LiDAR (10 m)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterVectorDestination('snapped_outlets', self.tr('Couche de sortie (Snapped_outlets)'), type=QgsProcessing.TypeVectorPoint, createByDefault=True, defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)

		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro. ! Veuillez fournir un champ identifiant du segment présent comme attribut de la couche.")
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
		results = {}

		# Making layers and parameters needed for processing
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)

		# Interpolate point on line
		#interpolated_points_output = QgsProcessingUtils.generateTempFilename("interpolatedPoints.gpkg")
		alg_params = {
			'DISTANCE': QgsProperty.fromExpression('if(length($geometry) > 100, length($geometry) - 30, length($geometry) * 0.9)'),
			'INPUT': parameters['stream_network'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		interp = processing.run('native:interpolatepoint', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# RasterizeStreams
		alg_params = {
			'base': parameters['dem'],
			'feature_id': False,
			'nodata': True,
			'streams': parameters['stream_network'],
			'output': QgsProcessingUtils.generateTempFilename("snapped_tmp.tif")
		}
		Rasterizestreams = processing.run('wbt:RasterizeStreams', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# JensonSnapPourPoints
		snapped_tmp = QgsProcessingUtils.generateTempFilename("snapped_tmp.shp")
		alg_params = {
			'pour_pts': interp['OUTPUT'],
			'snap_dist': 40,
			'streams': Rasterizestreams['output'],
			'output': snapped_tmp
		}
		snapped = processing.run('wbt:JensonSnapPourPoints', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}
		
		# Copy the segment ID from the stream network to the snapped points
		alg_params = {
			'INPUT': snapped['output'], # snapped points as target
			'INPUT_2': parameters['stream_network'],            # join from lines
			'FIELDS_TO_COPY': [seg_id_field],
			'NEIGHBORS': 1,
			'MAX_DISTANCE': 50,                                 # Snap tolerance
			'DISCARD_NONMATCHING': False,
			'OUTPUT': parameters['snapped_outlets']
		}
		joined = processing.run('native:joinbynearest', alg_params,
								context=context, feedback=None, is_child_algorithm=True)['OUTPUT']
		results['OUTPUT'] = joined

		feedback.setCurrentStep(4)
		if feedback.isCanceled():
			return {}
		return results


	def name(self):
		return 'extractandsnapoutlets'

	def displayName(self):
		return self.tr('Extraction And Snap Outlets')


	def shortHelpString(self):
		return self.tr(
			"Extrait et met ensemble les embouchures des segments.\n" \
			"Paramètres\n" \
			"----------\n" \
			"MNT LiDAR (10 m) : Matriciel\n" \
			"-> Modèle numérique de terrain par levés aériennes LiDAR de résolution de 1 m rééchantilloné à 10 m pour le bassin versant donné. Source des données : MINISTÈRE DES RESSOURCES NATURELLES ET DES FORÊTS. Lidar - Modèles numériques (terrain, canopée, pente, courbe de niveau), [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie (Snapped_outlets) : Vectoriel (points)\n" \
			"-> Couche vectorielle de données ponctuelles de l'embouchure de chaque UEA"
		)

	def group(self):
		return self.tr('IQM utils')

	def groupId(self):
		return 'iqmutils'

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return ExtractAndSnapOutlets()
