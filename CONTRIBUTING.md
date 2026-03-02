<!-- omit in toc -->
# Contribuer à QGIS-IQM9
[![fr-CA](https://img.shields.io/badge/lang-fr--CA-blue.svg)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/CONTRIBUTING.md)
[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/CONTRIBUTING.en.md)

Tout d'abord, merci de prendre le temps de contribuer!

Tous les types de contributions sont encouragés et valorisés. Consultez la [table des matières](#table-des-matières) pour découvrir les différentes façons d'aider et les détails sur la manière dont ce projet les gère. Veuillez vous assurer de lire la section pertinente avant de faire votre contribution. Cela facilitera grandement la tâche des mainteneurs et améliorera l'expérience pour tous les participants. Nous avons hâte de recevoir vos contributions.

> Et si vous aimez le projet, mais que vous n'avez tout simplement pas le temps de contribuer, c'est très bien. Il existe d'autres façons simples de soutenir le projet et de montrer votre appréciation, ce qui nous ferait également très plaisir :
> - Mettre une étoile au projet
> - En parler sur les réseaux sociaux
> - Mentionner ce projet dans le README de votre propre projet
> - Parler du projet lors de rencontres locales et en informer vos amis/collègues


<!-- omit in toc -->
## Table des matières

- [J'ai une question](#jai-une-question)
  - [Je veux contribuer](#je-veux-contribuer)
  - [Signaler des bogues](#signaler-des-bogues)
  - [Suggérer des améliorations](#suggérer-des-améliorations)
  - [Ma première contribution de code](#ma-première-contribution-de-code)
  - [Améliorer la documentation](#améliorer-la-documentation)
- [Guides de style](#guides-de-style)
  - [Messages de commit](#messages-de-commit)
  - [Versionnage](#versionnage)
  - [Structure du code](#structure-du-code)
  - [Accessibilité linguistique](#accessibilité-linguistique)
- [Attribution](#attribution)

## J'ai une question

> Si vous souhaitez poser une question, nous supposons que vous avez lu la [documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.md) disponible.

Avant de poser une question, il est préférable de rechercher parmi les [Issues](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) existantes qui pourraient vous aider. Si vous trouvez une issue pertinente, mais avez encore besoin de clarification, vous pouvez poser votre question dans cette issue. Il est également conseillé de chercher des réponses sur Internet en premier lieu.

Si vous ressentez toujours le besoin de poser une question et d'obtenir des clarifications, nous recommandons ce qui suit :

- Ouvrez une [Issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/new).
- Fournissez autant de contexte que possible sur ce que vous rencontrez.
- Indiquez les versions du projet et de la plateforme (QGIS, WhiteboxTools, autres plugins, etc.), selon ce qui semble pertinent.

Nous nous occuperons alors de l'issue dès que possible.

<!--
You might want to create a separate issue tag for questions and include it in this description. People should then tag their issues accordingly.

Depending on how large the project is, you may want to outsource the questioning, e.g. to Stack Overflow or Gitter. You may add additional contact and information possibilities:
- IRC
- Slack
- Gitter
- Stack Overflow tag
- Blog
- FAQ
- Roadmap
- E-Mail List
- Forum
-->

## Je veux contribuer

> ### Avis légal <!-- omit in toc -->
> En contribuant à ce projet, vous devez accepter que vous êtes l'auteur à 100 % du contenu, que vous disposez des droits nécessaires sur celui-ci et que le contenu que vous contribuez puisse être fourni sous [la licence du projet](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/LICENSE).

### Signaler des bogues

<!-- omit in toc -->
#### Avant de soumettre un rapport de bogue

Un bon rapport de bogue ne devrait pas obliger les autres à vous relancer pour obtenir plus d'informations. C'est pourquoi nous vous demandons d'enquêter soigneusement, de collecter des informations et de décrire le problème en détail dans votre rapport. Veuillez compléter les étapes suivantes au préalable pour nous aider à corriger tout bogue potentiel le plus rapidement possible.

- Assurez-vous d'utiliser la dernière version.
- Déterminez si votre bogue est vraiment un bogue et non une erreur de votre côté, par exemple en utilisant des composants/versions d'environnement incompatibles (assurez-vous d'avoir lu la [documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.md). Si vous cherchez de l'aide, vous pouvez consulter [cette section](#jai-une-question)).
- Pour vérifier si d'autres utilisateurs ont rencontré (et potentiellement déjà résolu) le même problème, vérifiez s'il n'existe pas déjà un rapport de bogue pour votre bogue ou erreur dans le [gestionnaire de bogues](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues?q=label%3Abug).
- Assurez-vous également de faire une recherche sur Internet (y compris Stack Overflow, les différentes [plateformes de signalement de bogues QGIS](https://qgis.org/resources/support/bug-reporting/) et le [tableau des issues GitHub de QGIS pour votre version actuelle](https://github.com/qgis/QGIS/issues)) pour voir si des utilisateurs en dehors des communautés GitHub ou QGIS ont discuté du problème.
- Collectez des informations sur le bogue :
  - Stack trace (Traceback)
  - Système d'exploitation, plateforme, version et version de QGIS (Windows, Linux, macOS, x86, ARM)
  - Version de l'interpréteur, compilateur, SDK, environnement d'exécution, gestionnaire de paquets, selon ce qui semble pertinent
  - Éventuellement, vos données d'entrée et de sortie
  - Pouvez-vous reproduire le problème de manière fiable ? Et pouvez-vous également le reproduire avec des versions plus anciennes ?

<!-- omit in toc -->
#### Comment soumettre un bon rapport de bogue ?

> Vous ne devez jamais signaler des problèmes de sécurité, des vulnérabilités ou des bogues contenant des informations sensibles dans le gestionnaire d’issues ou ailleurs en public. Les bogues sensibles doivent plutôt être envoyés par courriel à <span style="color:red">**TBD**</span>.
<!-- You may add a PGP key to allow the messages to be sent encrypted as well. -->

Nous utilisons les issues GitHub pour suivre les bogues et les erreurs. Si vous rencontrez un problème avec le projet :

- Ouvrez une [Issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/new). (Comme nous ne pouvons pas être certains à ce stade s'il s'agit d'un bogue ou non, nous vous demandons de ne pas encore parler d'un bogue et de ne pas étiqueter l'issue.)
- Expliquez le comportement attendu et le comportement réel.
- Veuillez fournir autant de contexte que possible et décrire les *étapes de reproduction* que quelqu'un d'autre peut suivre pour recréer le problème par lui-même. Cela inclut généralement votre code. Pour de bons rapports de bogues, vous devriez isoler le problème et créer un cas de test réduit.
- Fournissez les informations collectées dans la section précédente.
- Veuillez également fournir une copie de la sortie du journal QGIS du script qui rencontre une erreur sous format txt (dans le cas d'un problème dans l'exécution d'un script)

Une fois soumise :

- L'équipe du projet étiquettera l'issue en conséquence.
- Un membre de l'équipe essaiera de reproduire le problème avec les étapes que vous avez fournies. S'il n'y a pas d'étapes de reproduction ou aucun moyen évident de reproduire le problème, l'équipe vous demandera ces étapes et marquera l'issue comme `needs-repro`. Les bogues avec l'étiquette `needs-repro` ne seront pas traités tant qu'ils ne seront pas reproduits.
- Si l'équipe est en mesure de reproduire le problème, il sera marqué `needs-fix`, ainsi que potentiellement d'autres étiquettes (comme `critical`), et l'issue sera laissée pour être [implémentée par quelqu'un](#ma-première-contribution-de-code).

<!-- You might want to create an issue template for bugs and errors that can be used as a guide and that defines the structure of the information to be included. If you do so, reference it here in the description. -->


### Suggérer des améliorations

Cette section vous guide dans la soumission d'une suggestion d'amélioration pour QGIS-IQM9, **y compris des fonctionnalités entièrement nouvelles et des améliorations mineures aux fonctionnalités existantes**. Suivre ces directives aidera les mainteneurs et la communauté à comprendre votre suggestion et à trouver des suggestions connexes.

<!-- omit in toc -->
#### Avant de soumettre une amélioration

- Assurez-vous d'utiliser la dernière version.
- Lisez attentivement la [documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.md) et vérifiez si la fonctionnalité est déjà couverte, peut-être par une configuration individuelle.
- Effectuez une [recherche](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) pour voir si l'amélioration a déjà été suggérée. Si c'est le cas, ajoutez un commentaire à l'issue existante plutôt que d'en ouvrir une nouvelle.
- Déterminez si votre idée correspond à la portée et aux objectifs du projet. C'est à vous de présenter un argumentaire solide pour convaincre les développeurs du projet des mérites de cette fonctionnalité. Gardez à l'esprit que nous voulons des fonctionnalités utiles à la majorité de nos utilisateurs et non à un petit sous-ensemble. Si vous ciblez uniquement une minorité d'utilisateurs, envisagez d'écrire une bibliothèque d'extension/plugin.

<!-- omit in toc -->
#### Comment soumettre une bonne suggestion d'amélioration ?

Les suggestions d'amélioration sont suivies sous forme d'[issues GitHub](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues).

- Utilisez un **titre clair et descriptif** pour l'issue afin d'identifier la suggestion.
- Fournissez une **description étape par étape de l'amélioration suggérée** avec autant de détails que possible.
- **Décrivez le comportement actuel** et **expliquez quel comportement vous vous attendiez à voir à la place** et pourquoi. À ce stade, vous pouvez également indiquer quelles alternatives ne fonctionnent pas pour vous.
- Vous pouvez **inclure des captures d'écran ou des enregistrements d'écran** qui vous aident à démontrer les étapes ou à indiquer la partie à laquelle la suggestion est liée. Vous pouvez utiliser [LICEcap](https://www.cockos.com/licecap/) pour enregistrer des GIFs sur macOS et Windows, et l'[enregistreur d'écran intégré de GNOME](https://help.gnome.org/users/gnome-help/stable/screen-shot-record.html.en) ou [SimpleScreenRecorder](https://github.com/MaartenBaert/ssr) sur Linux. <!-- this should only be included if the project has a GUI -->
- **Expliquez pourquoi cette amélioration serait utile** à la plupart des utilisateurs de QGIS-IQM9. Vous pouvez également signaler d'autres projets qui l'ont mieux résolu et qui pourraient servir d'inspiration.

<!-- You might want to create an issue template for enhancement suggestions that can be used as a guide and that defines the structure of the information to be included. If you do so, reference it here in the description. -->

### Ma première contribution de code
<!-- TODO
include Setup of env, IDE and typical getting started instructions?-->
> Veuillez vous référer aux instructions d'installation du [README](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.md) pour installer les scripts dans QGIS.

Assurez-vous d'avoir la dernière version de [git](https://git-scm.com/downloads) et un EDI avec une bonne intégration git (p. ex. [Visual Studio Code](https://code.visualstudio.com/)).
L'installation de diverses extensions Visual Studio est recommandée, mais non obligatoire. Les suivantes devraient vous aider dans vos efforts de contribution :
- [L'extension Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python) ;
- [L'extension Git Graph pour Visual Code](https://marketplace.visualstudio.com/items?itemName=mhutchie.git-graph), par mhutchie.

Nous recommandons également fortement d'installer le plugin QGIS [*Plugin Reloader*](https://plugins.qgis.org/plugins/plugin_reloader/). Il vous permettra de recharger les scripts après modification au lieu de fermer et rouvrir QGIS à chaque fois. Pour ce faire, sélectionnez l'option `processing` dans le menu déroulant du plugin pour recharger les scripts IQM9. Il peut être installé via le [gestionnaire de plugins intégré à QGIS](https://docs.qgis.org/3.40/en/docs/training_manual/qgis_plugins/fetching_plugins.html).

Avant de soumettre votre code, assurez-vous de tester vos modifications en exécutant chaque script affecté (n'oubliez pas d'exécuter les scripts qui en appellent d'autres, comme `Calcul_IQM.py`) pour vous assurer que cela ne provoque pas de plantage de QGIS ni ne dégrade leurs performances.

### Améliorer la documentation
<!-- TODO
Updating, improving and correcting the documentation-->
> Veuillez vous référer à la [section des guides de style](#guides-de-style) (en particulier la [section sur la structure du code](#structure-du-code) et la [section sur l'accessibilité linguistique](#accessibilité-linguistique)) avant de soumettre des améliorations à la documentation.

Les améliorations à la documentation peuvent être soumises de la même manière que les autres [suggestions d'amélioration](#comment-soumettre-une-bonne-suggestion-damélioration-).


## Guides de style
> Comme ce projet s'efforce d'appliquer les [principes FAIR (Findable, Accessible, Interoperable and Reusable)](https://www.nature.com/articles/s41597-022-01710-x), nous avons choisi de suivre les lignes directrices établies par les [directives FAIR-BioRS](https://fair-biors.org/docs/guidelines). **Veuillez lire attentivement ces directives pour vous assurer que votre contribution y est conforme**. Des détails concernant des aspects spécifiques de ces directives sont expliqués plus en détail ci-dessous.

### Messages de commit
Les messages de commit doivent être informatifs et concis. Le format de message git proposé ici est inspiré de la [spécification Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) et doit être composé d'un en-tête, d'un corps et d'un pied de page :
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```
Dans l'interface en ligne de commande (CLI), la commande git commit s'écrirait :
```
git commit -m "HEADER" -m "BODY" -m "Footer"
```
> Les informations suivantes sont tirées de la [Convention Angular](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines), des [*Git commit message best practices* de Greg Foster](https://graphite.dev/guides/git-commit-message-best-practices) et du [manuel d-centralize](https://handbook.d-centralize.nl/conventions/commitmessages/). Veuillez vous y référer pour de plus amples explications.

<!-- omit in toc -->
#### En-tête
L'en-tête est composé d'un type de commit, d'une portée (optionnelle) et d'une description **brève** du changement (de préférence moins de 50 caractères).

<!-- omit in toc -->
#### Types de commit
Le type définit la nature du changement du commit. Les types acceptés (tels que définis par la [Convention Angular](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines)) sont :
- Feat : Introduit une nouvelle fonctionnalité ;
- Fix : Corrige un bogue ;
- Docs : Modifications de la documentation uniquement (documentation rendue ou commentaires en ligne) ;
- Style : Modifications qui n'affectent pas la signification du code (espaces, formatage, points-virgules manquants, etc.) ;
- Refractor : Un changement de code qui ne corrige pas un bogue et n'ajoute pas de fonctionnalité ;
- Perf : Améliore les performances ;
- Test : Ajoute des tests manquants ou corrige des tests existants ;
- Chore : Modifications apportées au processus de construction ou aux outils et bibliothèques auxiliaires, tels que la génération de documentation (p. ex. mises à jour d'un `.gitignore` ou `setup.py`)

<!-- omit in toc -->
#### Portée (optionnelle)
La portée ajoute des informations sur l'emplacement où le changement a eu lieu. Pour les modifications apportées à une classe ou une fonction Python, la portée doit être le nom de la classe ou de la fonction. Une modification d'une méthode d'une classe est considérée comme une modification de la classe.

**Si les modifications ne sont pas limitées à un seul emplacement**, la portée doit être omise.

<!-- omit in toc -->
#### Description
La description résume les modifications du commit. Elle doit être à l'impératif, commencer par un mot d'action (p. ex. fix, handle, modify, etc.), la première lettre ne doit pas être en majuscule et aucun point ne doit apparaître à la fin.

**Note :** en cas de correctif, la description de l'en-tête doit contenir le nom de l'issue associée (p. ex. [`Fix : Journal Verbosity`](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/6)).

<!-- omit in toc -->
#### Corps (optionnel)
Bien que le corps soit optionnel, nous vous encourageons fortement à le remplir pour aider les réviseurs à évaluer le contenu du commit. Le corps doit indiquer les modifications incluses dans le commit. Il décrit quel est le problème et pourquoi le changement est effectué. Il doit être succinct et informatif sur la justification et les implications du changement.

<!-- omit in toc -->
#### Pied de page (optionnel)
Le pied de page relie le commit à un numéro d'issue ou de pull request et est détectable par GitHub pour mettre à jour automatiquement une issue. Si le commit est lié à une issue sans la fermer, il doit commencer par le mot `Refs` :
```
Refs: #<number>
```
Si le commit ferme une issue, le mot `Closes` doit être utilisé à la place de `Refs`.
Les changements majeurs qui introduisent une modification incompatible de l'API doivent être identifiés par `BREAKING CHANGE` suivi d'une description dudit changement :
```
BREAKING CHANGE : env vars now take precedence over config files.
```

### Versionnage
L'incrémentation du versionnage sera gérée par l'équipe du projet selon les [directives de versionnage sémantique](https://semver.org/) et incrémentée lors de l'approbation des pull requests. Le format SemVer est le suivant :
```
MAJOR.MINOR.PATCH
```
et incrémenté comme suit :
- La version MAJOR est incrémentée si des changements non rétrocompatibles sont introduits dans l'API (corrélé avec le statut `BREAKING CHANGE` du [pied de page de commit](#pied-de-page-optionnel)) ;
- La version MINOR est incrémentée si une nouvelle fonctionnalité ou une nouvelle capacité est introduite de manière rétrocompatible (corrélé avec le type de commit `Feat` [type de commit](#types-de-commit)) ;
- La version PATCH est incrémentée lors de corrections de bogues rétrocompatibles (corrélé avec le type de commit `Fix` [type de commit](#types-de-commit))

### Structure du code
En accord avec les [directives FAIR-BioRS concernant les normes de codage](https://fair-biors.org/docs/guidelines#2-follow-coding-standards-and-best-practices-during-development), votre code contribué doit :
>- *Avoir une documentation au niveau du code (p. ex. commentaires dans le code, description dans les en-têtes de fichiers) lorsque cela est jugé nécessaire pour la réutilisation du code.*
> - *Suivre les normes et bonnes pratiques propres au langage* [...]

Nous demandons donc aux contributeurs de suivre autant que possible le [Guide de style PEP 8 pour le code Python](https://peps.python.org/pep-0008/) ainsi que le [PEP 20 Zen de Python](https://peps.python.org/pep-0020/) lors de la rédaction de code pour ce projet.

<!-- omit in toc -->
#### Commentaires
Les commentaires doivent suivre la section sur les commentaires du [Guide de style PEP 8 pour le code Python](https://peps.python.org/pep-0008/#comments).

Chaque processus distinct doit inclure un **commentaire de bloc** court et descriptif au début dudit processus :
```
# Extract By Attribute
alg_params = {
'FIELD': self.ID_FIELD,
'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
'OPERATOR': 0,  # =
'VALUE': str(fid),
'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
}
outputs['single_point']= processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
```
Les **commentaires en ligne** doivent être utilisés pour clarifier les boucles ou les étapes qui ne sont pas explicites.

<!-- omit in toc -->
#### Format des docstrings
Les docstrings doivent suivre, autant que possible, les [Conventions de docstring PEP 257](https://peps.python.org/pep-0257/).

Lors de l'ajout d'une nouvelle classe ou fonction au code, veuillez suivre le format de docstring suivant :
```
def NewFunction(a, b) :
    """
    <Short description; one liner>
    <Long description>
    Parameters
    ----------
    a : <parameter type> ([optional default value])
        <succinct parameter description>
    b : <parameter type> ([optional default value])
        <succinct parameter description>
    Returns
    ----------
    foo : <output type>
        <succinct output description>
    """
    <function's body>
    return foo
```
Si la fonction ou la classe ne retourne aucune valeur (comme effectuer uniquement des affichages ou générer des graphiques), indiquez l'effet du corps du code (p. ex. `prints the number of X in Y` ou `outputs an histogram of X's distribution`).


### Accessibilité linguistique
Afin de rendre le projet accessible à un public plus large, les fichiers lisibles sont rendus disponibles en différentes langues. Inspirés du [dépôt multilanguage-readme-pattern](https://github.com/jonatasemidio/multilanguage-readme-pattern/tree/master), ces fichiers (comme README et CONTRIBUTING) sont nommés selon les [balises de langue W3C](https://www.w3.org/International/articles/language-tags/) **pour les autres langues que le français** (qui est le langage par défaut du dépôt).
```
README.en.md
```
Le haut des fichiers de documentation est également orné de badges de langue [Shields IO](https://shields.io/) (p. ex. ![en](https://img.shields.io/badge/lang-en-red.svg)) qui identifient la langue du fichier avec des liens vers le document en langue alternative correspondant.

Si vous souhaitez contribuer en incluant une version des documents dans votre propre langue, nous serions ravis de l'inclure dans le projet ! Manifestez votre intérêt en [soumettant une issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) à cet effet dans le dépôt.

<!-- omit in toc -->
#### Chaînes de caractères traduisibles
Pour toutes les chaînes de caractères affichées dans l'interface graphique de QGIS, utilisez des chaînes traduisibles (***translatable strings***) pouvant être exploitées par QGIS. Cela permettra aux sorties des scripts d'être traduites et rendues disponibles plus largement. Pour ce faire, assurez-vous d'importer la classe `QCoreApplication` et de définir une méthode de traduction dans votre classe de traitement (exemple de code tiré du [Guide de l'utilisateur QGIS](https://docs.qgis.org/3.40/en/docs/user_manual/processing/scripts.html)) :
```
from qgis.PyQt.QtCore import QCoreApplication
[...]

class ExampleProcessingAlgorithm(QgsProcessingAlgorithm):

	def tr(self, string):
		"""
		Returns a translatable string with the self.tr() function.
		"""
		return QCoreApplication.translate('Processing', string)

	[...]

	def displayName(self):
		"""
		Returns the translated algorithm name.
		"""
		return self.tr('Buffer and export to raster (extend)')
```

<!-- omit in toc -->
## Attribution
- Ce projet s'appuie sur les bases et étend le dépôt original ([QGIS-IQM](https://github.com/Mehourka/QGIS-IQM)) de [Karim Mehour](https://github.com/Mehourka). Nous les remercions pour leur contribution initiale. Le projet est maintenant maintenu par le [Laboratoire d'expertise et de recherche en géographie appliquée (LERGA)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC) à l'Université du Québec à Chicoutimi (UQAC).
- Ce guide est basé sur [contributing.md](https://contributing.md/generator)!

[Retour vers le haut](#top)
