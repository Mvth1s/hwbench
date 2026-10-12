import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from conftest import COOL_AC_STATE, make_result
from test_compare import disk, export
from test_scoring import REFERENCE, machine, snapshot

from hwbench.export import build_export, to_dict, write_export
from hwbench.leaderboard import __main__ as cli
from hwbench.leaderboard.catalog import FR
from hwbench.leaderboard.site import (
    ENV,
    build_site,
    category_points,
    load_entries,
    ranking,
    settings_note,
)
from hwbench.models import Battery, PowerData
from hwbench.results import Category
from hwbench.runner import RunSettings
from hwbench.scoring import score_results

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
EVIL = '<script>alert("x")</script> & <img src=x onerror=alert(1)>'
PACKAGE = Path(__file__).parents[1] / "src" / "hwbench" / "leaderboard"
CLASSEMENT_PAGES = ("index.html", "cpu-single.html", "cpu-multi.html", "gpu.html")
# seules URL externes autorisées dans le site (aucune ressource externe : liens seulement)
EXTERNAL_OK = ("https://github.com/Mvth1s/hwbench", "https://fio.readthedocs.io/")


def results_dir(tmp_path):
    d = tmp_path / "results"
    d.mkdir()
    write_export(export(machine(2.0), "Desktop rapide"), d / "rapide.json")
    write_export(export(machine(1.0), "Desktop moyen"), d / "moyen.json")
    cpu_only = [r for r in machine(3.0) if r.category is not Category.GPU]
    write_export(export(cpu_only, "Portable sans GPU"), d / "portable.json")
    write_export(export(machine(0.5), EVIL), d / "piege.json")
    return d


def site(tmp_path, d=None, **kwargs) -> Path:
    out = tmp_path / "_site"
    build_site(d or results_dir(tmp_path), out, REFERENCE, generated=NOW, **kwargs)
    return out


def html_pages(out: Path) -> list[Path]:
    return sorted(out.glob("*.html")) + sorted((out / "machines").glob("*.html"))


def ranking_rows(html: str) -> list[str]:
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr data-rank.*?</tr>", body, re.S)


# --- Données : classement, points recalculés ---


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
    out = site(tmp_path, d)
    assert "99999" not in (out / "index.html").read_text()
    assert "99999" not in (out / "data.json").read_text()


# --- Pages du classement ---


def test_site_files(tmp_path) -> None:
    out = site(tmp_path)
    for name in (*CLASSEMENT_PAGES, "data.json", "classement.csv", ".nojekyll"):
        assert (out / name).exists(), name
    for slug in ("rapide", "moyen", "portable", "piege"):
        assert (out / "machines" / f"{slug}.html").exists()
    for asset in (
        "hwbench.css",
        "hwbench.js",
        "favicon.svg",
        "fonts/SchibstedGrotesk-400_700.woff2",
        "fonts/IBMPlexMono-400.woff2",
        "fonts/IBMPlexMono-500.woff2",
        "fonts/Michroma-400.woff2",
        "fonts/OFL-Michroma.txt",
        "img/hero-tower-light.png",
        "img/hero-tower-dark.png",
    ):
        assert (out / "assets" / asset).stat().st_size > 0, asset


def test_assets_are_copied_unchanged(tmp_path) -> None:
    out = site(tmp_path)
    static = PACKAGE / "static"
    for source in static.rglob("*"):
        if source.is_file():
            copy = out / "assets" / source.relative_to(static)
            assert copy.read_bytes() == source.read_bytes(), source.name


