"""Rapport HTML : snapshot, aller-retour JSON, hors ligne, vie privée, sections partielles.

Snapshot : tests/fixtures/report/session.html, rendu de session.json. Dans cette session, CPU,
GPU, composants et états machine sont réels (export du Dell, copie figée dans
tests/fixtures/exports/dell-latitude-5420-schema2.json, passé au schéma 3) ; les résultats
mémoire et disque sont synthétiques, des valeurs construites pour couvrir ces sections (voir
tests/fixtures/report/README.md).

Pour accepter le snapshot après un changement voulu du gabarit :
HWBENCH_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/test_report.py
"""

import json
import os
import re
from dataclasses import replace
from html import escape as html_escape
from pathlib import Path

import pytest
from conftest import make_result
from test_fixtures_privacy import _live_identifiers
from test_leaderboard_site import EVIL
from test_scoring import REFERENCE, machine, snapshot

from hwbench import __version__, privacy
from hwbench.export import build_export, load_export, to_dict, write_export
from hwbench.report import DEFAULT_SETTINGS_NOTE, render_report
from hwbench.runner import RunSettings
from hwbench.scoring import score_results

FIXTURES = Path(__file__).parent / "fixtures" / "report"
SESSION = FIXTURES / "session.json"
EXPECTED = FIXTURES / "session.html"
EXPORTS = Path(__file__).parent / "fixtures" / "exports"  # copies figées, jamais results/
DELL = EXPORTS / "dell-latitude-5420-schema2.json"
B850 = EXPORTS / "asrock-b850-riptide-wifi-schema2.json"
VERSION_MARK = "@@HWBENCH_VERSION@@"


def rendered() -> str:
    return render_report(load_export(SESSION))


def embedded(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="hwbench-session">(.*?)</script>', html, re.S
    )
    assert match is not None
    return json.loads(match.group(1))


def test_snapshot() -> None:
    # la version de hwbench (pied de page) change à chaque release : neutralisée
    footer = "Rapport généré par hwbench "
    html = rendered().replace(footer + __version__, footer + VERSION_MARK)
    if os.environ.get("HWBENCH_UPDATE_SNAPSHOTS"):
        EXPECTED.write_text(html, encoding="utf-8")
    assert html == EXPECTED.read_text(encoding="utf-8")


def test_deterministic_and_roundtrip(tmp_path) -> None:
    session = load_export(SESSION)
    direct = render_report(session)
    assert render_report(session) == direct
    path = tmp_path / "session.json"
    write_export(session, path)
    assert render_report(load_export(path)) == direct


def test_every_section_of_a_full_session() -> None:
    html = rendered()
    for key in (
        "synthese",
        "conditions",
        "cpu",
        "gpu",
        "memoire",
        "disque",
        "temperatures",
        "fiabilite",
        "composants",
        "recommandations",
        "lexique",
        "annexe",
    ):
        assert f'<section id="{key}">' in html, key
    assert 'class="tiles"' in html
    assert "Température CPU maximale relevée avant et après chaque test" in html
    assert "pas pendant" in html  # légende de la frise
    assert "cache des SSD" in html and "btrfs" in html
    assert "sudo &quot;$(command -v hwbench)&quot; info" in html
    assert "sudo hwbench" not in html


def test_offline_single_file() -> None:
    html = rendered()
    assert re.search(r'(src|href)\s*=\s*"\s*https?:', html) is None
    assert "@import" not in html and "url(" not in html
    assert re.search(r"<script(?![^>]*application/json)", html) is None
    assert '<link rel="stylesheet"' not in html


def test_embedded_json_is_the_scrubbed_session() -> None:
    session = load_export(SESSION)
    data = embedded(render_report(session))
    assert data == to_dict(session)
    assert privacy.scrub(data) == data


def test_no_identifier() -> None:
    html = rendered()
    assert "FAKE" not in html and privacy.REDACTED not in html
    for value in _live_identifiers():
        assert value.lower() not in html.lower()


