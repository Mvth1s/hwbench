"""Site statique du classement : index.html (classements par catégorie) + une page par machine.

HTML et CSS intégrés, sans JavaScript (onglets en CSS pur). Les points sont recalculés à partir
des résultats bruts contre la référence actuelle du paquet, jamais repris de l'export. Tout
texte venu d'un export passe par html.escape (un export peut venir de n'importe qui).
"""

import html
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hwbench.display.fmt import compact, fr_date, measure, num
from hwbench.export import ExportError, MachineExport, from_dict
from hwbench.leaderboard.validate import (
    SubmissionError,
    read_bounded,
    resolves_to_itself,
    strict_json,
)
from hwbench.results import Category, Result, gpu_name
from hwbench.scoring import Reference, Scores, score_results

CATEGORY_LABELS = {
    Category.CPU_SINGLE: "CPU single-core",
    Category.CPU_MULTI: "CPU multi-core",
    Category.GPU: "GPU",
}
UNIT_LABELS = {"MiB/s": "Mio/s", "index": "indice brut"}


@dataclass(frozen=True)
class Entry:
    slug: str  # nom du fichier sans .json (validé : minuscules, chiffres, tirets)
    export: MachineExport
    scores: Scores


def e(value: object) -> str:
    """Texte échappé pour HTML (contenu et attributs entre guillemets)."""
    return html.escape("" if value is None else str(value), quote=True)


def load_entries(results_dir: Path, reference: Reference) -> tuple[list[Entry], list[str]]:
    """Exports lisibles du dossier, et la liste des fichiers ignorés (avec la raison)."""
    entries, skipped = [], []
    if not resolves_to_itself(results_dir):
        return [], [f"{results_dir} : lien symbolique refusé, aucun résultat lu"]
    for path in sorted(results_dir.glob("*.json")):
        try:
            export = from_dict(strict_json(read_bounded(path)))
        except (SubmissionError, ExportError, UnicodeDecodeError, ValueError) as exc:
            skipped.append(f"{path.name} : {exc}")
            continue
        entries.append(Entry(path.stem, export, score_results(export.results, reference)))
    return entries, skipped


def category_points(entry: Entry, category: Category | None) -> float | None:
    """Points de la catégorie, ou du combiné (None) s'il porte sur toutes les catégories."""
    if category is None:
        combined = entry.scores.combined
        # un combiné sans GPU n'a pas la même composition que la référence : pas classé
        if combined is None or combined.gpu_missing:
            return None
        return combined.points
    score = next((c for c in entry.scores.categories if c.category is category), None)
    return score.points if score else None


def ranking(entries: Iterable[Entry], category: Category | None) -> list[tuple[Entry, float]]:
    ranked = [
        (entry, p) for entry in entries if (p := category_points(entry, category)) is not None
    ]
    return sorted(ranked, key=lambda item: (-item[1], item[0].slug))


def _gpu(export: MachineExport) -> str | None:
    gpu = export.snapshot.gpu
    return (
        gpu.opengl_renderer
        or gpu.vulkan_device_name
        or (gpu.pci_devices[0].model if gpu.pci_devices else None)
    )


def _ram_gb(export: MachineExport) -> float | None:
    ram = export.snapshot.ram
    return ram.installed_gb if ram.installed_gb is not None else ram.total_gb


CSS = """
:root { color-scheme: light dark; --fg: #1d2129; --bg: #fff; --muted: #5f6b7a;
  --line: #d9dee5; --accent: #0b6bcb; --row: #f4f6f9; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6e9ee; --bg: #14171c;
  --muted: #9aa5b4; --line: #2c323b; --accent: #5aa9ff; --row: #1b1f26; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1100px; padding: 24px 16px; font: 15px/1.5 system-ui,
  sans-serif; color: var(--fg); background: var(--bg); }
h1 { margin: 0 0 4px; } h2 { margin-top: 32px; }
a { color: var(--accent); }
.muted { color: var(--muted); } .small { font-size: 13px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
tbody tr:nth-child(odd) { background: var(--row); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tabs > input { position: absolute; opacity: 0; }
.tabs > label { display: inline-block; padding: 6px 14px; margin: 0 4px 0 0;
  border: 1px solid var(--line); border-radius: 6px; cursor: pointer; }
.tabs > input:checked + label { background: var(--accent); color: var(--bg);
  border-color: var(--accent); }
.tabs > input:focus-visible + label { outline: 2px solid var(--accent); outline-offset: 2px; }
.panel { display: none; }
#tab-combined:checked ~ #panel-combined, #tab-cpu_single:checked ~ #panel-cpu_single,
#tab-cpu_multi:checked ~ #panel-cpu_multi, #tab-gpu:checked ~ #panel-gpu { display: block; }
"""


