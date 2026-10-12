"""Données de la page machine du site (sans HTML : le template machine.html les rend).

Points recalculés contre la référence du paquet (Entry.scores), fiabilité jugée avec les seuils
par défaut (RunSettings()), tout le reste lu tel quel dans l'export. Les libellés viennent de
hwbench.labels et du catalogue.
"""

from collections.abc import Callable
from typing import Any

from hwbench.display.fmt import fr_date, grouped
from hwbench.labels import BENCH_LABELS, CATEGORY_LABELS, DETAIL_LABELS, bench_label, unit_label
from hwbench.leaderboard import charts
from hwbench.leaderboard.catalog import FR, machines, plural
from hwbench.leaderboard.entries import Entry
from hwbench.leaderboard.views import MachineView, cv_percent, finite, median, ranked
from hwbench.results import COMBINED_CATEGORIES, Category, Result
from hwbench.runner import RunSettings
from hwbench.scoring import Reference

CATEGORY_TONES = {Category.CPU_SINGLE: "s1", Category.CPU_MULTI: "s2", Category.GPU: "s3"}
CATEGORY_MARKS = {Category.CPU_SINGLE: "●", Category.CPU_MULTI: "■", Category.GPU: "▲"}
TIME_GROUPS = (
    (Category.CPU_SINGLE, "s1"),
    (Category.CPU_MULTI, "s2"),
    (Category.GPU, "s3"),
    (Category.MEMORY, "acc"),
    (Category.DISK, "ctl"),
)
NEIGHBOURS = 2  # machines affichées de part et d'autre dans « Face à… »


def measure(value: float) -> str:
    """Valeur de bench : une décimale sous 10 000, aucune au-delà, milliers groupés."""
    return grouped(value, 1 if abs(value) < 10_000 else 0)


def pct(value: float) -> str:
    """Écart signé, une décimale : « +12,3 % », « −4,0 % »."""
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{grouped(abs(value), 1)} %"


def _bar_rows(
    items: list[tuple[str, float]], top: float, hl: str | None = None, suffix: str = ""
) -> list[dict[str, Any]]:
    return [
        {
            "label": label,
            "frac": f"{max(0.003, value / top if top else 0.0):.4f}",
            "display": grouped(value) + suffix,
            "hl": label == hl,
        }
        for label, value in items
    ]


def _duration(seconds: float) -> str:
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes} min {rest:02d} s" if minutes else f"{rest} s"


def _scale_top(values: list[float]) -> float:
    """Échelle des barres de points : au moins 1200 (référence 1000 visible)."""
    return max([1200.0, *(v * 1.05 for v in values)])


