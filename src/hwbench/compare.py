"""Comparaison de plusieurs exports ; le premier fichier sert de base.

Rien n'est comparé « à peu près » :
- un bench n'a d'écart que si son identité (BackendId : version du protocole, version de
  l'outil, mode de présentation) est la même dans les deux fichiers ;
- un score de catégorie ou le combiné n'a d'écart que si les deux fichiers ont été notés contre
  la même référence (même empreinte) avec exactement la même liste de backends (et, pour le
  combiné, les mêmes pondérations).
"""

from dataclasses import dataclass
from enum import StrEnum

from hwbench.export import MachineExport
from hwbench.results import BackendId, Category, Result
from hwbench.scoring import CategoryScore, CombinedScore, ScoreIssue

CATEGORY_ORDER = (Category.CPU_SINGLE, Category.CPU_MULTI, Category.GPU)


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


@dataclass(frozen=True)
class ScoreRow:
    category: Category | None  # None : score combiné
    cells: list[Cell]


@dataclass(frozen=True)
class Notice:
    code: CompareWarning
    subject: str  # nom du bench, ou fichier concerné


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
        base = results[0]
        cells = []
        for i, r in enumerate(results):
            if r is None:
                cells.append(Cell(None, issue=Incomparable.MISSING))
            elif i == 0:
                cells.append(Cell(r.value))
            elif base is None:
                cells.append(Cell(r.value, issue=Incomparable.MISSING))
            elif r.backend_id != base.backend_id:
                cells.append(Cell(r.value, issue=Incomparable.IDENTITY_DIFFERS))
            else:
                delta, better = _delta(r.value, base.value, r.higher_is_better)
                cells.append(Cell(r.value, delta, better))
        ref = first[name]
        rows.append(
            BenchRow(
                name,
                ref.category,
                ref.unit,
                [r.backend_id if r else None for r in results],
                cells,
            )
        )
    return rows


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


def _warnings(exports: list[MachineExport], benches: list[BenchRow]) -> list[Notice]:
    warnings = [
        Notice(CompareWarning.BENCH_VERSION_DIFFERS, row.name)
        for row in benches
        if len({i for i in row.identities if i is not None}) > 1
    ]
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
