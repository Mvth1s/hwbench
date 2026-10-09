"""Site statique du classement : index.html (classements par catégorie) + une page par machine.

HTML et CSS intégrés (moteur commun report/html.py), sans JavaScript (onglets en CSS pur). La
page machine assemble les sections du rapport (report/sections.py), sans recommandations ni
JSON embarqué, avec les seuils par défaut. Les points sont recalculés à partir des résultats
bruts contre la référence actuelle du paquet, jamais repris de l'export. Tout texte venu d'un
export passe par html.escape (un export peut venir de n'importe qui).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from hwbench.analysis import analyze
from hwbench.display.fmt import compact, fr_date, num
from hwbench.export import ExportError, MachineExport, from_dict
from hwbench.labels import CATEGORY_LABELS
from hwbench.leaderboard.validate import (
    SubmissionError,
    read_bounded,
    resolves_to_itself,
    strict_json,
)
from hwbench.report.html import e, page
from hwbench.report.sections import Context, render_sections
from hwbench.report.texts import plural
from hwbench.results import COMBINED_CATEGORIES, Category, gpu_name
from hwbench.runner import RunSettings
from hwbench.scoring import Reference, Scores, score_results

# Mémoire et disque : colonnes d'information, jamais classées ni dans le combiné
INFO_CATEGORIES = tuple(c for c in Category if c not in COMBINED_CATEGORIES)


@dataclass(frozen=True)
class Entry:
    slug: str  # nom du fichier sans .json (validé : minuscules, chiffres, tirets)
    export: MachineExport
    scores: Scores


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


def info_value(entry: Entry, category: Category) -> str | None:
    """Colonne d'information : points s'ils sont calculables contre la référence, sinon la
    valeur brute (mémoire : copie multi-processus ; disque : lecture séquentielle et 4K)."""
    points = category_points(entry, category)
    if points is not None:
        return f"{num(points, 0)} pts"
    results = {r.name: r for r in entry.export.results}
    if category is Category.MEMORY:
        r = results.get("native-memory-multi") or results.get("native-memory-single")
        return f"{num(r.value, 0)} Mio/s" if r else None
    if category is Category.DISK and (r := results.get("fio-disk")) is not None:
        seq, rand = r.details.get("seq_read"), r.details.get("rand_read_4k")
        parts = [
            f"{num(seq, 0)} Mio/s" if seq else None,
            f"{num(rand, 0)} IOPS 4K" if rand else None,
        ]
        return " · ".join(p for p in parts if p) or None
    return None


def _gpu(export: MachineExport) -> str | None:
    gpu = export.snapshot.gpu
    return (
        gpu.opengl_renderer
        or gpu.vulkan_device_name
        or (gpu.pci_devices[0].model if gpu.pci_devices else None)
    )


def _page(title: str, body: str, generated: datetime) -> str:
    footer = (
        f"Généré le {e(generated.strftime('%d/%m/%Y %H:%M'))} UTC par hwbench. Résultats "
        "déclaratifs, soumis par pull request. "
        '<a href="https://github.com/Mvth1s/hwbench">Dépôt</a> · '
        '<a href="https://github.com/Mvth1s/hwbench/blob/main/CONTRIBUTING.md">Soumettre un '
        "résultat</a>"
    )
    return page(title, body, footer)


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
            + "".join(
                f'<td class="num small">{e(info_value(entry, c) or "—")}</td>'
                for c in INFO_CATEGORIES
            )
            + f'<td class="small muted">{e(fr_date(ex.created))}</td></tr>'
        )
    info_headers = "".join(f'<th class="num">{e(CATEGORY_LABELS[c])}</th>' for c in INFO_CATEGORIES)
    return (
        '<table><thead><tr><th class="num">#</th><th>Machine</th><th>CPU</th><th>GPU</th>'
        f'<th class="num">Points</th>{info_headers}<th>Date</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        + '<p class="muted small">Mémoire (bande passante de copie multi-processus) et disque '
        "(lecture séquentielle, lecture aléatoire 4K) : colonnes d'information, hors classement "
        "et hors score combiné.</p>"
    )


def render_index(
    entries: list[Entry], reference: Reference, skipped: list[str], generated: datetime
) -> str:
    tabs: list[tuple[str, str, Category | None]] = [("combined", "Score combiné", None)]
    tabs += [(c.value, CATEGORY_LABELS[c], c) for c in COMBINED_CATEGORIES]
    radios = "".join(
        f'<input type="radio" name="cat" id="tab-{key}"{" checked" if i == 0 else ""}>'
        f'<label for="tab-{key}">{e(label)}</label>'
        for i, (key, label, _) in enumerate(tabs)
    )
    panels = []
    for key, label, category in tabs:
        ranked = ranking(entries, category)
        unranked = len(entries) - len(ranked)
        unranked_text = plural(unranked, "machine non classée", "machines non classées")
        note = (
            f'<p class="muted small">{unranked_text} ici : catégorie non '
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
    count = plural(len(entries), "machine", "machines")
    body = f"""<h1>hwbench · classement</h1>
