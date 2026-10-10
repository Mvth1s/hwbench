from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hwbench.display.fmt import measure, num
from hwbench.labels import (  # noqa: F401 — réexportés pour display/
    CATEGORY_LABELS,
    DETAIL_LABELS,
    ENVIRONMENT_LABELS,
    PRESENTATION_LABELS,
    PROFILE_LABELS,
    UNIT_LABELS,
    disk_size_label,
    unit_label,
)
from hwbench.results import BenchWarning, Category, MachineState, Result
from hwbench.runner import Cooldown, CooldownOutcome, RunSettings

NA = Text("non disponible", style="dim")


def _unit(unit: str) -> str:
    return unit_label(unit)


def warning_message(
    warning: BenchWarning, state: MachineState, result: Result | None = None
) -> str:
    match warning:
        case BenchWarning.ON_BATTERY:
            return (
                "Machine sur batterie : les performances sont souvent bridées. "
                "Relancez sur secteur pour des résultats comparables."
            )
        case BenchWarning.HOT_START:
            return (
                f"CPU déjà chaud au départ ({num(state.cpu_temp_c or 0, 0)} °C) : "
                "risque de throttling. Laissez refroidir avant de relancer."
            )
        case BenchWarning.POWER_PROFILE:
            current = {
                "platform_profile": state.platform_profile,
                "energy_performance_preference": state.energy_performance_preference,
            }
            settings = ", ".join(
                f"{PROFILE_LABELS[name]} « {current[name]} »"
                for name in state.throttling_settings()
            )
            return (
                f"Réglage d'énergie non « performance » ({settings}) : le CPU est peut-être "
                "bridé. Passez en profil performance pour des résultats comparables."
            )
        case BenchWarning.HIGH_VARIANCE:
            return (
                f"Mesures instables (CV {num(result.cv_percent if result else 0)} %) : "
                "une tâche de fond perturbe peut-être le bench."
            )
        case BenchWarning.WARMUP_UNSTABLE:
            return (
                f"Warm-up non stabilisé après {num(result.warmup_s if result else 0, 0)} s : "
                "la machine chauffe ou throttle encore. Allongez le plafond (--max-warmup)."
            )
        case BenchWarning.VSYNC_UNVERIFIED:
            return (
                "Rendu à l'écran : vsync coupée à la demande (mode immediate), sans garantie "
                "que le pilote l'applique ; le score peut être plafonné par l'écran. Installez "
                "le plugin headless de vkmark pour un rendu sans affichage."
            )
        case BenchWarning.SOFTWARE_RENDERING:
            return (
                "Rendu logiciel (llvmpipe/lavapipe) : c'est le CPU qui dessine, le score ne "
                "reflète pas le GPU. Vérifiez le pilote graphique."
            )


def _power(state: MachineState) -> str:
    if state.on_ac is None:
        return "?"
    if state.on_ac and state.has_battery is False:
        return "secteur (pas de batterie)"
    return "secteur" if state.on_ac else "batterie"


def _state_rows(t: Table, result: Result) -> None:
    before, after = result.state_before, result.state_after
    t.add_row("Governor", ", ".join(before.governors) if before.governors else NA)
    t.add_row("Profil plateforme", before.platform_profile or NA)
    t.add_row("EPP", before.energy_performance_preference or NA)
    power = _power(before)
    if after.on_ac != before.on_ac:
        power += f" → {_power(after)}"
    t.add_row("Alimentation", NA if before.on_ac is None and after.on_ac is None else power)
    if before.cpu_temp_c is None and after.cpu_temp_c is None:
        t.add_row("Température CPU", NA)
    else:
        temps = [
            "?" if v is None else f"{num(v, 0)} °C" for v in (before.cpu_temp_c, after.cpu_temp_c)
        ]
        t.add_row("Température CPU", f"{temps[0]} avant → {temps[1]} après")


