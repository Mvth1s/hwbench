"""Sections HTML du rapport, partagées avec la page machine du classement (sans recommandations
ni JSON embarqué). Une section sans donnée mesurée est absente, pas vide.

Tout vient de la session (MachineExport) et des constats de l'analyse ; rien n'interroge le
système. Tout texte de la session passe par e().
"""

import json
from dataclasses import dataclass

from hwbench.analysis import STATUS_ORDER, Finding, FindingCode, Status
from hwbench.display.fmt import compact, fr_date, measure, num
from hwbench.export import MachineExport, to_dict
from hwbench.labels import (
    CATEGORY_LABELS,
    DETAIL_LABELS,
    PRESENTATION_LABELS,
    bench_label,
    disk_size_label,
    unit_label,
)
from hwbench.report.charts import Bar, Segment, bars, timeline
from hwbench.report.html import e, kv, status_badge, table
from hwbench.report.texts import (
    finding_text,
    hot_start_sentence,
    plural,
    recommendations,
    synthesis,
)
from hwbench.results import COMBINED_CATEGORIES, Category, MachineState, Result, gpu_name
from hwbench.runner import RunSettings
from hwbench.scoring import ScoreIssue

CONDITION_CODES = (
    FindingCode.ON_BATTERY,
    FindingCode.POWER_PROFILE,
    FindingCode.HOT_START,
    FindingCode.CONDITIONS_OK,
)


@dataclass(frozen=True)
class Context:
    session: MachineExport
    findings: list[Finding]
    settings: RunSettings  # seuils appliqués par l'analyse et cités par les textes
    settings_note: str | None = None  # seuils par défaut, ou différents de ceux de la mesure


def _section(key: str, title: str, content: str) -> str:
    return f'<section id="{key}"><h2>{e(title)}</h2>{content}</section>'


def _results(ctx: Context, *categories: Category) -> list[Result]:
    return [r for r in ctx.session.results if r.category in categories]


def _points(ctx: Context, name: str) -> str:
    score = next((b for b in ctx.session.backend_scores if b.backend.name == name), None)
    if score is None:
        return "—"
    if score.points is not None:
        return f"{num(score.points, 0)} pts"
    return "non comparable" if score.issue is not ScoreIssue.NOT_IN_REFERENCE else "—"


def _category_points(ctx: Context, category: Category) -> float | None:
    score = next((c for c in ctx.session.categories if c.category is category), None)
    return score.points if score else None


def _value(r: Result) -> str:
    return f"{measure(r.value)} {unit_label(r.unit)}"


def _gpu_renderer(session: MachineExport) -> str | None:
    gpu = session.snapshot.gpu
    return (
        gpu.opengl_renderer
        or gpu.vulkan_device_name
        or (gpu.pci_devices[0].model if gpu.pci_devices else None)
    )


def _gpu(session: MachineExport) -> str | None:
    """Nom du GPU sans les détails du pilote (en-tête)."""
    return gpu_name(_gpu_renderer(session))


def _findings(ctx: Context, *codes: FindingCode) -> list[Finding]:
    return [f for f in ctx.findings if f.code in codes]


def conditions_status(findings: list[Finding]) -> Status | None:
    """Tuile « Conditions » : le pire statut parmi alimentation, profil et départ chaud."""
    statuses = [f.status for f in findings if f.code in CONDITION_CODES]
    return min(statuses, key=STATUS_ORDER.index) if statuses else None


def conditions_reason(findings: list[Finding]) -> str:
    """Ligne courte sous la tuile : ce qui la fait passer en À corriger ou À vérifier
    (« 4 départs chauds »), sinon ce qui la rend fiable."""
    reasons = []
    for f in findings:
        if f.code is FindingCode.ON_BATTERY:
            reasons.append(plural(len(f.items), "test sur batterie", "tests sur batterie"))
        elif f.code is FindingCode.POWER_PROFILE:
            reasons.append("réglage d'énergie non performance")
        elif f.code is FindingCode.HOT_START:
            reasons.append(plural(len(f.items), "départ chaud", "départs chauds"))
    if reasons:
        return " · ".join(reasons)
    if any(f.code is FindingCode.CONDITIONS_OK for f in findings):
        return "secteur, meilleur réglage d'énergie"
    return ""


# --- 1. En-tête, 2. chiffres clés, 3. synthèse ---------------------------------------------


