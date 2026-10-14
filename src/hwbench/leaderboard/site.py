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
from datetime import UTC, datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from hwbench.leaderboard import SITE_EXTRA_MISSING

try:  # extra « site » : absent de l'installation de base (CLI de benchmark)
    from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
    from markupsafe import Markup
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(SITE_EXTRA_MISSING, name=exc.name) from exc

from hwbench import __version__
from hwbench.display.fmt import compact, fr_date, grouped
from hwbench.export import EXPORT_SCHEMA_VERSION
from hwbench.leaderboard import charts, pages
from hwbench.leaderboard.catalog import (
    FR,
    GITHUB,
    category_label,
    machines,
    unranked_machines,
)
from hwbench.leaderboard.entries import (
    Entry,
    category_points,
    load_entries,
    ranking,
)
from hwbench.leaderboard.machine import machine_context, same_model_groups
from hwbench.leaderboard.pages import facts, fill
from hwbench.leaderboard.validate import read_bounded
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
from hwbench.results import COMBINED_CATEGORIES
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
ENV.filters["fill"] = fill  # {{ texte | fill(facts) }} : valeurs techniques injectées

# Pages du site, dans l'ordre de la navigation : fichier de sortie. Seules les pages déjà
# générées (PAGES) apparaissent dans la navigation et le pied de page.
PAGE_HREFS = {
    "classement": "index.html",
    "comparaison": "comparaison.html",
    "methodologie": "methodologie.html",
    "soumettre": "soumettre.html",
    "mentions": "mentions-legales.html",
}
PAGES = frozenset(PAGE_HREFS)
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
    page_key: str,
    title: str,
    root: str,
    generated: datetime,
    preview: bool,
    reference: Reference,
) -> dict[str, Any]:
    """Contexte commun à toutes les pages (layout, en-tête, pied de page). `root` : chemin vers
    la racine du site, relatif (« », « ../ ») ou absolu (404 : base de l'URL)."""
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
        "facts": facts(reference, generated),
        "noindex": False,
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
        "id": v.slug,
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
    ctx = _common("classement", title, "", generated, preview, reference)
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
            v.slug,
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


def render_comparaison(
    views: list[MachineView], reference: Reference, generated: datetime, preview: bool = False
) -> str:
    """Page Comparaison : sans JavaScript, toutes les machines côte à côte (points) ; avec, la
    comparaison choisie (?sel=…&base=…), construite par le script depuis data.json."""
    c = FR["comparaison"]
    ctx = _common("comparaison", c["title"], "", generated, preview, reference)
    table = ranked(views, "combined")

    def cell(value: float | None, digits: int = 0) -> str:
        return "—" if value is None else grouped(value, digits)

    ctx.update(
        category_keys=CATEGORY_KEYS[1:] + CATEGORY_KEYS[:1],
        category_labels={k: category_label(k) for k in CATEGORY_KEYS},
        all_rows=[
            {
                "href": f"machines/{v.slug}.html",
                "name": v.name,
                "points": [cell(v.points[k]) for k in (*CATEGORY_KEYS[1:], CATEGORY_KEYS[0])],
                "memory": cell(v.memory_mibs),
                "disk": cell(v.disk_seq_mibs),
            }
            for _, v in table
        ],
        options=[
            {
                "id": v.slug,
                "label": f"{v.name} · {grouped(p)}" if (p := v.points["combined"]) else v.name,
            }
            for _, v in table
        ],
    )
    return ENV.get_template("comparaison.html").render(ctx)


def render_methodologie(reference: Reference, generated: datetime, preview: bool = False) -> str:
    ctx = _common("methodologie", FR["methodologie"]["title"], "", generated, preview, reference)
    ctx["tip_keys"] = []
    ctx.update(pages.methodologie(reference))
    return ENV.get_template("methodologie.html").render(ctx)


def render_soumettre(reference: Reference, generated: datetime, preview: bool = False) -> str:
    ctx = _common("soumettre", FR["soumettre"]["title"], "", generated, preview, reference)
    ctx.update(
        contributing=CONTRIBUTING,
        privacy_json=_json_script(pages.privacy_rules()),
        current_schema=str(EXPORT_SCHEMA_VERSION),
        readable_schemas=pages.readable_schemas(),
    )
    return ENV.get_template("soumettre.html").render(ctx)


