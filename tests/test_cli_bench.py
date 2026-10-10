import json
import re
from pathlib import Path

import pytest
from conftest import TINY, TINY_MEMORY, tool_output
from rich.console import Console
from rich.text import Text
from test_scoring import snapshot
from typer.testing import CliRunner

from hwbench import cli
from hwbench import runner as bench_runner
from hwbench.benchmarks.native import cpu, memory
from hwbench.display.bench import render_failure, render_result
from hwbench.results import BenchWarning, Category, MachineState, Result
from hwbench.runner import Cooldown, CooldownOutcome

runner = CliRunner()
WIDE = {"COLUMNS": "200"}
COOL_AC = MachineState(governors=["performance"], on_ac=True, cpu_temp_c=45.0)


@pytest.fixture(autouse=True)
def fast_and_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpu, "WORKLOADS", TINY)
    monkeypatch.setattr(memory, "SINGLE", TINY_MEMORY)
    monkeypatch.setattr(memory, "MULTI", TINY_MEMORY)
    monkeypatch.setattr(cli, "capture_state", lambda: COOL_AC)
    # indépendant de la référence du paquet (testée dans test_reference_file.py)
    monkeypatch.setattr(cli, "load_reference", lambda: None)
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
    assert "Mémoire · native v1" in result.output
    assert re.search(r"Processus +2 ", result.output)
    assert "GPU : le backend « native » ne couvre pas cette catégorie." in result.output