def test_classement_page_content(tmp_path) -> None:
    index = (site(tmp_path) / "index.html").read_text()
    assert '<html lang="fr">' in index
    assert "Classement Combiné · hwbench</title>" in index
    assert "Classement Linux · 4 machines · mis à jour le 05/10/2026" in index
    # podium : les trois premières machines du combiné, P1 en tête
    podium = index.split('class="hw-section hw-podium"', 1)[1].split("</section>", 1)[0]
    assert podium.index("Desktop rapide") < podium.index("Desktop moyen")
    assert 'data-count="2000.0"' in podium
    # points en chiffres groupés (espace fine insécable), date de l'export
    assert "2 000" in index and "03/10/2026" in index
    # référence et seuil de CV lus dans les données, pas en dur
    assert REFERENCE.machine in index
    assert "CV supérieur à 5 % sur au moins un test" in index
    assert "Généré le" not in index and "généré le 05/10/2026 12:00 UTC" in index
    # renderer brut « Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2) » : nom normalisé
    assert ">Mesa Intel(R) Iris(R) Xe Graphics</td>" in index and "(TGL GT2)" not in index
    # nom du CPU brut (jamais reformaté)
    assert "11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz" in index


def test_each_tab_has_its_page_and_current_link(tmp_path) -> None:
    out = site(tmp_path)
    for name, label in zip(
        CLASSEMENT_PAGES, ("Combiné", "CPU single-core", "CPU multi-core", "GPU"), strict=True
    ):
        html = (out / name).read_text()
        assert f'id="h-rank">{label}</h2>' in html
        assert re.search(rf'href="{name}" data-tab aria-current="page"', html), name


def test_unranked_machines_stay_listed_at_the_end(tmp_path) -> None:
    out = site(tmp_path)
    rows = ranking_rows((out / "index.html").read_text())
    names = [re.search(r'data-name="([^"]*)"', r).group(1) for r in rows]
    assert names[-1] == "Portable sans GPU"  # combiné sans GPU : en fin de liste
    last = rows[-1]
    assert 'data-rank=""' in last and 'data-score=""' in last
    assert ">non classé<" in last and ">—</td>" in last
    assert "1 machine non classée ici, en fin de liste" in (out / "index.html").read_text()
    # visible et classé (premier) dans les onglets CPU, non classé à l'onglet GPU
    single = ranking_rows((out / "cpu-single.html").read_text())
    assert 'data-name="Portable sans GPU"' in single[0] and 'data-rank="1"' in single[0]
    gpu = ranking_rows((out / "gpu.html").read_text())
    assert 'data-name="Portable sans GPU"' in gpu[-1] and ">non classé<" in gpu[-1]


def test_reliability_and_stale_badges(tmp_path) -> None:
    from test_leaderboard_validate import stale_payload

    d = results_dir(tmp_path)
    noisy = [replace(r, stdev=r.value * 0.08) if r.name == "glmark2" else r for r in machine(1.0)]
    write_export(export(noisy, "Bruyant"), d / "bruyant.json")
    (d / "ancien.json").write_text(json.dumps(stale_payload() | {"machine": "Desktop ancien"}))
    rows = {
        re.search(r'data-name="([^"]*)"', r).group(1): r
        for r in ranking_rows((site(tmp_path, d) / "index.html").read_text())
    }
    assert 'data-rel="check"' in rows["Bruyant"] and "À vérifier" in rows["Bruyant"]
    assert 'data-cv="8.00"' in rows["Bruyant"]
    assert 'data-rel="ok"' in rows["Desktop moyen"] and "Fiable" in rows["Desktop moyen"]
    assert "hw-badge--stale" in rows["Desktop ancien"]
    assert "hw-badge--stale" not in rows["Desktop moyen"]


def test_machine_kind_and_brands(tmp_path) -> None:
    d = tmp_path / "results"
    d.mkdir()
    battery = Battery("BAT0", 80, "Discharging", 50.0, 45.0, 10)
    laptop_snapshot = replace(snapshot(), power=PowerData(on_ac=True, batteries=[battery]))
    results = machine(1.0)
    ex = build_export(laptop_snapshot, "Portable", results, score_results(results, REFERENCE))
    write_export(ex, d / "portable.json")
    write_export(export(machine(1.0), "Fixe"), d / "fixe.json")
    rows = ranking_rows((site(tmp_path, d) / "index.html").read_text())
    by_name = {re.search(r'data-name="([^"]*)"', r).group(1): r for r in rows}
    assert 'data-kind="laptop"' in by_name["Portable"] and "Portable</td>" in by_name["Portable"]
    assert 'data-kind="desktop"' in by_name["Fixe"]
    assert 'data-gpub="Intel"' in by_name["Fixe"]  # « Mesa Intel(R) Iris(R) Xe »


