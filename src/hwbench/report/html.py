"""Moteur de rendu HTML commun au rapport (report/) et au site du classement (leaderboard/).

Page unique, CSS intégré, aucune ressource externe (ni police, ni script, ni @import) : le
rapport s'ouvre hors ligne et s'imprime. Thème clair et sombre (prefers-color-scheme). Tout
texte venu d'une session ou d'un export passe par `e()` (html.escape) : un export peut venir de
n'importe qui.
"""

import html
from collections.abc import Iterable

from hwbench.analysis import Status
from hwbench.report.texts import STATUS_LABELS

# favicon intégré (data URI) : aucune requête externe
FAVICON = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<text y='.9em' font-size='90'>📊</text></svg>"
)

CSS = """
:root { color-scheme: light dark; --fg: #1d2129; --bg: #fff; --muted: #5f6b7a;
  --line: #d9dee5; --accent: #0b6bcb; --row: #f4f6f9; --data: #0b6bcb;
  --fix: #b42318; --check: #9a6700; --ok: #1a7f37; --info: #5f6b7a; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6e9ee; --bg: #14171c;
  --muted: #9aa5b4; --line: #2c323b; --accent: #5aa9ff; --row: #1b1f26; --data: #5aa9ff;
  --fix: #ff7b72; --check: #e3b341; --ok: #56d364; --info: #9aa5b4; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1100px; padding: 24px 16px; font: 15px/1.5 system-ui,
  sans-serif; color: var(--fg); background: var(--bg); }
h1 { margin: 0 0 4px; } h2 { margin-top: 32px; } h3 { margin-top: 20px; }
a { color: var(--accent); }
.muted { color: var(--muted); } .small { font-size: 13px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
tbody tr:nth-child(odd) { background: var(--row); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
code, pre { font: 13px/1.4 ui-monospace, monospace; }
pre { padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px; overflow-x: auto; }
abbr[title] { text-decoration: underline dotted; cursor: help; }
.tabs > input { position: absolute; opacity: 0; }
.tabs > label { display: inline-block; padding: 6px 14px; margin: 0 4px 0 0;
  border: 1px solid var(--line); border-radius: 6px; cursor: pointer; }
.tabs > input:checked + label { background: var(--accent); color: var(--bg);
  border-color: var(--accent); }
.tabs > input:focus-visible + label { outline: 2px solid var(--accent); outline-offset: 2px; }
.panel { display: none; }
#tab-combined:checked ~ #panel-combined, #tab-cpu_single:checked ~ #panel-cpu_single,
#tab-cpu_multi:checked ~ #panel-cpu_multi, #tab-gpu:checked ~ #panel-gpu { display: block; }
.status { display: inline-block; padding: 0 8px; border: 1px solid currentColor;
  border-radius: 10px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.status-fix { color: var(--fix); } .status-check { color: var(--check); }
.status-ok { color: var(--ok); } .status-info { color: var(--info); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px; margin: 16px 0; }
.tile { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.tile .label { color: var(--muted); font-size: 13px; }
.tile .value { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
ul.findings { list-style: none; padding: 0; }
ul.findings li { margin: 8px 0; }
figure { margin: 12px 0; }
figure svg { width: 100%; height: auto; max-width: 720px; }
figcaption { color: var(--muted); font-size: 13px; }
svg text { fill: var(--fg); font: 12px system-ui, sans-serif; }
svg .bar { fill: var(--data); } svg .grid { stroke: var(--line); }
svg .temp { stroke: var(--data); stroke-width: 2; fill: none; }
svg .dot { fill: var(--data); } svg .band { fill: var(--row); }
svg .limit { stroke: var(--fix); stroke-dasharray: 4 3; }
table.values { width: auto; font-size: 13px; }
@media print { body { max-width: none; padding: 0; color: #000; background: #fff; }
  a { color: inherit; text-decoration: none; } .tile, pre { break-inside: avoid; }
  h2 { break-after: avoid; } figure { break-inside: avoid; } }
"""


def e(value: object) -> str:
    """Texte échappé pour HTML (contenu et attributs entre guillemets)."""
    return html.escape("" if value is None else str(value), quote=True)


def page(title: str, body: str, footer: str) -> str:
    """Page complète ; `body` et `footer` sont déjà du HTML (textes échappés par l'appelant)."""
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="{FAVICON}">
<title>{e(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<footer class="muted small">{footer}</footer>
</body>
</html>
"""


def kv(rows: Iterable[tuple[str, object]]) -> str:
    """Tableau clé / valeur, valeurs échappées ; une valeur vide s'affiche « — »."""
    return (
        "<table><tbody>"
        + "".join(
            f"<tr><th>{e(k)}</th><td>{e(v if v not in (None, '') else '—')}</td></tr>"
            for k, v in rows
        )
        + "</tbody></table>"
    )


def table(
    headers: list[str], rows: list[list[str]], numeric: Iterable[int] = (), css: str = ""
) -> str:
    """Tableau ; en-têtes échappés, cellules déjà en HTML ; `numeric` : colonnes à droite."""
    nums = set(numeric)

    def cls(i: int) -> str:
        return ' class="num"' if i in nums else ""

    head = "".join(f"<th{cls(i)}>{e(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{cell}</td>" for i, cell in enumerate(row)) + "</tr>"
        for row in rows
    )
    attr = f' class="{css}"' if css else ""
    return f"<table{attr}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def status_badge(status: Status) -> str:
    return f'<span class="status status-{status.value}">{e(STATUS_LABELS[status])}</span>'
