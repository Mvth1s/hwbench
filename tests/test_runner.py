from collections.abc import Iterator

import pytest
from conftest import laptop_commands, laptop_sysfs, sysfs_fixture

from hwbench.benchmarks.base import Benchmark
from hwbench.machine_state import capture_state, cpu_temperature
from hwbench.models import SensorsData, TemperatureReading
from hwbench.reference import ReferenceIssue, state_issues
from hwbench.results import BenchWarning, Category, MachineState, Measurement, Result
from hwbench.runner import (
    COOLDOWN_POLL_S,
    Cooldown,
    CooldownOutcome,
    RunSettings,
    cool_down,
    run_benchmark,
    start_warnings,
)

COOL_AC = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=45.0)


class ScriptedBench(Benchmark):
    """Renvoie des valeurs scriptées ; chaque run fait avancer une horloge simulée."""

    name = "scripted"
    category = Category.CPU_SINGLE
    backend = "test"
    version = "7"
    unit = "index"
    detail_units = {"a": "MiB/s"}

    def __init__(self, values: list[float], run_s: float = 1.0) -> None:
        super().__init__()
        self._values: Iterator[float] = iter(values)
        self.run_s = run_s
        self.now = 0.0
        self.calls = 0

    def clock(self) -> float:
        return self.now

    def cleanup(self) -> None:
        self.cleaned = getattr(self, "cleaned", 0) + 1

    def run(self) -> Measurement:
        self.calls += 1
        self.now += self.run_s
        v = next(self._values)
        return Measurement(value=v, duration_s=self.run_s, details={"a": v * 2})


def run(bench: ScriptedBench, probe=lambda: COOL_AC, **settings) -> Result:
    return run_benchmark(bench, RunSettings(**settings), probe=probe, clock=bench.clock)


def probe_sequence(*states: MachineState):
    it = iter(states)
    return lambda: next(it)


def test_warmup_excluded_median_and_stdev() -> None:
    # à froid 120, puis 100 et 101 (écart < 3 %) : stable après 3 itérations
    bench = ScriptedBench([120.0, 100.0, 101.0, 100.0, 104.0, 102.0])
    result = run(bench)
    assert bench.calls == 6
    assert result.runs == [100.0, 104.0, 102.0]
    assert result.value == 102.0
    assert result.stdev == pytest.approx(2.0)
    assert result.details == {"a": 204.0}
    assert result.detail_units == {"a": "MiB/s"}
    assert (result.name, result.backend, result.version) == ("scripted", "test", "7")
    assert (result.warmup_runs, result.warmup_s, result.warmup_stable) == (3, 3.0, True)
    assert result.duration_s == 6.0
    assert result.warnings == []


def test_burst_is_the_cold_run_and_not_the_score() -> None:
    result = run(ScriptedBench([150.0, 100.0, 100.0, 100.0, 100.0, 100.0]))
    assert result.burst == 150.0
    assert result.value == 100.0
    assert 150.0 not in result.runs


def test_cold_run_counts_toward_stability() -> None:
    bench = ScriptedBench([100.0, 102.0] + [100.0] * 3)
    result = run(bench)
    assert (result.warmup_runs, result.warmup_stable, result.burst) == (2, True, 100.0)


def test_warmup_keeps_going_while_throttling() -> None:
    # chute de 5 % par itération : jamais 2 consécutives à moins de 3 %, jusqu'à 90 -> 90
    throttling = [100.0, 95.0, 90.0, 90.0] + [90.0] * 3
    result = run(ScriptedBench(throttling))
    assert result.warmup_runs == 4 and result.warmup_stable


def test_warmup_cap_reached_without_stability_warns() -> None:
    values = [100.0, 80.0] * 10 + [90.0] * 3
    result = run(ScriptedBench(values, run_s=10.0), max_warmup_s=35.0)
    # itérations lancées à t = 0, 10, 20, 30 ; à 40 s le plafond de 35 s est dépassé
    assert (result.warmup_runs, result.warmup_s, result.warmup_stable) == (4, 40.0, False)
    assert BenchWarning.WARMUP_UNSTABLE in result.warnings
    assert result.runs == [100.0, 80.0, 100.0]


