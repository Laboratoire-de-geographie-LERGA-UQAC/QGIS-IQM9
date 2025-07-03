<!-- omit in toc -->
# Contributing to QGIS-IQM9
[![fr-CA](https://img.shields.io/badge/lang-fr--CA-blue.svg)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/CONTRIBUTING.md)
[![en](https://img.shields.io/badge/lang-en-red.svg)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/CONTRIBUTING.en.md)

First off, thanks for taking the time to contribute!

All types of contributions are encouraged and valued. See the [Table of Contents](#table-of-contents) for different ways to help and details about how this project handles them. Please make sure to read the relevant section before making your contribution. It will make it a lot easier for us maintainers and smooth out the experience for all involved. We look forward to your contributions.

> And if you like the project, but just don't have time to contribute, that's fine. There are other easy ways to support the project and show your appreciation, which we would also be very happy about:
> - Star the project
> - Tweet about it
> - Refer this project in your project's readme
> - Mention the project at local meetups and tell your friends/colleagues


<!-- omit in toc -->
## Table of Contents

- [I Have a Question](#i-have-a-question)
  - [I Want To Contribute](#i-want-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Improving The Documentation](#improving-the-documentation)
- [Styleguides](#styleguides)
  - [Commit Messages](#commit-messages)
  - [Versioning](#versioning)
  - [Code structure](#code-structure)
  - [Language accessibility](#language-accessibility)
- [Attribution](#attribution)

## I Have a Question

> If you want to ask a question, we assume that you have read the available [Documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.en.md).

Before you ask a question, it is best to search for existing [Issues](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) that might help you. In case you have found a suitable issue and still need clarification, you can write your question in this issue. It is also advisable to search the internet for answers first.

If you then still feel the need to ask a question and need clarification, we recommend the following:

- Open an [Issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/new).
- Provide as much context as you can about what you're running into.
- Provide project and platform versions (QGIS, WhiteboxTools, other plugins, etc.), depending on what seems relevant.

We will then take care of the issue as soon as possible.

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

## I Want To Contribute

> ### Legal Notice <!-- omit in toc -->
> When contributing to this project, you must agree that you have authored 100% of the content, that you have the necessary rights to the content and that the content you contribute may be provided under [the project licence](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/LICENSE).

### Reporting Bugs

<!-- omit in toc -->
#### Before Submitting a Bug Report

A good bug report shouldn't leave others needing to chase you up for more information. Therefore, we ask you to investigate carefully, collect information and describe the issue in detail in your report. Please complete the following steps in advance to help us fix any potential bug as fast as possible.

- Make sure that you are using the latest version.
- Determine if your bug is really a bug and not an error on your side e.g. using incompatible environment components/versions (Make sure that you have read the [documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.en.md). If you are looking for support, you might want to check [this section](#i-have-a-question)).
- To see if other users have experienced (and potentially already solved) the same issue you are having, check if there is not already a bug report existing for your bug or error in the [bug tracker](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues?q=label%3Abug).
- Also make sure to search the internet (including Stack Overflow, the different [QGIS issue reporting platforms](https://qgis.org/resources/support/bug-reporting/) and [QGIS GitHub Issue board for your current version](https://github.com/qgis/QGIS/issues)) to see if users outside of the GitHub or QGIS community have discussed the issue.
- Collect information about the bug:
- Stack trace (Traceback)
- OS, Platform, Version and QGIS version (Windows, Linux, macOS, x86, ARM)
- Version of the interpreter, compiler, SDK, runtime environment, package manager, depending on what seems relevant.
- Possibly your input and the output
- Can you reliably reproduce the issue? And can you also reproduce it with older versions?

<!-- omit in toc -->
#### How Do I Submit a Good Bug Report?

> You must never report security related issues, vulnerabilities or bugs including sensitive information to the issue tracker, or elsewhere in public. Instead sensitive bugs must be sent by email to <span style="color:red">**TBD**</span>.
<!-- You may add a PGP key to allow the messages to be sent encrypted as well. -->

We use GitHub issues to track bugs and errors. If you run into an issue with the project:

- Open an [Issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/new). (Since we can't be sure at this point whether it is a bug or not, we ask you not to talk about a bug yet and not to label the issue.)
- Explain the behavior you would expect and the actual behavior.
- Please provide as much context as possible and describe the *reproduction steps* that someone else can follow to recreate the issue on their own. This usually includes your code. For good bug reports you should isolate the problem and create a reduced test case.
- Provide the information you collected in the previous section.

Once it's filed:

- The project team will label the issue accordingly.
- A team member will try to reproduce the issue with your provided steps. If there are no reproduction steps or no obvious way to reproduce the issue, the team will ask you for those steps and mark the issue as `needs-repro`. Bugs with the `needs-repro` tag will not be addressed until they are reproduced.
- If the team is able to reproduce the issue, it will be marked `needs-fix`, as well as possibly other tags (such as `critical`), and the issue will be left to be [implemented by someone](#your-first-code-contribution).

<!-- You might want to create an issue template for bugs and errors that can be used as a guide and that defines the structure of the information to be included. If you do so, reference it here in the description. -->


### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for QGIS-IQM9, **including completely new features and minor improvements to existing functionality**. Following these guidelines will help maintainers and the community to understand your suggestion and find related suggestions.

<!-- omit in toc -->
#### Before Submitting an Enhancement

- Make sure that you are using the latest version.
- Read the [documentation](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.en.md) carefully and find out if the functionality is already covered, maybe by an individual configuration.
- Perform a [search](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.
- Find out whether your idea fits with the scope and aims of the project. It's up to you to make a strong case to convince the project's developers of the merits of this feature. Keep in mind that we want features that will be useful to the majority of our users and not just a small subset. If you're just targeting a minority of users, consider writing an add-on/plugin library.

<!-- omit in toc -->
#### How Do I Submit a Good Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues).

- Use a **clear and descriptive title** for the issue to identify the suggestion.
- Provide a **step-by-step description of the suggested enhancement** in as many details as possible.
- **Describe the current behavior** and **explain which behavior you expected to see instead** and why. At this point you can also tell which alternatives do not work for you.
- You may want to **include screenshots or screen recordings** which help you demonstrate the steps or point out the part which the suggestion is related to. You can use [LICEcap](https://www.cockos.com/licecap/) to record GIFs on macOS and Windows, and the built-in [screen recorder in GNOME](https://help.gnome.org/users/gnome-help/stable/screen-shot-record.html.en) or [SimpleScreenRecorder](https://github.com/MaartenBaert/ssr) on Linux. <!-- this should only be included if the project has a GUI -->
- **Explain why this enhancement would be useful** to most QGIS-IQM9 users. You may also want to point out the other projects that solved it better and which could serve as inspiration.

<!-- You might want to create an issue template for enhancement suggestions that can be used as a guide and that defines the structure of the information to be included. If you do so, reference it here in the description. -->

### Your First Code Contribution
<!-- TODO
include Setup of env, IDE and typical getting started instructions?-->
> Please refer to the [README](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/blob/main/README.en.md) setup instructions to install the scripts in QGIS.

Make sure you have the latest version of [git](https://git-scm.com/downloads) and an IDE with good git integration (i.e. [Visual Studio Code](https://code.visualstudio.com/)).
The installation of various Visual Studio extensions is recommended, but not mandatory. The following should help you in your contribution efforts :
- [The Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python);
- [The Git Graph Visual Code Extension](https://marketplace.visualstudio.com/items?itemName=mhutchie.git-graph), by mhutchie.

We also highly recommend installing the QGIS plugin [*Plugin Reloader*](https://plugins.qgis.org/plugins/plugin_reloader/). It will allow you to reload the scripts unpon modification instead of closing and reopening QGIS each time. To do so, select the `processing` option in the scroll down menu of the plugin to reload the IQM9 scripts. It can be installed in the QGIS built in [plugin manager](https://docs.qgis.org/3.40/en/docs/training_manual/qgis_plugins/fetching_plugins.html).

Before submitting your code make sure to test your changes by running each scripts affected (don't forget to run the scripts that call others like the `calcul_A123.py` and `Calcul_IQM.py`) to ensure that it does not cause QGIS to crash or deteriorates their performance.

### Improving The Documentation
<!-- TODO
Updating, improving and correcting the documentation-->
>Please refer to the [styleguides section](#styleguides) (especially the [code structure section](#code-structure) and the [language accessibililty section](#language-accessibility)) before submitting documentation improvements.

Documentation improvements can be submitted in the same fashion as other [enhancement suggestions](#how-do-i-submit-a-good-enhancement-suggestion).


## Styleguides
> As this project strives to apply the [FAIR (Findable, Accessible, Interoperable and Reusable) principles](https://www.nature.com/articles/s41597-022-01710-x) we chose to follow the guidelines established by the [FAIR-BioRS guidelines](https://fair-biors.org/docs/guidelines). **Please read these guidelines carefully to ensure that your contribution complies with them**. Details regarding specific aspects of these guidelines are further explained below.
### Commit Messages
Commit messages should be informative and concise. The git message format proposed here is inspired by the [Conventional Commits specification](https://www.conventionalcommits.org/en/v1.0.0/) and should consist of a header, a body and a footer :
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```
In the Command Line Interface (CLI) the git commit command would be written :
```
git commit -m "HEADER" -m "BODY" -m "Footer"
```
>The following information is taken from the [Angular Convention](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines), [Greg Foster's *Git commit message best practices*](https://graphite.dev/guides/git-commit-message-best-practices) and the [d-centralize handbook](https://handbook.d-centralize.nl/conventions/commitmessages/). Please refer to them for further explanations.
<!-- omit in toc -->
#### Header
The header consists of a commit type, a scope (optional) and a **brief** description of the change (preferably less than 50 characters).

<!-- omit in toc -->
#### Types of commit
The type defines the type of change of the commit. Accepted types (as defined by the [Angular Convention](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines)) are :
- Feat : Introduces a new feature;
- Fix : Patches a bug;
- Docs : Documentation only changes (rendered documentation or inline comments);
- Style : Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc);
- Refractor : A code change that neither fixes a bug nor adds a feature;
- Perf : Improves performance;
- Test : Adds missing tests or corrects existing tests;
- Chore : Changes to the build process or auxiliary tools and libraries such as documentation generation (e.g. updates to a `.gitignore` or `setup.py`)

<!-- omit in toc -->
#### Scope (optional)
The scope add information on where the change as taken place. For changes made to a Python class or function the scope should be the name of the class or funtion. A change to a method of a class is considered a change to a class.

**If the changes are not limited to one location** the scope should be left out.

<!-- omit in toc -->
#### Description
The description summarizes the changes of the commit. It should be imperative, begin with a word of action (e.g. fix, handle, modify, etc.), the first letter should not be capitalized and no dot should appear at the end

**Note :** in case of a fix the description of the header should contain the issue name related to it (e.g. [`Fix : Journal Verbosity`](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues/6)).

<!-- omit in toc -->
#### Body (optional)
Even though the body is optional, we strongly encourage you to fill it to help reviewers assess the content of the commit. The body should state the modifications included in the commit. It describes what the problem is and why the change is made. It should be succint and informative about the rationale and implications of the change.

<!-- omit in toc -->
#### Footer (optional)
The footer relates the commit to an issue or pull request number and is detectable by GitHub to automatically update an issue. If the commit relates to an issue without closing it, it should begin with the word `Refs` :
```
Refs: #<number>
```
If the commit closes an issue the word `Closes` should be used instead of `Refs`.
Breaking changes that introduce a breaking API change should be identified as `BREAKING CHANGE` followed by a description of the said change :
```
BREAKING CHANGE : env vars now take precedence over config files.
```

### Versioning
Versioning incrementation will be handled by the project's team following the [Semantic Versioning guidelines](https://semver.org/) and incremented with pull request approval. The SemVer format is the following :
```
MAJOR.MINOR.PATCH
```
and incremented as follows :
- MAJOR version is incremented if backward compatible changes are introduced to the API (correlates with the `BREAKING CHANGE` status of the [commit footer](#footer-optional));
- MINOR version is incremented if a new feature or functionality is introduced in a backward compatible manner (correlates with the `Feat` [commit type](#types-of-commit));
- PATCH version is incremented when backward compatible bug fixes are made (correlates with the `Fix` [commit type](#types-of-commit))

### Code structure
Inline with the [FAIR-BioRS guidelines regargind coding standards](https://fair-biors.org/docs/guidelines#2-follow-coding-standards-and-best-practices-during-development)
your contributed code should :
>- *Have code-level documentation (e.g., in code comments, description in the file headers) when deemed necessary for code reuse.*
> - *Follow language-specific standards and best practices* [...]

We thus ask that contributors follow as much as possible the [PEP 8 Style Guide for Python Code](https://peps.python.org/pep-0008/) as well as the [PEP 20 Zen of Python](https://peps.python.org/pep-0020/) when writing code for this project.

<!-- omit in toc -->
#### Comments
Comments should follow the comments section of the [PEP 8 Style Guide for Python Code](https://peps.python.org/pep-0008/#comments).

Each separate process should include a short descriptive **block comment** at the begin of said process
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
**Inline comments** should be used to clarify loops or steps that are not explicit.

<!-- omit in toc -->
#### Docstring format
Docstring should follow, as much as possible, the [PEP 257 Docstring Conventions](https://peps.python.org/pep-0257/).

When adding a new class or function to the code please follow the following docstring format :
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
If the function or class returns no value (like only doing prints or outputting graphs) state the effect of the body of the code (i.e. `prints the number of X in Y` or `outputs an histogram of X's distribution`).


### Language accessibility
In order to make the project available to a wider audience the readable files are made available in different languages. Inspired by the [multilanguage-readme-pattern repo](https://github.com/jonatasemidio/multilanguage-readme-pattern/tree/master), such files (like README and CONTRIBUTING) are named following the [W3C language tags](https://www.w3.org/International/articles/language-tags/).
```
README.en.md
README.fr-CA.md
```
The files are also adorned of [Shields IO](https://shields.io/) language badges (e.g. ![en](https://img.shields.io/badge/lang-en-red.svg)) with links to the corresponding alternative language document placed at the top.

If you want to contribute by including a version of the documents in your own language we would be thrilled to include it to the project ! Show your interest by [submitting an issue](https://github.com/Laboratoire-de-geographie-LERGA-UQAC/QGIS-IQM9/issues) for this purpose in the repo.

<!-- omit in toc -->
#### Translatable strings
For all strings that are outputted in the QGIS GUI make use of translatable strings that can be exploited by QGIS. Doing so will allow the scripts output to be translatate and made available more widely. To do so make sure to import the `QCoreApplication` class and define a translate method in your processing class (exemple code taken from [QGIS User Guide](https://docs.qgis.org/3.40/en/docs/user_manual/processing/scripts.html)) :
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
- This project builds on the foundations and expands upon the original repo ([QGIS-IQM](https://github.com/Mehourka/QGIS-IQM)) of [Karim Mehour](https://github.com/Mehourka). We thank them for their initial contribution. The project is now maintened by the [_Laboratoire d’expertise et de recherche en géographie appliquée_ (LERGA)](https://github.com/Laboratoire-de-geographie-LERGA-UQAC) at the _Université du Québec à Chicoutimi_ (UQAC).
- This guide is based on the [contributing.md](https://contributing.md/generator)!