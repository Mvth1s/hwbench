import pytest
from conftest import TINY
from rich.console import Console
from typer.testing import CliRunner

from hwbench import cli
from hwbench.benchmarks.native import cpu
from hwbench.display.bench import render_result
from hwbench.results import BenchWarning, Category, MachineState, Result

runner = CliRunner()
WIDE = {"COLUMNS": "200"}
COOL_AC = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=45.0)


@pytest.fixture(autouse=True)
def fast_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpu, "WORKLOADS", TINY)
    monkeypatch.setattr(cli, "capture_state", lambda: COOL_AC)


def test_bench_single_core() -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "CPU single-core · native v1" in result.output
    assert "Score (médiane)" in result.output
    assert "SHA-256" in result.output and "Mio/s" in result.output
    assert "multi-core" not in result.output


def test_bench_all_with_workers() -> None:
    result = runner.invoke(
        cli.app, ["bench", "all", "--backend", "native", "--workers", "2", "--runs", "3"], env=WIDE
    )
    assert result.exit_code == 0, result.output
    assert "CPU single-core · native v1" in result.output
    assert "CPU multi-core · native v1" in result.output
    assert "Processus        2" in result.output
    assert "GPU : le backend « native » ne couvre pas cette catégorie." in result.output


def test_runs_below_three_is_rejected() -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--runs", "2"])
    assert result.exit_code == 2


def test_unknown_backend() -> None:
    result = runner.invoke(cli.app, ["bench", "--backend", "geekbench"])
    assert result.exit_code == 2
    assert "inconnu" in result.output and "native" in result.output


def test_gpu_without_backend_fails() -> None:
    result = runner.invoke(cli.app, ["bench", "gpu"], env=WIDE)
    assert result.exit_code == 1
    assert "GPU : aucun backend disponible." in result.output


def test_warns_upfront_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    hot_battery = MachineState(governors=["powersave"], on_ac=False, cpu_temp_c=82.0)
    monkeypatch.setattr(cli, "capture_state", lambda: hot_battery)
    result = runner.invoke(cli.app, ["bench", "cpu-single"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "Machine sur batterie" in result.output
    assert "CPU déjà chaud au départ (82 °C)" in result.output
    assert "Score (médiane)" in result.output


def _result(**overrides) -> Result:
    base = dict(
        name="native-cpu-single",
        category=Category.CPU_SINGLE,
        backend="native",
        version="1",
        unit="pts",
        higher_is_better=True,
        value=89.84,
        stdev=0.45,
        runs=[89.84, 90.21, 89.3],
        warmup_runs=1,
        duration_s=6.93,
        details={"sha256": 1624.23, "powmod": 42.31},
        detail_units={"sha256": "MiB/s", "powmod": "op/s"},
        workers=None,
        environment={"python": "CPython 3.14.7", "zlib": "1.3.1.zlib-ng"},
        state_before=COOL_AC,
        state_after=MachineState(["performance"], on_ac=False, cpu_temp_c=71.4),
        warnings=[],
    )
    return Result(**(base | overrides))


def _text(result: Result) -> str:
    console = Console(width=200, record=True)
    console.print(render_result(result))
    return console.export_text()


def test_render_result_french_formatting() -> None:
    out = _text(_result())
    assert "89,8 pts" in out and "± 0,5 (CV 0,5 %)" in out
    assert "89,8 · 90,2 · 89,3" in out and "6,9 s au total" in out
    assert "1624,2 Mio/s" in out and "42,3 op/s" in out
    assert "45 °C avant → 71 °C après" in out
    assert "secteur → batterie" in out
    assert "CPython 3.14.7 · zlib 1.3.1.zlib-ng" in out
    assert "Processus" not in out


def test_render_result_warnings() -> None:
    out = _text(_result(stdev=18.0, warnings=[BenchWarning.HOT_START, BenchWarning.HIGH_VARIANCE]))
    assert "CPU déjà chaud au départ (45 °C)" in out
    assert "Mesures instables (CV 20,0 %)" in out
