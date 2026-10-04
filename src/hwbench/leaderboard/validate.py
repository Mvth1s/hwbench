"""Validation des exports soumis au classement (results/<nom>.json).

Un fichier est accepté s'il :
- porte un nom simple (minuscules, chiffres, tirets) et reste de taille raisonnable ;
- est un export de schéma connu ;
- ne contient aucun identifiant : privacy.scrub ne doit rien masquer (idempotent) ;
- a été noté contre la référence actuelle du paquet (même empreinte), non forcée ;
- n'utilise que des benchs connus, à la version actuelle de leur protocole ;
- a des points cohérents avec ses résultats bruts (pas de points retouchés à la main).
Les résultats restent déclaratifs : rien ne garantit qu'ils ont été mesurés honnêtement.
"""

import json
import math
import re
from pathlib import Path
from typing import Any

from hwbench import privacy
from hwbench.benchmarks.base import benchmark_classes
from hwbench.export import ExportError, MachineExport, from_dict
from hwbench.scoring import Reference, score_results

FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.json$")
MAX_BYTES = 512 * 1024
RESULTS_DIR = "results"


def current_versions() -> dict[str, str]:
    """Version actuelle du protocole de chaque bench (nom -> version)."""
    return {cls.name: cls.version for cls in benchmark_classes()}


def identifier_problems(raw: Any) -> list[str]:
    """Champs que privacy.scrub masquerait : clé sensible ou valeur à motif d'identifiant."""
    problems = []
    if isinstance(raw, dict):
        stack: list[tuple[str, Any]] = [("", raw)]
        while stack:
            path, obj = stack.pop()
            if isinstance(obj, dict):
                for key, value in obj.items():
                    sub = f"{path}.{key}" if path else str(key)
                    if privacy.is_sensitive_key(str(key)) and value is not None:
                        problems.append(f"{sub} : champ d'identifiant interdit")
                    else:
                        stack.append((sub, value))
            elif isinstance(obj, list):
                stack += [(f"{path}[{i}]", item) for i, item in enumerate(obj)]
            elif isinstance(obj, str) and not privacy.is_allowed(path.rsplit(".", 1)[-1], obj):
                for name, pattern in zip(
                    privacy.SENSITIVE_VALUE_NAMES, privacy.SENSITIVE_VALUE_PATTERNS, strict=True
                ):
                    if pattern.search(obj):
                        problems.append(f"{path} : ressemble à un(e) {name}")
    return sorted(problems)


def _points_problems(export: MachineExport, reference: Reference) -> list[str]:
    recomputed = {
        s.backend.name: s.points for s in score_results(export.results, reference).backends
    }
    problems = []
    for stored in export.backend_scores:
        expected = recomputed.get(stored.backend.name)
        if stored.points is None or expected is None:
            continue
        if not math.isclose(stored.points, expected, rel_tol=1e-9):
            problems.append(
                f"{stored.backend.name} : points incohérents avec les résultats "
                f"({stored.points:.3f} au lieu de {expected:.3f})"
            )
    return problems


def validate_payload(raw: Any, reference: Reference) -> list[str]:
    problems = []
    if privacy.scrub(raw) != raw:
        found = identifier_problems(raw)
        problems += found or ["contient des données que privacy.scrub masquerait"]
    try:
        export = from_dict(raw)
    except ExportError as exc:
        return [*problems, str(exc)]

    if export.reference is None:
        problems.append("exporté sans référence : relancer hwbench export avec la version actuelle")
    else:
        if export.reference.digest != reference.digest:
            problems.append(
                "noté contre une autre référence que celle du paquet actuel : "
                "relancer hwbench export avec la dernière version de hwbench"
            )
        if export.reference.forced or export.reference.forced_reasons:
            problems.append("noté contre une référence forcée (--force)")

    versions = current_versions()
    for r in export.results:
        if r.name not in versions:
            problems.append(f"{r.name} : bench inconnu")
        elif r.version != versions[r.name]:
            problems.append(
                f"{r.name} : protocole v{r.version}, la version actuelle est "
                f"v{versions[r.name]} (relancer avec la dernière version de hwbench)"
            )
    if export.reference is not None and export.reference.digest == reference.digest:
        problems += _points_problems(export, reference)
    return problems


def validate_file(path: Path, reference: Reference) -> list[str]:
    """Liste des problèmes du fichier ; vide s'il est accepté."""
    problems = []
    if path.parent.name != RESULTS_DIR:
        problems.append(f"doit être placé directement dans {RESULTS_DIR}/")
    if not FILENAME_RE.match(path.name):
        problems.append(
            "nom de fichier invalide : minuscules, chiffres et tirets, extension .json "
            "(ex. results/mon-desktop.json)"
        )
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            return [*problems, f"fichier trop gros ({size} octets, maximum {MAX_BYTES})"]
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [*problems, f"illisible : {exc.strerror or exc}"]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [*problems, f"JSON invalide : {exc}"]
    return problems + validate_payload(raw, reference)
