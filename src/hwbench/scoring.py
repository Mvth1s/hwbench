"""Normalisation par rapport à la machine de référence (1000 points) et score combiné.

Règles :
- un backend n'est noté que si la référence contient le même bench, à la même version, avec la
  même version d'outil et le même mode de présentation (BackendId) ;
- catégorie CPU (single, multi) : seul le natif compte ; les autres backends CPU sont notés à
  part, pour information ;
- catégorie GPU : moyenne géométrique de tous les backends GPU mesurés. La liste doit être
  exactement celle de la référence, sinon « non comparable » (jamais de moyenne silencieuse sur
  ce qui se trouve installé) ;
- mémoire : seul le natif compte (single et multi, moyenne géométrique), sysbench pour
  information ; disque : fio. Ces deux catégories sont notées si la référence contient leurs
  benchs, sinon elles restent en valeurs brutes ; elles ne comptent jamais dans le combiné ;
- un backend officiel de la référence qui manque (vkmark en échec, absent ou sans Vulkan
  fonctionnel) rend la catégorie « incomplète » (BACKENDS_INCOMPLETE), sans points ;
- combiné : moyenne géométrique pondérée des catégories CPU et GPU (COMBINED_CATEGORIES). Sans
  GPU mesuré, ou avec un GPU incomplet, il est calculé sans lui et le signale (gpu_missing :
  partiel, jamais classé) ; un GPU mesuré mais non comparable rend le combiné non comparable.
"""

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any

from hwbench.results import (
    COMBINED_CATEGORIES,
    TOOL_VERSION_NOT_IN_IDENTITY,
    BackendId,
    Category,
    Result,
    disk_key,
    driver_key,
    gpu_key,
    identity_tool_version,
)

REFERENCE_POINTS = 1000.0
REFERENCE_SCHEMA_VERSION = 1
OFFICIAL_CPU_BACKEND = "native"
DEFAULT_WEIGHTS: dict[Category, float] = {
    Category.CPU_SINGLE: 1.0,
    Category.CPU_MULTI: 1.0,
    Category.GPU: 1.0,
}


class ScoreIssue(StrEnum):
    NOT_IN_REFERENCE = "not_in_reference"
    VERSION_MISMATCH = "version_mismatch"
    TOOL_VERSION_MISMATCH = "tool_version_mismatch"
    PRESENTATION_MISMATCH = "presentation_mismatch"
    BACKENDS_DIFFER = "backends_differ"  # composition de la catégorie ≠ référence
    # une partie seulement des backends de la référence, tous comparables (vkmark en échec)
    BACKENDS_INCOMPLETE = "backends_incomplete"
    CATEGORY_NOT_COMPARABLE = "category_not_comparable"  # combiné : une catégorie ne l'est pas
    CPU_NOT_MEASURED = "cpu_not_measured"  # combiné : single ou multi manquant


class ReferenceError(ValueError):
    pass


@dataclass(frozen=True)
class ReferenceEntry:
    id: BackendId
    backend: str  # « native », « sysbench »…
    category: Category
    unit: str
    higher_is_better: bool
    value: float
    # pilote et GPU (renderer) de la référence : information, hors BackendId
    driver: str | None = None
    gpu: str | None = None
    # version de l'outil telle que relevée (dans id seulement si elle fait partie de l'identité)
    # et modèle du disque mesuré (fio)
    tool_version: str | None = None
    device: str | None = None


@dataclass(frozen=True)
class ReferenceInfo:
    """Ce qu'un export retient de la référence : de quoi savoir si deux scores ont la même base."""

    machine: str
    created: str
    forced: bool
    forced_reasons: list[str]
    digest: str  # empreinte du contenu : deux références différentes ne se comparent pas


@dataclass(frozen=True)
class Reference:
    machine: str
    created: str
    forced: bool
    forced_reasons: list[str]
    entries: list[ReferenceEntry]
    digest: str = ""

    def info(self) -> ReferenceInfo:
        return ReferenceInfo(
            self.machine, self.created, self.forced, list(self.forced_reasons), self.digest
        )

    def find(self, name: str) -> ReferenceEntry | None:
        return next((e for e in self.entries if e.id.name == name), None)


