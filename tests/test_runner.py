from collections.abc import Iterator

import pytest

from hwbench.benchmarks.base import Benchmark
from hwbench.machine_state import capture_state, cpu_temperature
from hwbench.models import SensorsData, TemperatureReading
from hwbench.results import BenchWarning, Category, MachineState, Measurement
from hwbench.runner import run_benchmark

COOL_AC = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=45.0)


class ScriptedBench(Benchmark):
    name = "scripted"
    category = Category.CPU_SINGLE
    backend = "test"
    version = "7"
    unit = "pts"
    detail_units = {"a": "MiB/s"}

    def __init__(self, values: list[float]) -> None:
        super().__init__()
        self._values: Iterator[float] = iter(values)
        self.calls = 0

    def run(self) -> Measurement:
        self.calls += 1
        v = next(self._values)
        return Measurement(value=v, duration_s=0.01, details={"a": v * 2})


def probe_sequence(*states: MachineState):
    it = iter(states)
    return lambda: next(it)


def test_warmup_excluded_median_and_stdev() -> None:
    bench = ScriptedBench([999.0, 100.0, 104.0, 102.0])
    result = run_benchmark(bench, runs=3, probe=lambda: COOL_AC)
    assert bench.calls == 4
    assert result.runs == [100.0, 104.0, 102.0]
    assert result.value == 102.0
    assert result.stdev == pytest.approx(2.0)
    assert result.details == {"a": 204.0}
    assert result.detail_units == {"a": "MiB/s"}
    assert (result.name, result.backend, result.version) == ("scripted", "test", "7")
    assert result.warmup_runs == 1
    assert result.warnings == []


def test_at_least_three_runs() -> None:
    with pytest.raises(ValueError):
        run_benchmark(ScriptedBench([1.0] * 3), runs=2, probe=lambda: COOL_AC)


def test_state_before_and_after() -> None:
    after = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=80.0)
    result = run_benchmark(ScriptedBench([1.0] * 4), probe=probe_sequence(COOL_AC, after))
    assert result.state_before.cpu_temp_c == 45.0
    assert result.state_after.cpu_temp_c == 80.0


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (MachineState([], on_ac=False, cpu_temp_c=40.0), [BenchWarning.ON_BATTERY]),
        (MachineState([], on_ac=True, cpu_temp_c=75.0), [BenchWarning.HOT_START]),
        (MachineState([], on_ac=None, cpu_temp_c=None), []),
    ],
)
def test_start_warnings(state: MachineState, expected: list[BenchWarning]) -> None:
    result = run_benchmark(ScriptedBench([1.0] * 4), probe=lambda: state)
    assert result.warnings == expected


def test_high_variance_warning() -> None:
    result = run_benchmark(ScriptedBench([0, 100.0, 80.0, 120.0]), probe=lambda: COOL_AC)
    assert BenchWarning.HIGH_VARIANCE in result.warnings
    assert result.cv_percent == pytest.approx(20.0)


def test_progress_callbacks() -> None:
    calls: list[tuple[str, int, int]] = []
    run_benchmark(
        ScriptedBench([1.0] * 5),
        runs=4,
        probe=lambda: COOL_AC,
        progress=lambda *a: calls.append(a),
    )
    assert calls == [("warmup", 1, 1)] + [("run", i, 4) for i in range(1, 5)]


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
    assert state == MachineState(governors=["performance"], on_ac=True, cpu_temp_c=68.0)
