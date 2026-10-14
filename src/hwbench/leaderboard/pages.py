"""Valeurs techniques injectées dans les textes du site, et données des pages de contenu
(Méthodologie, Soumettre, Mentions légales, 404).

Aucun chiffre technique (version, schéma, seuil, nombre de runs, référence, version d'outil)
n'est écrit dans le catalogue : les textes portent des marqueurs ({cv}, {version}…) remplacés
par `fill` avec les valeurs lues dans le code et dans la référence du paquet.
"""

import re
from datetime import datetime
from typing import Any

from hwbench import __version__, privacy
from hwbench.benchmarks.external._gpu import RESOLUTION
from hwbench.benchmarks.external.fio import JOBS
from hwbench.display.fmt import compact, fr_date, grouped
from hwbench.export import EXPORT_SCHEMA_VERSION, READABLE_SCHEMA_VERSIONS
from hwbench.labels import CATEGORY_LABELS, bench_label, unit_label
from hwbench.leaderboard.catalog import FR
from hwbench.runner import DEFAULT_MAX_WARMUP_S, RunSettings
from hwbench.scoring import Reference, is_official

# Contraste minimal du texte (WCAG AA), vérifié par les tests sur les couleurs du CSS
CONTRAST_MIN = 4.5
EXAMPLE_POINTS = (1000.0, 1000.0, 250.0)  # exemple de la Méthodologie : single, multi, GPU
DOCS = {
    "native": "https://github.com/Mvth1s/hwbench",
    "sysbench": "https://github.com/akopytov/sysbench",
    "glmark2": "https://github.com/glmark2/glmark2",
    "vkmark": "https://github.com/vkmark/vkmark",
    "fio": "https://fio.readthedocs.io/",
}


def facts(reference: Reference, generated: datetime) -> dict[str, str]:
    """Valeurs remplaçant les marqueurs des textes du catalogue."""
    settings = RunSettings()
    warmups = sorted(DEFAULT_MAX_WARMUP_S.values())
    qd = {job.key: job.iodepth for job in JOBS}
    return {
        "version": __version__,
        "schema": str(EXPORT_SCHEMA_VERSION),
        "cv": compact(settings.high_variance_cv_percent),
        "runs": str(settings.runs),
        "tolerance": compact(settings.warmup_tolerance_percent),
        "hot": compact(settings.hot_start_c),
        "warmup_min": compact(warmups[0]),
        "warmup_max": compact(warmups[-1]),
        "qd_seq": str(qd["seq_read"]),
        "qd_rand": str(qd["rand_read_4k"]),
        "resolution": RESOLUTION.replace("x", " × "),
        "reference": reference.machine,
        "reference_date": fr_date(reference.created) or "—",
        "digest": reference.digest[:19],
        "year": str(generated.year),
        "contrast": compact(CONTRAST_MIN).replace(".", ","),
        "host": FR["mentions"]["host"],
        "contact_private": FR["contact_private"],
    }


def fill(text: str, values: dict[str, str]) -> str:
    """Remplace chaque {marqueur} connu ; les autres accolades restent telles quelles."""
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def methodologie(reference: Reference) -> dict[str, Any]:
    t = FR["methodologie"]
    single, multi, gpu = EXAMPLE_POINTS
    geo = (single * multi * gpu) ** (1 / 3)
    arith = (single + multi + gpu) / 3
    benches = [
        {
            "name": bench_label(entry.id.name),
            "what": t["what"].get(entry.id.name, ""),
            "unit": unit_label(entry.unit),
            "category": CATEGORY_LABELS[entry.category],
            "official": is_official(entry.backend, entry.category),
            "version": " · ".join(
                x
                for x in (
                    t["protocol_v"].replace("{protocol}", entry.id.version),
                    t["tool_v"].replace("{tool}", entry.tool_version)
                    if entry.tool_version
                    else None,
                )
                if x
            ),
            "doc": DOCS.get(entry.backend, DOCS["native"]),
            "doc_label": entry.backend,
        }
        for entry in reference.entries
    ]
    return {
        "example": [
            {"k": k, "v": grouped(v), "n": t["ex_points"]}
            for k, v in zip(("SINGLE", "MULTI", "GPU"), EXAMPLE_POINTS, strict=True)
        ]
        + [
            {
                "k": t["ex_combined"],
                "v": grouped(geo),
                "n": "∛(" + " × ".join(grouped(v) for v in EXAMPLE_POINTS) + ")",
            }
        ],
        "example_values": {"arith": grouped(arith), "geo": grouped(geo)},
        "benches": benches,
    }


def readable_schemas() -> str:
    return ",".join(str(v) for v in READABLE_SCHEMA_VERSIONS)


def contrast_ratio(foreground: str, background: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs #RRGGBB."""

    def luminance(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _js_pattern(pattern: re.Pattern[str]) -> dict[str, str]:
    """Motif Python transmis au navigateur (syntaxe commune aux deux moteurs), drapeau i."""
    return {"source": pattern.pattern, "flags": "i" if pattern.flags & re.IGNORECASE else ""}


def privacy_rules() -> dict[str, object]:
    """Règles de privacy.py pour le contrôle local de Soumettre : clés sensibles, valeurs
    sensibles (MAC, UUID, EUI), clés autorisées avec le format exact de leur valeur. Le
    JavaScript ne porte aucune liste en dur : il applique ces motifs."""
    return {
        "keys": _js_pattern(privacy.SENSITIVE_KEY_RE),
        "values": [
            _js_pattern(p) | {"name": name}
            for p, name in zip(
                privacy.SENSITIVE_VALUE_PATTERNS, privacy.SENSITIVE_VALUE_NAMES, strict=True
            )
        ],
        "allowed": {key: _js_pattern(p) for key, p in privacy.NON_SENSITIVE_KEYS.items()},
    }
