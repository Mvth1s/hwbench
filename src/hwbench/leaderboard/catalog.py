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

FR: dict[str, Any] = {
    "lang": "fr",
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
            "accessibilite": "Accessibilité : partiellement conforme",
            "cookies": "Cookies : aucun",
        },
        "publisher_t": "Éditeur.",
        "publisher": (
            "Projet open source non commercial maintenu par Mvth1s. Éditeur non professionnel : "
            "conformément à l'article 6-III-2 de la LCEN, ses coordonnées ont été communiquées "
            "à l'hébergeur. Contact : issues du dépôt GitHub."
        ),
        "host_t": "Hébergeur.",
        "host": "GitHub, Inc. (service GitHub Pages), États-Unis.",
        "data_t": "Données personnelles.",
        "data": (
            "Aucun cookie, aucun traceur, aucune ressource tierce. Le thème choisi reste dans le "
            "stockage local de votre navigateur. L'hébergeur journalise les adresses IP pour la "
            "sécurité du service. Les résultats soumis sont publics : retrait et droits RGPD "
            "(art. 15 à 21) sur simple demande via une issue ; réclamation possible auprès de la "
            "CNIL."
        ),
        "copyright": (
            "© 2026 contributeurs hwbench · code AGPL-3.0 · résultats CC0-1.0 · généré le "
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
                "e": "CV 0,8 % : les runs sont quasi identiques.",
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
        },
    },
    "kinds": {"desktop": "Fixe", "laptop": "Portable"},
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