def cooldown_message(cooldown: Cooldown, settings: RunSettings) -> str:
    seuil = f"{num(settings.hot_start_c, 0)} °C"
    waited = f"{num(cooldown.waited_s, 0)} s"
    start, end = (
        "?" if v is None else f"{num(v, 0)} °C" for v in (cooldown.start_c, cooldown.end_c)
    )
    match cooldown.outcome:
        case CooldownOutcome.FIXED:
            return f"pause de {waited}."
        case CooldownOutcome.ALREADY_COOL:
            return f"CPU à {end}, déjà sous {seuil} : aucune attente."
        case CooldownOutcome.COOLED:
            return f"CPU de {start} à {end} en {waited} (seuil {seuil})."
        case CooldownOutcome.TIMEOUT:
            return (
                f"CPU encore à {end} après {waited} (seuil {seuil}, départ à {start}) : "
                "test lancé quand même."
            )
        case CooldownOutcome.NO_SENSOR:
            return "température CPU non disponible : pas d'attente automatique."


def render_result(result: Result) -> Panel:
    unit = _unit(result.unit)
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column()
    score = Text(f"{measure(result.value)} {unit}", style="bold")
    score.append(
        f"  ± {measure(result.stdev)} (CV {num(result.cv_percent)} %)",
        style="yellow" if BenchWarning.HIGH_VARIANCE in result.warnings else "dim",
    )
    t.add_row("Score (médiane)", score)
    t.add_row("Runs", " · ".join(measure(v) for v in result.runs))
    t.add_row(
        "Warm-up",
        f"{result.warmup_runs} itérations, {num(result.warmup_s)} s"
        + ("" if result.warmup_stable else " (non stabilisé)")
        + f" · {num(result.duration_s)} s au total",
    )
    if result.cooldown_s > 0:
        t.add_row("Refroidissement", f"{num(result.cooldown_s, 0)} s de pause avant le test")
    t.add_row("Burst (à froid)", Text(f"{measure(result.burst)} {unit}  (hors score)", style="dim"))
    if result.workers is not None:
        # le natif lance des processus (GIL) ; les outils externes, des threads
        t.add_row("Processus" if result.backend == "native" else "Threads", str(result.workers))
    if result.presentation is not None and result.category is Category.DISK:
        t.add_row("Fichier de test", disk_size_label(result.presentation))
    elif result.presentation is not None:
        t.add_row("Présentation", PRESENTATION_LABELS.get(result.presentation, result.presentation))
    _state_rows(t, result)

    parts: list[Table | Text] = [t]
    if result.details:
        details = Table(show_edge=False, box=None, header_style="bold")
        details.add_column("Charge")
        details.add_column("Médiane", justify="right")
        for key, value in result.details.items():
            details.add_row(
                DETAIL_LABELS.get(key, key),
                f"{measure(value)} {_unit(result.detail_units.get(key, ''))}".strip(),
            )
        parts.append(details)
    if result.environment:
        parts.append(Text(" · ".join(_environment(result.environment)), style="dim"))
    for warning in result.warnings:
        message = warning_message(warning, result.state_before, result)
        parts.append(Text(f"⚠ {message}", style="yellow"))

    # v{version} : version du protocole hwbench (charges, scènes, durée) ; outil : son binaire
    tool = f" · outil {result.tool_version}" if result.tool_version else ""
    return Panel(
        Group(*parts),
        title=f"{CATEGORY_LABELS[result.category]} · {result.backend} v{result.version}{tool}",
        title_align="left",
    )


def _environment(env: dict[str, str]) -> list[str]:
    items: list[str] = []
    for key, value in env.items():
        if key in ENVIRONMENT_LABELS:
            items.append(f"{ENVIRONMENT_LABELS[key]} {value}")
        else:
            # « CPython 3.14.7 » / « OpenSSL 3.5.1 » se nomment déjà eux-mêmes
            items.append(f"{key} {value}" if value[:1].isdigit() else value)
    return items
