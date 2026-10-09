"""Graphiques SVG générés en Python, sans bibliothèque : barres horizontales et frise thermique.

Chaque graphique est suivi de ses valeurs en texte (tableau), lisibles sans le dessin et à
l'impression. Les coordonnées sont arrondies : même session, même SVG, à l'octet près.
"""

from dataclasses import dataclass

from hwbench.display.fmt import num
from hwbench.report.html import e, table

WIDTH = 720
LABEL_W = 260
VALUE_W = 110
ROW_H = 26


def _f(x: float) -> str:
    return f"{x:.1f}"


@dataclass(frozen=True)
class Bar:
    label: str
    value: float
    text: str  # valeur formatée, affichée au bout de la barre et dans le tableau


def bars(title: str, rows: list[Bar], caption: str = "") -> str:
    """Barres horizontales proportionnelles à la plus grande valeur (axe partant de zéro)."""
    if not rows:
        return ""
    peak = max(r.value for r in rows) or 1.0
    span = WIDTH - LABEL_W - VALUE_W
    height = ROW_H * len(rows) + 8
    shapes = []
    for i, r in enumerate(rows):
        y = 4 + i * ROW_H
        w = max(r.value, 0.0) / peak * span
        shapes.append(
            f'<text x="{LABEL_W - 8}" y="{_f(y + 17)}" text-anchor="end">{e(r.label)}</text>'
            f'<rect class="bar" x="{LABEL_W}" y="{_f(y + 4)}" width="{_f(w)}" height="18"/>'
            f'<text x="{_f(LABEL_W + w + 6)}" y="{_f(y + 17)}">{e(r.text)}</text>'
        )
    svg = (
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{e(title)}">'
        f"<title>{e(title)}</title>{''.join(shapes)}</svg>"
    )
    values = table(
        ["Mesure", "Valeur"], [[e(r.label), e(r.text)] for r in rows], numeric=[1], css="values"
    )
    note = f"<figcaption>{e(caption)}</figcaption>" if caption else ""
    return f"<figure>{svg}{note}</figure>{values}"


@dataclass(frozen=True)
class Segment:
    label: str
    duration_s: float
    before_c: float | None
    after_c: float | None


TIMELINE_H = 220
PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 16, 40


def timeline(segments: list[Segment], threshold_c: float | None) -> str:
    """Frise de la session : un segment par test (largeur = durée), températures CPU relevées au
    début et à la fin de chaque test, reliées par un trait. hwbench ne mesure rien pendant un
    test : le trait ne montre pas l'évolution réelle entre les deux relevés."""
    measured = [t for s in segments for t in (s.before_c, s.after_c) if t is not None]
    if not segments or not measured:
        return ""
    total = sum(max(s.duration_s, 0.0) for s in segments) or 1.0
    low = min(20.0, min(measured) - 5)
    high = max([*measured, threshold_c or 0.0]) + 5
    plot_w = WIDTH - PAD_L - PAD_R
    plot_h = TIMELINE_H - PAD_T - PAD_B

    def y(t: float) -> float:
        return PAD_T + (high - t) / (high - low) * plot_h

    shapes = []
    for tick in range(int(low // 10 + 1) * 10, int(high) + 1, 10):
        shapes.append(
            f'<line class="grid" x1="{PAD_L}" x2="{WIDTH - PAD_R}" y1="{_f(y(tick))}" '
            f'y2="{_f(y(tick))}"/><text x="{PAD_L - 6}" y="{_f(y(tick) + 4)}" '
            f'text-anchor="end">{tick}</text>'
        )
    x = float(PAD_L)
    for i, s in enumerate(segments, start=1):
        w = max(s.duration_s, 0.0) / total * plot_w
        if i % 2:
            shapes.append(
                f'<rect class="band" x="{_f(x)}" y="{PAD_T}" width="{_f(w)}" height="{plot_h}"/>'
            )
        points = [(x, s.before_c), (x + w, s.after_c)]
        known = [(px, t) for px, t in points if t is not None]
        if len(known) == 2:
            (x1, t1), (x2, t2) = known
            shapes.append(
                f'<line class="temp" x1="{_f(x1)}" y1="{_f(y(t1))}" x2="{_f(x2)}" '
                f'y2="{_f(y(t2))}"/>'
            )
        for px, t in known:
            shapes.append(f'<circle class="dot" cx="{_f(px)}" cy="{_f(y(t))}" r="3"/>')
        shapes.append(
            f'<text x="{_f(x + w / 2)}" y="{TIMELINE_H - PAD_B + 16}" '
            f'text-anchor="middle">{i}</text>'
        )
        x += w
    if threshold_c is not None:
        shapes.append(
            f'<line class="limit" x1="{PAD_L}" x2="{WIDTH - PAD_R}" y1="{_f(y(threshold_c))}" '
            f'y2="{_f(y(threshold_c))}"/><text x="{WIDTH - PAD_R}" '
            f'y="{_f(y(threshold_c) - 4)}" text-anchor="end">seuil haut du capteur '
            f"{num(threshold_c, 0)} °C</text>"
        )
    shapes.append(
        f'<text x="{PAD_L}" y="{TIMELINE_H - 4}">°C, tests dans l\'ordre (largeur = durée)</text>'
    )
    title = "Températures CPU relevées avant et après chaque test"
    svg = (
        f'<svg viewBox="0 0 {WIDTH} {TIMELINE_H}" role="img" aria-label="{e(title)}">'
        f"<title>{e(title)}</title>{''.join(shapes)}</svg>"
    )

    def celsius(t: float | None) -> str:
        return "—" if t is None else f"{num(t, 0)} °C"

    values = table(
        ["#", "Test", "Durée", "Avant", "Après"],
        [
            [
                str(i),
                e(s.label),
                e(f"{num(s.duration_s, 0)} s"),
                celsius(s.before_c),
                celsius(s.after_c),
            ]
            for i, s in enumerate(segments, start=1)
        ],
        numeric=[0, 2, 3, 4],
        css="values",
    )
    caption = (
        "Température CPU relevée au début et à la fin de chaque test, pas pendant : le trait "
        "relie deux relevés et ne montre pas l'évolution réelle entre eux."
    )
    return f"<figure>{svg}<figcaption>{e(caption)}</figcaption></figure>{values}"