def machine_context(
    entry: Entry,
    view: MachineView,
    views: list[MachineView],
    same_model: list[MachineView],
    reference: Reference,
) -> dict[str, Any]:
    t = FR["machine"]
    ex = entry.export
    results = {r.name: r for r in ex.results}
    backend_points = {b.backend.name: b for b in entry.scores.backends}
    settings = RunSettings()
    ctx: dict[str, Any] = {}

    # --- En-tête ---
    snap = ex.snapshot
    cpu = snap.cpu
    cores = (
        t["cores"]
        .replace("{physical}", str(cpu.physical_cores))
        .replace("{logical}", str(cpu.logical_cores))
        if cpu.physical_cores and cpu.logical_cores
        else None
    )
    ram = finite(snap.ram.total_gb)
    ctx["hero"] = {
        "rel": "ok" if view.reliable else "check",
        "cv": t["cv_max"].replace("{cv}", pct_plain(view.cv_max))
        if view.cv_max is not None
        else None,
        "exported": t["exported"]
        .replace("{date}", fr_date(view.date) or "—")
        .replace("{version}", ex.hwbench_version),
        "cpu": " · ".join(x for x in (view.cpu, cores) if x) or "—",
        "gpu": view.gpu or "—",
        "ram": t["ram_visible"].replace("{size}", grouped(ram, 1)) if ram else None,
    }

    # --- Score combiné et rangs ---
    combined = view.points["combined"]
    table = [(rank, v) for rank, v in ranked(views, "combined") if rank is not None]
    total = len(table)
    rank = next((r for r, v in table if v.slug == view.slug), None)
    same_kind = [v for _, v in table if v.kind == view.kind]
    rank_kind = next((i for i, v in enumerate(same_kind, 1) if v.slug == view.slug), None)
    ctx["score"] = {
        "value": grouped(combined) if combined is not None else None,
        "raw": f"{combined:.1f}" if combined is not None else "",
        "delta": t["vs_ref"].replace("{delta}", pct(combined / 10 - 100))
        if combined is not None
        else None,
        "rank": rank,
        "rank_txt": t["rank_of"].replace("{machines}", machines(total)),
        "rank_kind": rank_kind,
        "rank_kind_txt": t["rank_kind_of"]
        .replace("{count}", str(len(same_kind)))
        .replace(
            "{kind}",
            FR["kinds_plural"][view.kind] if len(same_kind) > 1 else FR["kinds"][view.kind].lower(),
        ),
        "beat": (
            f"{grouped((total - rank) / (total - 1) * 100 if total > 1 else 100.0)} %"
            if rank
            else None
        ),
    }

    # --- Par catégorie ---
    cat_values = [(c, view.points[c.value]) for c in COMBINED_CATEGORIES]
    top = _scale_top([v for _, v in cat_values if v is not None])
    ctx["categories"] = {
        "rows": [
            {
                "label": CATEGORY_LABELS[c],
                "short": FR["classement"]["short"][c.value],  # écran étroit
                "mark": CATEGORY_MARKS[c],
                "tone": CATEGORY_TONES[c],
                "frac": f"{max(0.003, (v or 0.0) / top):.4f}",
                "display": grouped(v) if v is not None else FR["unranked"],
                "delta": pct(v / 10 - 100) if v is not None else "",
            }
            for c, v in cat_values
        ],
        "ref_frac": f"{1000 / top:.4f}",
        "raw": [
            {"label": f"{bench_label(name)} · {unit_label(r.unit)}", "value": measure(r.value)}
            for name in ("native-cpu-single", "native-cpu-multi", "glmark2", "vkmark")
            if (r := results.get(name))
        ],
    }

    # --- Face à… (combiné) ---
    if combined is not None:
        idx = next(i for i, (_, v) in enumerate(table) if v.slug == view.slug)
        around = [
            v
            for _, v in table[max(0, idx - NEIGHBOURS) : idx + NEIGHBOURS + 1]
            if v.slug != view.slug
        ]
        med = median([v.points["combined"] or 0.0 for _, v in table]) or 0.0
        items: list[tuple[str, float, str]] = [
            (t["this"], combined, "this"),
            (t["reference"], 1000.0, "ref"),
            (t["median"].replace("{machines}", machines(total)), med, "median"),
            *((v.name, v.points["combined"] or 0.0, "other") for v in around),
        ]
        top = _scale_top([x for _, x, _ in items])
        ctx["face"] = {
            "rows": [
                {
                    "label": label,
                    "frac": f"{max(0.003, value / top):.4f}",
                    "display": grouped(value),
                    "hl": role == "this",
                }
                for label, value, role in items
            ],
            "ref_frac": f"{1000 / top:.4f}",
            "top": f"{top:.1f}",
            "options": [
                {"name": v.name, "points": f"{v.points['combined']:.1f}"}
                for _, v in table
                if v.slug != view.slug
            ],
        }
    else:
        ctx["face"] = None

    # --- Même modèle ---
    if len(same_model) >= 2:
        scored = [(v, p) for v in same_model if (p := v.points["combined"]) is not None]
        if len(scored) >= 2:
            values = [p for _, p in scored]
            top = _scale_top(values)
            ctx["same"] = {
                "text": t["same_p"]
                .replace("{files}", plural(len(same_model), "fichier", "fichiers"))
                .replace("{low}", grouped(min(values)))
                .replace("{high}", grouped(max(values))),
                "rows": [
                    {
                        "label": t["same_this"]
                        if v.slug == view.slug
                        else f"{v.slug} · {fr_date(v.date)}",
                        "frac": f"{max(0.003, p / top):.4f}",
                        "display": grouped(p),
                        "hl": v.slug == view.slug,
                    }
                    for v, p in sorted(scored, key=lambda item: -item[1])
                ],
                "ref_frac": f"{1000 / top:.4f}",
            }
        else:
            ctx["same"] = None
    else:
        ctx["same"] = None

    # --- CPU natif : sous-tests ---
    single, multi = results.get("native-cpu-single"), results.get("native-cpu-multi")
    ctx["cpu"] = None
    if single and multi and single.details and multi.details and single.value:
        workers = multi.workers or cpu.logical_cores or 1
        rows = []
        for key, s in single.details.items():
            m = multi.details.get(key)
            if m is None or not s:
                continue
            gain = m / s
            rows.append(
                {
                    "label": DETAIL_LABELS.get(key, key),
                    "unit": unit_label(single.detail_units.get(key, "")),
                    "single": measure(s),
                    "multi": measure(m),
                    "gain": f"{grouped(gain, 1)}×",
                    "frac": f"{min(1.0, max(0.003, gain / workers)):.4f}",
                }
            )
        ctx["cpu"] = {
            "workers": workers,
            "scaling": f"{grouped(multi.value / single.value, 1)}×",
            "rows": rows,
        }

    # --- GPU : scènes ---
    ctx["gpu"] = None
    gl, vk = results.get("glmark2"), results.get("vkmark")
    if gl or vk:
        resolution = next(
            (
                r.environment.get("resolution")
                for r in (gl, vk)
                if r and r.environment.get("resolution")
            ),
            None,
        )
        blocks = []
        for key, r in (("gl", gl), ("vk", vk)):
            if not r:
                continue
            scenes = sorted(r.details.items(), key=lambda item: -item[1])
            blocks.append(
                {
                    "title": t[f"{key}_h"],
                    "tip": "glmark2" if key == "gl" else "vkmark",
                    "median": t["med_fps"].replace("{value}", grouped(r.value)),
                    "rows": _bar_rows(scenes, max([v for _, v in scenes] or [1.0]) * 1.06),
                }
            )
        ctx["gpu"] = {
            "text": t["gpu_p"].replace("{resolution}", (resolution or "—").replace("x", " × ")),
            "blocks": blocks,
        }

    # --- Fiabilité et températures ---
    ordered = list(ex.results)
    runs_rows = [
        charts.RunsRow(
            bench_label(r.name),
            r.runs,
            r.value,
            r.burst,
            f"{t['cv_l']} {pct_plain(cv_percent(r))}",
            (cv_percent(r) or 0.0) > settings.high_variance_cv_percent,
        )
        for r in ordered
        if r.runs and r.value
    ]
    ch = FR["charts"]
    ctx["runs_svg"] = (
        charts.runs_chart(runs_rows, ch["runs_caption"], ch["median"]) if runs_rows else None
    )
    ctx["runs_rows"] = [
        [
            row.label,
            " / ".join(measure(x) for x in row.runs),
            measure(row.median),
            measure(row.burst),
            row.cv_text,
        ]
        for row in runs_rows
    ]
    ctx["warm"] = (
        t["warm_l"]
        .replace("{stable}", str(sum(1 for r in ordered if r.warmup_stable)))
        .replace("{total}", str(len(ordered)))
    )
    temps = [
        charts.TempRow(bench_label(r.name), b, a)
        for r in ordered
        if (b := finite(r.state_before.cpu_temp_c)) is not None
        and (a := finite(r.state_after.cpu_temp_c)) is not None
    ]
    ctx["temps_svg"] = charts.dumbbell(temps, ch["temps_caption"]) if temps else None
    ctx["temps_rows"] = [
        [row.label, grouped(row.before, 1), grouped(row.after, 1)] for row in temps
    ]

    # --- Temps de test ---
    slices = []
    for category, tone in TIME_GROUPS:
        seconds = sum(r.duration_s for r in ordered if r.category is category)
        if seconds > 0:
            slices.append(charts.Slice(CATEGORY_LABELS[category], seconds, tone))
    cooldown = sum(r.cooldown_s for r in ordered)
    if cooldown > 0:
        slices.append(charts.Slice(t["cooldown"], cooldown, "mute"))
    total_s = sum(s.value for s in slices)
    ctx["time"] = None
    if total_s > 0:
        minutes, rest = divmod(round(total_s), 60)
        ctx["time"] = {
            "svg": charts.donut(
                slices, ch["time_caption"], f"{minutes}:{rest:02d}", t["time_center"]
            ),
            "rows": [
                {
                    "label": s.label,
                    "tone": s.tone,
                    "duration": _duration(s.value),
                    "share": f"{grouped(s.value / total_s * 100)} %",
                }
                for s in slices
            ],
            "total": _duration(total_s),
        }

    # --- Mémoire et disque (information) ---
    memory = [
        (bench_label(name), r.value)
        for name in (
            "native-memory-single",
            "native-memory-multi",
            "sysbench-memory-single",
            "sysbench-memory-multi",
        )
        if (r := results.get(name)) and finite(r.value) is not None
    ]
    fio = results.get("fio-disk")
    seq = rand = []
    disk_title = None
    if fio:
        seq = [
            (DETAIL_LABELS[k], v)
            for k in ("seq_read", "seq_write")
            if (v := finite(fio.details.get(k))) is not None
        ]
        rand = [
            (DETAIL_LABELS[k], v / 1000)
            for k in ("rand_read_4k", "rand_write_4k")
            if (v := finite(fio.details.get(k))) is not None
        ]
        disk_title = " · ".join(
            x
            for x in (t["disk_h"], fio.environment.get("filesystem"), fio.environment.get("device"))
            if x
        )
    ctx["info"] = {
        "memory": _bar_rows(memory, max([v for _, v in memory] or [1.0]) * 1.06),
        "seq": _bar_rows(seq, max([v for _, v in seq] or [1.0]) * 1.06),
        "rand": _bar_rows(rand, max([v for _, v in rand] or [1.0]) * 1.06, suffix=" k"),
        "disk_title": disk_title,
    }

    # --- Détail technique ---
    board = snap.board
    k = t["comp_k"]
    drivers = sorted({r.environment["driver"] for r in ordered if r.environment.get("driver")})
    disks = [
        " ".join(x for x in (d.model, _size(d.size_bytes)) if x)
        for d in snap.disks.disks
        if d.model
    ]
    freq = (
        t["freq"].replace("{min}", grouped(cpu.min_mhz)).replace("{max}", grouped(cpu.max_mhz))
        if cpu.min_mhz and cpu.max_mhz
        else None
    )
    components = [
        (k["board"], " ".join(x for x in (board.board_vendor, board.board_name) if x)),
        (k["bios"], " · ".join(x for x in (board.bios_version, fr_date(board.bios_date)) if x)),
        (k["cpu"], " · ".join(x for x in (view.cpu, cores, freq) if x)),
        (k["memory"], t["ram_visible"].replace("{size}", grouped(ram, 1)) if ram else ""),
        (k["gpu"], snap.gpu.opengl_renderer or snap.gpu.vulkan_device_name or ""),
        (k["drivers"], " · ".join(drivers)),
        (k["disks"], " · ".join(disks)),
    ]
    ctx["components"] = [(key, value) for key, value in components if value]
    first = ordered[0].state_before if ordered else None
    if first is None or first.on_ac is None:
        power = None
    elif first.on_ac:
        power = t["on_ac"] if snap.power.batteries else t["on_ac_desktop"]
    else:
        power = t["on_battery"]
    ck = t["cond_k"]
    conditions = [
        (ck["power"], power),
        (ck["epp"], first.energy_performance_preference if first else None),
        (
            ck["governor"],
            ", ".join(sorted(set(first.governors))) if first and first.governors else None,
        ),
        (ck["profile"], first.platform_profile if first else None),
        (ck["driver"], cpu.scaling_driver),
        (ck["total"], ctx["time"]["total"] if ctx["time"] else None),
    ]
    ctx["conditions"] = [(key, value) for key, value in conditions if value]
    ctx["sensors"] = [
        " ".join(x for x in (s.instance or s.chip, s.label, f"{grouped(c, 1)} °C") if x)
        for s in snap.sensors.temperatures
        if (c := finite(s.current_c)) is not None
    ] + [
        " ".join(x for x in (f.instance or f.chip, f.label, f"{f.rpm} tr/min") if x)
        for f in snap.sensors.fans
        if f.rpm is not None
    ]
    ctx["raw"] = [_raw_row(r, backend_points.get(r.name), settings) for r in ordered]
    ctx["file_note"] = (
        t["file"]
        .replace("{file}", f"results/{entry.slug}.json")
        .replace("{reference}", reference.machine)
    )
    return ctx


