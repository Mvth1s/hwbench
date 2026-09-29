"""Exécution fiable d'un benchmark : warm-up, N runs, médiane, écart-type, état machine."""

from collections.abc import Callable
from statistics import median, stdev
from time import perf_counter

from hwbench.benchmarks.base import Benchmark
from hwbench.machine_state import HOT_START_C, capture_state
from hwbench.results import BenchWarning, MachineState, Result

MIN_RUNS = 3
WARMUP_RUNS = 1
HIGH_VARIANCE_CV_PERCENT = 5.0

Probe = Callable[[], MachineState]
# (phase « warmup » ou « run », index 1-based, total)
Progress = Callable[[str, int, int], None]


def start_warnings(state: MachineState) -> list[BenchWarning]:
    warnings: list[BenchWarning] = []
    if state.on_ac is False:
        warnings.append(BenchWarning.ON_BATTERY)
    if state.cpu_temp_c is not None and state.cpu_temp_c >= HOT_START_C:
        warnings.append(BenchWarning.HOT_START)
    return warnings


def run_benchmark(
    bench: Benchmark,
    runs: int = MIN_RUNS,
    warmup: int = WARMUP_RUNS,
    probe: Probe = capture_state,
    progress: Progress | None = None,
) -> Result:
    if runs < MIN_RUNS:
        raise ValueError(f"au moins {MIN_RUNS} runs sont nécessaires (reçu {runs})")

    before = probe()
    start = perf_counter()
    for i in range(warmup):
        if progress:
            progress("warmup", i + 1, warmup)
        bench.run()
    measurements = []
    for i in range(runs):
        if progress:
            progress("run", i + 1, runs)
        measurements.append(bench.run())
    duration = perf_counter() - start
    after = probe()

    values = [m.value for m in measurements]
    value = median(values)
    spread = stdev(values)
    warnings = start_warnings(before)
    if value and 100.0 * spread / value > HIGH_VARIANCE_CV_PERCENT:
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
        warmup_runs=warmup,
        duration_s=duration,
        details={k: median(m.details[k] for m in measurements) for k in measurements[0].details},
        detail_units=dict(bench.detail_units),
        workers=bench.workers,
        environment=bench.environment(),
        state_before=before,
        state_after=after,
        warnings=warnings,
    )
