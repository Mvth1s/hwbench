"""Catalogue des textes du site du classement (français).

Aucun texte n'est écrit en dur dans les templates ni dans le JavaScript : les templates lisent
`FR` (variable `t`), le JavaScript lit le sous-ensemble `FR["js"]`, publié dans chaque page en
JSON. Les libellés de catégories et de benchs restent ceux de `hwbench.labels` (une seule table
pour le terminal, le rapport et le site). Une traduction anglaise ajoutera un dictionnaire de
même forme.

Les textes à paramètres utilisent `str.format` (`{n}`, `{date}`…) ; les valeurs venues d'un
export sont échappées par Jinja au moment du rendu, jamais insérées ici.
"""

from typing import Any

from hwbench.labels import CATEGORY_LABELS
from hwbench.results import Category

GITHUB = "https://github.com/Mvth1s/hwbench"
GITHUB_PRIVACY = (
    "https://docs.github.com/fr/site-policy/privacy-policies/github-general-privacy-statement"
)
CNIL = "https://www.cnil.fr/"
# Adresse vérifiée le 12/10/2026 sur la déclaration de confidentialité de GitHub
# (docs.github.com, github-general-privacy-statement, en vigueur au 27/04/2026).
HOST = (
    "GitHub, Inc. (service GitHub Pages), 88 Colin P. Kelly Jr. St., San Francisco, CA 94107, "
    "États-Unis."
)
# Contact privé pour l'exercice des droits (jamais une issue publique), fourni par l'éditeur.
# Tant que FR["contact_private"] vaut l'emplacement réservé, la génération du site de
# production échoue (__main__, testé).
CONTACT_PLACEHOLDER = "[adresse de contact à fournir]"
CONTACT_PRIVATE = "mag.d3v+hwbench@pm.me"