@dataclass(frozen=True)
class BackendScore:
    backend: BackendId
    category: Category
    official: bool  # compte dans le score de sa catégorie
    points: float | None
    issue: ScoreIssue | None = None
    reference_backend: BackendId | None = None  # ce que contient la référence, si différent
    # Pilote et GPU (renderer brut) mesurés / de la référence. Hors identité : un autre pilote
    # n'empêche pas de noter (sinon chaque mise à jour de Mesa imposerait de régénérer la
    # référence) ; il n'est signalé que sur le GPU de la référence.
    driver: str | None = None
    reference_driver: str | None = None
    gpu: str | None = None
    reference_gpu: str | None = None
    # Version brute de l'outil et modèle du disque, mesurés / de la référence. Hors identité
    # (TOOL_VERSION_NOT_IN_IDENTITY, fio) : même règle que le pilote, signalée sur le disque de
    # la référence. Dans l'identité : seule la version amont compte, un autre build est cité.
    tool_version: str | None = None
    reference_tool_version: str | None = None
    device: str | None = None
    reference_device: str | None = None

    @property
    def same_device(self) -> bool:
        ours, theirs = disk_key(self.device), disk_key(self.reference_device)
        return ours is not None and ours == theirs

    @property
    def tool_differs(self) -> bool:
        """Même disque que la référence, autre version d'un outil hors identité : à signaler."""
        return (
            self.backend.name in TOOL_VERSION_NOT_IN_IDENTITY
            and self.same_device
            and self.tool_version is not None
            and self.reference_tool_version is not None
            and self.tool_version != self.reference_tool_version
        )

    @property
    def tool_info(self) -> bool:
        """Autre disque (ou inconnu) : la version de l'outil est une information neutre."""
        return (
            self.backend.name in TOOL_VERSION_NOT_IN_IDENTITY
            and self.tool_version is not None
            and not self.same_device
        )

    @property
    def tool_build_differs(self) -> bool:
        """Noté, même version amont que la référence mais autre build (« 1.0.20-1472a05 » contre
        « 1.0.20 ») : information, sans ⚠."""
        return (
            self.backend.name not in TOOL_VERSION_NOT_IN_IDENTITY
            and self.points is not None
            and self.tool_version is not None
            and self.reference_tool_version is not None
            and self.tool_version != self.reference_tool_version
        )

    @property
    def same_gpu(self) -> bool:
        ours, theirs = gpu_key(self.gpu), gpu_key(self.reference_gpu)
        return ours is not None and ours == theirs

    @property
    def driver_differs(self) -> bool:
        """Même GPU que la référence, autre pilote amont : à signaler (⚠)."""
        ours, theirs = driver_key(self.driver), driver_key(self.reference_driver)
        return self.same_gpu and ours is not None and theirs is not None and ours != theirs

    @property
    def driver_info(self) -> bool:
        """Autre GPU (ou GPU inconnu) : le pilote est une information neutre, sans ⚠."""
        return self.driver is not None and not self.same_gpu


@dataclass(frozen=True)
class CategoryScore:
    category: Category
    points: float | None
    backends: list[BackendId]
    reference_backends: list[BackendId]
    issue: ScoreIssue | None = None

    @property
    def missing(self) -> list[str]:
        """Backends de la référence non mesurés, dans l'ordre de la référence."""
        measured = {b.name for b in self.backends}
        return [b.name for b in self.reference_backends if b.name not in measured]


@dataclass(frozen=True)
class CombinedScore:
    points: float | None
    weights: dict[Category, float]  # poids effectifs, normalisés sur les catégories utilisées
    backends: list[BackendId]
    gpu_missing: bool
    issue: ScoreIssue | None = None


