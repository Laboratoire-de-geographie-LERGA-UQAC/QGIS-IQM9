
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


import processing
from qgis.PyQt.QtCore import QMetaType, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsProcessingUtils,
	QgsProcessingAlgorithm,
	QgsProcessingParameterRasterLayer,
	QgsProcessingParameterBoolean,
	QgsProcessingParameterString,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink
)


class IndiceA2(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'
	DEFAULT_SEG_ID_FIELD = 'Id_UEA'

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterBoolean('SUB_WATERSHED_GIVEN', self.tr('Couche de sous-BV fournie ?'), defaultValue=False))
		self.addParameter(QgsProcessingParameterVectorLayer('watersheds', self.tr('Sous bassins versants et util. terr (sortant de Extract. sous-BV)'), types=[QgsProcessing.TypeVectorPolygon], defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterRasterLayer('D8', self.tr('WBT D8 Pointer (sortant de Calcule pointeur D8)'), defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterVectorLayer('dams', self.tr('Barrages (CEHQ)'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterRasterLayer('landuse', self.tr('Utilisation du territoire (MELCCFP)'), defaultValue=None, optional=True))
		self.addParameter(QgsProcessingParameterVectorLayer('stream_network', self.tr('Réseau hydrographique (CRHQ)'), types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterString('segment_id_field', self.tr('Nom du champ identifiant segment'), defaultValue=self.DEFAULT_SEG_ID_FIELD))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr('Couche de sortie'), defaultValue=None))


	def checkParameterValues(self, parameters, context):
		# Checks if all the parameters are given properly
		use_sub_watershed = self.parameterAsBool(parameters, 'SUB_WATERSHED_GIVEN', context)
		rivnet_layer = self.parameterAsVectorLayer(parameters, 'stream_network', context)
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)

		if seg_id_field not in [f.name() for f in rivnet_layer.fields()]:
			return False, self.tr(f"Le champ '{seg_id_field}' est absent de la couche du réseau hydro. ! Veuillez fournir un champ identifiant du segment présent comme attribut de la couche.")
		if use_sub_watershed:
			if parameters['watersheds'] is None:
				return False, self.tr('Vous avez choisi d’utiliser la couche de sous-BV, mais elle n’est pas fournie.')
		else:
			if parameters['D8'] is None or parameters['dams'] is None or parameters['landuse'] is None :
				return False, self.tr('Vous devez fournir les couches nécessaires (WBT D8 Pointer, Barrages et Util. du terr.) pour créer la couche de sous-BV.')
		return True, ''


	def processAlgorithm(self, parameters, context, model_feedback):
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
		outputs = {}

		# Making layers and parameters needed for processing
		seg_id_field = self.parameterAsString(parameters, 'segment_id_field', context)

		# Define stream netwprk as source for data output
		source = self.parameterAsVectorLayer(parameters, 'stream_network', context)

		# Define Sink fields
		sink_fields = source.fields()
		sink_fields.append(QgsField("dam_area_sum_m2", QMetaType.Double))
		sink_fields.append(QgsField("Indice A2", QMetaType.Int))

		# Define sink
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		if feedback.isCanceled():
			return {}

		watersheds = self.parameterAsVectorLayer(parameters, 'watersheds', context)
		if watersheds is None :
			# If the sub watershed layer is not given
			feedback.setProgressText(self.tr(f"Création de la couche de sous-BV"))
			try :
				# Create the sub watersheds
				alg_params = {
					'stream_network' : parameters['stream_network'],
					'D8' : parameters['D8'],
					'dams' : parameters['dams'],
					'landuse' : parameters['landuse'],
					'OUTPUT' : QgsProcessing.TEMPORARY_OUTPUT
				}
				watersheds_data = processing.run('script:extract_subwatershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
				watersheds = QgsProcessingUtils.mapLayerFromString(watersheds_data, context)
				if not watersheds or not watersheds.isValid() :
					# Verify if the created layer is valid
					feedback.reportError(self.tr("La couche watersheds est invalide."))
					return {}
			except Exception as e :
				feedback.reportError(self.tr(f"Erreur dans la création de la couche de sous-BV : {str(e)}"))
		feedback.setCurrentStep(1)
		# Compute A2 index
		feedback.setProgressText(self.tr(f"Calcul de l'indice A2"))
		try :
			outputs['watersheds'] = computeA2(watersheds, context, feedback=None)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans le calcul de l'indice A2 : {str(e)}"))
		feedback.setCurrentStep(2)
		if feedback.isCanceled():
			return {}

		# Getting results ready to output
		feedback.setProgressText(self.tr(f"Sortie des résultats."))
		try :
			# Convert watershed features to vector layers
			watersheds_lyr = QgsVectorLayer(outputs['watersheds'], 'ws', 'ogr')
			# If present, a ‘seg_id_field’ key is preferred; otherwise, ‘DN’ (temporary) is used.
			use_key = seg_id_field if (watersheds_lyr.fields().indexFromName(seg_id_field) != -1) else 'DN'
			# Map feature ID and index values for each watershed layer
			a2_map = {f[use_key]: f['Indice A2'] for f in watersheds_lyr.getFeatures()}
			dam_area_map = {f[use_key]: f["dam_area_sum"] for f in watersheds.getFeatures()}
			# Write final indices to sink using map
			for feat in source.getFeatures():
				seg = feat[seg_id_field]
				# Get existing attributes
				vals = feat.attributes()
				# Get wanted values (None if absent)
				a2_val   = a2_map.get(seg, None)
				dam_area_val = dam_area_map.get(seg, None)
				# Add the new attributes
				vals += [dam_area_val, a2_val]
				feat.setAttributes(vals)
				sink.addFeature(feat, QgsFeatureSink.FastInsert)
		except Exception as e :
			feedback.reportError(self.tr(f"Erreur dans la sortie des résultats : {str(e)}"))
		feedback.setCurrentStep(3)
		if feedback.isCanceled():
			return {}

		# Ending message
		feedback.setProgressText(self.tr('\tProcessus terminé !'))

		return {self.OUTPUT: dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceA2()

	def name(self):
		return 'indicea2'

	def displayName(self):
		return self.tr('Indice A2')

	def group(self):
		return self.tr('IQM (indice solo)')

	def groupId(self):
		return 'iqm'

	def shortHelpString(self):
		return self.tr(
			"Calcule de l'indice A2 afin d'évaluer l’impact des barrages présents à l’amont du segment sur les processus hydrogéomorphologiques en aval en fonction de l’aire d’alimentation affectée.\n Les barrages localisés sur l’ensemble du réseau hydrographique à l’amont du segment analysé sont considérés dans le calcul de l’aire de drainage.\n" \
			"Paramètres\n" \
			"----------\n" \
			"Couche de sous-BV fournis: Booléen (optionnel; valeur par défaut : Faux)\n" \
			"-> Détermine si la couche de sous-BV (préalablement produite par Extract sous-BV et landuse [A123]) est fournie par l'utilisateur.\n" \
			"Sous bassins versants et util. terr: Vectoriel (polygone) (optionnel, mais obligatoire si couche de sous-BV fournis est coché)\n" \
			"-> Couche de polygones contenant les sous bassin versant du BV donné ainsi que l'information d'utilisation du territoire. Produit par le script IQM utils Extract sous-BV et landuse (A123). Source des données : À produire soi-même préalablement.\n" \
			"WBT D8 Pointer: Matriciel (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Grille de pointeurs de flux pour le bassin versant donné (obtenu par l'outil D8Pointer de WhiteboxTools). Source des données : Sortie du script Calcule pointeur D8.\n" \
			"Barrages : Vectoriel (point) (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Répertorie les barrages d'un mètre et plus pour le bassin versant donné. Source des données : Centre d'expertise hydrique du Québec (CEHQ). Répertoire des barrages, [Jeu de données], dans Navigateur cartographique du Partenariat Données Québec, IGO2.\n" \
			"Utilisation du territoire : Matriciel (optionnel, mais obligatoire si couche de sous-BV fournis n'est pas coché)\n" \
			"-> Classes d'utilisation du territoire pour le bassin versant donné sous forme matriciel (résolution 10 m) qui sera reclassé pour les classes forestière, agricole et anthropique, selon le guide d'utilisation du jeu de données. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). Utilisation du territoire, [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. Cadre de référence hydrologique du Québec (CRHQ), [Jeu de données], dans Données Québec.\n" \
			"Champ ID segment : Chaine de caractère ('Id_UEA' par défaut)\n" \
			"-> Nom du champ (attribut) identifiant le segment de rivière. NOTE : Doit se retrouver à la fois dans la table attributaire de la couche de réseau hydro et de la couche de PtRef. Source des données : Couche réseau hydrographique.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique du bassin versant avec le score de l'indice A2 calculé pour chaque UEA."
		)


def computeA2(watersheds, context, feedback) :
	a2_formula = """
		CASE
			WHEN "watershed_area" = 0 THEN NULL
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.05 THEN 0
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.33 THEN 2
			WHEN (coalesce("dam_area_sum", 0)/"watershed_area") < 0.66 THEN 3
			ELSE 4
		END
		"""
	alg_params = {
		'INPUT': watersheds,
		'FIELD_NAME': 'Indice A2',
		'FIELD_TYPE': 2,  # 2 = Integer
		'FIELD_LENGTH': 3,
		'FIELD_PRECISION': 0,
		'NEW_FIELD': True,
		'FORMULA': a2_formula,
		'OUTPUT': QgsProcessingUtils.generateTempFilename("watersheds.shp")
	}
	return processing.run('native:fieldcalculator', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']