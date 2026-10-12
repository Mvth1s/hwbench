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


# --- Page machine ---------------------------------------------------------------------


@dataclass(frozen=True)
class RunsRow:
    label: str
    runs: list[float]
    median: float
    burst: float
    cv_text: str
    noisy: bool  # CV au-dessus du seuil


RUNS_SPAN = 4.0  # ± % autour de la médiane ; au-delà, le point est posé au bord


def runs_chart(rows: list[RunsRow], caption: str, median_label: str) -> Markup:
    """Chaque run (●) et le burst (◇) en écart relatif à la médiane, CV à droite."""
    w, ml, mr, mt, row_h = 640, 190, 70, 26, 30
    h = mt + len(rows) * row_h + 10
    iw = w - ml - mr

    def sx(delta: float) -> float:
        clamped = max(-RUNS_SPAN, min(RUNS_SPAN, delta))
        return ml + (clamped + RUNS_SPAN) / (2 * RUNS_SPAN) * iw

    def delta(value: float, median: float) -> float:
        d = (value / median - 1) * 100 if median else 0.0
        return d if math.isfinite(d) else 0.0

    parts = [
        f'<svg class="hw-svg hw-svg--wide" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(caption)}">'
    ]
    for t in (-4, -2, 0, 2, 4):
        cls = "axis" if t == 0 else "grid"
        label = escape(median_label) if t == 0 else f"{'+' if t > 0 else '−'}{abs(t)} %"
        parts.append(
            f'<line class="{cls}" x1="{_r(sx(t))}" x2="{_r(sx(t))}" y1="{mt - 6}" y2="{h - 10}"/>'
            f'<text class="mono" x="{_r(sx(t))}" y="{mt - 10}" text-anchor="middle">{label}</text>'
        )
    for i, row in enumerate(rows):
        y = mt + i * row_h + row_h / 2
        parts.append(
            f'<text class="ink" x="{ml - 12}" y="{_r(y + 4)}" text-anchor="end">'
            f"{escape(row.label)}</text>"
        )
        for run in row.runs:
            parts.append(
                f'<circle class="run" cx="{_r(sx(delta(run, row.median)))}" cy="{_r(y)}" r="4"/>'
            )
        bx, s = sx(delta(row.burst, row.median)), 4.6
        parts.append(
            f'<polygon class="burst" points="{_r(bx)},{_r(y - s)} {_r(bx + s)},{_r(y)} '
            f'{_r(bx)},{_r(y + s)} {_r(bx - s)},{_r(y)}"/>'
            f'<text class="mono{" alert" if row.noisy else ""}" x="{w - 4}" y="{_r(y + 4)}" '
            f'text-anchor="end">{escape(row.cv_text)}</text>'
        )
    parts.append("</svg>")
    return Markup("".join(parts))


@dataclass(frozen=True)
class TempRow:
    label: str
    before: float
    after: float


def dumbbell(rows: list[TempRow], caption: str) -> Markup:
    """Température avant (○) et après (■) chaque test : deux relevés, jamais une courbe."""
    w, ml, mr, mt, row_h = 640, 190, 16, 26, 26
    h = mt + len(rows) * row_h + 14
    temps = [t for r in rows for t in (r.before, r.after)]
    lo = math.floor(min([40.0, *temps]) / 10) * 10
    hi = math.ceil(max([60.0, *temps]) / 10) * 10
    iw = w - ml - mr

    def sx(t: float) -> float:
        return ml + (t - lo) / (hi - lo) * iw

    parts = [
        f'<svg class="hw-svg hw-svg--wide" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(caption)}">'
    ]
    for t in range(lo, hi + 1, 10):
        parts.append(
            f'<line class="grid" x1="{_r(sx(t))}" x2="{_r(sx(t))}" y1="{mt - 6}" y2="{h - 10}"/>'
            f'<text class="mono" x="{_r(sx(t))}" y="{mt - 10}" text-anchor="middle">{t} °C</text>'
        )
    for i, row in enumerate(rows):
        y = mt + i * row_h + row_h / 2
        a, b, s = sx(row.before), sx(row.after), 4.2
        parts.append(
            f'<text class="ink" x="{ml - 12}" y="{_r(y + 4)}" text-anchor="end">'
            f"{escape(row.label)}</text>"
            f'<line class="link" x1="{_r(a)}" x2="{_r(b)}" y1="{_r(y)}" y2="{_r(y)}"/>'
            f'<circle class="before" cx="{_r(a)}" cy="{_r(y)}" r="4.5"/>'
            f'<rect class="after" x="{_r(b - s)}" y="{_r(y - s)}" width="{_r(2 * s)}" '
            f'height="{_r(2 * s)}"/>'
        )
    parts.append("</svg>")
    return Markup("".join(parts))


@dataclass(frozen=True)
class Slice:
    label: str
    value: float
    tone: str  # classe de couleur : s1, s2, s3, acc, ctl


def donut(slices: list[Slice], caption: str, center: str, center_label: str) -> Markup:
    """Anneau de répartition (réservé au temps de test), légende rendue par le template."""
    size, thick = 220, 24
    c, outer = size / 2, size / 2 - 4
    inner = outer - thick
    total = sum(s.value for s in slices) or 1.0
    parts = [
        f'<svg class="hw-svg hw-donut" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="{escape(caption)}">'
    ]
    start = -math.pi / 2
    for s in slices:
        end = start + s.value / total * 2 * math.pi
        gap = 0.012 if s.value < total else 0.0
        a, b = start + gap, max(start + gap, end - gap)
        large = 1 if b - a > math.pi else 0
        if b - a >= 2 * math.pi - 0.001:  # une seule part : deux demi-arcs
            b = a + 2 * math.pi - 0.001

        def pt(r: float, t: float) -> str:
            return f"{_r(c + math.cos(t) * r)},{_r(c + math.sin(t) * r)}"

        parts.append(
            f'<path class="slice tone-{s.tone}" d="M{pt(outer, a)} A{_r(outer)},{_r(outer)} 0 '
            f"{large} 1 {pt(outer, b)} L{pt(inner, b)} A{_r(inner)},{_r(inner)} 0 {large} 0 "
            f'{pt(inner, a)} Z"/>'
        )
        start = end
    parts.append(
        f'<text class="center" x="{_r(c)}" y="{_r(c - 2)}" text-anchor="middle">'
        f"{escape(center)}</text>"
        f'<text x="{_r(c)}" y="{_r(c + 18)}" text-anchor="middle">{escape(center_label)}</text>'
        "</svg>"
    )
    return Markup("".join(parts))