def _page(title: str, body: str, generated: datetime) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<p class="muted small">Généré le {e(generated.strftime("%d/%m/%Y %H:%M"))} UTC par hwbench.
Résultats déclaratifs, soumis par pull request.
<a href="https://github.com/Mvth1s/hwbench">Dépôt</a> ·
<a href="https://github.com/Mvth1s/hwbench/blob/main/CONTRIBUTING.md">Soumettre un résultat</a></p>
</body>
</html>
"""


def _reference_block(reference: Reference) -> str:
    rows = "".join(
        f"<tr><td>{e(entry.id.name)}</td><td>v{e(entry.id.version)}</td>"
        f"<td>{e(entry.id.tool_version or '—')}</td><td>{e(entry.id.presentation or '—')}</td>"
        f"<td>{e(CATEGORY_LABELS[entry.category])}</td></tr>"
        for entry in reference.entries
    )
    return f"""<h2>Référence et versions</h2>
<p>Chaque bench vaut <strong>1000 points</strong> sur la machine de référence
<strong>{e(reference.machine)}</strong> (mesurée le {e(fr_date(reference.created))},
empreinte <code>{e(reference.digest[:19])}</code>). Seuls les résultats obtenus avec les mêmes
versions de protocole, d'outil et le même mode de présentation sont notés.</p>
<table><thead><tr><th>Bench</th><th>Protocole</th><th>Outil</th><th>Présentation</th>
<th>Catégorie</th></tr></thead><tbody>{rows}</tbody></table>"""


def _ranking_table(ranked: list[tuple[Entry, float]]) -> str:
    if not ranked:
        return '<p class="muted">Aucune machine classée dans cette catégorie.</p>'
    rows = []
    for rank, (entry, points) in enumerate(ranked, start=1):
        ex = entry.export
        rows.append(
            f'<tr><td class="num">{rank}</td>'
            f'<td><a href="machines/{e(entry.slug)}.html">{e(ex.machine)}</a></td>'
            # nom normalisé (sans pilote, noyau ni DRM), casse d'origine
            f"<td>{e(ex.snapshot.cpu.model or '?')}</td><td>{e(gpu_name(_gpu(ex)) or '?')}</td>"
            f'<td class="num"><strong>{e(num(points, 0))}</strong></td>'
            f'<td class="small muted">{e(fr_date(ex.created))}</td></tr>'
        )
    return (
        '<table><thead><tr><th class="num">#</th><th>Machine</th><th>CPU</th><th>GPU</th>'
        '<th class="num">Points</th><th>Date</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_index(
    entries: list[Entry], reference: Reference, skipped: list[str], generated: datetime
) -> str:
    tabs: list[tuple[str, str, Category | None]] = [("combined", "Score combiné", None)]
    tabs += [(c.value, CATEGORY_LABELS[c], c) for c in CATEGORY_LABELS]
    radios = "".join(
        f'<input type="radio" name="cat" id="tab-{key}"{" checked" if i == 0 else ""}>'
        f'<label for="tab-{key}">{e(label)}</label>'
        for i, (key, label, _) in enumerate(tabs)
    )
    panels = []
    for key, label, category in tabs:
        ranked = ranking(entries, category)
        unranked = len(entries) - len(ranked)
        note = (
            f'<p class="muted small">{unranked} machine(s) non classée(s) ici : catégorie non '
            "mesurée, non comparable à la référence"
            + (", ou score combiné calculé sans GPU" if category is None else "")
            + ".</p>"
            if unranked
            else ""
        )
        panels.append(
            f'<section class="panel" id="panel-{key}"><h2>{e(label)}</h2>'
            f"{_ranking_table(ranked)}{note}</section>"
        )
    skipped_html = (
        "<h2>Fichiers ignorés</h2><ul>" + "".join(f"<li>{e(s)}</li>" for s in skipped) + "</ul>"
        if skipped
        else ""
    )
    body = f"""<h1>hwbench · classement</h1>
