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

import errno
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any

from hwbench import privacy
from hwbench.benchmarks.base import benchmark_classes
from hwbench.export import ExportError, MachineExport, from_dict
from hwbench.scoring import (
    BackendScore,
    CategoryScore,
    CombinedScore,
    Reference,
    score_results,
)

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


_ABSENT = object()  # entrée absente, distincte de points à None


def _score_map(
    backends: list[BackendScore], categories: list[CategoryScore], combined: CombinedScore | None
) -> dict[str, float | None]:
    scores: dict[str, float | None] = {f"backend {b.backend.name}": b.points for b in backends}
    scores |= {f"catégorie {c.category.value}": c.points for c in categories}
    if combined is not None:
        scores["score combiné"] = combined.points
    return scores


def _same(got: object, want: object) -> bool:
    if got is _ABSENT or want is _ABSENT or got is None or want is None:
        return got is want
    return math.isclose(got, want, rel_tol=1e-9)  # type: ignore[arg-type]


def _fmt(points: object) -> str:
    if points is _ABSENT:
        return "absent"
    return "non comparable" if points is None else f"{points:.3f}"


def _points_problems(export: MachineExport, reference: Reference) -> list[str]:
    """Scores de l'export comparés, entrée par entrée, à ceux recalculés depuis les résultats.

    Strict : mêmes backends, catégories et combiné, mêmes points (None compris). Supprimer une
    entrée ou mettre des points à null n'échappe pas au contrôle.
    """
    exp = score_results(export.results, reference)
    want = _score_map(exp.backends, exp.categories, exp.combined)
    got = _score_map(export.backend_scores, export.categories, export.combined)
    return [
        f"{key} : points incohérents avec les résultats "
        f"({_fmt(got.get(key, _ABSENT))} au lieu de {_fmt(want.get(key, _ABSENT))})"
        for key in sorted(want.keys() | got.keys())
        if not _same(got.get(key, _ABSENT), want.get(key, _ABSENT))
    ]


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
    if path.parent.name != RESULTS_DIR or not resolves_to_itself(path.parent):
        # rien n'est ouvert : un dossier results/ remplacé par un lien pointerait ailleurs
        return [f"doit être placé directement dans {RESULTS_DIR}/, sans lien symbolique"]
    problems = []
    if not FILENAME_RE.match(path.name):
        problems.append(
            "nom de fichier invalide : minuscules, chiffres et tirets, extension .json "
            "(ex. results/mon-desktop.json)"
        )
    try:
        data = read_bounded(path)
    except SubmissionError as exc:
        return [*problems, str(exc)]
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [*problems, f"JSON invalide : {exc}"]
    return problems + validate_payload(raw, reference)


def resolves_to_itself(directory: Path) -> bool:
    """Vrai si aucun élément du chemin du dossier n'est un lien symbolique.

    O_NOFOLLOW ne protège que le dernier élément : si la PR remplace le dossier results/ par
    un lien, results/x.json serait lu ailleurs que dans le dépôt.
    """
    return os.path.realpath(directory) == os.path.abspath(directory)


class SubmissionError(ValueError):
    pass


def read_bounded(path: Path, limit: int = MAX_BYTES) -> bytes:
    """Contenu d'un fichier ordinaire, sans suivre de lien symbolique, au plus `limit` octets.

    Une PR peut ajouter un lien symbolique (git le recrée tel quel) vers /dev/zero ou un fichier
    du runner : O_NOFOLLOW le refuse, et la lecture est bornée quoi qu'il arrive.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SubmissionError(
                "lien symbolique refusé : soumettre un fichier ordinaire"
            ) from exc
        raise SubmissionError(f"illisible : {exc.strerror or exc}") from exc
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise SubmissionError("pas un fichier ordinaire")
        data = f.read(limit + 1)
    if len(data) > limit:
        raise SubmissionError(f"fichier trop gros (maximum {limit} octets)")
    return data
