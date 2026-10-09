"""Textes français des constats (analysis.Finding) : phrases courtes, à l'indicatif, qui citent
les valeurs mesurées et les seuils de la session. Aucune cause non mesurée.
"""

from dataclasses import dataclass

from hwbench.analysis import Finding, FindingCode, Status
from hwbench.display.fmt import num
from hwbench.labels import CATEGORY_LABELS, PROFILE_LABELS, bench_label, disk_size_label
from hwbench.results import Category

STATUS_LABELS = {
    Status.FIX: "À corriger",
    Status.CHECK: "À vérifier",
    Status.OK: "Fiable",
    Status.INFO: "Information",
}

NEEDS_ROOT_LABELS = {"ram_modules": "barrettes RAM", "smart": "santé SMART des disques"}


def _list(parts: list[str]) -> str:
    """« a », « a et b », « a, b et c »."""
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " et " + parts[-1]


def _celsius(value: float | None) -> str:
    return "?" if value is None else f"{num(value, 0)} °C"


# hwbench relève la température CPU au début et à la fin de chaque test, pas pendant : le
# maximum cité est celui de ces relevés.
TEMPERATURE_PREFIX = "Température CPU maximale relevée avant et après chaque test"


def _tests(count: int) -> str:
    return "1 test" if count == 1 else f"{count} tests"


def _benches(finding: Finding) -> str:
    return _list([bench_label(i["bench"]) for i in finding.items])


def finding_text(finding: Finding) -> str:
    p, items = finding.params, finding.items
    match finding.code:
        case FindingCode.ON_BATTERY:
            return (
                f"Tests réalisés sur batterie ({_benches(finding)}) : les résultats ne "
                "représentent pas la machine sur secteur."
            )
        case FindingCode.POWER_PROFILE:
            current = {
                "platform_profile": p["platform_profile"],
                "energy_performance_preference": p["energy_performance_preference"],
            }
            settings = _list([f"{PROFILE_LABELS[s]} « {current[s]} »" for s in p["settings"]])
            return (
                f"Réglage d'énergie non performance pendant les tests ({settings}) : les scores "
                "sont inférieurs à ce que permet le profil performance."
            )
        case FindingCode.SOFTWARE_RENDERING:
            return (
                f"Rendu graphique fait par le processeur (llvmpipe ou lavapipe) pour "
                f"{_benches(finding)} : le score ne mesure pas la carte graphique."
            )
        case FindingCode.CONDITIONS_OK:
            power = "sur secteur" + (" (pas de batterie)" if p["has_battery"] is False else "")
            parts = [power]
            for key in ("platform_profile", "energy_performance_preference"):
                if p[key] is not None:
                    parts.append(f"{PROFILE_LABELS[key]} « {p[key]} »")
            return (
                f"Conditions conformes pendant tous les tests : {_list(parts)}, au meilleur "
                "réglage disponible."
            )
        case FindingCode.HOT_START:
            threshold = _celsius(p["threshold_c"])
            starts = _list([f"{bench_label(i['bench'])} à {_celsius(i['temp_c'])}" for i in items])
            after = (
                ", chacun juste après un autre test" if all(i["previous"] for i in items) else ""
            )
            subject = "Un test a" if len(items) == 1 else f"{_tests(len(items))} ont"
            return (
                f"{subject} démarré à {threshold} ou plus (seuil de départ chaud){after} : "
                f"{starts}."
            )
        case FindingCode.HIGH_VARIANCE:
            values = _list(
                [f"{bench_label(i['bench'])} avec un CV de {num(i['cv_percent'])} %" for i in items]
            )
            return (
                f"Mesures instables pour {_tests(len(items))} : {values}, au-delà du seuil de "
                f"{num(p['threshold_percent'], 0)} %. Ces scores sont à confirmer."
            )
        case FindingCode.WARMUP_UNSTABLE:
            values = _list(
                [f"{bench_label(i['bench'])} (plafond {num(i['cap_s'], 0)} s)" for i in items]
            )
            return f"Régime stable non atteint avant la fin du warm-up : {values}."
        case FindingCode.VSYNC_UNVERIFIED:
            return (
                f"Mode de présentation non vérifiable pour {_benches(finding)} : le score peut "
                "être plafonné par la fréquence de l'écran."
            )
        case FindingCode.TEMPERATURE_REACHED:
            return (
                f"{TEMPERATURE_PREFIX} : {_celsius(p['max_c'])}, au niveau du seuil haut du "
                f"capteur ({_celsius(p['threshold_c'])})."
            )
        case FindingCode.REPRODUCIBLE:
            return (
                f"Les {p['count']} tests sont très reproductibles : écart entre les runs de "
                f"{num(p['max_cv_percent'])} % au plus (seuil {num(p['threshold_percent'], 0)} %)."
            )
        case FindingCode.TEMPERATURE_OK:
            return (
                f"{TEMPERATURE_PREFIX} : {_celsius(p['max_c'])}, sous le seuil haut du capteur "
                f"({_celsius(p['threshold_c'])})."
            )
        case FindingCode.TEMPERATURE_MAX:
            return (
                f"{TEMPERATURE_PREFIX} : {_celsius(p['max_c'])} (le capteur n'indique pas de "
                "seuil)."
            )
        case FindingCode.MULTI_FACTOR:
            native = p["backend"] == "native"
            tool = "bench natif" if native else p["backend"]
            if p["kind"] == "cpu":
                subject, verb, gain = f"Le processeur ({tool})", "va", "plus vite"
            else:
                subject, verb, gain = f"La bande passante mémoire ({tool})", "est", "plus élevée"
            unit = "processus" if native else "threads"
            where = (
                f"sur {p['workers']} {unit} que sur un seul"
                if p["workers"]
                else "en parallèle qu'en un seul flux"
            )
            cores = (
                f" ({p['cores']} cœurs / {p['threads']} threads)"
                if p["cores"] and p["threads"]
                else ""
            )
            return f"{subject} {verb} {num(p['factor'])} fois {gain} {where}{cores}."
        case FindingCode.GPU_NOT_MEASURED:
            return "GPU non mesuré : le score combiné porte sur le processeur seul."
        case FindingCode.NEEDS_ROOT:
            missing = _list([NEEDS_ROOT_LABELS[m] for m in p["missing"]])
            return f"Non lus sans droits administrateur : {missing}."
        case FindingCode.NO_REFERENCE:
            return "Aucune machine de référence : les scores sont des valeurs brutes, sans points."
        case FindingCode.NOT_IN_REFERENCE:
            categories = _list([CATEGORY_LABELS[Category(c)].lower() for c in p["categories"]])
            return (
                f"Catégories d'information sans points ({categories}) : la référence ne les "
                "contient pas encore, les valeurs restent brutes."
            )
        case FindingCode.DISK_CONTEXT:
            where = _list(
                [
                    x
                    for x in (
                        f"fichier de {disk_size_label(p['size'])}" if p["size"] else None,
                        f"système de fichiers {p['filesystem']}" if p["filesystem"] else None,
                        p["device"],
                    )
                    if x
                ]
            )
            return (
                f"Disque mesuré dans ces conditions : {where}. Le score dépend du système de "
                "fichiers et du cache du SSD : il ne se compare qu'à configuration égale."
            )


