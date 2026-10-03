"""Commandes `hwbench reference`, `hwbench backends` et scores affichés par `hwbench bench`."""

import json
import re
from dataclasses import replace

import pytest
from conftest import COOL_AC_STATE, make_result, tool_output
from test_scoring import REFERENCE, snapshot
from typer.testing import CliRunner

from hwbench import cli
from hwbench.results import MachineState
from hwbench.scoring import load_reference

runner = CliRunner()
WIDE = {"COLUMNS": "200"}
DESKTOP = MachineState(
    ["performance"], True, 40.0, energy_performance_preference="performance", has_battery=False
)


class FakeRuns:
    def __init__(self) -> None:
        self.ran: list[str] = []
        self.unstable: set[str] = set()  # benchs dont le warm-up ne se stabilise pas
        # l'outil n'est jamais lancé : sa version est celle des fixtures
        self.tool_versions = {"glmark2": "2023.01", "vkmark": "2025.01"}


@pytest.fixture
def fake_runs(monkeypatch: pytest.MonkeyPatch) -> FakeRuns:
    """run_benchmark remplacé par un résultat fabriqué (valeur 100), instantané."""
    runs = FakeRuns()

    def run_benchmark(bench, settings, **kwargs):
        runs.ran.append(bench.name)
        return make_result(
            bench.name,
            100.0,
            backend=bench.backend,
            category=bench.category,
            version=bench.version,
            tool_version=runs.tool_versions.get(bench.name),
            presentation=bench.presentation(),
            warmup_stable=bench.name not in runs.unstable,
        )

    monkeypatch.setattr(cli, "run_benchmark", run_benchmark)
    monkeypatch.setattr(
        cli, "collect_snapshot", lambda include_identifiers=False: (snapshot(), None)
    )
    monkeypatch.setattr(cli, "capture_state", lambda: COOL_AC_STATE)
    return runs


def test_reference_written_when_conditions_are_met(fake_runs, tmp_path) -> None:
    out = tmp_path / "reference.json"
    result = runner.invoke(cli.app, ["reference", "-o", str(out)], env=WIDE)
    assert result.exit_code == 0, result.output
    assert fake_runs.ran == ["native-cpu-single", "native-cpu-multi"]
    assert "sysbench-cpu-single : absent de la référence" in result.output
    data = json.loads(out.read_text())
    assert data["forced"] is False and data["forced_reasons"] == []
    assert data["machine"] == "Dell Inc. Latitude 5420"
    reference = load_reference(out)
    assert reference is not None and {e.id.name for e in reference.entries} == set(fake_runs.ran)


def test_reference_works_on_a_desktop(fake_runs, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "capture_state", lambda: DESKTOP)
    out = tmp_path / "ref.json"
    assert runner.invoke(cli.app, ["reference", "-o", str(out)]).exit_code == 0
    assert out.exists()


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (replace(COOL_AC_STATE, on_ac=False), "la machine n'est pas sur secteur"),
        (
            replace(COOL_AC_STATE, platform_profile="balanced"),
            "profil d'énergie non « performance »",
        ),
        (replace(COOL_AC_STATE, platform_profile=None), "profil d'énergie inconnu"),
    ],
)
def test_reference_refused_before_measuring(
    fake_runs, monkeypatch, tmp_path, state, message
) -> None:
    monkeypatch.setattr(cli, "capture_state", lambda: state)
    out = tmp_path / "reference.json"
    result = runner.invoke(cli.app, ["reference", "-o", str(out)], env=WIDE)
    assert result.exit_code == 1
    assert "Référence refusée avant les mesures" in result.output and message in result.output
    assert fake_runs.ran == [] and not out.exists()


def test_reference_refused_when_warmup_unstable(fake_runs, tmp_path) -> None:
    fake_runs.unstable = {"native-cpu-multi"}
    out = tmp_path / "reference.json"
    result = runner.invoke(cli.app, ["reference", "-o", str(out)], env=WIDE)
    assert result.exit_code == 1
    assert "fichier non écrit" in result.output
    assert "native-cpu-multi : warm-up non stabilisé" in result.output
    assert not out.exists()


def test_reference_force_marks_the_file(fake_runs, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "capture_state", lambda: replace(COOL_AC_STATE, on_ac=False))
    fake_runs.unstable = {"native-cpu-single"}
    out = tmp_path / "reference.json"
    result = runner.invoke(cli.app, ["reference", "-o", str(out), "--force"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "forcée" in result.output
    data = json.loads(out.read_text())
    assert data["forced"] is True
    assert data["forced_reasons"] == ["not_on_ac", "warmup_unstable:native-cpu-single"]
    reference = load_reference(out)
    assert reference is not None and reference.forced


def test_backends_lists_availability_and_install_hints(fake_tools) -> None:
    fake_tools(
        outputs={"glmark2-wayland": "", "vkmark": ""},
        env={"WAYLAND_DISPLAY": "wayland-0"},
        files={"/usr/lib/vkmark/headless.so"},
    )
    result = runner.invoke(cli.app, ["backends"], env=WIDE)
    assert result.exit_code == 0, result.output
    rows = {line.split("│")[1].strip(): line for line in result.output.splitlines() if "│" in line}
    assert "disponible" in rows["native-cpu-multi"]
    assert "disponible" in rows["glmark2"] and "disponible" in rows["vkmark"]
    assert "outil absent" in rows["sysbench-cpu-single"]
    assert "sudo apt install sysbench" in rows["sysbench-cpu-single"]


def test_backends_without_session(fake_tools) -> None:
    fake_tools(outputs={"glmark2-wayland": "", "vkmark": ""}, env={})
    result = runner.invoke(cli.app, ["backends"], env=WIDE)
    rows = {line.split("│")[1].strip(): line for line in result.output.splitlines() if "│" in line}
    assert "aucune session graphique" in rows["glmark2"]
    assert "aucune session graphique" in rows["vkmark"]


def test_bench_prints_scores_against_reference(fake_runs, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    result = runner.invoke(cli.app, ["bench", "--backend", "native"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "Scores · référence Dell Inc. Latitude 5420 = 1000 pts" in result.output
    # 100 contre 100 en single, 100 contre 400 en multi -> 1000 et 250 pts
    assert re.search(r"CPU single-core +1000 pts", result.output)
    assert re.search(r"CPU multi-core +250 pts", result.output)
    assert re.search(r"Score combiné +500 pts", result.output)
    assert "calculé sans GPU" in result.output


def test_bench_gpu_subset_is_not_comparable(fake_runs, fake_tools, monkeypatch) -> None:
    fake_tools(
        outputs={"glmark2-wayland": tool_output("glmark2-wayland_offscreen.txt")},
        env={"WAYLAND_DISPLAY": "wayland-0"},
    )
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    result = runner.invoke(cli.app, ["bench", "gpu"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert re.search(r"GPU +non comparable \(backends différents de la référence\)", result.output)
    assert "mesurés : glmark2" in result.output and "vkmark v2" in result.output


def test_bench_without_reference_says_how_to_make_one(fake_runs, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: None)
    result = runner.invoke(cli.app, ["bench", "cpu-single"], env=WIDE)
    assert result.exit_code == 0
    assert "Pas de fichier de référence" in result.output
    assert "hwbench reference -o" in result.output