def header(ctx: Context) -> str:
    s = ctx.session
    duration = sum(r.duration_s for r in s.results)
    facts = [
        s.snapshot.cpu.model,
        _gpu(s),
        f"mesuré le {fr_date(s.created)}",
        f"hwbench {s.hwbench_version}",
        f"{num(duration / 60, 0)} min de tests" if duration >= 60 else f"{num(duration, 0)} s",
    ]
    line = " · ".join(e(f) for f in facts if f)
    return f'<header><h1>{e(s.machine)}</h1><p class="muted">{line}</p></header>'


def _tile(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="small muted">{e(note)}</div>' if note else ""
    return (
        f'<div class="tile"><div class="label">{e(label)}</div>'
        f'<div class="value">{value}</div>{note_html}</div>'
    )


def key_figures(ctx: Context) -> str:
    s = ctx.session
    tiles = []
    if s.combined is not None and s.combined.points is not None:
        note = f"référence {s.reference.machine} = 1000" if s.reference else ""
        if s.combined.gpu_missing:
            gpu = next((c for c in s.categories if c.category is Category.GPU), None)
            note = "sans GPU (incomplet)" if gpu is not None else "sans GPU (non mesuré)"
        tiles.append(_tile("Score combiné", e(f"{num(s.combined.points, 0)} pts"), note))
    for category in COMBINED_CATEGORIES:
        points = _category_points(ctx, category)
        if points is not None:
            tiles.append(_tile(CATEGORY_LABELS[category], e(f"{num(points, 0)} pts")))
            continue
        main = next((r for r in _results(ctx, category) if r.backend == "native"), None)
        main = main or next(iter(_results(ctx, category)), None)
        if main is not None:
            tiles.append(_tile(CATEGORY_LABELS[category], e(_value(main)), "valeur brute"))
    status = conditions_status(ctx.findings)
    tiles.append(
        _tile(
            "Conditions de mesure",
            status_badge(status) if status else e("non déterminées"),
            conditions_reason(ctx.findings),
        )
    )
    return f'<div class="tiles">{"".join(tiles)}</div>'


def synthesis_section(ctx: Context) -> str:
    kept = synthesis(ctx.findings)
    by_text = {finding_text(f): f for f in ctx.findings}
    items = "".join(f"<li>{status_badge(by_text[t].status)} {e(t)}</li>" for t in kept)
    return _section("synthese", "Synthèse", f'<ul class="findings">{items}</ul>')


# --- 4. Conditions de mesure ---------------------------------------------------------------


def _states(ctx: Context) -> list[MachineState]:
    return [st for r in ctx.session.results for st in (r.state_before, r.state_after)]


def _cooldown_rows(ctx: Context) -> list[tuple[str, str | None, Status, str]]:
    """--cooldown : pauses effectives avant chaque catégorie (rien si l'option n'a pas servi)."""
    measured = ctx.session.settings
    paused = [r for r in ctx.session.results if r.cooldown_s > 0]
    if not paused and not (measured and measured.cooldown_enabled):
        return []
    if measured is not None and measured.cooldown_auto:
        delta, window = measured.cooldown_stall_delta_c, measured.cooldown_stall_s
        stall = (
            f", arrêtée si la baisse est inférieure à {compact(delta)} °C en {num(window, 0)} s"
            if window > 0
            else ""
        )
        mode = (
            f"Mode auto : attente du passage sous {num(measured.hot_start_c, 0)} °C, "
            f"au plus {num(measured.cooldown_timeout_s, 0)} s{stall}, avant chaque catégorie."
        )
    elif measured is not None and measured.cooldown_s:
        mode = f"Pause fixe de {num(measured.cooldown_s, 0)} s à chaque changement de catégorie."
    else:
        mode = "Pause de refroidissement avant certaines catégories."
    if not paused:
        return [("Refroidissement", "aucune attente", Status.INFO, mode)]
    total = sum(r.cooldown_s for r in paused)
    detail = ", ".join(f"{bench_label(r.name)} {num(r.cooldown_s, 0)} s" for r in paused)
    value = f"{num(total, 0)} s au total"
    return [("Refroidissement", value, Status.INFO, f"{mode} Pauses : {detail}.")]


def conditions(ctx: Context) -> str:
    states = _states(ctx)
    if not states:
        return ""
    first = ctx.session.results[0].state_before
    rows = []

    on_ac = {st.on_ac for st in states}
    if on_ac == {True}:
        power = "secteur" + (" (pas de batterie)" if first.has_battery is False else "")
        rows.append(("Alimentation", power, Status.OK, "Sur secteur avant et après chaque test."))
    elif False in on_ac:
        rows.append(
            ("Alimentation", "batterie", Status.FIX, "Au moins un test a été mesuré sur batterie.")
        )
    else:
        rows.append(("Alimentation", "inconnue", Status.INFO, "État du secteur non disponible."))

    for key, label in (
        ("platform_profile", "Profil plateforme"),
        ("energy_performance_preference", "EPP"),
    ):
        value = getattr(first, key)
        if any(key in st.throttling_settings() for st in states):
            rows.append(
                (label, value, Status.FIX, "Réglage plus économe que le meilleur disponible.")
            )
        elif value is None:
            rows.append((label, None, Status.INFO, "Non exposé par cette machine."))
        else:
            rows.append((label, value, Status.OK, "Meilleur réglage disponible."))

    governors = ", ".join(sorted({g for st in states for g in st.governors})) or None
    rows.append(("Governor", governors, Status.INFO, "Affiché pour information, non jugé seul."))
    hot = _findings(ctx, FindingCode.HOT_START)
    starts = [r.state_before.cpu_temp_c for r in ctx.session.results]
    known = [t for t in starts if t is not None]
    if known:
        low, high = min(known), max(known)
        span = (
            f"{num(low, 0)} °C"
            if round(low) == round(high)
            else f"{num(low, 0)} à {num(high, 0)} °C"
        )
        threshold = f"seuil de départ chaud {num(ctx.settings.hot_start_c, 0)} °C"
        if hot:
            count = len(hot[0].items)
            text = f"{hot_start_sentence(count, ctx.settings.hot_start_c)} (seuil de départ chaud)."
            rows.append(("Température de départ", span, Status.CHECK, text))
        else:
            text = f"Tous les tests ont démarré sous le {threshold}."
            rows.append(("Température de départ", span, Status.OK, text))
    rows += _cooldown_rows(ctx)

    html_rows = [
        [e(label), e(value if value not in (None, "") else "—"), status_badge(st), e(text)]
        for label, value, st, text in rows
    ]
    s = ctx.settings
    thresholds = (
        f"Seuils appliqués : CV {num(s.high_variance_cv_percent, 0)} % (mesures instables), "
        f"{num(s.reliable_cv_percent, 0)} % (très reproductibles), départ chaud "
        f"{num(s.hot_start_c, 0)} °C, tolérance du warm-up {num(s.warmup_tolerance_percent, 0)} %, "
        f"{s.runs} runs."
    )
    note = f" {ctx.settings_note}" if ctx.settings_note else ""
    content = (
        table(["Élément", "Valeur", "Statut", "Constat"], html_rows)
        + f'<p class="muted small">{e(thresholds + note)}</p>'
    )
    return _section("conditions", "Conditions de mesure", content)


# --- 5. Processeur, 6. GPU, 7. mémoire, 8. disque ------------------------------------------


def _bench_table(ctx: Context, results: list[Result]) -> str:
    rows = [
        [
            e(bench_label(r.name)),
            e(_value(r)),
            e(_points(ctx, r.name)),
            e(f"{num(r.cv_percent)} %"),
            e(r.workers if r.workers is not None else "—"),
        ]
        for r in results
    ]
    return table(
        ["Test", "Valeur (médiane)", "Points", "CV", "Processus / threads"], rows, [1, 2, 3, 4]
    )


def _factors(ctx: Context, kind: str) -> str:
    texts = [
        finding_text(f)
        for f in _findings(ctx, FindingCode.MULTI_FACTOR)
        if f.params["kind"] == kind
    ]
    return "".join(f"<p>{e(t)}</p>" for t in texts)


def _detail_charts(r: Result) -> str:
    """Une figure par unité : des débits en Mio/s et des op/s ne partagent pas une échelle."""
    charts = []
    for unit in dict.fromkeys(r.detail_units.get(k, "") for k in r.details):
        rows = [
            Bar(DETAIL_LABELS.get(k, k), v, f"{measure(v)} {unit_label(unit)}".strip())
            for k, v in r.details.items()
            if r.detail_units.get(k, "") == unit
        ]
        title = f"{bench_label(r.name)} : détail ({unit_label(unit)})"
        charts.append(f"<h3>{e(title)}</h3>" + bars(title, rows))
    return "".join(charts)


def cpu(ctx: Context) -> str:
    results = _results(ctx, Category.CPU_SINGLE, Category.CPU_MULTI)
    if not results:
        return ""
    charts = "".join(_detail_charts(r) for r in results if r.backend == "native" and r.details)
    content = _bench_table(ctx, results) + _factors(ctx, "cpu") + charts
    return _section("cpu", "Processeur", content)


def gpu(ctx: Context) -> str:
    results = _results(ctx, Category.GPU)
    if not results:
        return ""
    blocks = []
    for r in results:
        env = r.environment
        facts = kv(
            [
                ("Score (médiane)", _value(r)),
                ("Points", _points(ctx, r.name)),
                ("Outil", f"{r.backend} {r.tool_version or ''}".strip()),
                ("Résolution", env.get("resolution")),
                ("Présentation", PRESENTATION_LABELS.get(r.presentation or "", r.presentation)),
                ("Pilote", env.get("driver")),
                ("Rendu", env.get("renderer")),
            ]
        )
        scenes = [Bar(k, v, f"{measure(v)} fps") for k, v in r.details.items()]
        blocks.append(
            f"<h3>{e(bench_label(r.name))}</h3>{facts}"
            + bars(f"{bench_label(r.name)} : fps par scène", scenes)
        )
    note = (
        '<p class="muted small">Les scores de deux outils différents ne se comparent pas entre '
        "eux.</p>"
    )
    return _section("gpu", "Carte graphique", "".join(blocks) + note)


INFO_NOTE = "Catégorie d'information : elle n'entre pas dans le score combiné ni le classement."


def memory(ctx: Context) -> str:
    results = _results(ctx, Category.MEMORY)
    if not results:
        return ""
    points = _category_points(ctx, Category.MEMORY)
    total = f"<p>Score mémoire : {e(num(points, 0))} pts.</p>" if points is not None else ""
    content = (
        f'<p class="muted small">{e(INFO_NOTE)}</p>'
        + total
        + _bench_table(ctx, results)
        + _factors(ctx, "memory")
    )
    return _section("memoire", "Mémoire", content)


DISK_NOTE = (
    "Le score disque dépend du système de fichiers (btrfs, ext4…) et du cache des SSD : il ne se "
    "compare qu'à configuration et taille de fichier égales."
)


def disk(ctx: Context) -> str:
    results = _results(ctx, Category.DISK)
    if not results:
        return ""
    blocks = []
    for r in results:
        facts = kv(
            [
                ("Indice (médiane)", _value(r)),
                ("Points", _points(ctx, r.name)),
                ("Outil", f"{r.backend} {r.tool_version or ''}".strip()),
                ("Fichier de test", disk_size_label(r.presentation) if r.presentation else None),
                ("Système de fichiers", r.environment.get("filesystem")),
                ("Disque", r.environment.get("device")),
            ]
        )
        charts = []
        for unit, title in (("MiB/s", "Débits séquentiels"), ("IOPS", "Accès aléatoires 4K")):
            rows = [
                Bar(DETAIL_LABELS.get(k, k), v, f"{measure(v)} {unit_label(unit)}")
                for k, v in r.details.items()
                if r.detail_units.get(k) == unit
            ]
            charts.append(f"<h3>{e(title)}</h3>" + bars(title, rows) if rows else "")
        blocks.append(f"<h3>{e(bench_label(r.name))}</h3>{facts}{''.join(charts)}")
    content = f'<p class="muted small">{e(INFO_NOTE)} {e(DISK_NOTE)}</p>' + "".join(blocks)
    return _section("disque", "Disque", content)


# --- 9. Températures, 10. fiabilité --------------------------------------------------------


def temperatures(ctx: Context) -> str:
    s = ctx.session
    sensor = s.snapshot.sensors.cpu_sensor()
    segments = [
        Segment(
            bench_label(r.name), r.duration_s, r.state_before.cpu_temp_c, r.state_after.cpu_temp_c
        )
        for r in s.results
    ]
    chart = timeline(segments, sensor.high_c if sensor else None)
    found = _findings(
        ctx,
        FindingCode.TEMPERATURE_OK,
        FindingCode.TEMPERATURE_REACHED,
        FindingCode.TEMPERATURE_MAX,
    )
    summary = "".join(f"<p>{status_badge(f.status)} {e(finding_text(f))}</p>" for f in found)
    readings = [
        [
            e(t.source),
            e(t.label),
            e("—" if t.current_c is None else f"{num(t.current_c, 0)} °C"),
            e("—" if t.high_c is None else f"{num(t.high_c, 0)} °C"),
            e("—" if t.critical_c is None else f"{num(t.critical_c, 0)} °C"),
        ]
        for t in s.snapshot.sensors.temperatures
    ]
    sensors = (
        "<h3>Capteurs relevés avec les composants</h3>"
        '<p class="muted small">Un seul relevé, au moment de la collecte des composants.</p>'
        + table(
            ["Puce", "Capteur", "Température", "Seuil haut", "Seuil critique"], readings, [2, 3, 4]
        )
        if readings
        else ""
    )
    if not chart and not sensors:
        return ""
    return _section("temperatures", "Températures", summary + chart + sensors)


def reliability(ctx: Context) -> str:
    results = ctx.session.results
    if not results:
        return ""
    s = ctx.settings
    rows = []
    for r in results:
        status = Status.CHECK if r.cv_percent > s.high_variance_cv_percent else Status.OK
        burst = 100.0 * (r.burst / r.value - 1.0) if r.value else 0.0
        warmup = f"{r.warmup_runs} itérations, {num(r.warmup_s, 0)} s" + (
            "" if r.warmup_stable else ", non stabilisé"
        )
        rows.append(
            [
                e(bench_label(r.name)),
                e(f"{num(r.cv_percent)} %"),
                status_badge(status),
                e(" · ".join(measure(v) for v in r.runs)),
                e(f"{'+' if burst > 0 else ''}{num(burst)} %"),
                e(warmup),
            ]
        )
    content = (
        f'<p class="muted small">CV au-delà de {e(num(s.high_variance_cv_percent, 0))} % : à '
        "vérifier. Le burst (premier run, à froid) est comparé à la médiane ; il n'entre jamais "
        "dans le score.</p>"
        + table(["Test", "CV", "Statut", "Runs", "Burst / médiane", "Warm-up"], rows, [1, 4])
    )
    return _section("fiabilite", "Fiabilité des mesures", content)


# --- 11. Composants ------------------------------------------------------------------------


def _ram(ctx: Context) -> str | None:
    ram = ctx.session.snapshot.ram
    size = ram.installed_gb if ram.installed_gb is not None else ram.total_gb
    text = f"{compact(round(size, 1))} Gio" if size is not None else None
    if ram.modules:
        speeds = {m.speed_mts for m in ram.modules if m.speed_mts}
        types = {m.type for m in ram.modules if m.type}
        parts = [plural(len(ram.modules), "barrette", "barrettes"), *sorted(types)]
        parts += [f"{s} MT/s" for s in sorted(speeds)]
        text = f"{text or '?'} ({', '.join(parts)})"
    elif ram.modules_unavailable is not None and ram.modules_unavailable.value == "needs_root":
        text = f"{text or '?'} (barrettes : relancer avec sudo)"
    return text


def components(ctx: Context) -> str:
    snap = ctx.session.snapshot
    board, cpu_data = snap.board, snap.cpu
    disks = ", ".join(
        f"{d.model or d.name} ({compact(round(d.size_bytes / 1024**3))} Gio)"
        if d.size_bytes
        else (d.model or d.name)
        for d in snap.disks.disks
    )
    batteries = ", ".join(
        f"{b.name} ({num(b.health_percent, 0)} % de la capacité d'origine)"
        if b.health_percent is not None
        else b.name
        for b in snap.power.batteries
    )
    rows = [
        ("Machine", " ".join(filter(None, [board.system_vendor, board.product_name])) or None),
        ("Carte mère", " ".join(filter(None, [board.board_vendor, board.board_name])) or None),
        ("BIOS", " ".join(filter(None, [board.bios_version, fr_date(board.bios_date)])) or None),
        ("CPU", cpu_data.model),
        (
            "Cœurs / threads",
            f"{cpu_data.physical_cores or '?'} / {cpu_data.logical_cores or '?'}",
        ),
        ("RAM", _ram(ctx)),
        ("GPU", _gpu_renderer(ctx.session)),  # détail : renderer complet
        ("Disques", disks or None),
        ("Batterie", batteries or None),
    ]
    return _section("composants", "Composants", kv(rows))


# --- 12. Recommandations, 13. lexique, 14. annexe ------------------------------------------


def recommendations_section(ctx: Context) -> str:
    recs = recommendations(ctx.findings)
    if not recs:
        return ""
    items = "".join(
        f"<li>{e(r.text)}"
        + "".join(f"<pre><code>{e(c)}</code></pre>" for c in r.commands)
        + "</li>"
        for r in recs
    )
    return _section("recommandations", "Recommandations", f"<ol>{items}</ol>")


GLOSSARY = {
    "CV": "Coefficient de variation : écart-type des runs divisé par leur médiane. Plus il est "
    "bas, plus la mesure est reproductible.",
    "Médiane": "Valeur du milieu des runs mesurés : c'est le score retenu.",
    "Run": "Une exécution mesurée d'un test. Chaque test en compte au moins trois.",
    "Warm-up": "Itérations lancées avant les runs mesurés, jusqu'à un régime stable.",
    "Burst": "Premier run, à froid : affiché pour information, jamais compté dans le score.",
    "Points": "Score ramené à la machine de référence, qui vaut 1000 points.",
    "Indice brut": "Moyenne géométrique de débits de natures différentes, sans unité.",
    "EPP": "Energy Performance Preference : préférence d'énergie du processeur (performance, "
    "équilibre, économie).",
    "Profil plateforme": "Profil d'énergie de la machine exposé par le firmware (ACPI "
    "platform_profile).",
    "Governor": "Politique de fréquence du noyau Linux ; affichée pour information.",
    "fps": "Images par seconde.",
    "IOPS": "Opérations d'entrée-sortie par seconde.",
    "QD": "Profondeur de file : nombre de requêtes disque en attente simultanément.",
}


def glossary(ctx: Context) -> str:
    s = ctx.session
    states = _states(ctx)
    present = {"CV", "Médiane", "Run", "Warm-up", "Burst"} if s.results else set()
    if s.reference is not None:
        present.add("Points")
    if any(r.unit == "index" for r in s.results):
        present.add("Indice brut")
    if any(st.energy_performance_preference for st in states):
        present.add("EPP")
    if any(st.platform_profile for st in states):
        present.add("Profil plateforme")
    if any(st.governors for st in states):
        present.add("Governor")
    if _results(ctx, Category.GPU):
        present.add("fps")
    if _results(ctx, Category.DISK):
        present |= {"IOPS", "QD"}
    if not present:
        return ""
    items = "".join(
        f"<dt><strong>{e(term)}</strong></dt><dd>{e(text)}</dd>"
        for term, text in GLOSSARY.items()
        if term in present
    )
    return _section("lexique", "Lexique", f"<dl>{items}</dl>")


def _embedded_json(session: MachineExport) -> str:
    """JSON de la session (déjà passé par privacy.scrub dans to_dict), sans « < » littéral :
    une chaîne « </script> » d'un export ne peut pas fermer la balise."""
    text = json.dumps(to_dict(session), ensure_ascii=False, indent=1)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/json" id="hwbench-session">{text}</script>'


def appendix(ctx: Context, embed_json: bool) -> str:
    rows = [
        [
            e(r.name),
            e(f"v{r.version}"),
            e(r.tool_version or "—"),
            e(r.presentation or "—"),
            e(measure(r.value)),
            e(unit_label(r.unit)),
            e(measure(r.stdev)),
            e(" · ".join(measure(v) for v in r.runs)),
        ]
        for r in ctx.session.results
    ]
    content = table(
        ["Bench", "Protocole", "Outil", "Présentation", "Médiane", "Unité", "Écart-type", "Runs"],
        rows,
        [4, 6],
    )
    if embed_json:
        content += (
            '<p class="muted small">Les données complètes de la session sont incluses dans ce '
            "fichier, au format JSON (bloc « hwbench-session », invisible à l'affichage).</p>"
            + _embedded_json(ctx.session)
        )
    return _section("annexe", "Annexe : résultats bruts", content)


def render_sections(
    ctx: Context, *, with_recommendations: bool, embed_json: bool, after_header: str = ""
) -> str:
    """Sections dans l'ordre de docs/rapport.md ; `after_header` : HTML propre à la page (bloc
    de classement du site)."""
    parts = [
        header(ctx),
        after_header,
        key_figures(ctx),
        synthesis_section(ctx),
        conditions(ctx),
        cpu(ctx),
        gpu(ctx),
        memory(ctx),
        disk(ctx),
        temperatures(ctx),
        reliability(ctx),
        components(ctx),
        recommendations_section(ctx) if with_recommendations else "",
        glossary(ctx),
        appendix(ctx, embed_json),
    ]
    return "\n".join(p for p in parts if p)
