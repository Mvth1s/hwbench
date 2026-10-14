"""Exports du dossier results/ lus pour le site et les notifications, points recalculés.

Les points sont toujours recalculés à partir des résultats bruts contre la référence du paquet,
jamais repris de l'export.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from hwbench.export import ExportError, MachineExport, from_dict
from hwbench.leaderboard.validate import (
    SubmissionError,
    read_bounded,
    resolves_to_itself,
    stale_reference,
    strict_json,
)
from hwbench.results import COMBINED_CATEGORIES, Category
from hwbench.scoring import Reference, Scores, score_results

# Mémoire et disque : colonnes d'information, jamais classées ni dans le combiné
INFO_CATEGORIES = tuple(c for c in Category if c not in COMBINED_CATEGORIES)


@dataclass(frozen=True)
class Entry:
    slug: str  # nom du fichier sans .json (validé : minuscules, chiffres, tirets)
    export: MachineExport
    scores: Scores
    stale: bool = False  # noté contre une référence antérieure : à ré-exporter


def load_entries(results_dir: Path, reference: Reference) -> tuple[list[Entry], list[str]]:
    """Exports lisibles du dossier, et la liste des fichiers ignorés (avec la raison)."""
    entries, skipped = [], []
    if not resolves_to_itself(results_dir):
        return [], [f"{results_dir} : lien symbolique refusé, aucun résultat lu"]
    for path in sorted(results_dir.glob("*.json")):
        try:
            export = from_dict(strict_json(read_bounded(path)))
        except (SubmissionError, ExportError, UnicodeDecodeError, ValueError) as exc:
            skipped.append(f"{path.name} : {exc}")
            continue
        scores = score_results(export.results, reference)
        entries.append(Entry(path.stem, export, scores, stale_reference(export, reference)))
    return entries, skipped


def category_points(entry: Entry, category: Category | None) -> float | None:
    """Points de la catégorie, ou du combiné (None) s'il porte sur toutes les catégories."""
    if category is None:
        combined = entry.scores.combined
        # un combiné sans GPU n'a pas la même composition que la référence : pas classé
        if combined is None or combined.gpu_missing:
            return None
        return combined.points
    score = next((c for c in entry.scores.categories if c.category is category), None)
    return score.points if score else None


def ranking(entries: Iterable[Entry], category: Category | None) -> list[tuple[Entry, float]]:
    ranked = [
        (entry, p) for entry in entries if (p := category_points(entry, category)) is not None
    ]
    return sorted(ranked, key=lambda item: (-item[1], item[0].slug))