<p class="muted">{len(entries)} machine(s). Benchmarks CPU et GPU notés contre une machine de
référence (1000 points). Score combiné : moyenne géométrique des trois catégories.</p>
<div class="tabs">{radios}{"".join(panels)}</div>
{_reference_block(reference)}
{skipped_html}"""
    return _page("hwbench · classement", body, generated)


def _kv(rows: Iterable[tuple[str, object]]) -> str:
    return (
        "<table><tbody>"
        + "".join(
            f"<tr><th>{e(k)}</th><td>{e(v if v not in (None, '') else '—')}</td></tr>"
            for k, v in rows
        )
        + "</tbody></table>"
    )


def _bench_rows(results: list[Result], scores: Scores) -> str:
    by_name = {s.backend.name: s for s in scores.backends}
    rows = []
    for r in results:
        score = by_name.get(r.name)
        points = num(score.points, 0) if score and score.points is not None else "non comparable"
        cv = num(r.cv_percent) + " %"
        rows.append(
            f"<tr><td>{e(r.name)}</td><td>v{e(r.version)}</td><td>{e(r.tool_version or '—')}</td>"
            f"<td>{e(r.presentation or '—')}</td>"
            f'<td class="num">{e(measure(r.value))} {e(UNIT_LABELS.get(r.unit, r.unit))}</td>'
            f'<td class="num">{e(cv)}</td><td class="num">{e(points)}</td>'
            f'<td class="small">{e(r.environment.get("driver", "—"))}</td></tr>'
        )
    return (
        "<table><thead><tr><th>Bench</th><th>Protocole</th><th>Outil</th><th>Présentation</th>"
        '<th class="num">Valeur (médiane)</th><th class="num">CV</th><th class="num">Points</th>'
        "<th>Pilote</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render_machine(entry: Entry, reference: Reference, generated: datetime) -> str:
    ex = entry.export
    snap = ex.snapshot
    ram = _ram_gb(ex)
    disks = ", ".join(
        f"{d.model or d.name} ({compact(round(d.size_bytes / 1024**3))} Gio)"
        if d.size_bytes
        else (d.model or d.name)
        for d in snap.disks.disks
    )
    components = _kv(
        [
            ("Machine", ex.machine),
            ("CPU", snap.cpu.model),
            (
                "Cœurs / threads",
                f"{snap.cpu.physical_cores or '?'} / {snap.cpu.logical_cores or '?'}",
            ),
            ("GPU", _gpu(ex)),
            ("RAM", f"{compact(round(ram, 1))} Gio" if ram is not None else None),
            (
                "Carte mère",
                " ".join(filter(None, [snap.board.board_vendor, snap.board.board_name])),
            ),
            ("Disques", disks),
        ]
    )
    scores = [(CATEGORY_LABELS[c], category_points(entry, c)) for c in CATEGORY_LABELS] + [
        ("Score combiné", category_points(entry, None))
    ]
    score_rows = "".join(
        f'<tr><th>{e(label)}</th><td class="num">'
        f"{e(num(points, 0) + ' pts' if points is not None else 'non classé')}</td></tr>"
        for label, points in scores
    )
    state = ex.results[0].state_before if ex.results else None
    conditions = _kv(
        [
            ("Exporté le", fr_date(ex.created)),
            ("Version de hwbench", ex.hwbench_version),
            ("Governor", ", ".join(state.governors) if state else None),
            ("EPP", state.energy_performance_preference if state else None),
            ("Profil plateforme", state.platform_profile if state else None),
            (
                "Alimentation",
                None
                if not state or state.on_ac is None
                else ("secteur" if state.on_ac else "batterie"),
            ),
        ]
    )
    body = f"""<p><a href="../index.html">← Classement</a></p>
<h1>{e(ex.machine)}</h1>
<p class="muted">Fichier <code>results/{e(entry.slug)}.json</code></p>
<h2>Scores</h2>
<table><tbody>{score_rows}</tbody></table>
<p class="muted small">Recalculés contre la référence {e(reference.machine)} (1000 points).</p>
<h2>Composants</h2>
{components}
<h2>Benchmarks</h2>
{_bench_rows(ex.results, entry.scores)}
<h2>Conditions de mesure</h2>
{conditions}"""
    return _page(f"{ex.machine} · hwbench", body, generated)


def build_site(
    results_dir: Path, out_dir: Path, reference: Reference, generated: datetime | None = None
) -> list[Entry]:
    generated = generated or datetime.now(UTC)
    entries, skipped = load_entries(results_dir, reference)
    (out_dir / "machines").mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(
        render_index(entries, reference, skipped, generated), encoding="utf-8"
    )
    for entry in entries:
        (out_dir / "machines" / f"{entry.slug}.html").write_text(
            render_machine(entry, reference, generated), encoding="utf-8"
        )
    # GitHub Pages : pas de traitement Jekyll
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return entries