def synthesis(findings: list[Finding], limit: int = 5) -> list[str]:
    """Phrases de la synthèse, de la plus importante à la moins importante.

    Le facteur multi-cœur n'y figure que pour le bench natif du processeur ; les autres facteurs
    restent dans leurs sections.
    """
    kept = [
        f
        for f in findings
        if f.code is not FindingCode.MULTI_FACTOR
        or (f.params["kind"] == "cpu" and f.params["backend"] == "native")
    ]
    return [finding_text(f) for f in kept[:limit]]


# --- Recommandations (rapport seulement) -------------------------------------------------------

# Catégorie (valeur de Category) -> cible de `hwbench bench`
BENCH_TARGETS = {
    "cpu_single": "cpu-single",
    "cpu_multi": "cpu-multi",
    "gpu": "gpu",
    "memory": "memory",
    "disk": "disk",
}
# sudo utilise son propre PATH (secure_path) : hwbench installé par pipx n'y est pas (README).
SUDO_INFO = 'sudo "$(command -v hwbench)" info'


@dataclass(frozen=True)
class Recommendation:
    text: str
    commands: list[str]


def _targets(finding: Finding) -> str:
    targets = []
    for item in finding.items:
        target = BENCH_TARGETS.get(item.get("category", ""))
        if target and target not in targets:
            targets.append(target)
    return targets[0] if len(targets) == 1 else "all"


def recommendation(finding: Finding) -> Recommendation | None:
    """Action à mener pour un constat, avec les commandes exactes ; None s'il n'y en a pas."""
    match finding.code:
        case FindingCode.ON_BATTERY:
            return Recommendation(
                "Brancher la machine sur secteur, puis relancer les tests.", ["hwbench bench"]
            )
        case FindingCode.POWER_PROFILE:
            return Recommendation(
                f"Passer au profil « {finding.params['best_profile']} » avant de relancer les "
                "tests (commande de power-profiles-daemon, s'il est installé).",
                [f"powerprofilesctl set {finding.params['best_profile']}", "hwbench bench"],
            )
        case FindingCode.SOFTWARE_RENDERING:
            return Recommendation(
                "Vérifier le pilote graphique : le renderer doit nommer la carte graphique, pas "
                "llvmpipe ou lavapipe.",
                ["glxinfo -B", "vulkaninfo --summary"],
            )
        case FindingCode.HOT_START:
            return Recommendation(
                "Laisser refroidir la machine, puis relancer les tests concernés.",
                [f"hwbench bench {_targets(finding)}"],
            )
        case FindingCode.HIGH_VARIANCE:
            return Recommendation(
                "Fermer les autres applications, puis relancer avec plus de runs.",
                [f"hwbench bench {_targets(finding)} --runs 5"],
            )
        case FindingCode.WARMUP_UNSTABLE:
            return Recommendation(
                "Relancer avec un plafond de warm-up plus long.",
                [f"hwbench bench {_targets(finding)} --max-warmup 180"],
            )
        case FindingCode.VSYNC_UNVERIFIED:
            return Recommendation(
                "Installer le plugin headless de vkmark pour un rendu sans affichage, puis "
                "relancer le test GPU.",
                ["hwbench bench gpu"],
            )
        case FindingCode.TEMPERATURE_REACHED:
            return Recommendation(
                "Laisser refroidir la machine avant de relancer les tests.", ["hwbench bench"]
            )
        case FindingCode.NEEDS_ROOT:
            return Recommendation(
                "Lire les barrettes RAM et la santé SMART avec les droits administrateur. sudo "
                "n'utilise pas le PATH de l'utilisateur : passer le chemin complet de hwbench "
                "(sous fish < 3.4 : sudo (command -v hwbench) info).",
                [SUDO_INFO],
            )
    return None


def recommendations(findings: list[Finding]) -> list[Recommendation]:
    return [r for f in findings if (r := recommendation(f)) is not None]
