"""Analyse déterministe d'une session (un export) : des constats codés, sans texte ni HTML.

Chaque règle se déclenche sur les données mesurées et produit un `Finding` : un code, un statut
et des paramètres (valeurs mesurées, seuils lus dans les RunSettings passés à `analyze`). Les
constats liés à un seuil (batterie, profil, départ chaud, CV, warm-up) sont recalculés depuis les
valeurs mesurées avec ces RunSettings, pas lus dans les avertissements enregistrés : le site du
classement peut ainsi appliquer les seuils par défaut à tout fichier soumis. Seuls les
avertissements propres à un outil (vsync, rendu logiciel) sont repris tels quels. Le texte
français est produit par la couche de rendu (report/texts.py). Aucune règle n'explique une
cause qu'elle n'a pas mesurée.

Ne dépend que des modèles : testable règle par règle, sans HTML ni système.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from hwbench.export import MachineExport
from hwbench.models import Unavailable
from hwbench.results import BenchWarning, Category, Result
from hwbench.runner import RunSettings, start_warnings
from hwbench.scoring import ScoreIssue


class Status(StrEnum):
    """Vocabulaire constant du rapport : À corriger · À vérifier · Fiable, puis information."""

    FIX = "fix"
    CHECK = "check"
    OK = "ok"
    INFO = "info"


STATUS_ORDER = (Status.FIX, Status.CHECK, Status.OK, Status.INFO)


class FindingCode(StrEnum):
    ON_BATTERY = "on_battery"
    POWER_PROFILE = "power_profile"
    SOFTWARE_RENDERING = "software_rendering"
    CONDITIONS_OK = "conditions_ok"  # secteur, profil plateforme et EPP au meilleur réglage
    HOT_START = "hot_start"
    HOT_IDLE = "hot_idle"  # départ chaud à la température de repos (--cooldown auto, stagnation)
    HIGH_VARIANCE = "high_variance"
    WARMUP_UNSTABLE = "warmup_unstable"
    VSYNC_UNVERIFIED = "vsync_unverified"
    TEMPERATURE_REACHED = "temperature_reached"  # seuil haut du capteur CPU atteint
    REPRODUCIBLE = "reproducible"
    TEMPERATURE_OK = "temperature_ok"
    TEMPERATURE_MAX = "temperature_max"  # seuil du capteur inconnu : maximum seul
    MULTI_FACTOR = "multi_factor"
    GPU_NOT_MEASURED = "gpu_not_measured"
    NEEDS_ROOT = "needs_root"
    NO_REFERENCE = "no_reference"
    NOT_IN_REFERENCE = "not_in_reference"
    DISK_CONTEXT = "disk_context"


@dataclass(frozen=True)
class Finding:
    code: FindingCode
    status: Status
    params: dict[str, Any] = field(default_factory=dict)
    # un élément par test concerné (nom du bench et ses valeurs), dans l'ordre de la session
    items: list[dict[str, Any]] = field(default_factory=list)


# Paires single / multi comparées par la règle du facteur multi-cœur (catégorie, nom du multi)
MULTI_PAIRS = (
    ("cpu", "native-cpu-single", "native-cpu-multi"),
    ("cpu", "sysbench-cpu-single", "sysbench-cpu-multi"),
    ("memory", "native-memory-single", "native-memory-multi"),
    ("memory", "sysbench-memory-single", "sysbench-memory-multi"),
)


def _with(results: list[Result], warning: BenchWarning) -> list[Result]:
    """Tests qui portent un avertissement d'outil enregistré (vsync, rendu logiciel)."""
    return [r for r in results if warning in r.warnings]


def _at_start(results: list[Result], warning: BenchWarning, settings: RunSettings) -> list[Result]:
    """Tests dont l'état de départ déclenche l'avertissement avec ces seuils (même calcul que
    le runner : runner.start_warnings)."""
    return [
        r
        for r in results
        if warning in start_warnings(r.state_before, settings, r.cooldown_outcome)
    ]


def _bench_items(results: list[Result]) -> list[dict[str, Any]]:
    return [{"bench": r.name, "category": r.category.value} for r in results]