def test_bench_memory_native() -> None:
    result = runner.invoke(cli.app, ["bench", "memory", "--backend", "native"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "Mémoire · native v1" in result.output and "Mio/s" in result.output
    assert "CPU single-core" not in result.output


def test_bench_disk_with_fio(fake_tools) -> None:
    tools = fake_tools(
        outputs={
            "fio": tool_output("fio_disk.json"),
            "findmnt": tool_output("findmnt_cache.json"),
            "lsblk": tool_output("lsblk_inverse.json"),
        }
    )
    result = runner.invoke(cli.app, ["bench", "disk", "--disk-path", "/mnt/data"], env=WIDE)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Disque · fio : fichier de test de 1 Gio dans /mnt/data, supprimé à la fin" in out
    assert "Disque · fio v1 · outil 3.40" in out
    assert re.search(r"Fichier de test +1 Gio", out)
    assert "Lecture aléatoire 4K (QD32)" in out and "IOPS" in out
    assert "système de fichiers btrfs" in out and "Samsung SSD 990 EVO Plus 1TB" in out
    # fichier supprimé après les runs
    assert tools.temp_files == [Path("/mnt/data/hwbench-fio-0.tmp")]
    assert tools.removed == tools.temp_files


def test_bench_disk_size_option(fake_tools) -> None:
    tools = fake_tools(outputs={"fio": tool_output("fio_disk.json")})
    result = runner.invoke(cli.app, ["bench", "disk", "--disk-size", "512M"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert f"--size={512 * 1024**2}" in tools.calls[-1]
    assert re.search(r"Fichier de test +512 Mio", result.output)


@pytest.mark.parametrize("size", ["32M", "1T", "beaucoup"])
def test_bench_disk_size_is_validated(size: str) -> None:
    result = runner.invoke(cli.app, ["bench", "disk", "--disk-size", size])
    assert result.exit_code == 2
    assert "--disk-size" in result.output


def test_bench_disk_without_fio_fails() -> None:
    result = runner.invoke(cli.app, ["bench", "disk"], env=WIDE)
    assert result.exit_code == 1
    assert "Disque · fio : indisponible (outil absent), ignoré." in result.output


def test_memory_weight_is_refused() -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--weights", "memory=1"])
    assert result.exit_code == 2
    assert "ne fait pas partie du score combiné" in result.output


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


def test_tool_error_text_is_not_rich_markup(fake_tools) -> None:
    fake_tools(failing={"sysbench": "[/boom] FATAL: invalid option"})
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--backend", "sysbench"], env=WIDE)
    assert result.exit_code == 1  # aucun résultat, mais pas de MarkupError
    assert "[/boom] FATAL: invalid option" in result.output


# --- --cooldown : cool_down simulé (aucune vraie attente) ---------------------------------


@pytest.fixture
def cooldowns(monkeypatch: pytest.MonkeyPatch) -> dict:
    """cool_down remplacé : renvoie 12 s (ou l'issue choisie) ; enregistre les appels et la
    pause transmise à chaque bench."""
    seen: dict = {"calls": [], "runs": [], "outcome": CooldownOutcome.COOLED}
    real = cli.run_benchmark

    def fake_cool_down(settings, **kwargs):
        seen["calls"].append(settings)
        return Cooldown(12.0, seen["outcome"], 82.0, 66.0)

    def spy(bench, settings, **kwargs):
        seen["runs"].append((bench.name, kwargs.get("cooldown_s")))
        return real(bench, settings, **kwargs)

    monkeypatch.setattr(cli, "cool_down", fake_cool_down)
    monkeypatch.setattr(cli, "run_benchmark", spy)
    return seen


def test_without_cooldown_nothing_waits(cooldowns) -> None:
    result = runner.invoke(cli.app, ["bench", "all", "--backend", "native"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert cooldowns["calls"] == []


def test_fixed_cooldown_between_categories_only(cooldowns) -> None:
    args = ["bench", "all", "--backend", "native", "--cooldown", "30"]
    result = runner.invoke(cli.app, args, env=WIDE)
    assert result.exit_code == 0, result.output
    assert [(s.cooldown_s, s.cooldown_auto) for s in cooldowns["calls"]] == [(30.0, False)] * 2
    # pas avant la première catégorie, ni entre deux benchs d'une même catégorie
    assert cooldowns["runs"] == [
        ("native-cpu-single", 0.0),
        ("native-cpu-multi", 12.0),
        ("native-memory-single", 12.0),
        ("native-memory-multi", 0.0),
    ]
    assert "CPU multi-core · refroidissement : CPU de 82 °C à 66 °C en 12 s" in result.output
    assert re.search(r"Refroidissement +12 s de pause avant le test", result.output)


def test_auto_cooldown_before_every_category(cooldowns) -> None:
    args = ["bench", "all", "--backend", "native", "--cooldown", "auto"]
    result = runner.invoke(cli.app, [*args, "--cooldown-timeout", "60", "--hot-start", "65"])
    assert result.exit_code == 0, result.output
    settings = cooldowns["calls"]
    assert len(settings) == 3  # CPU single (la première comprise), CPU multi, mémoire
    assert all(s.cooldown_auto and s.cooldown_timeout_s == 60 for s in settings)
    assert all(s.hot_start_c == 65 for s in settings)


def test_cooldown_timeout_is_a_warning(cooldowns) -> None:
    cooldowns["outcome"] = CooldownOutcome.TIMEOUT
    args = ["bench", "cpu-single", "--backend", "native", "--cooldown", "auto"]
    result = runner.invoke(cli.app, args, env=WIDE)
    assert result.exit_code == 0, result.output
    assert "⚠ CPU single-core · refroidissement : CPU encore à 66 °C après 12 s" in result.output


@pytest.mark.parametrize(
    ("value", "expected"),
    [("auto", (0.0, True)), ("AUTO", (0.0, True)), ("30", (30.0, False)), ("7,5", (7.5, False))],
)
def test_parse_cooldown(value, expected) -> None:
    assert cli.parse_cooldown(value) == expected


@pytest.mark.parametrize("value", ["-5", "chaud", "inf", "nan", ""])
def test_invalid_cooldown_is_refused(value) -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--cooldown", value])
    assert result.exit_code == 2
    assert "--cooldown" in result.output


def test_cooldown_settings_are_exported(cooldowns, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli, "collect_snapshot", lambda include_identifiers=False: (snapshot(), None)
    )
    out = tmp_path / "m.json"
    args = ["export", "-o", str(out), "all", "--backend", "native", "--cooldown", "auto"]
    result = runner.invoke(cli.app, args, env=WIDE)
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["schema_version"] == 4 and data["settings"]["cooldown_auto"] is True
    assert [r["cooldown_s"] for r in data["results"]] == [12.0, 12.0, 12.0, 0.0]


def test_render_failure_is_a_panel_of_its_category() -> None:
    panel = render_failure(Category.GPU, "vkmark", "1", "[/x] vkmark interrompu")
    assert panel.title == "GPU · vkmark v1" and panel.border_style == "red"
    message = panel.renderable.columns[1]._cells[1]
    assert isinstance(message, Text) and message.plain == "[/x] vkmark interrompu"


def test_failed_bench_is_shown_in_its_panel(fake_tools, monkeypatch) -> None:
    fake_tools(failing={"sysbench": (-11, "MESA-INTEL: warning: something")})
    shown = []
    monkeypatch.setattr(cli, "render_failure", lambda *args: shown.append(args) or "")
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--backend", "sysbench"], env=WIDE)
    assert result.exit_code == 1  # aucun résultat, mais pas de plantage
    ((category, backend, version, message),) = shown
    assert (category, backend, version) == (Category.CPU_SINGLE, "sysbench", "1")
    assert message.startswith("sysbench interrompu par le signal SIGSEGV (code -11).")