@dataclass(frozen=True)
class Scores:
    reference: Reference
    backends: list[BackendScore] = field(default_factory=list)
    categories: list[CategoryScore] = field(default_factory=list)
    combined: CombinedScore | None = None


# --- Référence -------------------------------------------------------------------------


def reference_digest(payload: Mapping[str, Any]) -> str:
    """sha256 complet du JSON canonique ; la clé « digest » est autorisée par privacy.scrub."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def reference_from_dict(payload: Mapping[str, Any]) -> Reference:
    if payload.get("schema_version") != REFERENCE_SCHEMA_VERSION:
        raise ReferenceError(
            f"schéma de référence {payload.get('schema_version')!r} non pris en charge "
            f"(attendu : {REFERENCE_SCHEMA_VERSION})"
        )
    try:
        entries = [
            ReferenceEntry(
                id=BackendId(
                    b["name"],
                    b["version"],
                    identity_tool_version(b["name"], b.get("tool_version")),
                    b.get("presentation"),
                ),
                backend=b["backend"],
                category=Category(b["category"]),
                unit=b["unit"],
                higher_is_better=bool(b["higher_is_better"]),
                value=float(b["value"]),
                driver=(b.get("environment") or {}).get("driver"),
                gpu=(b.get("environment") or {}).get("renderer"),
                tool_version=b.get("tool_version"),
                device=(b.get("environment") or {}).get("device"),
            )
            for b in payload["benchmarks"]
        ]
        return Reference(
            machine=str(payload["machine"]),
            created=str(payload["created"]),
            forced=bool(payload.get("forced", False)),
            forced_reasons=[str(r) for r in payload.get("forced_reasons", [])],
            entries=entries,
            digest=reference_digest(payload),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceError(f"fichier de référence invalide : {exc}") from exc


def load_reference(path: Path | None = None) -> Reference | None:
    """Référence du paquet (hwbench/data/reference.json), ou None si elle n'existe pas encore."""
    if path is None:
        resource = resources.files("hwbench").joinpath("data/reference.json")
        if not resource.is_file():
            return None
        text = resource.read_text(encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    return reference_from_dict(json.loads(text))


# --- Normalisation ---------------------------------------------------------------------


def is_official(result_backend: str, category: Category) -> bool:
    """Compte dans le score de sa catégorie : tous les backends GPU et disque, le natif ailleurs."""
    if category in (Category.GPU, Category.DISK):
        return True
    return result_backend == OFFICIAL_CPU_BACKEND


def normalize(result: Result, reference: Reference) -> BackendScore:
    ours = result.backend_id
    official = is_official(result.backend, result.category)
    entry = reference.find(ours.name)
    if entry is None:
        return BackendScore(ours, result.category, official, None, ScoreIssue.NOT_IN_REFERENCE)
    drivers = {
        "driver": result.environment.get("driver"),
        "reference_driver": entry.driver,
        "gpu": result.environment.get("renderer"),
        "reference_gpu": entry.gpu,
        "tool_version": result.tool_version,
        "reference_tool_version": entry.tool_version,
    }
    if ours.name in TOOL_VERSION_NOT_IN_IDENTITY:
        drivers |= {
            "device": result.environment.get("device"),
            "reference_device": entry.device,
        }
    if entry.id.version != ours.version:
        issue = ScoreIssue.VERSION_MISMATCH
    elif entry.id.tool_version != ours.tool_version:
        issue = ScoreIssue.TOOL_VERSION_MISMATCH
    elif entry.id.presentation != ours.presentation:
        issue = ScoreIssue.PRESENTATION_MISMATCH
    else:
        ratio = (
            result.value / entry.value if result.higher_is_better else entry.value / result.value
        )
        return BackendScore(ours, result.category, official, REFERENCE_POINTS * ratio, **drivers)
    return BackendScore(ours, result.category, official, None, issue, entry.id, **drivers)


def _geometric_mean(values: Iterable[float], weights: Iterable[float] | None = None) -> float:
    values = list(values)
    weights = list(weights) if weights is not None else [1.0] * len(values)
    total = sum(weights)
    return math.exp(sum(w * math.log(v) for v, w in zip(values, weights, strict=True)) / total)


def _category_score(
    category: Category, scored: list[BackendScore], reference: Reference
) -> CategoryScore | None:
    official = [s for s in scored if s.category is category and s.official]
    if not official:
        return None
    ours = [s.backend for s in official]
    theirs = [
        e.id
        for e in reference.entries
        if e.category is category and is_official(e.backend, category)
    ]
    blocking = next((s.issue for s in official if s.issue is not None), None)
    if blocking is None and {b.name for b in ours} < {b.name for b in theirs}:
        blocking = ScoreIssue.BACKENDS_INCOMPLETE
    elif blocking is None and sorted(b.name for b in ours) != sorted(b.name for b in theirs):
        blocking = ScoreIssue.BACKENDS_DIFFER
    if blocking is not None:
        return CategoryScore(category, None, ours, theirs, blocking)
    points = _geometric_mean(s.points for s in official if s.points is not None)
    return CategoryScore(category, points, ours, theirs)


def combine(
    categories: list[CategoryScore], weights: Mapping[Category, float] = DEFAULT_WEIGHTS
) -> CombinedScore | None:
    # mémoire et disque : jamais dans le combiné ; GPU incomplet : traité comme non mesuré
    by_cat = {
        c.category: c
        for c in categories
        if c.category in COMBINED_CATEGORIES and c.issue is not ScoreIssue.BACKENDS_INCOMPLETE
    }
    if not by_cat:
        return None
    gpu_missing = Category.GPU not in by_cat
    used = [c for c in COMBINED_CATEGORIES if c in by_cat]
    used = [c for c in used if weights.get(c, 0) > 0]
    total = sum(weights[c] for c in used)
    effective = {c: weights[c] / total for c in used} if total else {}
    backends = [b for c in used for b in by_cat[c].backends]
    if Category.CPU_SINGLE not in by_cat or Category.CPU_MULTI not in by_cat:
        return CombinedScore(None, effective, backends, gpu_missing, ScoreIssue.CPU_NOT_MEASURED)
    if any(by_cat[c].points is None for c in used):
        return CombinedScore(
            None, effective, backends, gpu_missing, ScoreIssue.CATEGORY_NOT_COMPARABLE
        )
    points = _geometric_mean((by_cat[c].points or 0.0 for c in used), (effective[c] for c in used))
    return CombinedScore(points, effective, backends, gpu_missing)


def score_results(
    results: list[Result],
    reference: Reference,
    weights: Mapping[Category, float] = DEFAULT_WEIGHTS,
) -> Scores:
    scored = [normalize(r, reference) for r in results]
    categories = [
        c for cat in Category if (c := _category_score(cat, scored, reference)) is not None
    ]
    return Scores(reference, scored, categories, combine(categories, weights))


def parse_weights(text: str) -> dict[Category, float]:
    """« cpu-single=1,cpu-multi=2,gpu=0.5 » ; catégories absentes = poids par défaut."""
    weights = dict(DEFAULT_WEIGHTS)
    for part in filter(None, (p.strip() for p in text.split(","))):
        key, sep, value = part.partition("=")
        try:
            category = Category(key.strip().replace("-", "_"))
            weight = float(value)
        except ValueError as exc:
            raise ValueError(f"pondération invalide : « {part} »") from exc
        if category not in COMBINED_CATEGORIES:
            raise ValueError(f"« {key.strip()} » ne fait pas partie du score combiné")
        if not sep or weight < 0 or not math.isfinite(weight):
            raise ValueError(f"pondération invalide : « {part} »")
        weights[category] = weight
    if not any(weights[c] > 0 for c in (Category.CPU_SINGLE, Category.CPU_MULTI)):
        raise ValueError("au moins une catégorie CPU doit avoir un poids non nul")
    return weights