def test_memory_and_disk_are_information_only(tmp_path) -> None:
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
    index = (site(tmp_path, d) / "index.html").read_text()
    info = index.split('id="h-info"', 1)[1]
    assert "25 000" in info and "3 347" in info and "239 k" in info
    assert "4 machines sans mesure." in info
    assert not (tmp_path / "_site" / "memory.html").exists()


def test_histogram_needs_ten_machines(tmp_path) -> None:
    index = (site(tmp_path) / "index.html").read_text()
    assert "à partir de 10 machines. Pour l" in index
    assert "3 machines, médiane 1 000 points" in index
    d = tmp_path / "many"
    d.mkdir()
    for i in range(10):
        write_export(export(machine(0.5 + i / 10), f"M{i}"), d / f"m{i}.json")
    out = tmp_path / "many-site"
    build_site(d, out, REFERENCE, generated=NOW)
    html = (out / "index.html").read_text()
    assert 'aria-label="Distribution des scores · Combiné"' in html
    assert "Tranche de points" in html  # tableau équivalent


def test_empty_results_show_the_empty_state(tmp_path) -> None:
    d = tmp_path / "results"
    d.mkdir()
    index = (site(tmp_path, d) / "index.html").read_text()
    assert "Le classement démarre avec vous." in index
    assert index.count("Place libre — soumettez votre machine") == 3
    assert 'id="rank-table"' not in index


def test_unreadable_file_is_skipped_and_listed(tmp_path) -> None:
    d = results_dir(tmp_path)
    (d / "ancien.json").write_text('{"schema_version": 1}')
    out = tmp_path / "_site"
    entries = build_site(d, out, REFERENCE, generated=NOW)
    assert len(entries) == 4
    index = (out / "index.html").read_text()
    assert "Fichiers ignorés" in index and "ancien.json" in index


def test_unreadable_date_does_not_break_the_site(tmp_path) -> None:
    d = results_dir(tmp_path)
    data = json.loads((d / "rapide.json").read_text()) | {"created": "<b>jamais</b>"}
    (d / "rapide.json").write_text(json.dumps(data))
    assert "&lt;b&gt;jamais&lt;/b&gt;" in (site(tmp_path, d) / "index.html").read_text()


# --- Sécurité, liens, assets ---


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()
        self.handlers: list[str] = []
        self.scripts: list[str] = []
        self.images: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag, attrs) -> None:
        self.names.add(tag)
        if tag == "img":
            self.images.append(dict(attrs).get("src") or "")
        self.handlers += [name for name, _ in attrs if name.startswith("on")]
        self._in_script = tag == "script"

    def handle_endtag(self, tag) -> None:
        self._in_script = False

    def handle_data(self, data) -> None:
        if self._in_script:
            self.scripts.append(data)


def test_export_text_is_escaped_everywhere(tmp_path) -> None:
    out = site(tmp_path)
    for path in html_pages(out):
        page = path.read_text()
        assert '<script>alert("x")</script>' not in page, path.name
        tags = _Tags()
        tags.feed(page)
        # aucune balise ni attribut actif venu d'un export (le texte échappé reste lisible)
        assert not tags.handlers, (path.name, tags.handlers)
        assert all("assets/img/" in src for src in tags.images), (path.name, tags.images)
        assert all("alert" not in script for script in tags.scripts), path.name
        # aucune ressource externe ; liens externes seulement vers les adresses connues
        for url in re.findall(r'(?:src|href)="(https?://[^"]*)"', page):
            assert url.startswith(EXTERNAL_OK), (path.name, url)
        assert re.search(r'src="https?://', page) is None
    index = (out / "index.html").read_text()
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt; &amp; &lt;img" in index
    # JSON du catalogue : rien ne peut fermer la balise <script>
    i18n = index.split('id="hw-i18n">', 1)[1].split("</script>", 1)[0]
    assert "<" not in i18n and json.loads(i18n)["copied"] == FR["js"]["copied"]


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs) -> None:
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.urls.append(value)
            if name == "id" and value:
                self.ids.add(value)


