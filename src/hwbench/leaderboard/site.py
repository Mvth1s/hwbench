"""Site statique du classement (GitHub Pages), rendu par des templates Jinja2.

Pages : index.html (classement combiné) et une page par catégorie classée (cpu-single.html,
cpu-multi.html, gpu.html : onglets lisibles sans JavaScript), une page par machine, data.json et
classement.csv. CSS, JavaScript, polices et images sont des fichiers statiques du paquet
(leaderboard/static/), copiés dans <out>/assets/ ; aucune ressource externe. Chaque page est
complète sans JavaScript, qui n'ajoute que tri, filtres, pagination, bascule de thème et popups.

Les points sont recalculés à partir des résultats bruts contre la référence actuelle du paquet,
jamais repris de l'export (entries.py). Jinja échappe tout texte (autoescape) : un export peut
venir de n'importe qui. Les textes du site viennent du catalogue (catalog.py).
"""

import json
import math
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from hwbench import __version__
from hwbench.analysis import analyze
from hwbench.display.fmt import compact, fr_date, grouped, num
from hwbench.labels import CATEGORY_LABELS
from hwbench.leaderboard import charts
from hwbench.leaderboard.catalog import (
    FR,
    GITHUB,
    category_label,
    machines,
    unranked_machines,
)
from hwbench.leaderboard.entries import (
    INFO_CATEGORIES,
    Entry,
    category_points,
    load_entries,
    ranking,
)
from hwbench.leaderboard.views import (
    CATEGORY_KEYS,
    PAGE_FILES,
    MachineView,
    csv_text,
    data_json,
    machine_view,
    median,
    ranked,
)
from hwbench.report.html import e, page
from hwbench.report.sections import Context, render_sections
from hwbench.results import COMBINED_CATEGORIES, Category
from hwbench.runner import RunSettings
from hwbench.scoring import Reference

__all__ = ["Entry", "build_site", "category_points", "load_entries", "ranking", "settings_note"]

