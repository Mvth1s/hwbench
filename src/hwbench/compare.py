"""Comparaison de plusieurs exports ; le premier fichier sert de base.

Rien n'est comparé « à peu près » :
- un bench n'a d'écart que si son identité (BackendId : version du protocole, version de
  l'outil sauf pour fio, mode de présentation) est la même dans les deux fichiers ;
- un score de catégorie ou le combiné n'a d'écart que si les deux fichiers ont été notés contre
  la même référence (même empreinte) avec exactement la même liste de backends (et, pour le
  combiné, les mêmes pondérations).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from hwbench.export import MachineExport
from hwbench.results import (
    TOOL_VERSION_NOT_IN_IDENTITY,
    BackendId,
    Category,
    Result,
    disk_key,
    driver_key,
    gpu_key,
)
from hwbench.scoring import CategoryScore, CombinedScore, ScoreIssue

CATEGORY_ORDER = tuple(Category)


class Incomparable(StrEnum):
    MISSING = "missing"  # mesure absente de ce fichier ou de la base
    IDENTITY_DIFFERS = "identity_differs"  # version, outil ou présentation différents
    NO_REFERENCE = "no_reference"  # fichier exporté sans référence : pas de points
    REFERENCE_DIFFERS = "reference_differs"
    NOT_SCORED = "not_scored"  # déjà non comparable à sa propre référence
    BACKENDS_DIFFER = "backends_differ"
    WEIGHTS_DIFFER = "weights_differ"


class CompareWarning(StrEnum):
    BENCH_VERSION_DIFFERS = "bench_version_differs"
    REFERENCE_DIFFERS = "reference_differs"
    FORCED_REFERENCE = "forced_reference"
    # information : le pilote n'est pas dans BackendId, l'écart reste calculé
    DRIVER_DIFFERS = "driver_differs"
    # même règle pour la version d'un outil hors identité (fio) : signalée sur un même disque
    TOOL_VERSION_DIFFERS = "tool_version_differs"
    # disques différents : versions citées pour information, sans avertissement
    TOOL_VERSION_INFO = "tool_version_info"


# Notices d'information : affichées sans ⚠
INFO_NOTICES = frozenset({CompareWarning.TOOL_VERSION_INFO})


@dataclass(frozen=True)
class Cell:
    value: float | None
    delta_percent: float | None = None  # écart à la base ; None pour la base elle-même
    better: bool | None = None  # écart favorable, compte tenu de « plus haut = mieux »
    issue: Incomparable | None = None
    score_issue: ScoreIssue | None = None  # raison d'origine quand issue = NOT_SCORED


@dataclass(frozen=True)
class BenchRow:
    name: str
    category: Category
    unit: str
    identities: list[BackendId | None]
    cells: list[Cell]
    drivers: list[str | None] = field(default_factory=list)  # pilote GPU par fichier (brut)
    gpus: list[str | None] = field(default_factory=list)  # renderer GPU par fichier (brut)
    # version de l'outil et modèle du disque par fichier (benchs hors identité d'outil : fio)
    tool_versions: list[str | None] = field(default_factory=list)
    devices: list[str | None] = field(default_factory=list)
    detail: str | None = None  # sous-mesure d'un bench (disque : seq_read…), ligne d'information


@dataclass(frozen=True)
class ScoreRow:
    category: Category | None  # None : score combiné
    cells: list[Cell]


@dataclass(frozen=True)
class Notice:
    code: CompareWarning
    subject: str  # nom du bench, ou fichier concerné
    values: list[str | None] = field(default_factory=list)  # ex. pilote par fichier


@dataclass(frozen=True)
class Comparison:
    exports: list[MachineExport]
    scores: list[ScoreRow]
    benches: list[BenchRow]
    warnings: list[Notice]


def _delta(value: float, base: float, higher_is_better: bool) -> tuple[float, bool | None]:
    delta = 100.0 * (value / base - 1.0) if base else 0.0
    better = None if delta == 0 else (delta > 0) == higher_is_better
    return delta, better


def _bench_rows(exports: list[MachineExport]) -> list[BenchRow]:
    by_file = [{r.name: r for r in e.results} for e in exports]
    names: list[str] = []
    for results in by_file:
        names += [n for n in results if n not in names]
    first: dict[str, Result] = {}
    for results in by_file:
        for name, r in results.items():
            first.setdefault(name, r)
    names.sort(
        key=lambda n: (CATEGORY_ORDER.index(first[n].category), first[n].backend != "native", n)
    )

    rows = []
    for name in names:
        results = [f.get(name) for f in by_file]
        ref = first[name]
        identities = [r.backend_id if r else None for r in results]
        rows.append(
            BenchRow(
                name,
                ref.category,
                ref.unit,
                identities,
                _cells(results, lambda r: r.value),
                [r.environment.get("driver") if r else None for r in results],
                [r.environment.get("renderer") if r else None for r in results],
                [r.tool_version if r else None for r in results],
                [r.environment.get("device") if r else None for r in results],
            )
        )
        # disque : débits et IOPS de chaque test, sous l'indice (mêmes règles d'identité)
        if ref.category is Category.DISK:
            for key in ref.details:
                rows.append(
                    BenchRow(
                        name,
                        ref.category,
                        ref.detail_units.get(key, ""),
                        identities,
                        _cells(results, lambda r, key=key: r.details.get(key)),
                        detail=key,
                    )
                )
    return rows


def _cells(results: list[Result | None], value_of: Callable[[Result], float | None]) -> list[Cell]:
    """Valeur de chaque fichier et écart à la base, si l'identité du bench est la même."""
    base = results[0]
    base_value = value_of(base) if base is not None else None
    cells = []
    for i, r in enumerate(results):
        value = value_of(r) if r is not None else None
        if r is None or value is None:
            cells.append(Cell(None, issue=Incomparable.MISSING))
        elif i == 0:
            cells.append(Cell(value))
        elif base is None or base_value is None:
            cells.append(Cell(value, issue=Incomparable.MISSING))
        elif r.backend_id != base.backend_id:
            cells.append(Cell(value, issue=Incomparable.IDENTITY_DIFFERS))
        else:
            delta, better = _delta(value, base_value, r.higher_is_better)
            cells.append(Cell(value, delta, better))
    return cells