def test_internal_links_and_assets_resolve(tmp_path) -> None:
    out = site(tmp_path)
    for path in html_pages(out):
        parser = _Links()
        parser.feed(path.read_text())
        for url in parser.urls:
            parts = urlsplit(url)
            if parts.scheme in ("http", "https", "data"):
                continue
            if not parts.path:  # ancre de la même page
                assert parts.fragment in parser.ids, (path.name, url)
                continue
            target = (path.parent / parts.path).resolve()
            assert target.is_file(), (path.name, url)
    css = (out / "assets" / "hwbench.css").read_text()
    for url in re.findall(r"url\(([^)]+)\)", css):
        assert (out / "assets" / url).is_file(), url


def test_wheel_package_data_lists_every_site_file() -> None:
    """Les motifs package-data du pyproject couvrent chaque template et asset (la CI génère le
    site depuis la wheel installée)."""
    import tomllib

    patterns = tomllib.loads((PACKAGE.parents[2] / "pyproject.toml").read_text())["tool"][
        "setuptools"
    ]["package-data"]["hwbench"]
    root = PACKAGE.parent
    for folder in ("templates", "static"):
        for path in (PACKAGE / folder).rglob("*"):
            if path.is_file():
                rel = path.relative_to(root)
                assert any(
                    rel.match(p) and len(rel.parts) == len(Path(p).parts) for p in patterns
                ), rel


def test_installed_package_has_every_site_file() -> None:
    """Paquet importé (la wheel installée quand la CI relance la suite sur la wheel) : chaque
    template et asset du dépôt y est, à l'identique."""
    from importlib.resources import files

    installed = files("hwbench.leaderboard")
    for folder in ("templates", "static"):
        for path in (PACKAGE / folder).rglob("*"):
            if path.is_file():
                resource = installed.joinpath(*path.relative_to(PACKAGE).parts)
                assert resource.read_bytes() == path.read_bytes(), path.relative_to(PACKAGE)


# --- Catalogue : aucun texte en dur ---


def _visible_text(template: str) -> list[str]:
    """Texte d'un template hors balises Jinja et HTML, et valeurs des attributs lus à voix
    haute (aria-label, title, placeholder, alt) hors expressions."""
    src = re.sub(r"\{#.*?#\}", "", template, flags=re.S)
    attrs = re.findall(r'(?:aria-label|title|placeholder|alt)="([^"]*)"', src)
    src = re.sub(r"<script.*?</script>", "", src, flags=re.S)
    src = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", src, flags=re.S)
    src = re.sub(r"<[^>]*>", " ", src)
    attrs = [re.sub(r"\{\{.*?\}\}", "", a) for a in attrs]
    return [w for w in (src.split() + attrs) if re.search(r"[A-Za-zÀ-ÿ]", w)]


def test_templates_have_no_hardcoded_text() -> None:
    for path in sorted((PACKAGE / "templates").rglob("*.html")):
        assert _visible_text(path.read_text()) == [], path.name


def test_catalog_keys_do_not_shadow_dict_methods() -> None:
    """Jinja lit `t.x.copy` comme la méthode dict.copy : aucune clé ne doit en masquer une."""
    shadowed = set(dir(dict))

    def walk(node: dict, path: str) -> None:
        for key, value in node.items():
            assert key not in shadowed, path + key
            if isinstance(value, dict):
                walk(value, f"{path}{key}.")

    walk(FR, "")


def test_jinja_escapes_by_default() -> None:
    assert ENV.from_string("{{ x }}").render(x="<b>") == "&lt;b&gt;"


# --- data.json et CSV ---