def test_zero_cap_only_cold_run() -> None:
    result = run(ScriptedBench([100.0] * 4), max_warmup_s=0)
    assert (result.warmup_runs, result.warmup_stable) == (1, False)


def test_default_caps_per_category() -> None:
    settings = RunSettings()
    assert settings.warmup_cap(Category.CPU_SINGLE) == 30.0
    assert settings.warmup_cap(Category.CPU_MULTI) == 90.0
    assert RunSettings(max_warmup_s=12).warmup_cap(Category.CPU_MULTI) == 12
    assert settings.warmup_cap(Category.MEMORY) == 30.0
    assert settings.warmup_cap(Category.DISK) == 60.0


def test_cleanup_once_after_the_runs() -> None:
    bench = ScriptedBench([10.0] * 10)
    run(bench)
    assert bench.cleaned == 1


@pytest.mark.parametrize("error", [RuntimeError("outil en échec"), KeyboardInterrupt()])
def test_cleanup_even_on_error_or_interrupt(error: BaseException) -> None:
    class Failing(ScriptedBench):
        def run(self) -> Measurement:
            if self.calls == 2:
                raise error
            return super().run()

    bench = Failing([10.0] * 10)
    with pytest.raises(type(error)):
        run(bench)
    assert bench.cleaned == 1


def test_single_core_cap_applies() -> None:
    values = [100.0, 80.0] * 20
    result = run(ScriptedBench(values, run_s=10.0))
    assert result.warmup_runs == 3 and not result.warmup_stable  # 0, 10, 20 < 30 s


def test_warmup_tolerance_is_configurable() -> None:
    values = [100.0, 95.0] + [95.0] * 3
    assert run(ScriptedBench(values), warmup_tolerance_percent=6.0).warmup_runs == 2
    values = [100.0, 95.0, 95.0] + [95.0] * 3
    assert run(ScriptedBench(values), warmup_tolerance_percent=3.0).warmup_runs == 3


def test_at_least_three_runs() -> None:
    with pytest.raises(ValueError):
        RunSettings(runs=2)
    with pytest.raises(ValueError):
        RunSettings(max_warmup_s=-1)


def test_state_before_and_after() -> None:
    after = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=80.0)
    result = run(ScriptedBench([1.0] * 5), probe=probe_sequence(COOL_AC, after))
    assert result.state_before.cpu_temp_c == 45.0
    assert result.state_after.cpu_temp_c == 80.0


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MachineState([], on_ac=False, cpu_temp_c=40.0), [BenchWarning.ON_BATTERY]),
        (MachineState([], on_ac=True, cpu_temp_c=75.0), [BenchWarning.HOT_START]),
        (MachineState([], on_ac=None, cpu_temp_c=None), []),
        (
            MachineState([], True, 40.0, platform_profile="balanced"),
            [BenchWarning.POWER_PROFILE],
        ),
        (
            MachineState([], True, 40.0, energy_performance_preference="balance_power"),
            [BenchWarning.POWER_PROFILE],
        ),
    ],
)
def test_start_warnings(state: MachineState, expected: list[BenchWarning]) -> None:
    result = run(ScriptedBench([1.0] * 5), probe=lambda: state)
    assert result.warnings == expected


def test_hot_start_threshold_is_configurable() -> None:
    warm = MachineState([], on_ac=True, cpu_temp_c=65.0)
    assert start_warnings(warm) == []
    assert start_warnings(warm, RunSettings(hot_start_c=60.0)) == [BenchWarning.HOT_START]


def test_high_variance_warning() -> None:
    result = run(ScriptedBench([100.0, 100.0, 100.0, 80.0, 120.0]))
    assert BenchWarning.HIGH_VARIANCE in result.warnings
    assert result.cv_percent == pytest.approx(20.0)