FR: dict[str, Any] = {
    "lang": "fr",
    "contact_private": CONTACT_PRIVATE,
    "site": {
        "name": "HWBENCH",
        "title_suffix": "hwbench",
        "description": "Classement des performances de PC sous Linux, mesurées avec hwbench.",
        "skip": "Aller au contenu",
    },
    "preview": {
        "title_prefix": "Preview · ",
        "banner": (
            "Preview : site généré depuis la branche dev, pour vérification avant une release. "
            "Ce n'est pas"
        ),
        "banner_link": "le classement officiel",
    },
    "header": {
        "home_aria": "hwbench, accueil",
        "version_aria": "version {version}",
        "nav_aria": "Navigation principale",
        "nav": {
            "classement": "Classement",
            "comparaison": "Comparer",
            "methodologie": "Méthodologie",
            "soumettre": "Soumettre",
        },
        "submit": "Soumettre ma machine",
        "submit_short": "Soumettre",
        "menu": "Menu",
        "theme": "Basculer le thème clair ou sombre",
    },
    "footer": {
        "pitch": (
            "Banc d'essai libre pour PC sous Linux. Résultats publics, mesurés par la "
            "communauté et soumis par pull request."
        ),
        "submit": "Soumettre ma machine",
        "col_rank": "Classement",
        "col_project": "Projet",
        "col_legal": "Informations légales",
        "links": {
            "classement": "Classement général",
            "comparaison": "Comparer des machines",
            "methodologie": "Méthodologie",
            "soumettre": "Soumettre un résultat",
            "contributing": "Guide de contribution ↗",
            "github": "Code source sur GitHub ↗",
            "issues": "Signaler un problème ↗",
            "releases": "Notes de version ↗",
            "license": "Licence AGPL-3.0 ↗",
            "mentions": "Mentions légales",
            "confidentialite": "Politique de confidentialité",
            "accessibilite": "Accessibilité",
            "cookies": "Cookies : aucun",
        },
        "publisher_t": "Éditeur.",
        "publisher": (
            "Projet open source non commercial, édité à titre non professionnel. Contact : "
            "issues du dépôt GitHub (publiques) ; données personnelles et retrait d'un "
            "résultat : {contact_private}."
        ),
        "host_t": "Hébergeur.",
        "host": HOST,
        "data_t": "Données personnelles.",
        "data": (
            "Aucun cookie, aucun traceur, aucune ressource tierce. Le thème choisi reste dans le "
            "stockage local de votre navigateur. L'hébergeur journalise des données techniques de "
            "connexion pour la sécurité du service. Les résultats soumis sont publics ; retrait et "
            "exercice de vos droits : voir les mentions légales."
        ),
        "copyright": (
            "© {year} contributeurs hwbench · code AGPL-3.0 · résultats CC0-1.0 · généré le "
            "{date} UTC"
        ),
        "trademarks": (
            "AMD, Intel, NVIDIA et les autres marques citées appartiennent à leurs détenteurs."
        ),
        "top": "Haut de page ↑",
    },
    "tips": {
        "button": "i",
        "why": "Pourquoi ça compte",
        "example": "Exemple",
        "close": "Fermer",
        "aria": "Explication : {term}",
        "entries": {
            "points": {
                "t": "Points",
                "term": "points",
                "d": (
                    "Une note qui compare votre machine à une machine de référence, qui vaut "
                    "1000 points sur chaque test."
                ),
                "w": (
                    "Vous lisez directement « plus ou moins rapide que la référence », sans "
                    "connaître les unités de chaque outil."
                ),
                "e": (
                    "500 points = deux fois plus lent que la référence ; 2000 = deux fois plus "
                    "rapide."
                ),
                "links": [],
            },
            "geomean": {
                "t": "Moyenne géométrique",
                "term": "moyenne géométrique",
                "d": (
                    "Une moyenne qui multiplie les scores puis en prend la racine, au lieu de "
                    "les additionner."
                ),
                "w": (
                    "Un score énorme dans une seule catégorie ne peut pas masquer une faiblesse "
                    "dans une autre."
                ),
                "e": "1000, 1000 et 250 donnent 630, et non 750.",
                "links": [],
            },
            "cv": {
                "t": "CV — coefficient de variation",
                "term": "coefficient de variation",
                "d": (
                    "La dispersion des runs d'un test (écart-type), en pourcentage de leur médiane."
                ),
                "w": (
                    "Plus il est bas, plus le résultat est reproductible. Au-delà de {cv} % sur "
                    "au moins un test, la machine est marquée « À vérifier »."
                ),
                "e": "Un CV proche de zéro : les runs sont quasi identiques.",
                "links": [],
            },
            "fio": {
                "t": "fio",
                "term": "fio",
                "d": "L'outil de référence pour mesurer la vitesse d'un disque.",
                "w": (
                    "Le résultat dépend du SSD mais aussi du système de fichiers : il reste "
                    "hors classement."
                ),
                "e": "",
                "links": [["Documentation fio", "https://fio.readthedocs.io/"]],
            },
            "iops": {
                "t": "IOPS",
                "term": "IOPS",
                "d": "Nombre de petites lectures ou écritures que le disque traite par seconde.",
                "w": (
                    "C'est ce qui rend un système réactif : ouvrir des applications, chercher "
                    "des fichiers."
                ),
                "e": "",
                "links": [["Documentation fio", "https://fio.readthedocs.io/"]],
            },
            "index": {
                "t": "Indice brut",
                "term": "indice brut",
                "d": "Le résultat interne d'un test, sans unité physique.",
                "w": "Il n'a de sens qu'en comparaison : c'est pourquoi il est converti en points.",
                "e": "",
                "links": [],
            },
            "native": {
                "t": "Tests natifs",
                "term": "tests natifs",
                "d": (
                    "Des tests écrits par hwbench : hachage SHA-256, compression zlib et LZMA, "
                    "exponentiation modulaire sur grands nombres."
                ),
                "w": "Ils imitent des tâches réelles et servent de base officielle aux points CPU.",
                "e": "",
                "links": [["Code source hwbench", "https://github.com/Mvth1s/hwbench"]],
            },
            "fps": {
                "t": "fps",
                "term": "fps",
                "d": "Images calculées par seconde.",
                "w": "Plus il y en a, plus la carte graphique est rapide sur la scène testée.",
                "e": "",
                "links": [],
            },
            "glmark2": {
                "t": "glmark2",
                "term": "glmark2",
                "d": (
                    "Un test graphique OpenGL qui affiche une série de scènes et compte les "
                    "images par seconde."
                ),
                "w": (
                    "Il représente les applications et jeux OpenGL. Ses fps ne se comparent pas "
                    "à ceux de vkmark."
                ),
                "e": "",
                "links": [["glmark2 sur GitHub", "https://github.com/glmark2/glmark2"]],
            },
            "vkmark": {
                "t": "vkmark",
                "term": "vkmark",
                "d": "L'équivalent de glmark2 pour Vulkan, l'interface graphique plus récente.",
                "w": (
                    "Il représente les jeux récents. Ses fps ne se comparent pas à ceux de glmark2."
                ),
                "e": "",
                "links": [["vkmark sur GitHub", "https://github.com/vkmark/vkmark"]],
            },
            "burst": {
                "t": "Burst",
                "term": "burst",
                "d": "Le tout premier passage, machine encore froide. Il n'est jamais noté.",
                "w": (
                    "Beaucoup de processeurs accélèrent brièvement à froid puis ralentissent en "
                    "chauffant : l'écart avec la médiane révèle ce comportement."
                ),
                "e": "",
                "links": [],
            },
            "median": {
                "t": "Médiane",
                "term": "médiane",
                "d": "La valeur du milieu quand on range les runs du plus petit au plus grand.",
                "w": "Un run raté (trop haut ou trop bas) ne déforme pas le résultat.",
                "e": "118, 121, 122 → médiane 121.",
                "links": [],
            },
            "warmup": {
                "t": "Warm-up (échauffement)",
                "term": "warm-up",
                "d": (
                    "Des passages préliminaires non comptés, répétés jusqu'à deux résultats "
                    "consécutifs à {tolerance} % près, dans une durée plafonnée."
                ),
                "w": "On mesure la machine dans son régime normal, pas pendant sa mise en route.",
                "e": "",
                "links": [],
            },
            "qd": {
                "t": "QD — profondeur de file",
                "term": "profondeur de file",
                "d": (
                    "Le nombre de demandes envoyées au disque en même temps ({qd_seq} en "
                    "séquentiel, {qd_rand} en aléatoire 4K)."
                ),
                "w": (
                    "Un SSD récent est bien plus rapide quand on lui donne plusieurs demandes à "
                    "la fois."
                ),
                "e": "",
                "links": [["Documentation fio", "https://fio.readthedocs.io/"]],
            },
            "epp": {
                "t": "EPP",
                "term": "EPP",
                "d": (
                    "Un réglage qui indique au processeur s'il doit privilégier la vitesse ou "
                    "l'économie d'énergie."
                ),
                "w": (
                    "Le même PC peut perdre une part notable de ses performances en mode économie."
                ),
                "e": "« performance » ou « power ».",
                "links": [
                    [
                        "amd-pstate (noyau Linux)",
                        "https://docs.kernel.org/admin-guide/pm/amd-pstate.html",
                    ],
                    [
                        "intel_pstate (noyau Linux)",
                        "https://docs.kernel.org/admin-guide/pm/intel_pstate.html",
                    ],
                ],
            },
            "governor": {
                "t": "Governor",
                "term": "governor",
                "d": "La règle choisie par Linux pour faire varier la fréquence du processeur.",
                "w": (
                    "Comme l'EPP, il change les résultats : il est noté pour que la comparaison "
                    "reste honnête."
                ),
                "e": "",
                "links": [
                    [
                        "CPU Performance Scaling (noyau Linux)",
                        "https://docs.kernel.org/admin-guide/pm/cpufreq.html",
                    ]
                ],
            },
        },
    },
    "kinds": {"desktop": "Fixe", "laptop": "Portable"},
    "kinds_plural": {"desktop": "fixes", "laptop": "portables"},
    "brands": {"AMD": "AMD", "Intel": "Intel", "NVIDIA": "NVIDIA", "other": "Autres"},
    "reliability": {"ok": "Fiable", "check": "À vérifier"},
    "stale": "à ré-exporter",
    "unranked": "non classé",
    "classement": {
        "title": "Classement {category}",
        "kicker": "Classement Linux · {machines} · mis à jour le {date}",
        "h1a": "Chaque machine,",
        "h1b": "au millième près.",
        "lede1": "Chaque test vaut",
        "lede2": "1000 points",
        "lede3": (
            "sur la machine de référence, {reference}. Le score combiné est la moyenne géométrique"
        ),
        "lede4": "du CPU single-core, du CPU multi-core et du GPU.",
        "see_rank": "Voir le classement",
        "how": "Comment les points sont calculés",
        "object_label": "TOUR ATX · FLUX D’AIR",
        "podium": "Podium",
        "podium_pos": "P{pos}",
        "cmd_bench": "hwbench bench",
        "cmd_export": "hwbench export",
        "free_spot": "Place libre — soumettez votre machine",
        "empty_k": "Aucune donnée",
        "empty_h": "Le classement démarre avec vous.",
        "empty_p": (
            "Mesurez votre PC, exportez le résultat, puis proposez le fichier JSON par pull "
            "request :"
        ),
        "guide": "Lire le guide de contribution",
        "rank_k": "Classement",
        "combined": "Combiné",
        "short": {
            "combined": "Combiné",
            "cpu_single": "Single",
            "cpu_multi": "Multi",
            "gpu": "GPU",
        },
        "cat_aria": "Catégorie du classement",
        "filters": "Recherche et filtres",
        "search": "Rechercher",
        "search_ph": "Machine, CPU, GPU…",
        "type_aria": "Type de machine",
        "all": "Toutes",
        "cpu_brand": "Marque CPU",
        "gpu_brand": "Marque GPU",
        "any_brand": "Toutes marques",
        "rel": "Fiabilité",
        "rel_all": "Toutes",
        "since": "Date",
        "since_all": "Depuis le début",
        "since_days": {
            "30": "30 derniers jours",
            "90": "90 derniers jours",
            "365": "12 derniers mois",
        },
        "range": "Plage de points",
        "min": "Min.",
        "max": "Max.",
        "reset": "Réinitialiser les filtres",
        "no_res": "Aucune machine ne correspond.",
        "no_res_p": "Élargissez la plage de points ou retirez un filtre.",
        "table_aria": "Tableau du classement, défilable",
        "caption": "Classement {category}, du plus rapide au plus lent",
        "head": {
            "rank": "Rang",
            "name": "Machine",
            "cpu": "CPU",
            "gpu": "GPU",
            "type": "Type",
            "score": "Points",
            "rel": "Fiabilité",
            "date": "Date",
        },
        "unranked_note": (
            "{machines} ici, en fin de liste : catégorie non mesurée ou non comparable à la "
            "référence"
        ),
        "unranked_note_combined": ", ou score combiné calculé sans GPU complet",
        "pagination": "Pagination",
        "first_p": "Première page",
        "prev_p": "Page précédente",
        "next_p": "Page suivante",
        "last_p": "Dernière page",
        "per_page": "Par page",
        "csv": "Exporter en CSV",
        "copy_link": "Copier le lien",
        "legend_ok": "Fiable",
        "legend_check": "À vérifier : CV supérieur à {cv} % sur au moins un test",
        "legend_stale": "À ré-exporter : noté contre une ancienne référence, points recalculés",
        "legend_shapes": "● fixe ■ portable",
        "downloads": "Données :",
        "download_json": "JSON",
        "download_csv": "CSV",
        "viz_k": "Vue d'ensemble",
        "viz_h": "Où se situent les machines",
        "scatter_h": "CPU contre GPU",
        "scatter_caption": "Nuage de points : score CPU contre score GPU",
        "hist_h": "Distribution des scores",
        "png": "Exporter en PNG",
        "few": (
            "La distribution s'affiche à partir de {min} machines. Pour l'instant : "
            "{machines}, médiane {median} points."
        ),
        "few_none": "Aucune machine classée dans cette catégorie pour l'instant.",
        "info_k": "Informations · hors classement",
        "info_h": "Mémoire et disque",
        "info_p": (
            "Ces mesures dépendent du système de fichiers et du SSD utilisés pour le test : "
            "elles n'entrent ni dans le classement, ni dans le score combiné."
        ),
        "info_missing": "{machines} sans mesure.",
        "mem_h": "Bande passante mémoire",
        "seq_h": "Disque séquentiel",
        "rand_h": "Disque aléatoire 4K",
        "mem_unit": "Mio/s · copie multi",
        "seq_unit": "Mio/s · lecture",
        "rand_unit": "k IOPS · lecture",
        "skipped_h": "Fichiers ignorés",
        "scatter_hint": "cliquez un point pour le sélectionner",
        "tray_aria": "Machines sélectionnées",
        "clear_selection": "Vider",
        "compare_cta": "Comparer",
        "select_head": "Comparer",
        "select_aria": "Comparer {name}",
    },
    "methodologie": {
        "title": "Méthodologie",
        "kicker": "Méthodologie · hwbench {version}",
        "h1": "Comment une machine gagne ses points.",
        "lede": (
            "Tout ce que mesure hwbench, comment chaque mesure devient un score, et ce que ces "
            "chiffres ne disent pas. Les résultats bruts restent publics : chacun peut refaire le "
            "calcul."
        ),
        "toc": "Sommaire",
        "formula": "combiné = ∛( single × multi × GPU )",
        "ex_cap": (
            "Exemple : une machine très forte en CPU mais faible en GPU ne compense pas sa "
            "faiblesse. La moyenne arithmétique donnerait {arith} ; la moyenne géométrique donne "
            "{geo}."
        ),
        "ex_points": "points",
        "ex_combined": "COMBINÉ",
        "ranked": "CLASSÉES",
        "ranked_l": [
            "CPU single-core (tests natifs, un processus)",
            "CPU multi-core (tests natifs, un processus par thread logique)",
            "GPU (glmark2 et vkmark)",
            "Score combiné = moyenne géométrique des trois",
        ],
        "info": "INFORMATIONS · HORS CLASSEMENT",
        "info_l": [
            "Mémoire : bande passante de copie (natif ; sysbench pour information)",
            "Disque : fio, séquentiel et aléatoire 4K",
            "Dépendent du système de fichiers et du SSD",
            "Jamais mélangées au classement",
        ],
        "bench_cap": "Les tests et outils de la référence actuelle",
        "bench_head": ["Test", "Ce qu'il mesure", "Unité", "Catégorie", "Statut", "Version"],
        "status_official": "officiel",
        "status_indicative": "indicatif",
        "protocol_v": "protocole {protocol}",
        "tool_v": "outil {tool}",
        "what": {
            "native-cpu-single": "Hachage, compression, calcul sur grands nombres (1 processus)",
            "native-cpu-multi": "Les mêmes charges, un processus par thread logique",
            "sysbench-cpu-single": "Recherche de nombres premiers (1 thread)",
            "sysbench-cpu-multi": "Recherche de nombres premiers (tous les threads)",
            "glmark2": "Scènes OpenGL rendues hors écran",
            "vkmark": "Scènes Vulkan rendues sans affichage",
            "native-memory-single": "Copie de gros blocs mémoire (1 processus)",
            "native-memory-multi": "Copie de gros blocs mémoire (un processus par thread)",
            "sysbench-memory-single": "Lecture séquentielle de la mémoire (1 thread)",
            "sysbench-memory-multi": "Lecture séquentielle de la mémoire (tous les threads)",
            "fio-disk": "Lecture et écriture séquentielles et aléatoires 4K",
        },
        "docs": "Documentation",
        "secs": [
            {
                "id": "points",
                "h": "Le système de points",
                "ps": [
                    (
                        "Chaque test vaut 1000 points sur la machine de référence, {reference}, "
                        "mesurée le {reference_date}. Une machine qui obtient 1500 points est "
                        "1,5 fois plus rapide que la référence sur ce test ; 500 points, deux "
                        "fois plus lente."
                    ),
                    (
                        "Les points rendent comparables des mesures exprimées dans des unités "
                        "différentes : images par seconde, événements par seconde, mébioctets "
                        "par seconde ou indice interne."
                    ),
                ],
            },
            {
                "id": "combine",
                "h": "Le score combiné",
                "ps": [
                    (
                        "Le classement principal utilise la moyenne géométrique des trois "
                        "catégories classées, à pondérations égales : on multiplie les trois "
                        "scores, puis on prend la racine cubique."
                    ),
                    (
                        "Une moyenne classique laisserait un score exceptionnel masquer une "
                        "faiblesse ; la moyenne géométrique récompense l'équilibre. Une machine "
                        "sans GPU mesuré, ou avec un GPU mesuré par une partie seulement des "
                        "outils, n'est pas classée au combiné."
                    ),
                ],
            },
            {
                "id": "categories",
                "h": "Catégories classées et informations",
                "ps": [
                    (
                        "Trois catégories forment le classement. La mémoire et le disque sont "
                        "mesurés et publiés, mais restent à part : leurs résultats dépendent trop "
                        "du système de fichiers, du SSD et de son remplissage pour être comparés "
                        "honnêtement."
                    )
                ],
            },
            {
                "id": "protocole",
                "h": "Le protocole de mesure",
                "ps": [
                    (
                        "Avant chaque test, des passes d'échauffement (warm-up) sont répétées "
                        "jusqu'à deux résultats consécutifs à {tolerance} % près, dans une "
                        "limite de {warmup_min} à {warmup_max} s selon la catégorie. Le test est "
                        "ensuite lancé au moins {runs} fois ; la médiane des runs est retenue."
                    ),
                    (
                        "Le premier passage à froid (burst) est enregistré à part et n'est "
                        "jamais noté : son écart avec la médiane révèle un processeur qui "
                        "accélère brièvement puis ralentit en chauffant."
                    ),
                    (
                        "Le coefficient de variation (CV) mesure la dispersion des runs. "
                        "Au-delà de {cv} % sur au moins un test, la machine est marquée « À "
                        "vérifier » : elle reste classée, mais signalée. Un test qui démarre "
                        "au-dessus de {hot} °C est signalé comme départ chaud."
                    ),
                    (
                        "Un résultat noté contre une ancienne machine de référence est marqué "
                        "« À ré-exporter » : ses points sont recalculés à partir de ses valeurs "
                        "brutes, mais les tests dont la version a changé depuis ne sont pas notés."
                    ),
                ],
            },
            {
                "id": "outils",
                "h": "Les outils",
                "ps": [
                    (
                        "Les tests natifs de hwbench sont la base officielle des points CPU ; "
                        "sysbench est mesuré pour information. glmark2 et vkmark se lisent "
                        "séparément : leurs fps ne sont jamais comparés entre eux. Deux mesures "
                        "ne sont comparables qu'avec la même version de protocole, la même "
                        "version d'outil et le même mode de rendu."
                    )
                ],
            },
            {
                "id": "conditions",
                "h": "Les conditions de mesure",
                "ps": [
                    (
                        "Chaque export enregistre l'alimentation (secteur ou batterie), l'EPP "
                        "(le réglage qui arbitre entre vitesse et économie d'énergie), le profil "
                        "de la plateforme et le governor (la règle de fréquence du noyau Linux). "
                        "Ces informations sont affichées sur chaque page machine."
                    )
                ],
            },
            {
                "id": "limites",
                "h": "Ce que les chiffres ne disent pas",
                "ps": [
                    (
                        "Les températures ne sont relevées qu'avant et après chaque test, pas "
                        "pendant : les graphiques relient deux instants, ils ne montrent pas "
                        "l'évolution réelle."
                    ),
                    (
                        "Les résultats sont déclaratifs, soumis par pull request. Les fichiers "
                        "sont vérifiés (format, absence d'identifiant, cohérence des points), "
                        "mais pas reproduits sur la machine d'origine."
                    ),
                    (
                        "Un même modèle peut obtenir des scores différents selon le BIOS, les "
                        "pilotes, le refroidissement et la température de la pièce."
                    ),
                ],
            },
            {
                "id": "reference",
                "h": "Changer de référence",
                "ps": [
                    (
                        "La référence actuelle est {reference}, mesurée le {reference_date} "
                        "(empreinte {digest}). Si elle change, tous les points sont recalculés "
                        "à partir des valeurs brutes ; les anciens exports sont marqués « À "
                        "ré-exporter »."
                    )
                ],
            },
        ],
        "kernel_links": [
            ["amd-pstate", "https://docs.kernel.org/admin-guide/pm/amd-pstate.html"],
            ["intel_pstate", "https://docs.kernel.org/admin-guide/pm/intel_pstate.html"],
            ["CPU Performance Scaling", "https://docs.kernel.org/admin-guide/pm/cpufreq.html"],
        ],
    },
    "soumettre": {
        "title": "Soumettre un résultat",
        "kicker": "Soumettre un résultat",
        "h1": "Ajoutez votre machine au classement.",
        "lede": (
            "Une mesure, un fichier JSON, une pull request vers la branche dev. Pendant les "
            "tests, la machine doit rester au repos."
        ),
        "facts": [
            ["FICHIER", "1 JSON"],
            ["LICENCE", "CC0-1.0"],
            ["VALIDATION", "CI"],
        ],
        "steps_h": "Cinq étapes",
        "copy_btn": "Copier",
        "copied": "Copié ✓",
        "copy_aria": "Copier la commande : {step}",
        "steps": [
            {
                "h": "Installer la dernière version",
                "p": (
                    "La validation exige un export de hwbench {version}, noté contre la "
                    "référence actuelle, avec des tests à leur version courante."
                ),
                "code": "pipx install hwbench        # ou : pipx upgrade hwbench",
            },
            {
                "h": "Mesurer dans de bonnes conditions",
                "p": (
                    "Sur secteur, profil d'énergie « performance », navigateur et autres "
                    "programmes fermés, depuis la session graphique pour les tests GPU. "
                    "Installez sysbench, glmark2 et vkmark si possible : le score GPU, et donc "
                    "le score combiné, ne sont classés qu'avec les mêmes outils que la machine "
                    "de référence."
                ),
                "code": "",
            },
            {
                "h": "Exporter dans un clone de votre fork",
                "p": (
                    "Forkez le dépôt sur GitHub, clonez votre fork, puis exportez. <nom> : "
                    "minuscules, chiffres et tirets (mon-desktop, latitude-5420). Il apparaît "
                    "publiquement dans l'adresse de la page de la machine : n'y mettez pas votre "
                    "nom si vous ne souhaitez pas qu'il soit publié."
                ),
                "code": "hwbench export -o results/<nom>.json",
            },
            {
                "h": "Vérifier avant d'envoyer",
                "p": (
                    "Depuis le clone, avec hwbench installé en mode développement "
                    "(pip install -e .). Vous pouvez aussi déposer le fichier ci-dessous pour un "
                    "premier contrôle dans le navigateur."
                ),
                "code": "python -m hwbench.leaderboard validate results/<nom>.json",
            },
            {
                "h": "Ouvrir la pull request vers dev",
                "p": (
                    "Avec un message de commit conventionnel. La CI (workflow results.yml) "
                    "valide le fichier : schéma d'export connu, aucun identifiant, référence "
                    "actuelle et non forcée, versions des tests à jour, points cohérents avec "
                    "les résultats bruts. Une fois la pull request fusionnée, la machine "
                    "apparaît sur le site à la release suivante."
                ),
                "code": ('git add results/<nom>.json && git commit -m "chore(results): add <nom>"'),
            },
        ],
        "guide": "Guide de contribution complet",
        "check_k": "Vérification locale",
        "check_h": "Contrôlez votre fichier avant la pull request.",
        "check_p": "Le fichier est lu dans votre navigateur : il n'est envoyé nulle part.",
        "drop": "Choisissez votre fichier JSON",
        "drop_sub": "ou déposez-le ici",
        "idle": "Aucun fichier analysé pour l'instant.",
        "nojs": (
            "Le contrôle dans le navigateur demande JavaScript ; la commande de l'étape 4 fait "
            "la même vérification, et davantage."
        ),
        "ci_note": (
            "Ce contrôle couvre la forme du fichier. La validation de l'étape 4 et la CI "
            "vérifient en plus la référence, les versions des tests et la cohérence des points."
        ),
        "faq_h": "Questions fréquentes",
        "faq": [
            {
                "q": "Quelles données sont publiées ?",
                "a": (
                    "Les composants sans aucun identifiant (CPU, GPU, carte mère, disques, RAM, "
                    "capteurs), les résultats bruts de chaque run, les versions des outils et "
                    "les conditions de mesure. Numéros de série, UUID, adresses MAC, nom d'hôte "
                    "et asset tags ne sont jamais collectés dans un export, et la validation "
                    "refuse tout fichier qui en contiendrait."
                ),
            },
            {
                "q": "Sous quelle licence ?",
                "a": (
                    "Les fichiers de résultats sont publiés sous CC0-1.0 (domaine public). Le "
                    "code de hwbench reste sous AGPL-3.0-or-later."
                ),
            },
            {
                "q": "Mon résultat est marqué « À vérifier ».",
                "a": (
                    "Au moins un test a un coefficient de variation supérieur à {cv} % : ses "
                    "runs étaient trop dispersés. Fermez les programmes en arrière-plan, "
                    "branchez le secteur et relancez la mesure."
                ),
            },
            {
                "q": "Comment retirer mon résultat ?",
                "a": (
                    "Ouvrez une pull request qui supprime results/<nom>.json, ou écrivez à "
                    "l'adresse indiquée dans les mentions légales. Le fichier est retiré du "
                    "dépôt et du site au déploiement suivant."
                ),
            },
        ],
    },
    "mentions": {
        "title": "Mentions légales",
        "kicker": "Informations légales",
        "h1": "Mentions légales, confidentialité et accessibilité",
        "toc": "Sur cette page",
        "updated": "Dernière mise à jour : 26/10/2026",
        "host": HOST,
        "secs": [
            {
                "id": "mentions",
                "h": "Mentions légales",
                "items": [
                    [
                        "Éditeur",
                        "Projet open source non commercial, édité à titre non professionnel.",
                    ],
                    [
                        "Contact",
                        (
                            "Questions générales : issues du dépôt GitHub (publiques). Données "
                            "personnelles : {contact_private}, jamais une issue publique (voir "
                            "« Vos droits » ci-dessous)."
                        ),
                    ],
                    ["Hébergeur", "{host}"],
                    [
                        "Propriété intellectuelle",
                        (
                            "Code source sous licence AGPL-3.0-or-later. Fichiers de résultats "
                            "sous licence CC0-1.0 (domaine public). Polices Schibsted Grotesk, "
                            "IBM Plex Mono et Michroma sous licence SIL Open Font License, "
                            "hébergées sur le site avec leur texte de licence. Les marques "
                            "citées appartiennent à leurs détenteurs."
                        ),
                    ],
                ],
            },
            {
                "id": "confidentialite",
                "h": "Données personnelles",
                "items": [
                    [
                        "Ce que traite le site",
                        (
                            "Rien côté serveur : le site est statique, sans compte, sans "
                            "formulaire envoyé à un serveur, sans mesure d'audience et sans "
                            "ressource chargée depuis un tiers. Le contrôle d'un fichier sur la "
                            "page « Soumettre » se fait dans votre navigateur ; le fichier n'est "
                            "envoyé nulle part."
                        ),
                    ],
                    [
                        "Résultats publiés",
                        (
                            "Les fichiers soumis sont publiés tels quels : composants sans "
                            "identifiant (numéros de série, UUID, adresses MAC, nom d'hôte et "
                            "asset tags ne sont pas collectés, et un filtre les retire de "
                            "l'export par précaution), mesures, versions des outils, conditions "
                            "de test, et le nom de fichier choisi. La validation refuse tout "
                            "fichier qui contiendrait un identifiant."
                        ),
                    ],
                    [
                        "Pseudonyme GitHub",
                        (
                            "Le pseudonyme GitHub de l'auteur d'une pull request est visible dans "
                            "la pull request et dans l'historique du dépôt."
                        ),
                    ],
                    [
                        "Préférence de thème",
                        (
                            "Le thème choisi (clair ou sombre) est conservé dans le stockage "
                            "local de votre navigateur, sous la clé hwbench.theme. Il ne quitte "
                            "pas votre appareil et ne sert à aucun suivi."
                        ),
                    ],
                    [
                        "Journaux de l'hébergeur",
                        (
                            "GitHub enregistre des données techniques de connexion, dont "
                            "l'adresse IP, pour le fonctionnement et la sécurité de GitHub "
                            "Pages, selon sa propre déclaration de confidentialité."
                        ),
                    ],
                    [
                        "Vos droits",
                        (
                            "Pour accéder aux données qui vous concernent, les faire rectifier "
                            "ou effacer (retrait d'un résultat), ou vous opposer à leur "
                            "publication, écrivez à {contact_private}. Le fichier est retiré du "
                            "dépôt et du site au déploiement suivant ; l'historique git peut "
                            "en conserver une trace."
                        ),
                    ],
                    [
                        "Réclamation",
                        "Vous pouvez introduire une réclamation auprès de la CNIL.",
                    ],
                ],
                "links": [
                    ["Déclaration de confidentialité de GitHub", GITHUB_PRIVACY],
                    ["CNIL", CNIL],
                ],
            },
            {
                "id": "cookies",
                "h": "Cookies et stockage local",
                "items": [
                    ["Cookies", "Le site ne dépose aucun cookie."],
                    [
                        "Stockage local",
                        (
                            "Seule la préférence de thème est conservée (clé hwbench.theme). "
                            "Vous pouvez l'effacer depuis les réglages de votre navigateur."
                        ),
                    ],
                ],
            },
            {
                "id": "accessibilite",
                "h": "Accessibilité",
                "items": [
                    [
                        "Contrastes",
                        (
                            "Contraste du texte d'au moins {contrast}:1 sur les fonds du site, "
                            "dans les deux thèmes, vérifié automatiquement par les tests à "
                            "chaque modification."
                        ),
                    ],
                    [
                        "Navigation au clavier",
                        (
                            "Liens, boutons, onglets, filtres et popups s'utilisent au clavier, "
                            "avec un focus visible ; un lien d'évitement mène directement au "
                            "contenu."
                        ),
                    ],
                    [
                        "Contenu sans JavaScript",
                        (
                            "Chaque page reste complète sans JavaScript : le script n'ajoute que "
                            "le tri, les filtres, la comparaison choisie et la bascule de thème."
                        ),
                    ],
                    [
                        "Graphiques",
                        (
                            "Chaque graphique est suivi d'un tableau équivalent, masqué à "
                            "l'écran et destiné aux lecteurs d'écran ; la couleur n'est jamais "
                            "seule porteuse d'information (formes et libellés)."
                        ),
                    ],
                    [
                        "Animations",
                        "Désactivées quand le système demande de réduire les animations.",
                    ],
                    [
                        "Limites connues",
                        (
                            "Les images PNG exportées n'ont pas de texte alternatif : l'export "
                            "CSV donne les mêmes données sous forme de tableau. Le site n'a pas "
                            "été testé avec un lecteur d'écran."
                        ),
                    ],
                    [
                        "Signaler un problème",
                        (
                            "Ouvrez une issue sur le dépôt GitHub en décrivant la page, l'outil "
                            "utilisé et le problème rencontré."
                        ),
                    ],
                ],
            },
        ],
    },
    "notfound": {
        "title": "Page introuvable",
        "kicker": "Erreur 404 · page introuvable",
        "code": "404",
        "h1": "Aucun résultat à cette adresse.",
        "p": (
            "La page a peut-être été renommée, ou la machine retirée du classement. Cherchez-la "
            "par son nom, son CPU ou son GPU."
        ),
        "search": "Rechercher",
        "search_ph": "Machine, CPU, GPU…",
        "gauge": "{label} · 0",
        "links": {
            "classement": "Classement",
            "methodologie": "Méthodologie",
            "soumettre": "Soumettre un résultat",
        },
    },
    "comparaison": {
        "title": "Comparaison",
        "kicker": "Comparaison côte à côte",
        "h1": "Comparer des machines",
        "copy_link": "Copier le lien",
        "csv": "Exporter en CSV",
        "nojs_p": (
            "Sans JavaScript, la comparaison choisie dans le classement ne peut pas se "
            "construire : voici toutes les machines côte à côte, en points (référence 1000)."
        ),
        "to_rank": "Aller au classement",
        "all_caption": "Toutes les machines, en points, par score combiné",
        "selected": "Machines comparées",
        "as_base": "Base des écarts",
        "add": "Ajouter une machine",
        "choose": "Choisir…",
        "max": "8 machines au maximum.",
        "few_h": "Il faut au moins deux machines.",
        "few_p": "Ajoutez une machine ci-dessus, ou cochez-en plusieurs dans le classement.",
        "diff_h": "Écarts en %",
        "cat": "Catégorie",
        "diff_note": (
            "▲ au-dessus de la base · ▼ en dessous. Les écarts se lisent en points, jamais en "
            "fps : glmark2 et vkmark ne se comparent pas entre eux."
        ),
        "radar_h": "Profil single / multi / GPU",
        "radar_cap": (
            "Le radar superpose les 4 premières machines pour rester lisible ; le tableau les "
            "montre toutes."
        ),
        "group_h": "Points par catégorie",
        "png": "Exporter en PNG",
        "info_k": "Informations · hors classement",
        "info_h": "Mémoire et disque",
        "info_p": (
            "Mesures dépendantes du système de fichiers et du SSD : affichées à part, jamais "
            "intégrées aux écarts ci-dessus."
        ),
        "mem_h": "Bande passante mémoire",
        "seq_h": "Disque séquentiel",
        "mibs": "Mio/s",
        "head": {
            "name": "Machine",
            "combined": "Combiné",
            "memory": "Mémoire (Mio/s)",
            "disk": "Disque séq. (Mio/s)",
        },
    },
    "machine": {
        "title": "{machine}",
        "crumbs": "Fil d'Ariane",
        "rank": "Classement",
        "cv_max": "CV max {cv}",
        "exported": "{date} · hwbench {version}",
        "cpu": "CPU",
        "gpu": "GPU",
        "ram": "RAM",
        "cores": "{physical} cœurs / {logical} threads",
        "ram_visible": "{size} Gio visibles",
        "stale_p": (
            "Ce résultat a été noté contre une ancienne machine de référence. Ses points sont "
            "recalculés contre la référence actuelle à partir de ses résultats bruts ; les "
            "benchs dont la version a changé depuis ne sont pas notés. Un nouvel export donnera "
            "une note complète."
        ),
        "combined": "Score combiné",
        "vs_ref": "{delta} vs référence",
        "combined_missing": "Non classé : score combiné calculé sans GPU complet, ou absent.",
        "rank_of": "sur {machines}",
        "rank_kind_of": "sur {count} {kind}",
        "beat": "des machines derrière elle",
        "by_cat": "Par catégorie",
        "raw_vals": "Valeurs brutes",
        "face_to": "Face à…",
        "combined_lc": "score combiné",
        "this": "Cette machine",
        "reference": "Référence",
        "median": "Médiane ({machines})",
        "add_machine": "Ajouter une machine",
        "full_cmp": "Comparaison complète →",
        "choose": "Choisir…",
        "added": "ajoutée",
        "same_h": "Même modèle, autres soumissions",
        "same_p": (
            "{files} pour ce modèle. Dispersion du score combiné : {low} – {high}. BIOS, "
            "pilotes, refroidissement et température ambiante, non mesurés, peuvent l'expliquer."
        ),
        "same_this": "Ce fichier",
        "cpu_h": "CPU · tests natifs",
        "faster": "plus rapide sur {workers} processus",
        "subtest": "Sous-test",
        "single": "Single",
        "multi": "Multi ({workers})",
        "gain": "Gain multi / single",
        "ideal": "┆ gain idéal = {workers}× (un processus par thread logique)",
        "gpu_h": "GPU · fps par scène",
        "gpu_p": (
            "glmark2 et vkmark utilisent des échelles différentes : leurs fps ne se comparent "
            "pas entre eux. Rendu {resolution}."
        ),
        "gl_h": "glmark2 · OpenGL",
        "vk_h": "vkmark · Vulkan",
        "med_fps": "médiane {value} fps",
        "rel_h": "Fiabilité des mesures",
        "runs_l": "● runs",
        "burst_l": "◇ burst",
        "median_l": "| médiane",
        "cv_l": "CV",
        "warm_l": "warm-up stable sur {stable} tests sur {total}",
        "temp_h": "Températures CPU",
        "temp_p": (
            "○ avant · ■ après chaque test. Deux relevés seulement par test : la ligne "
            "pointillée relie deux instants, elle ne décrit pas l'évolution pendant le test."
        ),
        "time_h": "Répartition du temps de test",
        "time_p": "Durée totale, warm-up et pauses de refroidissement compris.",
        "time_center": "min:s au total",
        "cooldown": "Refroidissement",
        "info_k": "Informations · hors classement",
        "mem_h": "Mémoire",
        "disk_h": "Disque",
        "mem_unit": "Mio/s",
        "seq_unit": "Mio/s",
        "rand_unit": "k IOPS",
        "tech_h": "Détail technique",
        "file": "Fichier {file} · points recalculés contre la référence {reference} (1000 points).",
        "comp": "Composants",
        "cond": "Conditions de mesure",
        "sensors": "Capteurs",
        "raw_h": "Résultats bruts",
        "comp_k": {
            "board": "Carte mère",
            "bios": "BIOS",
            "cpu": "CPU",
            "memory": "Mémoire",
            "gpu": "GPU",
            "drivers": "Pilotes GPU",
            "disks": "Disques",
        },
        "freq": "{min}–{max} MHz",
        "cond_k": {
            "power": "Alimentation",
            "epp": "EPP",
            "governor": "Governor",
            "profile": "Profil plateforme",
            "driver": "Pilote de fréquence",
            "total": "Durée totale",
            "settings": "Seuils",
        },
        "on_ac": "secteur",
        "on_ac_desktop": "secteur (pas de batterie)",
        "on_battery": "batterie",
        "head": {
            "test": "Test",
            "median": "Médiane",
            "runs": "Runs",
            "cv": "CV",
            "burst": "Burst",
            "warmup": "Warm-up",
            "points": "Points",
            "status": "Statut",
        },
        "official": "officiel",
        "indicative": "indicatif",
        "unscored": "non noté",
        "csv": "Exporter en CSV",
        "json": "Télécharger le JSON source",
        "none": "—",
    },
    "charts": {
        "reference": "Référence",
        "reference_1000": "Référence 1000",
        "median": "médiane",
        "x_cpu": "CPU (√ single × multi)",
        "cpu": "CPU",
        "y_gpu": "GPU",
        "band": "Tranche de points",
        "machines": "Machines",
        "machine": "Machine",
        "value": "Valeur",
        "test": "Test",
        "before": "Avant (°C)",
        "after": "Après (°C)",
        "runs": "Runs",
        "burst": "Burst",
        "cv": "CV",
        "category": "Catégorie",
        "duration": "Durée",
        "share": "Part",
        "runs_caption": "Dispersion des runs autour de la médiane",
        "temps_caption": "Température CPU avant et après chaque test",
        "time_caption": "Répartition du temps de test",
    },
    # Textes lus par le JavaScript (publiés en JSON dans chaque page)
    "js": {
        "count": "{a}–{b} sur {c} machines",
        "none": "Aucune machine",
        "page": "Page {p} sur {n}",
        "copied": "Lien copié ✓",
        "copy_link": "Copier le lien",
        "theme_to_dark": "Passer au thème sombre",
        "theme_to_light": "Passer au thème clair",
        "menu": "Menu",
        "close": "Fermer",
        "csv_name": "hwbench-classement-{category}.csv",
        "cmp_csv_name": "hwbench-comparaison.csv",
        "cmp_csv_head": [
            "machine",
            "single",
            "multi",
            "gpu",
            "combine",
            "memoire_mibs",
            "disque_seq_mibs",
        ],
        "cmp_title": "{n} machines face à face",
        "cmp_base": "base : {name}",
        "cmp_base_cell": "base",
        "cmp_remove": "Retirer {name}",
        "cmp_added": "{name} ajoutée",
        "cmp_removed": "{name} retirée",
        "rank_prefix": "#",
        "check": {
            "ok": "Prêt pour la pull request",
            "warn": "Prêt, avec des points à vérifier",
            "ko": "À corriger avant la pull request",
            "pass": "Réussi",
            "fail": "Échec",
            "note": "Attention",
            "json": "JSON lisible",
            "schema": "Schéma d'export connu",
            "version": "Version de hwbench à jour",
            "date": "Date d'export",
            "machine": "Nom de machine",
            "ids": "Aucun identifiant (série, UUID, MAC, nom d'hôte, asset tag)",
            "name": "Nom de fichier valide (minuscules, chiffres, tirets)",
        },
        "unranked": "non classé",
        "axes": ["Single", "Multi", "GPU"],
        "categories": {
            "cpu_single": "CPU single-core",
            "cpu_multi": "CPU multi-core",
            "gpu": "GPU",
            "combined": "Combiné",
        },
        "reliability": {"ok": "Fiable", "check": "À vérifier"},
        "select_aria": "Comparer {name}",
        "sel_count": "{n} sélectionnée",
        "sel_count_many": "{n} sélectionnées",
        "sel_live_on": "{name} ajoutée à la comparaison",
        "sel_live_off": "{name} retirée de la comparaison",
        "raw_csv_name": "hwbench-{machine}-resultats.csv",
        "csv_head": [
            "rang",
            "machine",
            "cpu",
            "gpu",
            "type",
            "points",
            "cv_max_pct",
            "fiable",
            "date",
        ],
    },
}


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count <= 1 else many}"


def machines(count: int) -> str:
    return plural(count, "machine", "machines")


def unranked_machines(count: int) -> str:
    return plural(count, "machine non classée", "machines non classées")


def category_label(key: str) -> str:
    """« combined » ou valeur d'une Category -> libellé (table commune de hwbench.labels)."""
    if key == "combined":
        return str(FR["classement"]["combined"])
    return CATEGORY_LABELS[Category(key)]
