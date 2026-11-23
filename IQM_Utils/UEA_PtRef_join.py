
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
*	any later version.															*
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
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink
)
import processing


class Uea_ptref_join(QgsProcessingAlgorithm):

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('ptref', self.tr('PtRef'), types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_mod_lotique', self.tr('PtRef_Mod_Lotique'), types=[QgsProcessing.TypeVector], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('riv_net', self.tr('Réseau hydrographique (CRHQ)'), defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink('Ptref_largeur', self.tr('Couche de sortie (PtRef largeur [CRHQ])'), optional=True, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, defaultValue='TEMPORARY_OUTPUT'))

	def processAlgorithm(self, parameters, context, model_feedback):
		# Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
		# overall progress through the model
		feedback = QgsProcessingMultiStepFeedback(2, model_feedback)
		results = {}
		outputs = {}

		# Extraire par expression
		alg_params = {
			'EXPRESSION': f"array_contains(\n\taggregate(\n\t\t '{parameters['riv_net']}' \n\t\t,\'array_agg\',\n\t\t\"Id_UEA\"\n\t),\n\t\"Id_UEA\"\n) AND Valide_bv",
			'INPUT': parameters['ptref'],
			'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
		}
		outputs['ExtraireParExpression'] = processing.run('native:extractbyexpression', alg_params, context=context, feedback=None, is_child_algorithm=True)

		feedback.setCurrentStep(1)
		if feedback.isCanceled():
			return {}

		# Join attributes by field value
		alg_params = {
			'DISCARD_NONMATCHING': True,
			'FIELD': 'Id_PtRef',
			'FIELDS_TO_COPY': ['Largeur_mod'],
			'FIELD_2': 'Id_PtRef',
			'INPUT': outputs['ExtraireParExpression']['OUTPUT'],
			'INPUT_2': parameters['ptref_mod_lotique'],
			'METHOD': 1,  # Prendre uniquement les attributs de la première entité correspondante (un à un)
			'PREFIX': '',
			'OUTPUT': parameters['Ptref_largeur']
		}
		outputs['JoinAttributesByFieldValue'] = processing.run('native:joinattributestable', alg_params, context=context, feedback=None, is_child_algorithm=True)
		results['Ptref_largeur'] = outputs['JoinAttributesByFieldValue']['OUTPUT']
		return results

	def name(self):
		return 'UEA_PtRef_join'

	def displayName(self):
		return 'UEA_PtRef_join'

	def group(self):
		return self.tr('IQM utils')

	def groupId(self):
		return 'iqmutils'

	def shortHelpString(self):
		return self.tr(
			"Lie les points de référence aux attributs de la table PtRef_mod_lotique des données du Cadre de référence hydrologique du Québec (CRHQ)\n" \
			"Paramètres\n" \
			"----------\n" \
			"PtRef : Vectoriel (points)\n" \
			"-> Ensemble des points de références du CRHQ pour le bassin versant donné. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). CRHQ, [Jeu de données], dans Données Québec..\n" \
			"PtRef_mod_lotique : table attibutaire\n" \
			"-> Ensemble des données sur les point de références dont l'attribut Largeur_mod qui correspond à la largeur modélisée des points de référence. Source des données : MINISTÈRE DE L’ENVIRONNEMENT, LUTTE CONTRE LES CHANGEMENTS CLIMATIQUES, FAUNE ET PARCS (MELCCFP). CRHQ, [Jeu de données], dans Données Québec.\n" \
			"Réseau hydrographique : Vectoriel (lignes)\n" \
			"-> Réseau hydrographique segmenté en unités écologiques aquatiques (UEA) pour le bassin versant donné. Source des données : MELCCFP. CRHQ, [Jeu de données], dans Données Québec.\n" \
			"Retourne\n" \
			"----------\n" \
			"Couche de sortie (PtRef_Largeur) : Vectoriel (points)\n" \
			"-> Couche vectorielle de données ponctuelles de largeur modélisée par point de référence du cours d'eau"
		)

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return Uea_ptref_join()
