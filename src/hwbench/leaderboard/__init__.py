"""Classement statique : validation des exports soumis (results/) et génération du site.

La génération du site (site.py, charts.py) demande l'extra « site » (Jinja2, et MarkupSafe qu'il
installe) ; la validation et le résumé n'en dépendent pas, le CLI de benchmark non plus.
"""

SITE_EXTRA_MISSING = (
    "la génération du site demande l'extra « site » (Jinja2) : pip install 'hwbench[site]'"
)
SITE_EXTRA_MODULES = frozenset({"jinja2", "markupsafe"})
