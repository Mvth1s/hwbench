"""`hwbench export` : benchs (simulés) + écriture d'un export relisible."""

from test_cli_reference import fake_runs  # noqa: F401 (fixture)
from test_scoring import REFERENCE
from typer.testing import CliRunner

from hwbench import cli
from hwbench.export import load_export

runner = CliRunner()
WIDE = {"COLUMNS": "200"}


def test_export_writes_a_loadable_file(fake_runs, monkeypatch, tmp_path) -> None:  # noqa: F811
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    out = tmp_path / "machine.json"
    result = runner.invoke(cli.app, ["export", "-o", str(out), "--backend", "native"], env=WIDE)
    assert result.exit_code == 0, result.output
    assert f"Export écrit : {out} (4 benchs)" in result.output.replace("\n", "")
    assert "Scores · référence" in result.output  # même affichage que bench
    export = load_export(out)
    assert export.machine == "Dell Inc. Latitude 5420"
    assert [r.name for r in export.results] == [
        "native-cpu-single",
        "native-cpu-multi",
        "native-memory-single",
        "native-memory-multi",
    ]
    assert export.reference is not None and export.reference.digest == REFERENCE.digest
    assert export.combined is not None and export.combined.gpu_missing
    assert export.snapshot.cpu.model is not None


def test_export_without_reference(fake_runs, monkeypatch, tmp_path) -> None:  # noqa: F811
    monkeypatch.setattr(cli, "load_reference", lambda: None)
    out = tmp_path / "machine.json"
    result = runner.invoke(cli.app, ["export", "-o", str(out), "cpu-single"], env=WIDE)
    assert result.exit_code == 0, result.output
    export = load_export(out)
    assert export.reference is None and export.combined is None
    # sysbench n'est pas installé dans les tests : seul le natif a tourné
    assert [r.name for r in export.results] == ["native-cpu-single"]


def test_export_rejects_unknown_backend_without_writing(fake_runs, tmp_path) -> None:  # noqa: F811
    out = tmp_path / "machine.json"
    result = runner.invoke(cli.app, ["export", "-o", str(out), "--backend", "geekbench"])
    assert result.exit_code == 2
    assert not out.exists()