def test_data_json(tmp_path) -> None:
    data = json.loads((site(tmp_path) / "data.json").read_text())
    assert data["schema"] == 1 and data["reference"]["digest"] == REFERENCE.digest
    machines = {m["id"]: m for m in data["machines"]}
    assert machines["rapide"]["points"]["combined"] == 2000.0
    assert machines["portable"]["points"]["combined"] is None
    assert machines["portable"]["points"]["cpu_single"] == 3000.0
    assert machines["piege"]["name"] == EVIL  # brut : l'échappement revient au consommateur
    assert machines["rapide"]["type"] == "desktop" and machines["rapide"]["reliable"]


def test_csv_neutralises_formulas(tmp_path) -> None:
    d = results_dir(tmp_path)
    write_export(export(machine(1.0), "=HYPERLINK(1)"), d / "formule.json")
    lines = (site(tmp_path, d) / "classement.csv").read_text().splitlines()
    assert lines[0].startswith("machine,type,cpu,gpu,points_combined,points_cpu_single")
    assert lines[1].startswith("Desktop rapide,desktop,")
    assert any(line.startswith("'=HYPERLINK(1)") for line in lines)


# --- Preview ---


ROBOTS_META = '<meta name="robots" content="noindex, nofollow">'


def test_production_site_has_no_preview_marks(tmp_path) -> None:
    out = site(tmp_path)
    assert not (out / "robots.txt").exists()
    for path in html_pages(out):
        html = path.read_text()
        assert ROBOTS_META not in html and "preview-banner" not in html
        assert "hw-preview" not in html and "<title>Preview" not in html


def test_preview_site_is_marked_and_not_indexed(tmp_path) -> None:
    out = site(tmp_path, preview=True)
    assert (out / "robots.txt").read_text() == "User-agent: *\nDisallow: /\n"
    pages = html_pages(out)
    assert len(pages) == 8
    for path in pages:
        html = path.read_text()
        assert html.count(ROBOTS_META) == 1, path.name
        assert "<title>Preview · " in html, path.name
        assert html.index("Preview : site généré") < html.index("<h1"), path.name
    # lien vers le classement officiel, dossier parent de /preview/
    assert 'href="../index.html">le classement officiel</a>' in (out / "index.html").read_text()
    machine_page = (out / "machines" / "rapide.html").read_text()
    assert 'href="../../index.html">le classement officiel</a>' in machine_page
    assert 'href="../index.html">← Classement</a>' in machine_page  # reste dans la preview


# --- CLI ---


