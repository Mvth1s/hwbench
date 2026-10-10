"""Exécution fiable d'un benchmark : warm-up adaptatif, runs, médiane, écart-type, état."""

from collections.abc import Callable
from dataclasses import dataclass
from statistics import median, stdev
from time import perf_counter
from time import sleep as real_sleep

from hwbench.benchmarks.base import Benchmark
from hwbench.machine_state import capture_state
from hwbench.results import BenchWarning, Category, CooldownOutcome, MachineState, Result

MIN_RUNS = 3

# Plafond du warm-up : le multi-cœur chauffe plus lentement (et plus fort) que le single-core.
DEFAULT_MAX_WARMUP_S = {
    Category.CPU_SINGLE: 30.0,
    Category.CPU_MULTI: 90.0,
    Category.GPU: 90.0,
    Category.MEMORY: 30.0,
    Category.DISK: 60.0,  # un run fio dure ~10 s (4 tests de 2 s)
}


@dataclass(frozen=True)
class RunSettings:
    runs: int = MIN_RUNS
    max_warmup_s: float | None = None  # None = plafond par défaut de la catégorie
    warmup_tolerance_percent: float = 3.0
    high_variance_cv_percent: float = 5.0
    hot_start_c: float = 70.0
    reliable_cv_percent: float = 1.0  # rapport : « très reproductible » sous ce CV
    # Pause entre catégories (--cooldown) : durée fixe, ou (auto) attente que la température CPU
    # passe sous hot_start_c, avant chaque catégorie, dans la limite de cooldown_timeout_s.
    cooldown_s: float = 0.0
    cooldown_auto: bool = False
    cooldown_timeout_s: float = 300.0
    # auto : arrêt si la température a baissé de moins de cooldown_stall_delta_c sur les
    # cooldown_stall_s dernières secondes (repos au-dessus du seuil) ; 0 s désactive
    cooldown_stall_s: float = 30.0
    cooldown_stall_delta_c: float = 1.0

    def __post_init__(self) -> None:
        if self.runs < MIN_RUNS:
            raise ValueError(f"au moins {MIN_RUNS} runs sont nécessaires (reçu {self.runs})")
        if self.max_warmup_s is not None and self.max_warmup_s < 0:
            raise ValueError("le plafond de warm-up ne peut pas être négatif")
        durations = (self.cooldown_s, self.cooldown_timeout_s, self.cooldown_stall_s)
        if min(durations) < 0 or self.cooldown_stall_delta_c < 0:
            raise ValueError("une durée de refroidissement ne peut pas être négative")
        if self.cooldown_auto and self.cooldown_s:
            raise ValueError("refroidissement : durée fixe ou auto, pas les deux")

    @property
    def cooldown_enabled(self) -> bool:
        return self.cooldown_auto or self.cooldown_s > 0

    def warmup_cap(self, category: Category) -> float:
        if self.max_warmup_s is not None:
            return self.max_warmup_s
        return DEFAULT_MAX_WARMUP_S[category]


Probe = Callable[[], MachineState]
Sleep = Callable[[float], None]
# (phase « warmup » ou « run », index 1-based, total ; None pendant le warm-up adaptatif)
Progress = Callable[[str, int, int | None], None]
Clock = Callable[[], float]


COOLDOWN_POLL_S = 2.0  # mode auto : intervalle entre deux relevés de température


@dataclass(frozen=True)
class Cooldown:
    waited_s: float
    outcome: CooldownOutcome
    start_c: float | None = None
    end_c: float | None = None


# (secondes écoulées, température relevée ou None en pause fixe)
CooldownProgress = Callable[[float, float | None], None]


