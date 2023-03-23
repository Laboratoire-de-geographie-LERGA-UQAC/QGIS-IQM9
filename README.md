# Guide d'utilisation outil IQM:

# Installation de l'outil QGIS et de ses dépendances:
## QGIS

QGIS est un logiciel libre et open-source de système d'information géographique (SIG) qui est utilisé pour visualiser, éditer et analyser des données géospatiales.

Avant de pouvoir utiliser l'outil, vous devez installer QGIS et ses dépendances. Voici les étapes à suivre :
- Téléchargez la dernière version de QGIS depuis le site officiel: https://www.qgis.org/fr/site/forusers/download.html
- Suivez les instructions d'installation pour votre système d'exploitation (Windows, macOS, Linux)
- Lors de l'installation, assurez-vous que les bibliothèques GDAL, GEOS, PROJ et SQLite sont installées avec QGIS

## WhiteBoxTools
WhiteboxTools est une bibliothèque de logiciels de géotraitement à code source ouvert, qui est utilisée pour effectuer une variété de tâches d'analyse spatiale et de traitement de données géospatiales. Cette bibliothèque offre une vaste gamme d'algorithmes pour le traitement des données matricielles et vectorielles.
L'outil nécessite une version à jour de Whiteboxtools. Pour cela, il est nécessaire d'intégrer cette boite à outil à QGIS en suivant les instructions d'installation sur le site officiel:
https://www.whiteboxgeo.com/manual/wbt_book/qgis_plugin.html

# Intégration de l’outil à QGIS

Pour intégrer l'algorithme Processing de l'outil à QGIS, vous devez télécharger les scripts fournis et ajouter le répertoire des scripts dans la section Processing des options de QGIS.

Les scripts sont disponibles sur le site officiel de l'outil QGIS avec pyqgis. Une fois que vous avez téléchargé les scripts, vous pouvez les ajouter à QGIS en suivant les instructions ci-dessous :
- Ouvrez QGIS et cliquez sur l'option "Préférences" dans la barre de menus.
- Sélectionnez "Options" dans le menu déroulant.
    