<p class="muted">{count}. Benchmarks CPU et GPU notés contre une machine de
référence (1000 points). Score combiné : moyenne géométrique des trois catégories. Mémoire et
disque : information, hors classement.</p>
<div class="tabs">{radios}{"".join(panels)}</div>
{_reference_block(reference)}
{skipped_html}"""
    return _page("hwbench · classement", body, generated)


SETTING_LABELS = {
    "runs": ("runs", ""),
    "max_warmup_s": ("plafond du warm-up", " s"),
    "warmup_tolerance_percent": ("tolérance du warm-up", " %"),
    "high_variance_cv_percent": ("seuil de CV", " %"),
    "hot_start_c": ("départ chaud", " °C"),
    "reliable_cv_percent": ("seuil de très bonne reproductibilité", " %"),
}


def settings_note(measured: RunSettings | None) -> str:
    """Le site analyse toujours avec les seuils par défaut, jamais ceux du fichier soumis : il
    le dit, et cite les seuils de la mesure qui en diffèrent."""
    default = RunSettings()
    if measured is None:
        return (
            "Seuils par défaut, comme pour toutes les machines du classement (réglages de la "
            "mesure non enregistrés dans ce fichier)."
        )
    changed = []
    for name, (label, unit) in SETTING_LABELS.items():
        ours, theirs = getattr(default, name), getattr(measured, name)
        if ours != theirs:
            shown = "défaut" if theirs is None else f"{compact(theirs)}{unit}"
            normal = "défaut" if ours is None else f"{compact(ours)}{unit}"
            changed.append(f"{label} {shown} au lieu de {normal}")
    if not changed:
        return "Seuils par défaut, identiques à ceux de la mesure."
    return (
        "Les seuils de la mesure diffèrent des seuils par défaut ("
        + ", ".join(changed)
        + ") : cette page applique les seuils par défaut, comme pour toutes les machines du "
        "classement."
    )


def _ranking_block(entry: Entry) -> str:
    rows = [(CATEGORY_LABELS[c], category_points(entry, c)) for c in COMBINED_CATEGORIES]
    rows.append(("Score combiné", category_points(entry, None)))
    cells = "".join(
        f'<tr><th>{e(label)}</th><td class="num">'
        f"{e(num(points, 0) + ' pts' if points is not None else 'non classé')}</td></tr>"
        for label, points in rows
    ) + "".join(
        f'<tr><th>{e(CATEGORY_LABELS[c])} (information)</th><td class="num">{e(value)}</td></tr>'
        for c in INFO_CATEGORIES
        if (value := info_value(entry, c)) is not None
    )
    return (
        '<section id="classement"><h2>Classement</h2>'
        f"<table><tbody>{cells}</tbody></table></section>"
    )


def render_machine(entry: Entry, reference: Reference, generated: datetime) -> str:
    """Page machine : sections du rapport (mêmes graphiques, même synthèse), sans
    recommandations ni JSON embarqué. Points recalculés contre la référence du paquet, analyse
    avec les seuils par défaut."""
    ex = entry.export
    scored = replace(
        ex,
        backend_scores=entry.scores.backends,
        categories=entry.scores.categories,
        combined=entry.scores.combined,
        reference=reference.info(),
    )
    settings = RunSettings()
    ctx = Context(scored, analyze(scored, settings), settings, settings_note(ex.settings))
    intro = (
        '<p><a href="../index.html">← Classement</a></p>'
        f'<p class="muted">Fichier <code>results/{e(entry.slug)}.json</code> · points recalculés '
        f"contre la référence {e(reference.machine)} (1000 points).</p>"
    )
    sections = render_sections(
        ctx, with_recommendations=False, embed_json=False, after_header=_ranking_block(entry)
    )
    return _page(f"{ex.machine} · hwbench", intro + sections, generated)


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
