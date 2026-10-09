"""Rapport HTML déterministe d'une session (docs/rapport.md).

`render_report` est la seule fonction d'entrée : `hwbench report FICHIER.json` et
`hwbench bench --report` passent par elle, toujours à partir du JSON relu (export.from_dict),
jamais du système. Même JSON, même HTML.
"""

from hwbench import __version__
from hwbench.analysis import analyze
from hwbench.display.fmt import fr_date
from hwbench.export import MachineExport
from hwbench.report.html import e, page
from hwbench.report.sections import Context, render_sections
from hwbench.runner import RunSettings

DEFAULT_SETTINGS_NOTE = (
    "Seuils par défaut : cet export (schéma 2) n'enregistre pas les réglages de la session."
)


def report_context(session: MachineExport) -> Context:
    """Seuils de la session s'ils sont enregistrés (schéma 3), sinon ceux par défaut, signalés."""
    settings = session.settings or RunSettings()
    note = None if session.settings is not None else DEFAULT_SETTINGS_NOTE
    return Context(session, analyze(session, settings), settings, note)


def render_report(session: MachineExport) -> str:
    body = render_sections(report_context(session), with_recommendations=True, embed_json=True)
    footer = (
        f"Rapport généré par hwbench {e(__version__)} à partir de la session du "
        f"{e(fr_date(session.created))}. Fichier autonome, consultable hors ligne."
    )
    return page(f"Rapport hwbench · {session.machine}", body, footer)
