"""Données des pages du site, calculées à partir des exports lus (Entry).

Logique pure, sans HTML : type de machine, marques, points recalculés par catégorie, CV max,
fiabilité, rangs. Les templates et data.json consomment ces vues ; aucun champ n'est repris
tel quel d'un calcul de l'export (points recalculés par entries.category_points).
"""

import csv
import io
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from hwbench.export import MachineExport
from hwbench.leaderboard.entries import Entry, category_points
from hwbench.results import COMBINED_CATEGORIES, Category, Result, gpu_name
from hwbench.runner import RunSettings
from hwbench.scoring import Reference

# « combined » puis les catégories classées, dans l'ordre des onglets
CATEGORY_KEYS: tuple[str, ...] = ("combined", *(c.value for c in COMBINED_CATEGORIES))
# page sans JavaScript de chaque onglet (même dossier : liens relatifs)
PAGE_FILES = {
    "combined": "index.html",
    Category.CPU_SINGLE.value: "cpu-single.html",
    Category.CPU_MULTI.value: "cpu-multi.html",
    Category.GPU.value: "gpu.html",
}
DATA_SCHEMA = 1  # forme de data.json (consommé par la page Comparaison)

CPU_VENDORS = {"AuthenticAMD": "AMD", "GenuineIntel": "Intel"}
GPU_VENDORS = (("NVIDIA", "NVIDIA"), ("AMD", "AMD"), ("ATI", "AMD"), ("Intel", "Intel"))


@dataclass(frozen=True)
class MachineView:
    slug: str
    name: str
    kind: str  # « desktop » (pas de batterie système) ou « laptop »
    cpu: str | None  # nom brut du fabricant (jamais reformaté)
    cpu_brand: str  # AMD, Intel ou other
    gpu: str | None  # nom normalisé (results.gpu_name), sans pilote ni noyau
    gpu_brand: str | None  # AMD, Intel, NVIDIA, other ; None sans GPU détecté
    points: dict[str, float | None]  # clé de CATEGORY_KEYS -> points, None = non classé
    memory_mibs: float | None  # copie multi-processus (native-memory-multi)
    disk_seq_mibs: float | None  # fio, lecture séquentielle
    disk_rand_iops: float | None  # fio, lecture aléatoire 4K
    cv_max: float | None  # CV maximal sur tous les tests, en %
    reliable: bool  # CV de chaque test sous le seuil des réglages par défaut
    stale: bool
    date: str | None  # AAAA-MM-JJ, ou la valeur brute si illisible


def kind(export: MachineExport) -> str:
    # power.batteries ne contient que les batteries système (pas souris ni manettes)
    return "laptop" if export.snapshot.power.batteries else "desktop"


def cpu_brand(vendor: str | None) -> str:
    return CPU_VENDORS.get(vendor or "", "other")


def gpu_label(export: MachineExport) -> str | None:
    gpu = export.snapshot.gpu
    raw = (
        gpu.opengl_renderer
        or gpu.vulkan_device_name
        or gpu.nvidia_name
        or (gpu.pci_devices[0].model if gpu.pci_devices else None)
    )
    return gpu_name(raw)


def gpu_brand(export: MachineExport) -> str | None:
    gpu = export.snapshot.gpu
    sources = [p.vendor for p in gpu.pci_devices] + [gpu_label(export)]
    texts = [s for s in sources if s]
    if not texts:
        return None
    for needle, brand in GPU_VENDORS:
        if any(needle in text for text in texts):
            return brand
    return "other"


def cv_percent(result: Result) -> float | None:
    return result.stdev / result.value * 100 if result.value else None


def cv_max(results: list[Result]) -> float | None:
    values = [cv for r in results if (cv := cv_percent(r)) is not None]
    return max(values) if values else None


def iso_day(created: str) -> str:
    """Jour de l'export (AAAA-MM-JJ) ; valeur brute si la date est illisible."""
    try:
        return date.fromisoformat(created[:10]).isoformat()
    except ValueError:
        return created


def finite(value: float | None) -> float | None:
    """Valeur affichable : un calcul qui déborde (inf, nan) sur un export retouché devient une
    donnée absente (non classé), jamais une coordonnée de graphique ni une erreur de rendu."""
    return value if value is not None and math.isfinite(value) else None


