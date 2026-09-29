"""Exécution fiable d'un benchmark : warm-up adaptatif, runs, médiane, écart-type, état."""

from collections.abc import Callable
from dataclasses import dataclass
from statistics import median, stdev
from time import perf_counter

from hwbench.benchmarks.base import Benchmark
from hwbench.machine_state import capture_state
from hwbench.results import BenchWarning, Category, MachineState, Result

MIN_RUNS = 3

# Plafond du warm-up : le multi-cœur chauffe plus lentement (et plus fort) que le single-core.
DEFAULT_MAX_WARMUP_S = {
    Category.CPU_SINGLE: 30.0,
    Category.CPU_MULTI: 90.0,
    Category.GPU: 90.0,
}


@dataclass(frozen=True)
class RunSettings:
    runs: int = MIN_RUNS
    max_warmup_s: float | None = None  # None = plafond par défaut de la catégorie
    warmup_tolerance_percent: float = 3.0
    high_variance_cv_percent: float = 5.0
    hot_start_c: float = 70.0

    def __post_init__(self) -> None:
        if self.runs < MIN_RUNS:
            raise ValueError(f"au moins {MIN_RUNS} runs sont nécessaires (reçu {self.runs})")
        if self.max_warmup_s is not None and self.max_warmup_s < 0:
            raise ValueError("le plafond de warm-up ne peut pas être négatif")

    def warmup_cap(self, category: Category) -> float:
        if self.max_warmup_s is not None:
            return self.max_warmup_s
        return DEFAULT_MAX_WARMUP_S[category]


Probe = Callable[[], MachineState]
# (phase « warmup » ou « run », index 1-based, total ; None pendant le warm-up adaptatif)
Progress = Callable[[str, int, int | None], None]
Clock = Callable[[], float]


def start_warnings(state: MachineState, settings: RunSettings | None = None) -> list[BenchWarning]:
    settings = settings or RunSettings()
    warnings: list[BenchWarning] = []
    if state.on_ac is False:
        warnings.append(BenchWarning.ON_BATTERY)
    if state.throttling_settings():
        warnings.append(BenchWarning.POWER_PROFILE)
    if state.cpu_temp_c is not None and state.cpu_temp_c >= settings.hot_start_c:
        warnings.append(BenchWarning.HOT_START)
    return warnings


def _close(a: float, b: float, tolerance_percent: float) -> bool:
    scale = max(abs(a), abs(b))
    return scale == 0 or 100.0 * abs(a - b) / scale <= tolerance_percent


def _warmup(
    bench: Benchmark, settings: RunSettings, progress: Progress | None, clock: Clock
) -> tuple[float, int, bool]:
    """Enchaîne les itérations jusqu'à 2 consécutives dans la tolérance, ou jusqu'au plafond.

    Renvoie (valeur du premier run à froid, nombre d'itérations, stabilisé).
    """
    cap = settings.warmup_cap(bench.category)
    start = clock()
    if progress:
        progress("warmup", 1, None)
    burst = previous = bench.run().value
    count = 1
    while clock() - start < cap:
        count += 1
        if progress:
            progress("warmup", count, None)
        value = bench.run().value
        if _close(previous, value, settings.warmup_tolerance_percent):
            return burst, count, True
        previous = value
    return burst, count, False


def run_benchmark(
    bench: Benchmark,
    settings: RunSettings | None = None,
    probe: Probe = capture_state,
    progress: Progress | None = None,
    clock: Clock = perf_counter,
) -> Result:
    settings = settings or RunSettings()
    before = probe()
    start = clock()
    burst, warmup_runs, stable = _warmup(bench, settings, progress, clock)
    warmup_s = clock() - start
    measurements = []
    for i in range(settings.runs):
        if progress:
            progress("run", i + 1, settings.runs)
        measurements.append(bench.run())
    duration = clock() - start
    after = probe()

    values = [m.value for m in measurements]
    value = median(values)
    spread = stdev(values)
    warnings = start_warnings(before, settings)
    if not stable:
        warnings.append(BenchWarning.WARMUP_UNSTABLE)
    if value and 100.0 * spread / value > settings.high_variance_cv_percent:
        warnings.append(BenchWarning.HIGH_VARIANCE)

    return Result(
        name=bench.name,
        category=bench.category,
        backend=bench.backend,
        version=bench.version,
        unit=bench.unit,
        higher_is_better=bench.higher_is_better,
        value=value,
        stdev=spread,
        runs=values,
        warmup_runs=warmup_runs,
        warmup_s=warmup_s,
        warmup_stable=stable,
        burst=burst,
        duration_s=duration,
        details={k: median(m.details[k] for m in measurements) for k in measurements[0].details},
        detail_units=dict(bench.detail_units),
        workers=bench.workers,
        environment=bench.environment(),
        state_before=before,
        state_after=after,
        warnings=warnings,
    )
