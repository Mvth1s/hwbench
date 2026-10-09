"""--report, --report-dir et `hwbench report` : rien d'écrit sans le demander, HTML rendu depuis le
JSON écrit, aucun fichier si le bench est interrompu ou sans résultat."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from conftest import TINY, TINY_MEMORY
from test_cli_bench import COOL_AC
from test_scoring import snapshot
from typer.testing import CliRunner

from hwbench import cli
from hwbench import runner as bench_runner
from hwbench.benchmarks.native import cpu, memory
from hwbench.export import load_export
from hwbench.report import render_report
from hwbench.results import Category

runner = CliRunner()
WIDE = {"COLUMNS": "200"}
REPORT_FIXTURE = Path(__file__).parent / "fixtures" / "report" / "session.json"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(cpu, "WORKLOADS", TINY)
    monkeypatch.setattr(memory, "SINGLE", TINY_MEMORY)
    monkeypatch.setattr(memory, "MULTI", TINY_MEMORY)
    monkeypatch.setattr(cli, "capture_state", lambda: COOL_AC)
    monkeypatch.setattr(cli, "load_reference", lambda: None)
    monkeypatch.setattr(
        cli, "collect_snapshot", lambda include_identifiers=False: (snapshot(), None)
    )
    monkeypatch.setattr(bench_runner, "DEFAULT_MAX_WARMUP_S", dict.fromkeys(Category, 0.2))
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    return data / "hwbench" / "reports"


def test_reports_dir_follows_xdg(isolated: Path, monkeypatch) -> None:
    assert cli.reports_dir() == isolated
    monkeypatch.delenv("XDG_DATA_HOME")
    assert cli.reports_dir() == Path.home() / ".local" / "share" / "hwbench" / "reports"


def test_bench_without_report_writes_nothing(isolated: Path) -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert not isolated.exists()
    assert "Rapport enregistré" not in result.output


def test_bench_with_report(isolated: Path) -> None:
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--report"], env=WIDE)
    assert result.exit_code == 0, result.output
    (json_path,) = isolated.glob("*.json")
    (html_path,) = isolated.glob("*.html")
    assert json_path.stem == html_path.stem
    datetime.strptime(json_path.stem, "%Y-%m-%d_%H%M%S")  # horodatage seul, à la seconde
    session = load_export(json_path)
    assert session.settings is not None and [r.name for r in session.results] == [
        "native-cpu-single"
    ]
    # le HTML est exactement celui rendu depuis le JSON écrit
    assert html_path.read_text() == render_report(session)
    out = result.output.replace("\n", "")
    assert f"JSON  {json_path}" in out and f"HTML  {html_path}" in out


def test_report_dir_option(tmp_path: Path, isolated: Path) -> None:
    target = tmp_path / "ailleurs"
    result = runner.invoke(
        cli.app, ["bench", "cpu-single", "--report", "--report-dir", str(target)], env=WIDE
    )
    assert result.exit_code == 0, result.output
    assert len(list(target.glob("*.html"))) == 1 and not isolated.exists()


def test_no_result_no_report(isolated: Path) -> None:
    result = runner.invoke(cli.app, ["bench", "gpu", "--report"], env=WIDE)
    assert result.exit_code == 1
    assert not isolated.exists()


def test_interrupted_bench_writes_nothing(isolated: Path, monkeypatch) -> None:
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_benchmark", interrupted)
    result = runner.invoke(cli.app, ["bench", "cpu-single", "--report"], env=WIDE)
    assert result.exit_code == 130
    assert not isolated.exists()


def test_same_second_does_not_overwrite(tmp_path: Path) -> None:
    session = load_export(REPORT_FIXTURE)
    now = datetime(2026, 10, 9, 15, 30, 12)
    first = cli.write_report(session, tmp_path, now)
    second = cli.write_report(session, tmp_path, now)
    assert first[0].name == "2026-10-09_153012.json"
    assert second[0].name == "2026-10-09_153012-2.json"


def test_export_with_report(tmp_path: Path, isolated: Path) -> None:
    out = tmp_path / "machine.json"
    result = runner.invoke(
        cli.app, ["export", "-o", str(out), "--backend", "native", "--report"], env=WIDE
    )
    assert result.exit_code == 0, result.output
    (json_path,) = isolated.glob("*.json")
    assert json.loads(json_path.read_text()) == json.loads(out.read_text())


def test_report_command(tmp_path: Path) -> None:
    src = tmp_path / "session.json"
    src.write_text(REPORT_FIXTURE.read_text())
    result = runner.invoke(cli.app, ["report", str(src)], env=WIDE)
    assert result.exit_code == 0, result.output
    html = (tmp_path / "session.html").read_text()
    assert html == render_report(load_export(REPORT_FIXTURE))
    custom = tmp_path / "rapport.html"
    assert runner.invoke(cli.app, ["report", str(src), "-o", str(custom)]).exit_code == 0
    assert custom.read_text() == html


def test_report_command_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 9}')
    result = runner.invoke(cli.app, ["report", str(bad)])
    assert result.exit_code == 2 and "schéma d'export 9 non pris en charge" in result.output
    assert not (tmp_path / "bad.html").exists()
    same = tmp_path / "x.html"
    same.write_text("{}")
    assert runner.invoke(cli.app, ["report", str(same)]).exit_code == 2
    missing = runner.invoke(cli.app, ["report", str(tmp_path / "absent.json")])
    assert missing.exit_code == 2
