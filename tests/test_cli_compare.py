"""`hwbench compare` : affichage côte à côte, écarts et non-comparables.

make_result met l'unité « index » partout : les motifs ne vérifient que les valeurs.
"""

import re
from dataclasses import replace

from test_cli_reference import fake_runs  # noqa: F401 (fixture)
from test_compare import export
from test_scoring import REFERENCE, machine
from typer.testing import CliRunner

from hwbench import cli
from hwbench.export import write_export

runner = CliRunner()
WIDE = {"COLUMNS": "220"}
CELL = r"\s*│\s*"  # séparateur de colonnes rich


def write(tmp_path, name: str, exp) -> str:
    path = tmp_path / f"{name}.json"
    write_export(exp, path)
    return str(path)


def invoke(*files: str):
    return runner.invoke(cli.app, ["compare", *files], env=WIDE)


def has_row(out: str, *cells: str) -> bool:
    """Ligne de tableau dont les cellules commencent par ces motifs, dans l'ordre."""
    return re.search(CELL.join(f"{c}[^│]*" for c in cells), out) is not None


def test_compare_shows_machines_scores_and_deltas(tmp_path) -> None:
    a = write(tmp_path, "desktop", export(machine(1.0), "ASRock B850 Riptide WiFi"))
    b = write(tmp_path, "laptop", export(machine(0.5), "Dell Inc. Latitude 5420"))
    result = invoke(a, b)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "desktop (base)" in out and "laptop" in out
    assert has_row(out, "Modèle", "ASRock B850 Riptide WiFi", "Dell Inc. Latitude 5420")
    assert has_row(out, "Score combiné", "1000 pts", "500 pts  -50,0 %")
    assert has_row(out, "native-cpu-single", "100,0 indice brut", "50,0 indice brut  -50,0 %")
    assert has_row(out, "glmark2", "2000,0", "1000,0 [^│]*-50,0 %")
    assert "⚠" not in out


def test_compare_flags_what_is_not_comparable(tmp_path) -> None:
    older_glmark2 = [
        replace(r, tool_version="2021.02") if r.name == "glmark2" else r for r in machine(1.0)
    ]
    a = write(tmp_path, "a", export(machine(1.0)))
    b = write(tmp_path, "b", export([r for r in older_glmark2 if r.name != "vkmark"]))
    out = invoke(a, b).output
    assert has_row(out, "glmark2", "2000,0", r"2000,0 [^│]*non comparé \(version différente\)")
    assert has_row(out, "vkmark", "5000,0", "—")
    # GPU de b : glmark2 non comparable à sa référence -> catégorie non comparable
    assert has_row(out, "GPU", "1000 pts", r"non comparable \(version de l'outil")
    assert "glmark2 : version du bench, de l'outil ou mode de présentation différents" in out


def test_compare_three_files_and_export_without_reference(tmp_path) -> None:
    files = [
        write(tmp_path, "a", export(machine(1.0))),
        write(tmp_path, "b", export(machine(2.0))),
        write(tmp_path, "c", export(machine(1.0), reference=None)),
    ]
    out = invoke(*files).output
    assert has_row(
        out, "Score combiné", "1000 pts", r"2000 pts  \+100,0 %", "exporté sans référence"
    )
    assert has_row(out, "Référence", "Dell Inc. Latitude 5420", "Dell Inc. Latitude 5420", "aucune")
    # les valeurs brutes restent comparées, référence ou pas
    assert has_row(out, "native-cpu-single", "100,0", r"200,0 [^│]*\+100,0 %", "100,0 [^│]*0,0 %")


def test_compare_needs_two_files(tmp_path) -> None:
    result = invoke(write(tmp_path, "a", export(machine(1.0))))
    assert result.exit_code == 2
    assert "au moins deux fichiers" in result.output


def test_compare_reports_the_broken_file(tmp_path) -> None:
    good = write(tmp_path, "good", export(machine(1.0)))
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 7}')
    result = invoke(good, str(bad))
    assert result.exit_code == 2
    assert "bad.json : schéma d'export 7 non pris en charge" in result.output


def test_export_then_compare_end_to_end(fake_runs, monkeypatch, tmp_path) -> None:  # noqa: F811
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    files = []
    for name in ("before", "after"):
        out = tmp_path / f"{name}.json"
        args = ["export", "-o", str(out), "--backend", "native"]
        assert runner.invoke(cli.app, args).exit_code == 0
        files.append(str(out))
    result = invoke(*files)
    assert result.exit_code == 0, result.output
    # mêmes valeurs simulées des deux côtés : écart nul
    assert has_row(result.output, "native-cpu-multi", "100,0 indice brut", "100,0 [^│]*0,0 %")
    assert has_row(result.output, "Score combiné", "500 pts", "500 pts  0,0 %")
