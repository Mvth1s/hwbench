import re

import pytest
from conftest import TINY
from rich.console import Console
from typer.testing import CliRunner

from hwbench import cli
from hwbench import runner as bench_runner
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
    # charges minuscules et bruitées : plafond de warm-up court pour garder les tests rapides
    monkeypatch.setattr(bench_runner, "DEFAULT_MAX_WARMUP_S", dict.fromkeys(Category, 0.2))


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
    assert re.search(r"Processus +2 ", result.output)
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
    assert "GPU · glmark2 : indisponible (outil absent), ignoré." in result.output
    assert "GPU · vkmark : indisponible (outil absent), ignoré." in result.output


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
        tool_version=None,
        presentation=None,
        unit="index",
        higher_is_better=True,
        value=89.84,
        stdev=0.45,
        runs=[89.84, 90.21, 89.3],
        warmup_runs=4,
        warmup_s=8.2,
        warmup_stable=True,
        burst=95.12,
        duration_s=15.13,
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
    assert "89,8 indice brut" in out and "± 0,5 (CV 0,5 %)" in out
    assert "pts" not in out
    assert "89,8 · 90,2 · 89,3" in out
    assert "4 itérations, 8,2 s · 15,1 s au total" in out and "non stabilisé" not in out
    assert "95,1 indice brut  (hors score)" in out
    assert "1624,2 Mio/s" in out and "42,3 op/s" in out
    assert "45 °C avant → 71 °C après" in out
    assert "secteur → batterie" in out
    assert "CPython 3.14.7 · zlib 1.3.1.zlib-ng" in out
    assert "Processus" not in out


def test_render_result_warnings() -> None:
    out = _text(_result(stdev=18.0, warnings=[BenchWarning.HOT_START, BenchWarning.HIGH_VARIANCE]))
    assert "CPU déjà chaud au départ (45 °C)" in out
    assert "Mesures instables (CV 20,0 %)" in out


def test_render_unstable_warmup() -> None:
    out = _text(
        _result(warmup_stable=False, warmup_s=91.4, warnings=[BenchWarning.WARMUP_UNSTABLE])
    )
    assert "8,2 s" not in out and "91,4 s (non stabilisé)" in out
    assert "Warm-up non stabilisé après 91 s" in out and "--max-warmup" in out


def test_render_desktop_power() -> None:
    desktop = MachineState(["performance"], on_ac=True, cpu_temp_c=40.0, has_battery=False)
    out = _text(_result(state_before=desktop, state_after=desktop))
    assert re.search(r"Alimentation +secteur \(pas de batterie\)", out)


def test_render_power_profile_and_epp() -> None:
    state = MachineState(
        ["powersave"],
        on_ac=True,
        cpu_temp_c=45.0,
        platform_profile="balanced",
        platform_profile_choices=["quiet", "balanced", "performance"],
        energy_performance_preference="balance_power",
    )
    out = _text(_result(state_before=state, warnings=[BenchWarning.POWER_PROFILE]))
    assert re.search(r"Profil plateforme +balanced", out)
    assert re.search(r"EPP +balance_power", out)
    assert "profil plateforme « balanced », EPP « balance_power »" in out
    assert re.search(r"EPP +non disponible", _text(_result()))


def test_bench_options_reach_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    real = cli.run_benchmark

    def spy(bench, settings, **kwargs):
        seen.append(settings)
        return real(bench, settings, **kwargs)

    monkeypatch.setattr(cli, "run_benchmark", spy)
    args = ["bench", "cpu-single", "--max-warmup", "0", "--max-cv", "8", "--hot-start", "60"]
    result = runner.invoke(cli.app, [*args, "--warmup-tolerance", "2"], env=WIDE)
    assert result.exit_code == 0, result.output
    (settings,) = seen
    assert (settings.max_warmup_s, settings.high_variance_cv_percent) == (0, 8)
    assert (settings.hot_start_c, settings.warmup_tolerance_percent) == (60, 2)
    assert "Warm-up non stabilisé" in result.output


def test_upfront_hot_threshold_uses_option(monkeypatch: pytest.MonkeyPatch) -> None:
    warm = MachineState(["performance"], on_ac=True, cpu_temp_c=65.0)
    monkeypatch.setattr(cli, "capture_state", lambda: warm)
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--hot-start", "60"], env=WIDE)
    assert "CPU déjà chaud au départ (65 °C)" in result.output
