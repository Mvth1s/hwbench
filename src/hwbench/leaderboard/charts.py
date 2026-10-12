"""Graphiques SVG du site, rendus en Python (lisibles sans JavaScript).

Chaque graphique a role="img", un aria-label, et le template le fait suivre d'un tableau
équivalent masqué (lecteurs d'écran). Couleurs par classes CSS (thèmes clair et sombre),
coordonnées arrondies. Tout texte venu d'un export passe par markupsafe.escape.
"""

import math
from dataclasses import dataclass

from hwbench.leaderboard import SITE_EXTRA_MISSING

try:  # extra « site » (MarkupSafe vient avec Jinja2)
    from markupsafe import Markup, escape
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(SITE_EXTRA_MISSING, name=exc.name) from exc

from hwbench.display.fmt import grouped


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    kind: str  # desktop (cercle) ou laptop (carré)
    label: str


def ticks(maximum: float) -> list[float]:
    """Graduations « rondes » (1, 2, 2,5 ou 5 × 10^k, au moins 50) de 0 à `maximum`, 5
    intervalles au plus quelle que soit la valeur : un export retouché aux points démesurés ne
    doit pas faire générer des milliards de graduations."""
    if not math.isfinite(maximum) or maximum <= 0:
        return [0.0]
    magnitude = 10 ** math.floor(math.log10(maximum / 5))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if maximum / (m * magnitude) <= 5)
    step = max(50.0, step)
    return [i * step for i in range(int(maximum // step) + 1)]


def _r(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _mark(kind: str, x: float, y: float, r: float, cls: str) -> str:
    if kind == "laptop":
        s = r * 0.88
        return (
            f'<rect class="{cls}" x="{_r(x - s)}" y="{_r(y - s)}" '
            f'width="{_r(2 * s)}" height="{_r(2 * s)}"/>'
        )
    return f'<circle class="{cls}" cx="{_r(x)}" cy="{_r(y)}" r="{_r(r)}"/>'


def scatter(points: list[Point], caption: str, x_label: str, y_label: str, ref: str) -> Markup:
    """Nuage CPU (√ single × multi) contre GPU, référence 1000 en pointillés."""
    points = [p for p in points if math.isfinite(p.x) and math.isfinite(p.y)]
    w, h, ml, mr, mt, mb = 640, 380, 52, 14, 16, 42
    x_max = max([1250.0, *(p.x for p in points)]) * 1.05
    y_max = max([1250.0, *(p.y for p in points)]) * 1.05
    iw, ih = w - ml - mr, h - mt - mb

    def sx(v: float) -> float:
        return ml + v / x_max * iw

    def sy(v: float) -> float:
        return mt + ih - v / y_max * ih

    parts = [
        f'<svg class="hw-svg" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(caption)}">'
    ]
    for t in ticks(x_max):
        parts.append(
            f'<line class="grid" x1="{_r(sx(t))}" x2="{_r(sx(t))}" y1="{mt}" y2="{mt + ih}"/>'
            f'<text x="{_r(sx(t))}" y="{h - 24}" text-anchor="middle">{grouped(t)}</text>'
        )
    for t in ticks(y_max):
        parts.append(
            f'<line class="grid" x1="{ml}" x2="{ml + iw}" y1="{_r(sy(t))}" y2="{_r(sy(t))}"/>'
            f'<text x="{ml - 8}" y="{_r(sy(t) + 4)}" text-anchor="end">{grouped(t)}</text>'
        )
    parts.append(
        f'<line class="ref" x1="{_r(sx(1000))}" x2="{_r(sx(1000))}" y1="{mt}" y2="{mt + ih}"/>'
        f'<line class="ref" x1="{ml}" x2="{ml + iw}" y1="{_r(sy(1000))}" y2="{_r(sy(1000))}"/>'
        f'<text class="ink" x="{_r(sx(1000) + 6)}" y="{mt + 12}">{escape(ref)}</text>'
        f'<text x="{ml + iw}" y="{h - 4}" text-anchor="end">{escape(x_label)} →</text>'
        f'<text transform="translate(14 {_r(mt + ih / 2)}) rotate(-90)" '
        f'text-anchor="middle">{escape(y_label)} →</text>'
    )
    r = 2.6 if len(points) > 120 else 4.2
    for p in points:
        parts.append(
            f"<g><title>{escape(p.label)} — CPU {grouped(p.x)} · GPU {grouped(p.y)}</title>"
            + _mark(p.kind, sx(p.x), sy(p.y), r, "pt")
            + "</g>"
        )
    parts.append("</svg>")
    return Markup("".join(parts))


HIST_MAX_BINS = 40


@dataclass(frozen=True)
class Histogram:
    svg: Markup
    bands: list[tuple[str, int]]  # (tranche, nombre de machines) pour le tableau équivalent


def histogram(values: list[float], median: float, caption: str, median_label: str) -> Histogram:
    w, h, ml, mr, mt, mb = 560, 260, 36, 10, 24, 32
    values = [v for v in values if math.isfinite(v)]
    v_max = max([1100.0, *values])
    width = 200.0 if v_max > 1600 else 100.0
    if v_max / width > HIST_MAX_BINS:  # valeurs démesurées : tranches plus larges, nombre borné
        width = ticks(v_max)[1] / 2
    n = min(math.ceil(v_max / width), HIST_MAX_BINS)
    counts = [sum(1 for v in values if i * width <= v < (i + 1) * width) for i in range(n)]
    c_max = max([1, *counts])
    iw, ih = w - ml - mr, h - mt - mb
    bw = iw / n

    def sx(v: float) -> float:
        return ml + v / (n * width) * iw

    parts = [
        f'<svg class="hw-svg" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(caption)}">',
        f'<line class="axis" x1="{ml}" x2="{ml + iw}" y1="{mt + ih}" y2="{mt + ih}"/>',
    ]
    for i, c in enumerate(counts):
        bh = c / c_max * ih
        x = ml + i * bw
        parts.append(
            f'<rect class="bar" x="{_r(x + 1.5)}" y="{_r(mt + ih - bh)}" '
            f'width="{_r(max(1.0, bw - 3))}" height="{_r(bh)}"/>'
        )
        if c and bw > 16:
            parts.append(
                f'<text class="mono" x="{_r(x + bw / 2)}" y="{_r(mt + ih - bh - 5)}" '
                f'text-anchor="middle">{c}</text>'
            )
    every = 2 if n > 12 else 1
    for i in range(0, n + 1, every):
        parts.append(
            f'<text class="mono" x="{_r(sx(i * width))}" y="{h - 12}" '
            f'text-anchor="middle">{grouped(i * width)}</text>'
        )
    parts.append(
        f'<line class="ref" x1="{_r(sx(median))}" x2="{_r(sx(median))}" y1="{mt - 6}" '
        f'y2="{mt + ih}"/><text class="ink" x="{_r(sx(median) + 5)}" y="{mt - 9}">'
        f"{escape(median_label)} {grouped(median)}</text></svg>"
    )
    bands = [(f"{grouped(i * width)}–{grouped((i + 1) * width)}", c) for i, c in enumerate(counts)]
    return Histogram(Markup("".join(parts)), bands)