def _power(results: list[Result], settings: RunSettings) -> list[Finding]:
    findings = []
    if battery := _at_start(results, BenchWarning.ON_BATTERY, settings):
        findings.append(Finding(FindingCode.ON_BATTERY, Status.FIX, items=_bench_items(battery)))
    # EPP et profil plateforme seulement (throttling_settings), jamais le governor : sous
    # intel_pstate, « powersave » est le governor normal et ne bride rien.
    if not findings and (conforming := _conforming_conditions(results)) is not None:
        findings.append(conforming)
    if throttled := _at_start(results, BenchWarning.POWER_PROFILE, settings):
        state = throttled[0].state_before
        findings.append(
            Finding(
                FindingCode.POWER_PROFILE,
                Status.FIX,
                {
                    "settings": state.throttling_settings(),
                    "platform_profile": state.platform_profile,
                    "energy_performance_preference": state.energy_performance_preference,
                    "best_profile": state.best_profile(),
                },
                _bench_items(throttled),
            )
        )
    return findings


def _conforming_conditions(results: list[Result]) -> Finding | None:
    """Fiable si, avant et après chaque test : secteur confirmé et aucun réglage d'énergie
    bridant (profil plateforme et EPP au meilleur réglage disponible). Rien n'est affirmé si ni
    le profil plateforme ni l'EPP ne sont connus."""
    states = [s for r in results for s in (r.state_before, r.state_after)]
    if not states:
        return None
    if any(s.on_ac is not True or s.throttling_settings() for s in states):
        return None
    if all(s.platform_profile is None and s.energy_performance_preference is None for s in states):
        return None
    first = states[0]
    return Finding(
        FindingCode.CONDITIONS_OK,
        Status.OK,
        {
            "has_battery": first.has_battery,
            "platform_profile": first.platform_profile,
            "energy_performance_preference": first.energy_performance_preference,
        },
    )


def _per_bench_warnings(results: list[Result], settings: RunSettings) -> list[Finding]:
    findings = []
    if software := _with(results, BenchWarning.SOFTWARE_RENDERING):
        findings.append(
            Finding(FindingCode.SOFTWARE_RENDERING, Status.FIX, items=_bench_items(software))
        )
    hot = []
    hot_names = {r.name for r in _at_start(results, BenchWarning.HOT_START, settings)}
    for i, r in enumerate(results):
        if r.name in hot_names:
            hot.append(
                {
                    "bench": r.name,
                    "category": r.category.value,
                    "temp_c": r.state_before.cpu_temp_c,
                    "previous": results[i - 1].name if i else None,
                }
            )
    if hot:
        findings.append(
            Finding(FindingCode.HOT_START, Status.CHECK, {"threshold_c": settings.hot_start_c}, hot)
        )
    if idle := _at_start(results, BenchWarning.HOT_IDLE, settings):
        findings.append(
            Finding(
                FindingCode.HOT_IDLE,
                Status.INFO,
                {"threshold_c": settings.hot_start_c},
                [
                    {
                        "bench": r.name,
                        "category": r.category.value,
                        "temp_c": r.state_before.cpu_temp_c,
                    }
                    for r in idle
                ],
            )
        )
    unstable = [r for r in results if r.cv_percent > settings.high_variance_cv_percent]
    if unstable:
        findings.append(
            Finding(
                FindingCode.HIGH_VARIANCE,
                Status.CHECK,
                {"threshold_percent": settings.high_variance_cv_percent},
                [
                    {"bench": r.name, "category": r.category.value, "cv_percent": r.cv_percent}
                    for r in unstable
                ],
            )
        )
    if warmup := [r for r in results if not r.warmup_stable]:
        findings.append(
            Finding(
                FindingCode.WARMUP_UNSTABLE,
                Status.CHECK,
                items=[
                    {
                        "bench": r.name,
                        "category": r.category.value,
                        "cap_s": settings.warmup_cap(r.category),
                    }
                    for r in warmup
                ],
            )
        )
    if vsync := _with(results, BenchWarning.VSYNC_UNVERIFIED):
        findings.append(
            Finding(FindingCode.VSYNC_UNVERIFIED, Status.CHECK, items=_bench_items(vsync))
        )
    return findings


