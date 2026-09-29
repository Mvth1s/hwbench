from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hwbench.display.fmt import num
from hwbench.results import BenchWarning, Category, MachineState, Result

CATEGORY_LABELS = {
    Category.CPU_SINGLE: "CPU single-core",
    Category.CPU_MULTI: "CPU multi-core",
    Category.GPU: "GPU",
}

DETAIL_LABELS = {
    "sha256": "SHA-256",
    "zlib": "Compression zlib (niveau 6)",
    "lzma": "Compression LZMA (preset 1)",
    "powmod": "Exponentiation modulaire 2048 bits",
}

# « index » : moyenne géométrique de débits, sans unité, tant que le scoring n'existe pas.
UNIT_LABELS = {"MiB/s": "Mio/s", "index": "indice brut"}

PROFILE_LABELS = {"platform_profile": "profil plateforme", "energy_performance_preference": "EPP"}

NA = Text("non disponible", style="dim")


def _unit(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


def _value(value: float) -> str:
    return num(value, 1 if value < 10_000 else 0)


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


def _power(state: MachineState) -> str:
    if state.on_ac is None:
        return "?"
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


def render_result(result: Result) -> Panel:
    unit = _unit(result.unit)
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column()
    score = Text(f"{_value(result.value)} {unit}", style="bold")
    score.append(
        f"  ± {_value(result.stdev)} (CV {num(result.cv_percent)} %)",
        style="yellow" if BenchWarning.HIGH_VARIANCE in result.warnings else "dim",
    )
    t.add_row("Score (médiane)", score)
    t.add_row("Runs", " · ".join(_value(v) for v in result.runs))
    t.add_row(
        "Warm-up",
        f"{result.warmup_runs} itérations, {num(result.warmup_s)} s"
        + ("" if result.warmup_stable else " (non stabilisé)")
        + f" · {num(result.duration_s)} s au total",
    )
    t.add_row("Burst (à froid)", Text(f"{_value(result.burst)} {unit}  (hors score)", style="dim"))
    if result.workers is not None:
        t.add_row("Processus", str(result.workers))
    _state_rows(t, result)

    parts: list[Table | Text] = [t]
    if result.details:
        details = Table(show_edge=False, box=None, header_style="bold")
        details.add_column("Charge")
        details.add_column("Médiane", justify="right")
        for key, value in result.details.items():
            details.add_row(
                DETAIL_LABELS.get(key, key),
                f"{_value(value)} {_unit(result.detail_units.get(key, ''))}".strip(),
            )
        parts.append(details)
    if result.environment:
        parts.append(
            Text(
                " · ".join(
                    # « CPython 3.14.7 » / « OpenSSL 3.5.1 » se nomment déjà eux-mêmes
                    f"{k} {v}" if v[:1].isdigit() else v
                    for k, v in result.environment.items()
                ),
                style="dim",
            )
        )
    for warning in result.warnings:
        message = warning_message(warning, result.state_before, result)
        parts.append(Text(f"⚠ {message}", style="yellow"))

    return Panel(
        Group(*parts),
        title=f"{CATEGORY_LABELS[result.category]} · {result.backend} v{result.version}",
        title_align="left",
    )
