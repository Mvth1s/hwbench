"""Les vrais fichiers de results/ (classement) passent la validation contre la référence du
paquet. Si une version de bench change, ce test échoue : re-exporter les exemples maintenus
dans le dépôt (ou les retirer).

Seule exception : un fichier noté contre une référence antérieure (régénérée depuis) émet un
StaleReferenceWarning au lieu d'échouer. Les ré-exports ne peuvent passer qu'après la release
qui amène la nouvelle référence sur main (results.yml valide avec la branche de base) ; entre
les deux, la CI de dev doit rester verte. Le marqueur filterwarnings l'autorise même si les
avertissements sont transformés en erreurs (-W error, filterwarnings = error) : un marqueur
prime sur la ligne de commande et sur la configuration. Tous les autres contrôles restent
stricts, et la validation des soumissions ne tolère jamais une référence périmée."""

import warnings
from pathlib import Path

import pytest

from hwbench.export import from_dict
from hwbench.leaderboard.site import load_entries
from hwbench.leaderboard.validate import (
    StaleReferenceWarning,
    read_bounded,
    stale_reference,
    strict_json,
    validate_file,
)
from hwbench.scoring import load_reference

RESULTS = Path(__file__).resolve().parent.parent / "results"
FILES = sorted(RESULTS.glob("*.json"))
ALLOW_STALE = pytest.mark.filterwarnings(
    "default::hwbench.leaderboard.validate.StaleReferenceWarning"
)


def test_there_is_at_least_one_example() -> None:
    assert FILES, "results/ doit contenir au moins un exemple"


@ALLOW_STALE
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_result_file_is_valid(path: Path) -> None:
    reference = load_reference()
    assert reference is not None
    if stale_reference(from_dict(strict_json(read_bounded(path))), reference):
        warnings.warn(
            f"results/{path.name} : noté contre une référence antérieure, à ré-exporter",
            StaleReferenceWarning,
            stacklevel=1,
        )
    assert validate_file(path, reference, tolerate_stale_reference=True) == []


def test_all_results_load_for_the_site() -> None:
    reference = load_reference()
    assert reference is not None
    entries, skipped = load_entries(RESULTS, reference)
    assert skipped == [] and len(entries) == len(FILES)


@ALLOW_STALE
def test_stale_warning_survives_warnings_as_errors() -> None:
    """Sous -W error ou filterwarnings = error, ce warn lèverait une exception sans le marqueur
    (pytest applique les marqueurs après les filtres de la ligne de commande et de la config).
    catch_warnings garde les filtres actifs et enregistre l'avertissement sans l'afficher."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.warn("à ré-exporter", StaleReferenceWarning, stacklevel=1)
    assert [w.category for w in caught] == [StaleReferenceWarning]