def cool_down(
    settings: RunSettings,
    probe: Probe = capture_state,
    progress: CooldownProgress | None = None,
    sleep: Sleep = real_sleep,
    clock: Clock = perf_counter,
) -> Cooldown:
    """Pause avant une catégorie : durée fixe (cooldown_s), ou attente que la température CPU
    passe sous hot_start_c (cooldown_auto), relevée toutes les COOLDOWN_POLL_S secondes,
    au plus cooldown_timeout_s, et arrêtée plus tôt si elle ne baisse plus (moins de
    cooldown_stall_delta_c sur cooldown_stall_s)."""
    start = clock()
    if not settings.cooldown_auto:
        while (elapsed := clock() - start) < settings.cooldown_s:
            if progress:
                progress(elapsed, None)
            sleep(min(1.0, settings.cooldown_s - elapsed))
        return Cooldown(clock() - start, CooldownOutcome.FIXED)

    first = temp = probe().cpu_temp_c
    if temp is None:
        return Cooldown(0.0, CooldownOutcome.NO_SENSOR)
    if temp < settings.hot_start_c:
        return Cooldown(0.0, CooldownOutcome.ALREADY_COOL, first, temp)
    readings = [(0.0, temp)]  # (secondes écoulées, température)
    while True:
        elapsed = clock() - start
        if elapsed >= settings.cooldown_timeout_s:
            return Cooldown(elapsed, CooldownOutcome.TIMEOUT, first, temp)
        if progress:
            progress(elapsed, temp)
        sleep(min(COOLDOWN_POLL_S, settings.cooldown_timeout_s - elapsed))
        reading = probe().cpu_temp_c
        if reading is None:  # capteur perdu en route : on s'arrête là
            return Cooldown(clock() - start, CooldownOutcome.NO_SENSOR, first, temp)
        temp = reading
        now = clock() - start
        if temp < settings.hot_start_c:
            return Cooldown(now, CooldownOutcome.COOLED, first, temp)
        readings.append((now, temp))
        if _stalled(readings, settings):
            return Cooldown(now, CooldownOutcome.STALLED, first, temp)


def _stalled(readings: list[tuple[float, float]], settings: RunSettings) -> bool:
    """Baisse de moins de cooldown_stall_delta_c depuis le relevé d'il y a au moins
    cooldown_stall_s secondes (le plus récent d'entre eux)."""
    if settings.cooldown_stall_s <= 0:
        return False
    now, temp = readings[-1]
    past = [t for at, t in readings if now - at >= settings.cooldown_stall_s]
    return bool(past) and past[-1] - temp < settings.cooldown_stall_delta_c


def start_warnings(
    state: MachineState,
    settings: RunSettings | None = None,
    cooldown_outcome: CooldownOutcome | None = None,
) -> list[BenchWarning]:
    """Avertissements de l'état de départ. Au-dessus du seuil chaud après une attente arrêtée
    sur stagnation (STALLED), le CPU est à sa température de repos : HOT_IDLE (information),
    pas HOT_START (« laissez refroidir »)."""
    settings = settings or RunSettings()
    warnings: list[BenchWarning] = []
    if state.on_ac is False:
        warnings.append(BenchWarning.ON_BATTERY)
    if state.throttling_settings():
        warnings.append(BenchWarning.POWER_PROFILE)
    if state.cpu_temp_c is not None and state.cpu_temp_c >= settings.hot_start_c:
        idle = cooldown_outcome is CooldownOutcome.STALLED
        warnings.append(BenchWarning.HOT_IDLE if idle else BenchWarning.HOT_START)
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
    cooldown_s: float = 0.0,
    cooldown_outcome: CooldownOutcome | None = None,
) -> Result:
    """cooldown_s, cooldown_outcome : pause de refroidissement effective juste avant ce bench
    et son issue (cool_down), None sans attente."""
    settings = settings or RunSettings()
    before = probe()
    start = clock()
    # cleanup() quoi qu'il arrive (erreur, Ctrl+C) : le bench disque supprime son fichier
    try:
        burst, warmup_runs, stable = _warmup(bench, settings, progress, clock)
        warmup_s = clock() - start
        measurements = []
        for i in range(settings.runs):
            if progress:
                progress("run", i + 1, settings.runs)
            measurements.append(bench.run())
    finally:
        bench.cleanup()
    duration = clock() - start
    after = probe()

    values = [m.value for m in measurements]
    value = median(values)
    spread = stdev(values)
    warnings = start_warnings(before, settings, cooldown_outcome) + bench.warnings()
    if not stable:
        warnings.append(BenchWarning.WARMUP_UNSTABLE)
    if value and 100.0 * spread / value > settings.high_variance_cv_percent:
        warnings.append(BenchWarning.HIGH_VARIANCE)

    return Result(
        name=bench.name,
        category=bench.category,
        backend=bench.backend,
        version=bench.version,
        tool_version=bench.tool_version(),
        presentation=bench.presentation(),
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
        cooldown_s=cooldown_s,
        cooldown_outcome=cooldown_outcome,
    )
