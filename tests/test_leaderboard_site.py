import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from conftest import COOL_AC_STATE, make_result
from test_compare import disk, export
from test_scoring import REFERENCE, machine, snapshot

from hwbench.export import build_export, to_dict, write_export
from hwbench.leaderboard import __main__ as cli
from hwbench.leaderboard.site import (
    build_site,
    category_points,
    load_entries,
    ranking,
    settings_note,
)
from hwbench.results import Category
from hwbench.runner import RunSettings
from hwbench.scoring import score_results

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
EVIL = '<script>alert("x")</script> & <img src=x onerror=alert(1)>'


def results_dir(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    write_export(export(machine(2.0), "Desktop rapide"), d / "rapide.json")
    write_export(export(machine(1.0), "Desktop moyen"), d / "moyen.json")
    cpu_only = [r for r in machine(3.0) if r.category is not Category.GPU]
    write_export(export(cpu_only, "Portable sans GPU"), d / "portable.json")
    write_export(export(machine(0.5), EVIL), d / "piege.json")
    return d


def test_rankings_follow_points_and_composition(tmp_path) -> None:
    entries, skipped = load_entries(results_dir(tmp_path), REFERENCE)
    assert skipped == []
    combined = [(e.slug, round(p)) for e, p in ranking(entries, None)]
    # le portable a un combiné CPU seul (gpu_missing) : absent du classement combiné
    assert combined == [("rapide", 2000), ("moyen", 1000), ("piege", 500)]
    single = [e.slug for e, _ in ranking(entries, Category.CPU_SINGLE)]
    assert single == ["portable", "rapide", "moyen", "piege"]
    gpu = [e.slug for e, _ in ranking(entries, Category.GPU)]
    assert "portable" not in gpu


def test_incomplete_gpu_is_ranked_nowhere_but_in_the_cpu_tabs(tmp_path) -> None:
    """vkmark en échec : combiné CPU seul (partiel), ni au combiné ni à l'onglet GPU."""
    d = tmp_path / "results"
    d.mkdir()
    no_vulkan = [r for r in machine(3.0) if r.name != "vkmark"]
    write_export(export(no_vulkan, "Sans Vulkan"), d / "sans-vulkan.json")
    write_export(export(machine(1.0), "Desktop moyen"), d / "moyen.json")
    entries, _ = load_entries(d, REFERENCE)
    assert [e.slug for e, _ in ranking(entries, None)] == ["moyen"]
    assert [e.slug for e, _ in ranking(entries, Category.GPU)] == ["moyen"]
    assert [e.slug for e, _ in ranking(entries, Category.CPU_MULTI)] == ["sans-vulkan", "moyen"]


def test_cpu_multi_alone_is_ranked_only_in_its_tab(tmp_path) -> None:
    d = tmp_path / "results"
    d.mkdir()
    multi_only = [r for r in machine(2.0) if r.name == "native-cpu-multi"]
    write_export(export(multi_only, "Multi seul"), d / "multi.json")
    (entry,) = load_entries(d, REFERENCE)[0]
    assert entry.scores.combined is not None and not entry.scores.combined.gpu_missing
    assert category_points(entry, None) is None
    assert round(category_points(entry, Category.CPU_MULTI)) == 2000


def test_points_are_recomputed_not_taken_from_the_file(tmp_path) -> None:
    d = tmp_path / "results"
    d.mkdir()
    data = to_dict(export(machine(1.0), "Retouché"))
    data["combined"]["points"] = 99999.0
    data["categories"][0]["points"] = 99999.0
    (d / "retouche.json").write_text(json.dumps(data))
    (entry,) = load_entries(d, REFERENCE)[0]
    assert round(category_points(entry, None)) == 1000
    assert round(category_points(entry, Category.CPU_SINGLE)) == 1000


def test_site_files_and_escaping(tmp_path) -> None:
    out = tmp_path / "_site"
    entries = build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    assert len(entries) == 4
    index = (out / "index.html").read_text()
    assert (out / ".nojekyll").exists()
    for slug in ("rapide", "moyen", "portable", "piege"):
        assert (out / "machines" / f"{slug}.html").exists()
    for page in [index, *(p.read_text() for p in (out / "machines").glob("*.html"))]:
        # aucune vraie balise venue d'un export (le texte échappé, lui, reste lisible)
        assert "<script" not in page and "<img" not in page
        assert re.search(r"<[^>]*onerror", page) is None
        assert re.search(r'(src|href)="https?://(?!github\.com/Mvth1s/hwbench)', page) is None
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &lt;img" in index
    assert 'href="machines/rapide.html">Desktop rapide</a>' in index
    assert "Généré le 05/10/2026 12:00 UTC" in index
    assert "1 machine non classée ici" in index  # le portable, dans le combiné


def test_machine_page_details(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    page = (out / "machines" / "rapide.html").read_text()
    assert "<h1>Desktop rapide</h1>" in page
    assert "results/rapide.json" in page
    assert "2000 pts" in page  # combiné recalculé
    assert "native-cpu-single" in page and "200,0 indice brut" in page
    portable = (out / "machines" / "portable.html").read_text()
    assert "non classé" in portable  # GPU et combiné


def test_unreadable_file_is_skipped_and_listed(tmp_path) -> None:
    d = results_dir(tmp_path)
    (d / "ancien.json").write_text('{"schema_version": 1}')
    out = tmp_path / "_site"
    entries = build_site(d, out, REFERENCE, generated=NOW)
    assert len(entries) == 4
    index = (out / "index.html").read_text()
    assert "Fichiers ignorés" in index and "ancien.json" in index


def test_cli_site(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    out = tmp_path / "_site"
    assert cli.main(["site", "--results", str(results_dir(tmp_path)), "--out", str(out)]) == 0
    assert "(4 machines)" in capsys.readouterr().out
    assert (out / "index.html").exists()


def test_cli_summary_gives_combined_ranks(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    d = results_dir(tmp_path)
    assert cli.main(["summary", "--results", str(d)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ranked"] == 3
    by_slug = {m["slug"]: m for m in summary["machines"]}
    assert by_slug["rapide"]["rank"] == 1 and round(by_slug["rapide"]["combined"]) == 2000
    assert by_slug["piege"]["machine"] == EVIL  # brut : l'échappement revient au consommateur
    # combiné sans GPU : présent, mais sans rang
    assert by_slug["portable"]["rank"] is None and by_slug["portable"]["combined"] is None

    new = [str(d / "moyen.json"), str(d / "portable.json")]
    assert cli.main(["summary", "--results", str(d), "--new", *new]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert [(m["slug"], m["rank"]) for m in summary["machines"]] == [
        ("moyen", 2),
        ("portable", None),
    ]


def test_site_skips_symlinks(tmp_path) -> None:
    d = results_dir(tmp_path)
    (d / "lien.json").symlink_to(d / "rapide.json")
    entries, skipped = load_entries(d, REFERENCE)
    assert "lien" not in {e.slug for e in entries}
    assert any(s.startswith("lien.json : lien symbolique refusé") for s in skipped)


def test_site_refuses_a_symlinked_results_dir(tmp_path) -> None:
    real = results_dir(tmp_path)
    (tmp_path / "lien").symlink_to(real)
    entries, skipped = load_entries(tmp_path / "lien", REFERENCE)
    assert entries == [] and "lien symbolique refusé" in skipped[0]


def test_gpu_column_and_dates(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    index = (out / "index.html").read_text()
    # renderer brut « Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2) » : nom seul, casse d'origine
    assert "<td>Mesa Intel(R) Iris(R) Xe Graphics</td>" in index
    assert "(TGL GT2)" not in index
    assert '<td class="small muted">03/10/2026</td>' in index  # date d'export
    assert "(mesurée le 29/09/2026," in index  # date de la référence
    page = (out / "machines" / "rapide.html").read_text()
    assert "mesuré le 03/10/2026" in page  # en-tête : date de l'export
    assert "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)" in page  # détail : renderer complet


def test_unreadable_date_does_not_break_the_site(tmp_path) -> None:
    d = results_dir(tmp_path)
    data = json.loads((d / "rapide.json").read_text()) | {"created": "<b>jamais</b>"}
    (d / "rapide.json").write_text(json.dumps(data))
    out = tmp_path / "_site"
    build_site(d, out, REFERENCE, generated=NOW)
    assert "&lt;b&gt;jamais&lt;/b&gt;" in (out / "index.html").read_text()  # brut, échappé


def test_memory_and_disk_are_information_columns(tmp_path) -> None:
    d = results_dir(tmp_path)
    with_info = machine(1.0) + [
        make_result("native-memory-multi", 25_000.0),
        disk(3347.0, 238_831.0),
    ]
    write_export(export(with_info, "Avec mémoire et disque"), d / "infos.json")
    entries, _ = load_entries(d, REFERENCE)
    # le classement ne bouge pas : mêmes points combinés que la même machine sans ces benchs
    combined = {e.slug: round(p) for e, p in ranking(entries, None)}
    assert combined["infos"] == combined["moyen"] == 1000
    out = tmp_path / "_site"
    build_site(d, out, REFERENCE, generated=NOW)
    index = (out / "index.html").read_text()
    assert '<th class="num">Mémoire</th><th class="num">Disque</th>' in index
    assert "25000 Mio/s" in index and "3347 Mio/s · 238831 IOPS 4K" in index
    assert 'id="tab-memory"' not in index and 'id="tab-disk"' not in index
    page = (out / "machines" / "infos.html").read_text()
    assert "Mémoire (information)" in page
    assert "Lecture aléatoire 4K (QD32)" in page and "<td>1 Gio</td>" in page


def test_machine_page_reuses_the_report_sections(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    page = (out / "machines" / "rapide.html").read_text()
    for section in ("classement", "synthese", "conditions", "cpu", "fiabilite", "annexe"):
        assert f'<section id="{section}">' in page, section
    # pas de recommandations ni de JSON embarqué sur le site
    assert '<section id="recommandations">' not in page
    assert "<script" not in page


def _with_settings(tmp_path, settings: RunSettings | None) -> str:
    d = tmp_path / "results"
    d.mkdir(parents=True)
    hot = replace(COOL_AC_STATE, cpu_temp_c=66.0)
    results = [replace(r, state_before=hot) for r in machine(1.0)]
    scores = score_results(results, REFERENCE)
    ex = build_export(snapshot(), "Seuils", results, scores, settings=settings)
    write_export(ex, d / "seuils.json")
    out = tmp_path / "_site"
    build_site(d, out, REFERENCE, generated=NOW)
    return (out / "machines" / "seuils.html").read_text()


def test_site_always_applies_the_default_thresholds(tmp_path) -> None:
    # mesuré avec --hot-start 60 : 66 °C au départ y était « chaud »
    page = _with_settings(tmp_path, RunSettings(hot_start_c=60.0, high_variance_cv_percent=2.0))
    assert "Les seuils de la mesure diffèrent des seuils par défaut" in page
    assert "départ chaud 60 °C au lieu de 70 °C" in page
    assert "seuil de CV 2 % au lieu de 5 %" in page
    # le site juge avec 70 °C : aucun départ chaud signalé
    assert "seuil de départ chaud)" not in page
    assert "Tous les tests ont démarré sous le seuil de départ chaud 70 °C." in page


def test_site_notes_default_or_missing_settings(tmp_path) -> None:
    assert "identiques à ceux de la mesure" in _with_settings(tmp_path / "a", RunSettings())
    assert "non enregistrés dans ce fichier" in _with_settings(tmp_path / "b", None)


def test_settings_note() -> None:
    assert settings_note(RunSettings()) == "Seuils par défaut, identiques à ceux de la mesure."
    note = settings_note(RunSettings(runs=5, max_warmup_s=180.0))
    assert "runs 5 au lieu de 3" in note
    assert "plafond du warm-up 180 s au lieu de défaut" in note


def test_generated_site_has_no_ambiguous_plural(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    for page in [out / "index.html", *(out / "machines").glob("*.html")]:
        assert "(s)" not in page.read_text(), page.name
    assert "4 machines." in (out / "index.html").read_text()


def test_real_site_has_no_ambiguous_plural(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(Path(__file__).parents[1] / "results", out, REFERENCE, generated=NOW)
    for page in [out / "index.html", *(out / "machines").glob("*.html")]:
        assert "(s)" not in page.read_text(), page.name


def test_stale_reference_is_flagged_for_re_export(tmp_path) -> None:
    from test_leaderboard_validate import stale_payload

    d = results_dir(tmp_path)
    (d / "ancien.json").write_text(json.dumps(stale_payload() | {"machine": "Desktop ancien"}))
    entries = {e.slug: e for e in load_entries(d, REFERENCE)[0]}
    assert entries["ancien"].stale and not entries["moyen"].stale
    # points recalculés contre la référence actuelle : l'ancien fichier reste classé
    assert round(category_points(entries["ancien"], None)) == 1000
    out = tmp_path / "_site"
    build_site(d, out, REFERENCE, generated=NOW)
    index = (out / "index.html").read_text()

    def row(name: str) -> str:  # une seule ligne <tr>…</tr> (premier onglet)
        return re.search(rf"<tr>(?:(?!</tr>).)*{name}.*?</tr>", index).group(0)

    assert "à ré-exporter" in row("Desktop ancien")
    assert "à ré-exporter" not in row("Desktop moyen")
    assert "noté contre une référence antérieure" in index
    page = (out / "machines" / "ancien.html").read_text()
    assert "à ré-exporter" in page and "référence antérieure" in page
    assert "à ré-exporter" not in (out / "machines" / "moyen.html").read_text()


def test_no_re_export_note_without_stale_file(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(results_dir(tmp_path), out, REFERENCE, generated=NOW)
    assert "à ré-exporter" not in (out / "index.html").read_text()


def test_reference_table_lists_recorded_tool_versions() -> None:
    from test_scoring import _fio_reference

    from hwbench.leaderboard.site import _reference_block

    block = _reference_block(REFERENCE)
    assert "<td>2023.01</td>" in block and "<td>1.0.20</td>" in block
    # fio : version hors identité, mais relevée et affichée
    assert "<td>fio-disk</td><td>v1</td><td>3.42</td><td>1GiB</td>" in _reference_block(
        _fio_reference()
    )
