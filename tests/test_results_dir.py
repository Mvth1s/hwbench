"""Les vrais fichiers de results/ (classement) passent la validation contre la référence du
paquet. Si une version de bench ou la référence change, ce test échoue : re-exporter les
exemples maintenus dans le dépôt (ou les retirer)."""

from pathlib import Path

import pytest

from hwbench.leaderboard.site import load_entries
from hwbench.leaderboard.validate import validate_file
from hwbench.scoring import load_reference

RESULTS = Path(__file__).resolve().parent.parent / "results"
FILES = sorted(RESULTS.glob("*.json"))


def test_there_is_at_least_one_example() -> None:
    assert FILES, "results/ doit contenir au moins un exemple"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_result_file_is_valid(path: Path) -> None:
    reference = load_reference()
    assert reference is not None
    assert validate_file(path, reference) == []


def test_all_results_load_for_the_site() -> None:
    reference = load_reference()
    assert reference is not None
    entries, skipped = load_entries(RESULTS, reference)
    assert skipped == [] and len(entries) == len(FILES)