def pct_plain(value: float | None) -> str:
    return "—" if value is None else f"{grouped(value, 2)} %"


def _size(size: int | None) -> str | None:
    if not size:
        return None
    for unit, factor in (("To", 1e12), ("Go", 1e9)):
        if size >= factor:
            return f"{grouped(size / factor, 1 if size < 10 * factor else 0)} {unit}"
    return None


def _raw_row(result: Result, score: Any, settings: RunSettings) -> dict[str, Any]:
    t = FR["machine"]
    cv = cv_percent(result)
    points = finite(score.points) if score is not None else None
    if score is None or points is None:
        status = t["unscored"]
    else:
        status = t["official"] if score.official else t["indicative"]
    return {
        "name": result.name,
        "label": BENCH_LABELS.get(result.name, result.name),
        "median": f"{measure(result.value)} {unit_label(result.unit)}",
        "runs": " · ".join(measure(x) for x in result.runs),
        "cv": pct_plain(cv),
        "noisy": (cv or 0.0) > settings.high_variance_cv_percent,
        "burst": measure(result.burst),
        "warmup": f"{grouped(result.warmup_s, 1)} s",
        "points": grouped(points) if points is not None else "—",
        "status": status,
    }


def same_model_groups(views: list[MachineView]) -> Callable[[MachineView], list[MachineView]]:
    """Fichiers qui portent le même nom de machine (casse et espaces ignorés)."""
    groups: dict[str, list[MachineView]] = {}
    for v in views:
        groups.setdefault(" ".join(v.name.lower().split()), []).append(v)
    return lambda v: groups[" ".join(v.name.lower().split())]