def _reproducible(results: list[Result], settings: RunSettings) -> list[Finding]:
    if results and all(r.cv_percent <= settings.reliable_cv_percent for r in results):
        return [
            Finding(
                FindingCode.REPRODUCIBLE,
                Status.OK,
                {
                    "count": len(results),
                    "threshold_percent": settings.reliable_cv_percent,
                    "max_cv_percent": max(r.cv_percent for r in results),
                },
            )
        ]
    return []


def _temperatures(session: MachineExport) -> list[Finding]:
    temps = [
        t
        for r in session.results
        for t in (r.state_before.cpu_temp_c, r.state_after.cpu_temp_c)
        if t is not None
    ]
    if not temps:
        return []
    peak = max(temps)
    sensor = session.snapshot.sensors.cpu_sensor()
    threshold = sensor.high_c if sensor is not None else None
    params = {"max_c": peak, "threshold_c": threshold}
    if threshold is None:
        return [Finding(FindingCode.TEMPERATURE_MAX, Status.INFO, params)]
    if peak >= threshold:
        return [Finding(FindingCode.TEMPERATURE_REACHED, Status.CHECK, params)]
    return [Finding(FindingCode.TEMPERATURE_OK, Status.OK, params)]


def _multi_factors(session: MachineExport) -> list[Finding]:
    by_name = {r.name: r for r in session.results}
    cpu = session.snapshot.cpu
    findings = []
    for kind, single_name, multi_name in MULTI_PAIRS:
        single, multi = by_name.get(single_name), by_name.get(multi_name)
        if single is None or multi is None or single.unit != multi.unit or not single.value:
            continue
        findings.append(
            Finding(
                FindingCode.MULTI_FACTOR,
                Status.INFO,
                {
                    "kind": kind,
                    "backend": multi.backend,
                    "factor": multi.value / single.value,
                    "single_value": single.value,
                    "multi_value": multi.value,
                    "unit": multi.unit,
                    "workers": multi.workers,
                    "cores": cpu.physical_cores,
                    "threads": cpu.logical_cores,
                },
                [{"bench": single_name}, {"bench": multi_name}],
            )
        )
    return findings


def _context(session: MachineExport) -> list[Finding]:
    findings = []
    if session.combined is not None and session.combined.gpu_missing:
        # GPU incomplet (backend de la référence en échec ou absent) : on nomme ce qui manque
        gpu = next((c for c in session.categories if c.category is Category.GPU), None)
        missing = gpu.missing if gpu is not None else []
        params = {"missing": missing} if missing else {}
        findings.append(Finding(FindingCode.GPU_NOT_MEASURED, Status.INFO, params))
    snapshot = session.snapshot
    missing = [
        name
        for name, value in (
            ("ram_modules", snapshot.ram.modules_unavailable),
            ("smart", snapshot.disks.smart_unavailable),
        )
        if value is Unavailable.NEEDS_ROOT
    ]
    if missing:
        findings.append(Finding(FindingCode.NEEDS_ROOT, Status.INFO, {"missing": missing}))
    if session.reference is None:
        findings.append(Finding(FindingCode.NO_REFERENCE, Status.INFO))
    raw = [
        c.category.value
        for c in session.categories
        if c.category in (Category.MEMORY, Category.DISK) and c.issue is ScoreIssue.NOT_IN_REFERENCE
    ]
    if raw:
        findings.append(Finding(FindingCode.NOT_IN_REFERENCE, Status.INFO, {"categories": raw}))
    for r in session.results:
        if r.category is Category.DISK:
            findings.append(
                Finding(
                    FindingCode.DISK_CONTEXT,
                    Status.INFO,
                    {
                        "size": r.presentation,
                        "filesystem": r.environment.get("filesystem"),
                        "device": r.environment.get("device"),
                    },
                    [{"bench": r.name}],
                )
            )
    return findings


def analyze(session: MachineExport, settings: RunSettings | None = None) -> list[Finding]:
    """Constats de la session, du plus important au moins important (statut, puis règle)."""
    settings = settings or RunSettings()
    results = session.results
    findings = (
        _power(results, settings)
        + _per_bench_warnings(results, settings)
        + _temperatures(session)
        + _reproducible(results, settings)
        + _multi_factors(session)
        + _context(session)
    )
    # tri stable : l'ordre des règles départage les constats de même statut
    return sorted(findings, key=lambda f: STATUS_ORDER.index(f.status))