ENV = Environment(
    loader=PackageLoader("hwbench.leaderboard", "templates"),
    autoescape=select_autoescape(default=True, default_for_string=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)

# Pages du site, dans l'ordre de la navigation : fichier de sortie. Seules les pages déjà
# générées (PAGES) apparaissent dans la navigation et le pied de page.
PAGE_HREFS = {
    "classement": "index.html",
    "comparaison": "comparaison.html",
    "methodologie": "methodologie.html",
    "soumettre": "soumettre.html",
    "mentions": "mentions-legales.html",
}
PAGES = frozenset({"classement"})
CONTRIBUTING = f"{GITHUB}/blob/main/CONTRIBUTING.md"
HIST_MIN = 10  # machines classées à partir desquelles la distribution est tracée
INFO_TOP = 8  # machines affichées par graphique mémoire / disque
KIND_MARKS = {"desktop": "●", "laptop": "■"}
REL_MARKS = {"ok": "●", "check": "▲"}
ROBOTS = "User-agent: *\nDisallow: /\n"


def _json_script(data: object) -> Markup:
    """JSON à placer dans un <script type="application/json"> : <, > et & échappés, aucune
    chaîne ne peut fermer la balise."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, code in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        text = text.replace(char, code)
    return Markup(text)


def _href(key: str, root: str) -> str | None:
    return root + PAGE_HREFS[key] if key in PAGES else None


def _common(
    page_key: str, title: str, root: str, generated: datetime, preview: bool
) -> dict[str, Any]:
    """Contexte commun à toutes les pages (layout, en-tête, pied de page)."""
    t = FR
    links = {key: _href(key, root) for key in PAGE_HREFS}
    nav = [
        {"key": key, "href": href, "label": t["header"]["nav"][key]}
        for key in ("classement", "comparaison", "methodologie", "soumettre")
        if (href := links[key])
    ]
    flinks = t["footer"]["links"]
    rank_col = [
        {"href": href, "label": flinks[key], "external": False}
        for key in ("classement", "comparaison", "methodologie", "soumettre")
        if (href := links[key])
    ]
    if not links["soumettre"]:
        rank_col.append({"href": CONTRIBUTING, "label": flinks["contributing"], "external": True})
    project = [
        {"href": href, "label": flinks[key], "external": True}
        for key, href in (
            ("github", GITHUB),
            ("issues", f"{GITHUB}/issues"),
            ("releases", f"{GITHUB}/releases"),
            ("license", f"{GITHUB}/blob/main/LICENSE"),
        )
    ]
    columns = [
        {"title": t["footer"]["col_rank"], "links": rank_col},
        {"title": t["footer"]["col_project"], "links": project},
    ]
    if links["mentions"]:
        columns.append(
            {
                "title": t["footer"]["col_legal"],
                "links": [
                    {"href": f"{links['mentions']}#{anchor}", "label": flinks[anchor]}
                    | {"external": False}
                    for anchor in ("mentions", "confidentialite", "accessibilite", "cookies")
                ],
            }
        )
    return {
        "t": t,
        "page": page_key,
        "title": title,
        "root": root,
        "assets": root + "assets/",
        "preview": preview,
        "version": __version__,
        "generated_txt": generated.strftime("%d/%m/%Y %H:%M"),
        "generated_day": generated.date().isoformat(),
        "links": links,
        "nav": nav,
        "footer_columns": columns,
        "submit_href": links["soumettre"] or CONTRIBUTING,
        "cv_threshold": compact(RunSettings().high_variance_cv_percent),
        "tip_keys": [],
        "i18n_json": _json_script(t["js"]),
    }


def _frac(value: float, top: float) -> str:
    return f"{max(0.004, value / top if top else 0.0):.4f}"


def _row(rank: int | None, v: MachineView, key: str, top: float) -> dict[str, Any]:
    score = v.points[key]
    rel = "ok" if v.reliable else "check"
    return {
        "rank": rank,
        "rank_txt": f"{rank:02d}" if rank else "—",
        "href": f"machines/{v.slug}.html",
        "name": v.name,
        "cpu": v.cpu or "—",
        "gpu": v.gpu or "—",
        "kind": v.kind,
        "kind_mark": KIND_MARKS[v.kind],
        "kind_label": FR["kinds"][v.kind],
        "cpu_brand": v.cpu_brand,
        "gpu_brand": v.gpu_brand or "",
        "score": None if score is None else grouped(score),
        "score_raw": "" if score is None else f"{score:.1f}",
        "frac": _frac(score or 0.0, top),
        "rel": rel,
        "rel_mark": REL_MARKS[rel],
        "rel_label": FR["reliability"][rel],
        "cv": "" if v.cv_max is None else f"{v.cv_max:.2f}",
        "stale": v.stale,
        "date": v.date or "",
        "date_txt": fr_date(v.date) or "—",
    }


def _bars(views: list[MachineView], value: Any, scale: float = 1.0, suffix: str = "") -> list:
    """Barres d'information (mémoire, disque) : meilleures machines, valeur brute."""
    measured = sorted(
        ((v, x) for v in views if (x := value(v)) is not None), key=lambda item: -item[1]
    )[:INFO_TOP]
    top = measured[0][1] if measured else 0.0
    return [
        {"label": v.name, "frac": _frac(x, top), "display": grouped(x / scale) + suffix}
        for v, x in measured
    ]


def classement_context(
    views: list[MachineView],
    key: str,
    reference: Reference,
    generated: datetime,
    skipped: list[str],
    preview: bool,
) -> dict[str, Any]:
    c = FR["classement"]
    label = category_label(key)
    title = c["title"].replace("{category}", label)
    ctx = _common("classement", title, "", generated, preview)
    ctx["tip_keys"] = ["points", "geomean", "cv", "fio", "iops"]
    table = ranked(views, key)
    scores = [s for _, v in table if (s := v.points[key]) is not None]
    top = scores[0] if scores else 0.0
    podium = []
    for pos in (1, 2, 3):
        if pos <= len(scores):
            v = table[pos - 1][1]
            podium.append(
                {
                    "pos": pos,
                    "filled": True,
                    "href": f"machines/{v.slug}.html",
                    "name": v.name,
                    "sub": f"{v.cpu or '—'} · {v.gpu or '—'}",
                    "score": grouped(scores[pos - 1]),
                    "score_raw": f"{scores[pos - 1]:.1f}",
                }
            )
        else:
            podium.append({"pos": pos, "filled": False})
    med = median(scores)
    hist = None
    if len(scores) >= HIST_MIN and med is not None:
        hist = charts.histogram(scores, med, f"{c['hist_h']} · {label}", FR["charts"]["median"])
    if not scores:
        hist_few = c["few_none"]
    else:
        hist_few = (
            c["few"]
            .replace("{min}", str(HIST_MIN))
            .replace("{machines}", machines(len(scores)))
            .replace("{median}", grouped(med or 0.0))
        )
    cats = [cat.value for cat in COMBINED_CATEGORIES]
    full = [v for v in views if all(v.points[k] is not None for k in cats)]
    points = [
        charts.Point(
            math.sqrt((v.points[cats[0]] or 0.0) * (v.points[cats[1]] or 0.0)),
            v.points[cats[2]] or 0.0,
            v.kind,
            v.name,
        )
        for v in full
    ]
    ch = FR["charts"]
    scatter = (
        charts.scatter(points, c["scatter_caption"], ch["x_cpu"], ch["y_gpu"], ch["reference"])
        if points
        else None
    )
    unranked = len(table) - len(scores)
    note = ""
    if unranked:
        note = c["unranked_note"].replace("{machines}", unranked_machines(unranked))
        note += (c["unranked_note_combined"] if key == "combined" else "") + "."
    missing = sum(1 for v in views if v.memory_mibs is None and v.disk_seq_mibs is None)
    ctx.update(
        category=key,
        category_label=label,
        kicker=c["kicker"]
        .replace("{machines}", machines(len(views)))
        .replace("{date}", fr_date(generated.date().isoformat()) or ""),
        reference_machine=reference.machine,
        tabs=[
            {
                "href": PAGE_FILES[k],
                "label": category_label(k),
                "short": c["short"][k],
                "current": k == key,
            }
            for k in CATEGORY_KEYS
        ],
        podium=podium,
        rows=[_row(rank, v, key, top) for rank, v in table],
        unranked_note=note,
        hist=hist,
        hist_few=hist_few,
        scatter=scatter,
        scatter_rows=[{"label": p.label, "x": grouped(p.x), "y": grouped(p.y)} for p in points],
        info_blocks=[
            {
                "title": c["mem_h"],
                "unit": c["mem_unit"],
                "tip": None,
                "rows": _bars(views, lambda v: v.memory_mibs),
            },
            {
                "title": c["seq_h"],
                "unit": c["seq_unit"],
                "tip": None,
                "rows": _bars(views, lambda v: v.disk_seq_mibs),
            },
            {
                "title": c["rand_h"],
                "unit": c["rand_unit"],
                "tip": "iops",
                "rows": _bars(views, lambda v: v.disk_rand_iops, 1000.0, " k"),
            },
        ],
        info_missing=c["info_missing"].replace("{machines}", machines(missing)) if missing else "",
        skipped=skipped,
    )
    return ctx


def render_classement(
    views: list[MachineView],
    key: str,
    reference: Reference,
    generated: datetime,
    skipped: list[str] | None = None,
    preview: bool = False,
) -> str:
    ctx = classement_context(views, key, reference, generated, skipped or [], preview)
    return ENV.get_template("classement.html").render(ctx)


def _copy_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.is_dir():
            _copy_tree(item, target / item.name)
        elif not item.name.startswith("."):
            with item.open("rb") as src, (target / item.name).open("wb") as dst:
                shutil.copyfileobj(src, dst)


def copy_assets(out_dir: Path) -> None:
    """CSS, JavaScript, polices et images du paquet -> <out>/assets/."""
    _copy_tree(files("hwbench.leaderboard") / "static", out_dir / "assets")


# --- Page machine : rendu du rapport (report/), provisoire jusqu'à la page machine du design ---

STALE_BADGE = '<span class="status status-check">à ré-exporter</span>'
STALE_NOTE = (
    "noté contre une référence antérieure à la référence actuelle. Les points affichés sont "
    "recalculés contre la référence actuelle à partir de ses résultats bruts ; les benchs dont "
    "la version d'outil ou de protocole a changé depuis ne sont pas notés."
)


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


# Preview (branche dev, publiée sous /preview/ du site) : bandeau en tête de chaque page, lien
# vers le classement officiel (dossier parent), pages en noindex. Style en ligne : le CSS commun
# est aussi celui du rapport, qui n'a pas de preview.
PREVIEW_STYLE = (
    "margin:0 0 16px;padding:8px 12px;border:2px dashed var(--check);border-radius:6px;"
    "color:var(--check);font-weight:600"
)
PREVIEW_TITLE = "Preview · "
# robots.txt n'est lu qu'à la racine de l'hôte : sous /hwbench/preview/, c'est la balise meta
# robots de chaque page qui empêche l'indexation ; le fichier ne sert que d'indication.
PREVIEW_ROBOTS = "User-agent: *\nDisallow: /\n"


def _preview_banner(root: str) -> str:
    """`root` : chemin relatif de la page vers la racine de la preview ("" ou "../")."""
    return (
        f'<p class="preview-banner" style="{PREVIEW_STYLE}">Preview : site généré depuis la '
        "branche dev, pour vérification avant une release. Ce n'est pas "
        f'<a href="{root}../index.html">le classement officiel</a>.</p>'
    )


def _page(title: str, body: str, generated: datetime, preview: bool = False, root: str = "") -> str:
    if preview:
        title = PREVIEW_TITLE + title
        body = _preview_banner(root) + body
    footer = (
        f"Généré le {e(generated.strftime('%d/%m/%Y %H:%M'))} UTC par hwbench. Résultats "
        "déclaratifs, soumis par pull request. "
        '<a href="https://github.com/Mvth1s/hwbench">Dépôt</a> · '
        '<a href="https://github.com/Mvth1s/hwbench/blob/main/CONTRIBUTING.md">Soumettre un '
        "résultat</a>"
    )
    return page(title, body, footer, noindex=preview)


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


def render_machine(
    entry: Entry, reference: Reference, generated: datetime, preview: bool = False
) -> str:
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
    if entry.stale:
        intro += f"<p>{STALE_BADGE} Ce fichier a été {STALE_NOTE}</p>"
    sections = render_sections(
        ctx, with_recommendations=False, embed_json=False, after_header=_ranking_block(entry)
    )
    return _page(f"{ex.machine} · hwbench", intro + sections, generated, preview, root="../")


def build_site(
    results_dir: Path,
    out_dir: Path,
    reference: Reference,
    generated: datetime | None = None,
    preview: bool = False,
) -> list[Entry]:
    """Site statique dans `out_dir`. `preview` : site de la branche dev, publié sous /preview/
    du site officiel (bandeau, titres préfixés, noindex, robots.txt)."""
    generated = generated or datetime.now(UTC)
    entries, skipped = load_entries(results_dir, reference)
    views = [machine_view(entry) for entry in entries]
    (out_dir / "machines").mkdir(parents=True, exist_ok=True)
    copy_assets(out_dir)
    for key in CATEGORY_KEYS:
        html = render_classement(views, key, reference, generated, skipped, preview)
        (out_dir / PAGE_FILES[key]).write_text(html, encoding="utf-8")
    for entry in entries:
        (out_dir / "machines" / f"{entry.slug}.html").write_text(
            render_machine(entry, reference, generated, preview), encoding="utf-8"
        )
    (out_dir / "data.json").write_text(
        json.dumps(data_json(views, reference, generated), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    (out_dir / "classement.csv").write_text(csv_text(views), encoding="utf-8")
    # GitHub Pages : pas de traitement Jekyll
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    if preview:
        (out_dir / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    return entries