def test_text_from_the_session_is_escaped() -> None:
    session = build_export(snapshot(), EVIL, [make_result("native-cpu-single", 100.0)], None)
    html = render_report(session)
    assert "<img" not in html and re.search(r"<script(?![^>]*application/json)", html) is None
    assert "&lt;script&gt;" in html
    # « </script> » d'un export ne ferme pas le bloc JSON
    assert embedded(html)["machine"] == EVIL


def test_partial_session_has_only_measured_sections() -> None:
    results = [make_result("native-cpu-single", 100.0)]
    html = render_report(build_export(snapshot(), "m", results, score_results(results, REFERENCE)))
    assert '<section id="cpu">' in html
    for absent in ("gpu", "memoire", "disque"):
        assert f'<section id="{absent}">' not in html


def test_schema_2_uses_default_thresholds_and_says_so() -> None:
    html = render_report(load_export(DELL))
    note = html_escape(DEFAULT_SETTINGS_NOTE)
    assert note in html
    assert note not in rendered()


@pytest.mark.parametrize("path", [DELL, B850], ids=lambda p: p.stem)
def test_real_exports_render(path: Path) -> None:
    html = render_report(load_export(path))
    assert html.startswith("<!doctype html>") and html.endswith("</html>\n")
    assert '<section id="synthese">' in html


def test_settings_of_the_session_are_cited() -> None:
    session = load_export(SESSION)
    strict = replace(session, settings=replace(session.settings, high_variance_cv_percent=2.0))
    assert "au-delà du seuil de 2 %" in render_report(strict)


def test_conditions_tile_says_why() -> None:
    html = render_report(load_export(DELL))
    assert (
        '<div class="label">Conditions de mesure</div><div class="value"><span class="status '
        'status-check">À vérifier</span></div><div class="small muted">4 départs chauds</div>'
    ) in html
    b850 = render_report(load_export(B850))
    assert 'Fiable</span></div><div class="small muted">secteur, meilleur réglage' in b850


def test_start_temperature_row_gives_the_range() -> None:
    html = render_report(load_export(DELL))
    assert "<td>51 à 72 °C</td>" in html
    assert "4 tests ont démarré à 70 °C ou plus (seuil de départ chaud)." in html


@pytest.mark.parametrize("path", [SESSION, DELL, B850])
def test_no_ambiguous_plural_or_strict_threshold_wording(path: Path) -> None:
    html = render_report(load_export(path))
    assert "(s)" not in html and "au-dessus du seuil" not in html


def _session_html(results, settings: RunSettings) -> str:
    scores = score_results(results, REFERENCE)
    return render_report(build_export(snapshot(), "m", results, scores, settings=settings))


def test_cooldown_pauses_are_listed_in_the_conditions() -> None:
    results = [
        replace(r, cooldown_s=42.0 if r.name == "native-cpu-multi" else 0.0) for r in machine(1.0)
    ]
    html = _session_html(results, RunSettings(cooldown_auto=True, cooldown_timeout_s=120.0))
    assert "Refroidissement" in html and "42 s au total" in html
    assert "Mode auto : attente du passage sous 70 °C, au plus 120 s" in html
    assert "Pauses : CPU multi-core (natif) 42 s." in html


def test_no_cooldown_row_without_the_option() -> None:
    assert "Refroidissement" not in _session_html(machine(1.0), RunSettings())


def test_cooldown_enabled_without_any_pause() -> None:
    html = _session_html(machine(1.0), RunSettings(cooldown_s=30.0))
    assert "aucune attente" in html
    assert "Pause fixe de 30 s à chaque changement de catégorie." in html


def test_key_figures_say_why_the_gpu_is_left_out() -> None:
    def html(results):
        scores = score_results(results, REFERENCE)
        return render_report(build_export(snapshot(), "m", results, scores))

    assert "sans GPU (incomplet)" in html([r for r in machine(1.0) if r.name != "vkmark"])
    cpu_only = [r for r in machine(1.0) if r.name not in ("glmark2", "vkmark")]
    assert "sans GPU (non mesuré)" in html(cpu_only)