def test_cli_site(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    out = tmp_path / "_site"
    assert cli.main(["site", "--results", str(results_dir(tmp_path)), "--out", str(out)]) == 0
    assert "(4 machines)" in capsys.readouterr().out
    assert (out / "index.html").exists() and (out / "assets" / "hwbench.css").exists()


def test_cli_site_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    results = str(results_dir(tmp_path))
    out = tmp_path / "preview"
    assert cli.main(["site", "--results", results, "--out", str(out), "--preview"]) == 0
    assert ROBOTS_META in (out / "index.html").read_text()
    assert (out / "robots.txt").exists()


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


def test_generated_site_has_no_ambiguous_plural(tmp_path) -> None:
    for page in html_pages(site(tmp_path)):
        assert "(s)" not in page.read_text(), page.name


def test_real_site_has_no_ambiguous_plural(tmp_path) -> None:
    out = tmp_path / "_site"
    build_site(Path(__file__).parents[1] / "results", out, REFERENCE, generated=NOW)
    for page in html_pages(out):
        assert "(s)" not in page.read_text(), page.name


# --- Page machine (rendu du rapport, jusqu'à la page machine du design) ---


def test_machine_page_details(tmp_path) -> None:
    out = site(tmp_path)
    page = (out / "machines" / "rapide.html").read_text()
    assert "<h1>Desktop rapide</h1>" in page
    assert "results/rapide.json" in page
    assert "2000 pts" in page  # combiné recalculé
    assert "native-cpu-single" in page and "200,0 indice brut" in page
    assert "non classé" in (out / "machines" / "portable.html").read_text()  # GPU et combiné
    assert "mesuré le 03/10/2026" in page  # en-tête : date de l'export
    assert "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)" in page  # détail : renderer complet


def test_machine_page_reuses_the_report_sections(tmp_path) -> None:
    page = (site(tmp_path) / "machines" / "rapide.html").read_text()
    for section in ("classement", "synthese", "conditions", "cpu", "fiabilite", "annexe"):
        assert f'<section id="{section}">' in page, section
    assert '<section id="recommandations">' not in page
    assert "<script" not in page


def test_machine_page_information_rows(tmp_path) -> None:
    d = results_dir(tmp_path)
    with_info = machine(1.0) + [make_result("native-memory-multi", 25_000.0), disk(3347, 238831)]
    write_export(export(with_info, "Avec mémoire et disque"), d / "infos.json")
    page = (site(tmp_path, d) / "machines" / "infos.html").read_text()
    assert "Mémoire (information)" in page
    assert "Lecture aléatoire 4K (QD32)" in page and "<td>1 Gio</td>" in page


def test_machine_page_flags_stale_reference(tmp_path) -> None:
    from test_leaderboard_validate import stale_payload

    d = results_dir(tmp_path)
    (d / "ancien.json").write_text(json.dumps(stale_payload() | {"machine": "Desktop ancien"}))
    entries = {e.slug: e for e in load_entries(d, REFERENCE)[0]}
    assert entries["ancien"].stale and not entries["moyen"].stale
    assert round(category_points(entries["ancien"], None)) == 1000
    out = site(tmp_path, d)
    page = (out / "machines" / "ancien.html").read_text()
    assert "à ré-exporter" in page and "référence antérieure" in page
    assert "à ré-exporter" not in (out / "machines" / "moyen.html").read_text()


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


# --- Extra « site » : Jinja2 optionnel ---


def test_benchmark_cli_does_not_load_jinja2() -> None:
    """Le CLI de benchmark (et la validation, lancée par results.yml) n'importe pas Jinja2 :
    l'extra « site » ne sert qu'à générer le site."""
    import subprocess
    import sys

    code = (
        "import sys, hwbench.cli, hwbench.leaderboard.__main__, hwbench.leaderboard.validate\n"
        "loaded = sorted(m for m in ('jinja2', 'markupsafe') if m in sys.modules)\n"
        "assert not loaded, loaded"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_site_without_the_extra_explains_how_to_install_it(tmp_path, monkeypatch, capsys) -> None:
    import sys

    import pytest

    monkeypatch.setitem(sys.modules, "jinja2", None)  # Jinja2 absent
    for name in ("hwbench.leaderboard.site", "hwbench.leaderboard.charts"):
        monkeypatch.delitem(sys.modules, name)
    with pytest.raises(ModuleNotFoundError, match=r"pip install 'hwbench\[site\]'"):
        import hwbench.leaderboard.site  # noqa: F401
    monkeypatch.setattr(cli, "load_reference", lambda: REFERENCE)
    out = tmp_path / "_site"
    assert cli.main(["site", "--results", str(results_dir(tmp_path)), "--out", str(out)]) == 2
    assert "pip install 'hwbench[site]'" in capsys.readouterr().err
    assert not out.exists()


def test_catalog_has_no_postal_address_or_phone() -> None:
    """Aucune adresse postale ni aucun numéro de téléphone dans les textes du site."""
    address = re.compile(
        r"\b\d{5}\b|\bCA \d|\b(street|avenue|boulevard|rue|bd|chemin|allée)\b"
        r"|(\+\d{1,3}|\b0\d)([ .-]?\d{2}){4}",
        re.IGNORECASE,
    )

    def strings(node: object) -> list[str]:
        if isinstance(node, str):
            return [node]
        if isinstance(node, dict):
            return [s for value in node.values() for s in strings(value)]
        if isinstance(node, list):
            return [s for value in node for s in strings(value)]
        return []

    found = [s for s in strings(FR) if address.search(s)]
    assert found == []