def machine_view(entry: Entry, settings: RunSettings | None = None) -> MachineView:
    settings = settings or RunSettings()
    ex = entry.export
    results = {r.name: r for r in ex.results}
    points: dict[str, float | None] = {"combined": finite(category_points(entry, None))}
    points |= {c.value: finite(category_points(entry, c)) for c in COMBINED_CATEGORIES}
    fio = results.get("fio-disk")
    memory = results.get("native-memory-multi")
    worst = cv_max(ex.results)
    return MachineView(
        slug=entry.slug,
        name=ex.machine,
        kind=kind(ex),
        cpu=ex.snapshot.cpu.model,
        cpu_brand=cpu_brand(ex.snapshot.cpu.vendor),
        gpu=gpu_label(ex),
        gpu_brand=gpu_brand(ex),
        points=points,
        memory_mibs=finite(memory.value) if memory else None,
        disk_seq_mibs=finite(fio.details.get("seq_read")) if fio else None,
        disk_rand_iops=finite(fio.details.get("rand_read_4k")) if fio else None,
        cv_max=worst,
        reliable=worst is None or worst <= settings.high_variance_cv_percent,
        stale=entry.stale,
        date=iso_day(ex.created),
    )


def ranked(views: list[MachineView], key: str) -> list[tuple[int | None, MachineView]]:
    """Toutes les machines pour un onglet : classées par points décroissants (égalité : slug),
    puis les non classées (rang None) en fin de liste, par nom."""
    scored = sorted(
        (v for v in views if v.points[key] is not None),
        key=lambda v: (-(v.points[key] or 0.0), v.slug),
    )
    unranked = sorted((v for v in views if v.points[key] is None), key=lambda v: (v.name, v.slug))
    return [(i, v) for i, v in enumerate(scored, 1)] + [(None, v) for v in unranked]


def median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = len(s) // 2
    return s[k] if len(s) % 2 else (s[k - 1] + s[k]) / 2


def data_json(
    views: list[MachineView], reference: Reference, generated: datetime
) -> dict[str, Any]:
    """Données agrégées publiées en data.json (forme inspirée de handoff/data.example.json)."""
    return {
        "schema": DATA_SCHEMA,
        "generated": generated.isoformat(timespec="seconds"),
        "reference": {"machine": reference.machine, "digest": reference.digest, "points": 1000},
        "machines": [
            {
                "id": v.slug,
                "name": v.name,
                "type": v.kind,
                "cpu": {"model": v.cpu, "brand": v.cpu_brand},
                "gpu": {"model": v.gpu, "brand": v.gpu_brand},
                "points": {k: _round(p) for k, p in v.points.items()},
                "info": {
                    "memory_mibs": _round(v.memory_mibs),
                    "disk_seq_mibs": _round(v.disk_seq_mibs),
                    "disk_rand_iops": _round(v.disk_rand_iops),
                },
                "cv_max_pct": _round(v.cv_max, 2),
                "reliable": v.reliable,
                "stale": v.stale,
                "date": v.date,
            }
            for v in views
        ],
    }


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


CSV_HEAD = [
    "machine",
    "type",
    "cpu",
    "gpu",
    *(f"points_{k}" for k in CATEGORY_KEYS),
    "memory_mibs",
    "disk_seq_mibs",
    "disk_rand_iops",
    "cv_max_pct",
    "reliable",
    "stale",
    "date",
]


def csv_text(views: list[MachineView]) -> str:
    """classement.csv : une ligne par machine, valeurs brutes (point décimal), lisible sans JS.
    Les champs venus d'un export qui commencent par =, +, - ou @ sont préfixés d'une apostrophe
    (pas de formule exécutée à l'ouverture dans un tableur)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_HEAD)
    for v in sorted(views, key=lambda v: (-(v.points["combined"] or -1.0), v.slug)):
        writer.writerow(
            [
                _cell(v.name),
                v.kind,
                _cell(v.cpu or ""),
                _cell(v.gpu or ""),
                *("" if (p := v.points[k]) is None else f"{p:.1f}" for k in CATEGORY_KEYS),
                *("" if x is None else f"{x:.0f}" for x in (v.memory_mibs, v.disk_seq_mibs)),
                "" if v.disk_rand_iops is None else f"{v.disk_rand_iops:.0f}",
                "" if v.cv_max is None else f"{v.cv_max:.2f}",
                int(v.reliable),
                int(v.stale),
                v.date or "",
            ]
        )
    return out.getvalue()


def _cell(text: str) -> str:
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