def test_high_variance_threshold_is_configurable() -> None:
    values = [100.0, 100.0, 100.0, 96.0, 104.0]  # CV 4 %
    assert BenchWarning.HIGH_VARIANCE not in run(ScriptedBench(values)).warnings
    tight = run(ScriptedBench(values), high_variance_cv_percent=3.0)
    assert BenchWarning.HIGH_VARIANCE in tight.warnings


def test_progress_callbacks() -> None:
    calls: list[tuple[str, int, int | None]] = []
    bench = ScriptedBench([1.0] * 6)
    run_benchmark(
        bench,
        RunSettings(runs=4),
        probe=lambda: COOL_AC,
        progress=lambda *a: calls.append(a),
        clock=bench.clock,
    )
    assert calls == [("warmup", 1, None), ("warmup", 2, None)] + [
        ("run", i, 4) for i in range(1, 5)
    ]


@pytest.mark.parametrize(
    ("profile", "choices", "epp", "issues"),
    [
        ("performance", [], "performance", []),
        (None, [], None, []),
        ("balanced", ["quiet", "balanced", "performance"], None, ["platform_profile"]),
        # pas de « performance » sur cette machine : le plus performant proposé suffit
        ("balanced-performance", ["low-power", "balanced", "balanced-performance"], None, []),
        ("balanced", ["low-power", "balanced", "balanced-performance"], None, ["platform_profile"]),
        ("custom", ["custom", "performance"], None, []),
        (None, [], "balance_performance", ["energy_performance_preference"]),
        ("quiet", [], "default", ["platform_profile", "energy_performance_preference"]),
    ],
)
def test_throttling_settings(
    profile: str | None, choices: list[str], epp: str | None, issues: list[str]
) -> None:
    state = MachineState([], True, 40.0, profile, choices, epp)
    assert state.throttling_settings() == issues


def _temp(chip: str, label: str, value: float) -> TemperatureReading:
    return TemperatureReading(chip, label, value, None, None)


@pytest.mark.parametrize(
    ("readings", "expected"),
    [
        ([_temp("nvme", "Composite", 40), _temp("coretemp", "Package id 0", 55)], 55.0),
        ([_temp("coretemp", "Core 0", 60), _temp("coretemp", "Package id 0", 58)], 58.0),
        ([_temp("k10temp", "Tctl", 70), _temp("k10temp", "Tdie", 60)], 60.0),
        ([_temp("k10temp", "Tctl", 70)], 70.0),
        ([_temp("cpu_thermal", "temp1", 51)], 51.0),
        ([_temp("acpitz", "temp1", 30), _temp("nvme", "Composite", 40)], None),
    ],
)
def test_cpu_temperature(readings: list[TemperatureReading], expected: float | None) -> None:
    assert cpu_temperature(SensorsData(temperatures=readings)) == expected


def test_capture_state_on_real_laptop_fixture(laptop) -> None:
    laptop()
    state = capture_state()
    assert state == MachineState(
        governors=["performance"], on_ac=True, cpu_temp_c=68.0, has_battery=True
    )