![image1](https://user-images.githubusercontent.com/84189822/227153987-c880d5d2-b5e8-4606-8ed1-2b7a528285c4.png)

- Dans la boîte de dialogue Options de traitement, sélectionnez l'onglet "Scripts".
- Cliquez sur le bouton Ajouter à droite du champ pour ajouter le répertoire contenant les scripts et les modèles téléchargés.

![image3](https://user-images.githubusercontent.com/84189822/227154199-0191a4ed-2248-4cc6-93f4-ee73594d5919.png)

- Cliquez sur "OK" pour enregistrer les modifications.

Une fois ajouté dans le répertoire des scripts, l'algorithme Processing de l'outil sera disponible dans QGIS.

![IQM_Toolbox](https://user-images.githubusercontent.com/84189822/227258271-8ce029ae-f6b2-431b-b85d-abcc6cfecd33.PNG)

# Préparation des données
Avant d'utiliser l'outil, il est important de s'assurer que toutes les couches de données sont projetées de la même manière. Il est recommandé d'utiliser le système de référence de coordonnées (CRS) Lambert conique conforme du Québec pour assurer la cohérence des données spatiales.
Il est également conseillé de minimiser l'emprise des données pour le bassin versant étudié, même si ce n'est pas obligatoire. Cela permettra d'alléger les calculs et d'améliorer les performances de l'outil. Vous pouvez réduire l'emprise en sélectionnant uniquement les données pertinentes pour votre étude.
Assurez-vous que toutes les données nécessaires à l'analyse sont présentes et correctement formatées. Les formats de fichiers testé par l'outil incluent les formats vectoriels tels que les fichiers Shapefile (.shp), les fichiers geopackge (.gpkg), et les formats raster tels que GeoTIFF (.tif)        .

## Données matricielles:
### DEM
Le modèle numérique de terrain (MNT) utilisé dans l'outil a été obtenu à partir de levés aériens LiDAR avec une résolution de 1 mètre et a été téléchargé à partir de la plateforme Forêt ouverte. Les données originales sont diffusées sous forme de feuillet 1/20 000 et sont en système de coordonnées NAD83 SCRS MTM.
Une mosaïque a été créée à partir des tuiles pour couvrir la zone d'intérêt, puis le MNT a été projeté dans le système de coordonnées du bassin versant étudié. Il est recommandé de rééchantillonner le MNT à une résolution spatiale de 10 mètres en utilisant la méthode du minimum local, qui est mieux adaptée pour les modélisations hydrologiques.
Le rééchantillonnage permettra de réduire la taille des données et d'accélérer les calculs tout en conservant une résolution suffisante pour les analyses hydrologiques. Assurez-vous que le MNT est correctement formaté et qu'il est dans un format compatible avec l'outil. Les formats de fichiers pris en charge incluent les formats raster tels que GeoTIFF.

Source : https://www.donneesquebec.ca/recherche/dataset/produits-derives-de-base-du-lidar


### Utilisation du territoire
Pour assurer une utilisation adéquate de la couche "Utilisation du territoire", il est important de s'assurer que les données proviennent du MELCCFP, car les tables de reclassification de l'outil sont basées sur ces données. De plus, pour optimiser les calculs, il est recommandé de procéder à la reprojection et au découpage de cette couche.

source : https://www.donneesquebec.ca/recherche/fr/dataset/utilisation-du-territoire

## Données vectorielles:
### CRHQ
Le réseau hydrographique utilisé provient du cadre de référence hydrologique (CRHQ). Dans la géodatabase du CRHQ, contient des données vectorielles linéaires des cours d'eau, qui sont divisés en unités écologiques aquatiques (UEA) et des points de référence contenant des variables descriptives.
L’outil nécessite la couche vectorielle des UEA “UEA_L_N2”, celle-ci doit être recadrée à l'emprise de la zone d'étude. Et aussi la couche vectorielle “PtRef” et la table attributaire “PtRef_mod_lotique” correspondantes, afin de lier les informations des points de références aux UEA.

source : https://www.donneesquebec.ca/recherche/dataset/crhq

### Barrage
Le jeu de données vectorielles ponctuelles des barrages préconisé est celui fourni par le Centre d'expertise hydrique du Québec (CEHQ). Ce jeu de données contient des informations sur les barrages au Québec, y compris leur emplacement et leur type. Les données ont été obtenues à partir du portail de données d’infrastructures ouvertes du gouvernement du Québec (IGO).

source : https://www.cehq.gouv.qc.ca/barrages/default.asp
### Structures

Les données vectorielles ponctuelles des structures de transport du Québec proviennent du Ministère des Transports et de la Mobilité durable.

Source : https://www.donneesquebec.ca/recherche/dataset/structure


### Réseau Routier
Le réseau routier utilisé provient des données vectorielles linéaires représentant les rues, les avenues, les autoroutes et les chemins de fer à partir de la plateforme OpenStreetMap.
Le téléchargement est possible depuis le [site officiel](https://welcome.openstreetmap.org/working-with-osm-data/downloading-and-using/) ou directement via [l'extension QGIS](https://plugins.qgis.org/plugins/QuickOSM/).

### Bande riveraine
Les données vectorielles surfaciques des peuplements forestiers on été utilisé pour représenter la bande riveraine, et proviennent du Ministère des Ressources naturelles et des Forêts (MRNF) via la plateforme Forêt ouverte. Ces données contiennent l’information vectorielle de la localisation, du périmètre et de la superficie des polygones écoforestiers.

Source:  https://www.donneesquebec.ca/recherche/fr/dataset/carte-ecoforestiere-avec-perturbations




# Utilisation de l’outil
## Calcule de l’IQM complet

Plusieurs sous module sont mise a disposition pour le calcule des indicateurs individuellement. Dans le catégorie “IQM - indices”

