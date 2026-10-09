import json
import re
from datetime import UTC, datetime

from test_compare import export
from test_scoring import REFERENCE, machine

from hwbench.export import to_dict, write_export
from hwbench.leaderboard import __main__ as cli
from hwbench.leaderboard.site import build_site, category_points, load_entries, ranking
from hwbench.results import Category

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
    assert "1 machine(s) non classée(s) ici" in index  # le portable, dans le combiné


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
    assert "4 machine(s)" in capsys.readouterr().out
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
    assert "<td>03/10/2026</td>" in page  # « Exporté le »
    assert "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)" in page  # détail : renderer complet


def test_unreadable_date_does_not_break_the_site(tmp_path) -> None:
    d = results_dir(tmp_path)
    data = json.loads((d / "rapide.json").read_text()) | {"created": "<b>jamais</b>"}
    (d / "rapide.json").write_text(json.dumps(data))
    out = tmp_path / "_site"
    build_site(d, out, REFERENCE, generated=NOW)
    assert "&lt;b&gt;jamais&lt;/b&gt;" in (out / "index.html").read_text()  # brut, échappé