def _composition(score: CategoryScore | CombinedScore) -> list[BackendId]:
    return sorted(score.backends, key=lambda b: (b.name, b.version))


def _score_cells(
    exports: list[MachineExport], scores: list[CategoryScore | CombinedScore | None]
) -> list[Cell]:
    base_export, base = exports[0], scores[0]
    cells = []
    for i, (export, score) in enumerate(zip(exports, scores, strict=True)):
        if score is None:
            issue = Incomparable.NO_REFERENCE if export.reference is None else Incomparable.MISSING
            cells.append(Cell(None, issue=issue))
        elif score.points is None:
            cells.append(Cell(None, issue=Incomparable.NOT_SCORED, score_issue=score.issue))
        elif i == 0:
            cells.append(Cell(score.points))
        elif base is None or base.points is None:
            cells.append(Cell(score.points, issue=Incomparable.MISSING))
        elif (
            base_export.reference is None
            or export.reference is None
            or export.reference.digest != base_export.reference.digest
        ):
            cells.append(Cell(score.points, issue=Incomparable.REFERENCE_DIFFERS))
        elif _composition(score) != _composition(base):
            cells.append(Cell(score.points, issue=Incomparable.BACKENDS_DIFFER))
        elif (
            isinstance(score, CombinedScore)
            and isinstance(base, CombinedScore)
            and score.weights != base.weights
        ):
            cells.append(Cell(score.points, issue=Incomparable.WEIGHTS_DIFFER))
        else:
            delta, better = _delta(score.points, base.points, True)
            cells.append(Cell(score.points, delta, better))
    return cells


def _score_rows(exports: list[MachineExport]) -> list[ScoreRow]:
    rows = []
    for category in CATEGORY_ORDER:
        scores = [next((c for c in e.categories if c.category is category), None) for e in exports]
        if any(s is not None for s in scores):
            rows.append(ScoreRow(category, _score_cells(exports, scores)))
    combined = [e.combined for e in exports]
    if any(c is not None for c in combined):
        rows.append(ScoreRow(None, _score_cells(exports, combined)))
    return rows


def _driver_notices(row: BenchRow) -> list[Notice]:
    """Pilotes amont différents entre fichiers qui ont le même GPU.

    Entre GPU différents, un autre pilote est attendu : rien n'est signalé. Les valeurs de la
    notice gardent les chaînes brutes, None pour les fichiers hors du groupe.
    """
    groups: dict[str, list[int]] = {}
    for i, (gpu, driver) in enumerate(zip(row.gpus, row.drivers, strict=False)):
        if gpu_key(gpu) is not None and driver_key(driver) is not None:
            groups.setdefault(gpu_key(gpu) or "", []).append(i)
    notices = []
    for members in groups.values():
        if len({driver_key(row.drivers[i]) for i in members}) > 1:
            values = [row.drivers[i] if i in members else None for i in range(len(row.drivers))]
            notices.append(Notice(CompareWarning.DRIVER_DIFFERS, row.name, values))
    return notices


def _tool_notices(row: BenchRow) -> list[Notice]:
    """Versions différentes d'un outil hors identité (fio), même règle que le pilote : un
    avertissement entre fichiers mesurés sur le même modèle de disque, une information entre
    disques différents (ou inconnus). Valeurs : version par fichier, None hors du groupe."""
    if row.name not in TOOL_VERSION_NOT_IN_IDENTITY or row.detail is not None:
        return []
    measured = [i for i, v in enumerate(row.tool_versions) if v is not None]
    if len({row.tool_versions[i] for i in measured}) < 2:
        return []
    groups: dict[str, list[int]] = {}
    for i in measured:
        if (key := disk_key(row.devices[i] if i < len(row.devices) else None)) is not None:
            groups.setdefault(key, []).append(i)

    def values(members: list[int]) -> list[str | None]:
        return [v if i in members else None for i, v in enumerate(row.tool_versions)]

    flagged = [m for m in groups.values() if len({row.tool_versions[i] for i in m}) > 1]
    if flagged:
        return [Notice(CompareWarning.TOOL_VERSION_DIFFERS, row.name, values(m)) for m in flagged]
    return [Notice(CompareWarning.TOOL_VERSION_INFO, row.name, values(measured))]


def _warnings(exports: list[MachineExport], benches: list[BenchRow]) -> list[Notice]:
    warnings = [
        Notice(CompareWarning.BENCH_VERSION_DIFFERS, row.name)
        for row in benches
        if row.detail is None and len({i for i in row.identities if i is not None}) > 1
    ]
    for row in benches:
        warnings += _driver_notices(row) + _tool_notices(row)
    digests = {e.reference.digest for e in exports if e.reference is not None}
    if len(digests) > 1:
        warnings.append(Notice(CompareWarning.REFERENCE_DIFFERS, ""))
    warnings += [
        Notice(CompareWarning.FORCED_REFERENCE, e.machine)
        for e in exports
        if e.reference is not None and e.reference.forced
    ]
    return warnings


def compare(exports: list[MachineExport]) -> Comparison:
    if len(exports) < 2:
        raise ValueError("au moins deux exports sont nécessaires")
    benches = _bench_rows(exports)
    return Comparison(exports, _score_rows(exports), benches, _warnings(exports, benches))