def test_desktop_state_is_on_ac_without_battery(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"))
    state = capture_state()
    assert (state.on_ac, state.has_battery) == (True, False)
    assert ReferenceIssue.POWER_UNKNOWN not in state_issues(state)
    assert ReferenceIssue.NOT_ON_AC not in state_issues(state)


def test_capture_state_reads_profile_and_epp(laptop_with_profile) -> None:
    state = capture_state()
    assert state.platform_profile == "quiet"
    assert state.platform_profile_choices == ["quiet", "balanced", "performance"]
    assert state.energy_performance_preference == "balance_power"
    assert state.throttling_settings() == ["platform_profile", "energy_performance_preference"]


@pytest.fixture
def laptop_with_profile(fake_system):
    files = laptop_sysfs() | {
        "/sys/firmware/acpi/platform_profile": "quiet",
        "/sys/firmware/acpi/platform_profile_choices": "quiet balanced performance",
        "/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference": "balance_power",
    }
    return fake_system(files=files, commands=laptop_commands())


# --- Refroidissement entre catégories (--cooldown) : horloge simulée, jamais de vrai temps ---


class FakeTime:
    """Horloge et sommeil simulés ; températures relevées tour à tour (la dernière répétée)."""

    def __init__(self, temps: list[float | None]) -> None:
        self.now = 0.0
        self.temps = list(temps)
        self.sleeps: list[float] = []
        self.progress: list[tuple[float, float | None]] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def probe(self) -> MachineState:
        temp = self.temps.pop(0) if len(self.temps) > 1 else self.temps[0]
        return MachineState(["performance"], on_ac=True, cpu_temp_c=temp)

    def cool_down(self, **settings) -> Cooldown:
        return cool_down(
            RunSettings(**settings),
            probe=self.probe,
            progress=lambda elapsed, temp: self.progress.append((elapsed, temp)),
            sleep=self.sleep,
            clock=self.clock,
        )


def test_fixed_cooldown_sleeps_the_requested_time() -> None:
    t = FakeTime([90.0])
    assert t.cool_down(cooldown_s=2.5) == Cooldown(2.5, CooldownOutcome.FIXED)
    assert t.sleeps == [1.0, 1.0, 0.5]  # par tranches, pour l'affichage et Ctrl+C
    assert [p[0] for p in t.progress] == [0.0, 1.0, 2.0]


def test_auto_cooldown_does_not_wait_when_already_cool() -> None:
    t = FakeTime([55.0])
    assert t.cool_down(cooldown_auto=True) == Cooldown(
        0.0, CooldownOutcome.ALREADY_COOL, 55.0, 55.0
    )
    assert t.sleeps == []


def test_auto_cooldown_waits_until_below_the_hot_start_threshold() -> None:
    t = FakeTime([85.0, 78.0, 70.0, 69.5])  # 70 °C n'est pas sous le seuil de 70 °C
    result = t.cool_down(cooldown_auto=True)
    assert result == Cooldown(3 * COOLDOWN_POLL_S, CooldownOutcome.COOLED, 85.0, 69.5)
    assert t.progress == [(0.0, 85.0), (2.0, 78.0), (4.0, 70.0)]


def test_auto_cooldown_follows_the_hot_start_option() -> None:
    t = FakeTime([65.0, 59.0])
    assert t.cool_down(cooldown_auto=True, hot_start_c=60.0).outcome is CooldownOutcome.COOLED


def test_auto_cooldown_stops_at_the_timeout() -> None:
    t = FakeTime([90.0, 88.0])
    result = t.cool_down(cooldown_auto=True, cooldown_timeout_s=5.0)
    assert result == Cooldown(5.0, CooldownOutcome.TIMEOUT, 90.0, 88.0)
    assert t.sleeps == [2.0, 2.0, 1.0]  # le dernier sommeil s'arrête au délai


@pytest.mark.parametrize(
    ("temps", "expected"),
    [
        ([None], Cooldown(0.0, CooldownOutcome.NO_SENSOR)),
        ([85.0, None], Cooldown(COOLDOWN_POLL_S, CooldownOutcome.NO_SENSOR, 85.0, 85.0)),
    ],
)
def test_auto_cooldown_without_sensor_does_not_wait(temps, expected) -> None:
    assert FakeTime(temps).cool_down(cooldown_auto=True) == expected


@pytest.mark.parametrize(
    "settings",
    [
        dict(cooldown_s=-1.0),
        dict(cooldown_timeout_s=-1.0),
        dict(cooldown_s=30.0, cooldown_auto=True),
    ],
)
def test_invalid_cooldown_settings(settings) -> None:
    with pytest.raises(ValueError):
        RunSettings(**settings)


def test_cooldown_is_recorded_in_the_result() -> None:
    def run(**kwargs) -> Result:
        bench = ScriptedBench([10.0] * 20)
        return run_benchmark(
            bench, RunSettings(), probe=lambda: COOL_AC, clock=bench.clock, **kwargs
        )

    assert run(cooldown_s=42.0).cooldown_s == 42.0
    assert run().cooldown_s == 0.0