def render_mentions(reference: Reference, generated: datetime, preview: bool = False) -> str:
    ctx = _common("mentions", FR["mentions"]["title"], "", generated, preview, reference)
    return ENV.get_template("mentions.html").render(ctx)


def render_404(
    reference: Reference, generated: datetime, base_url: str, preview: bool = False
) -> str:
    """404 servie par GitHub Pages à n'importe quelle profondeur : liens et assets absolus,
    à partir de `base_url` (« /hwbench/ » en prod). Sous /preview/, GitHub sert la 404 de la
    prod : ses liens mènent à la prod (voir CLAUDE.md)."""
    ctx = _common("404", FR["notfound"]["title"], base_url, generated, preview, reference)
    ctx["noindex"] = True
    return ENV.get_template("404.html").render(ctx)


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


# --- Page machine ---

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


def render_machine(
    entry: Entry,
    view: MachineView,
    views: list[MachineView],
    same_model: list[MachineView],
    reference: Reference,
    generated: datetime,
    preview: bool = False,
) -> str:
    """Page machine (design Machine.dc.html) : points recalculés contre la référence du paquet,
    fiabilité jugée avec les seuils par défaut, sans recommandations."""
    ctx = _common("machine", view.name, "../", generated, preview, reference)
    ctx["tip_keys"] = [
        "geomean",
        "points",
        "native",
        "fps",
        "glmark2",
        "vkmark",
        "burst",
        "median",
        "cv",
        "warmup",
        "qd",
        "iops",
        "epp",
        "governor",
    ]
    ctx.update(machine_context(entry, view, views, same_model, reference))
    ctx.update(
        view=view,
        kind_mark=KIND_MARKS[view.kind],
        settings_note=settings_note(entry.export.settings),
        csv_name=FR["js"]["raw_csv_name"].replace("{machine}", view.slug),
    )
    return ENV.get_template("machine.html").render(ctx)


def build_site(
    results_dir: Path,
    out_dir: Path,
    reference: Reference,
    generated: datetime | None = None,
    preview: bool = False,
    base_url: str = "/",
) -> list[Entry]:
    """Site statique dans `out_dir`. `preview` : site de la branche dev, publié sous /preview/
    du site officiel (bandeau, titres préfixés, noindex, robots.txt). `base_url` : chemin absolu
    de la racine du site (« /hwbench/ »), utilisé par la seule page 404 ; les autres pages ont
    des liens relatifs."""
    if not base_url.startswith("/") or not base_url.endswith("/"):
        raise ValueError(f"base_url doit commencer et finir par « / » : {base_url!r}")
    generated = generated or datetime.now(UTC)
    entries, skipped = load_entries(results_dir, reference)
    views = [machine_view(entry) for entry in entries]
    (out_dir / "machines").mkdir(parents=True, exist_ok=True)
    copy_assets(out_dir)
    for key in CATEGORY_KEYS:
        html = render_classement(views, key, reference, generated, skipped, preview)
        (out_dir / PAGE_FILES[key]).write_text(html, encoding="utf-8")
    for name, html in (
        ("methodologie.html", render_methodologie(reference, generated, preview)),
        ("soumettre.html", render_soumettre(reference, generated, preview)),
        ("mentions-legales.html", render_mentions(reference, generated, preview)),
        ("404.html", render_404(reference, generated, base_url, preview)),
    ):
        (out_dir / name).write_text(html, encoding="utf-8")
    (out_dir / "comparaison.html").write_text(
        render_comparaison(views, reference, generated, preview), encoding="utf-8"
    )
    same_model = same_model_groups(views)
    for entry, view in zip(entries, views, strict=True):
        html = render_machine(entry, view, views, same_model(view), reference, generated, preview)
        (out_dir / "machines" / f"{entry.slug}.html").write_text(html, encoding="utf-8")
        # JSON source téléchargeable : le fichier soumis, relu borné comme à la validation
        source = read_bounded(results_dir / f"{entry.slug}.json")
        (out_dir / "machines" / f"{entry.slug}.json").write_bytes(source)
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
