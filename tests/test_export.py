import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import make_result
from test_scoring import REFERENCE, machine, snapshot

from hwbench import privacy
from hwbench.collect import collect_snapshot
from hwbench.export import (
    EXPORT_SCHEMA_VERSION,
    ExportError,
    build_export,
    from_dict,
    load_export,
    to_dict,
    write_export,
)
from hwbench.results import COMBINED_CATEGORIES, BenchWarning
from hwbench.runner import RunSettings
from hwbench.scoring import score_results

NOW = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)


@pytest.fixture
def laptop_export(laptop):
    laptop(root=True)
    snapshot, _ = collect_snapshot(os_name="Linux")
    results = machine(1.5)
    results[0] = make_result(
        "native-cpu-single",
        150.0,
        warnings=[BenchWarning.HOT_START],
        details={"sha256": 1624.2},
        detail_units={"sha256": "MiB/s"},
    )
    scores = score_results(results, REFERENCE)
    return build_export(snapshot, "Dell Inc. Latitude 5420", results, scores, now=NOW)


def test_roundtrip_through_a_file(laptop_export, tmp_path) -> None:
    path = tmp_path / "latitude.json"
    write_export(laptop_export, path)
    loaded = load_export(path)
    assert loaded == laptop_export  # dataclasses reconstruites, enums et clés compris
    assert loaded.combined is not None
    assert loaded.combined.weights == {c: pytest.approx(1 / 3) for c in COMBINED_CATEGORIES}
    assert loaded.results[0].warnings == [BenchWarning.HOT_START]


def test_schema_header(laptop_export) -> None:
    data = to_dict(laptop_export)
    assert data["schema_version"] == EXPORT_SCHEMA_VERSION == 3
    assert data["created"] == "2026-09-30T08:00:00+00:00"
    assert data["reference"]["digest"] == REFERENCE.digest
    assert data["categories"][0]["category"] == "cpu_single"  # enums en chaînes
    assert set(data["combined"]["weights"]) == {"cpu_single", "cpu_multi", "gpu"}
    json.dumps(data)  # sérialisable tel quel


def test_export_contains_no_identifier(laptop_export) -> None:
    data = to_dict(laptop_export)
    assert privacy.scrub(data) == data
    text = json.dumps(data)
    for fake in ("FAKE", "fake-host", "00000000-0000-0000-0000-000000000000"):
        assert fake not in text


def test_export_without_reference(laptop_export) -> None:
    bare = build_export(laptop_export.snapshot, "x", laptop_export.results, None, now=NOW)
    loaded = from_dict(json.loads(json.dumps(to_dict(bare))))
    assert loaded.reference is None and loaded.categories == [] and loaded.combined is None


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(schema_version=1), "schéma d'export 1 non pris en charge"),
        (lambda d: d.pop("results"), "export.results : champ manquant"),
        (
            lambda d: d["results"][0].update(value="vite"),
            "export.results[0].value : nombre attendu",
        ),
        (lambda d: d["results"][0].update(category="npu"), "valeur inconnue 'npu'"),
    ],
)
def test_invalid_exports_are_rejected(laptop_export, mutate, message) -> None:
    data = json.loads(json.dumps(to_dict(laptop_export)))
    mutate(data)
    with pytest.raises(ExportError, match=re.escape(message)):
        from_dict(data)


def test_load_errors_name_the_file(tmp_path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{nope")
    with pytest.raises(ExportError, match="broken.json : JSON invalide"):
        load_export(broken)
    with pytest.raises(ExportError, match="absent.json"):
        load_export(tmp_path / "absent.json")


# --- schéma 3 : réglages des mesures ; schéma 2 toujours relu -------------------------------

RESULTS = Path(__file__).parents[1] / "results"


def test_settings_roundtrip(tmp_path) -> None:
    settings = RunSettings(runs=5, hot_start_c=65.0, reliable_cv_percent=0.5)
    ex = build_export(snapshot(), "m", machine(1.0), None, settings=settings)
    path = tmp_path / "m.json"
    write_export(ex, path)
    assert json.loads(path.read_text())["settings"]["hot_start_c"] == 65.0
    assert load_export(path).settings == settings


def test_schema_2_files_are_still_read_without_settings() -> None:
    for path in RESULTS.glob("*.json"):
        assert json.loads(path.read_text())["schema_version"] == 2
        ex = load_export(path)
        assert ex.settings is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": 4}, "schéma d'export 4 non pris en charge (attendu : 2, 3)"),
        ({"schema_version": True}, "non pris en charge"),
        ({"settings": {"runs": 1}}, "au moins 3 runs"),
        ({"schema_version": 2, "settings": {}}, "inattendu dans un schéma 2"),
    ],
)
def test_invalid_schema_or_settings(change: dict, message: str) -> None:
    data = to_dict(build_export(snapshot(), "m", machine(1.0), None, settings=RunSettings()))
    with pytest.raises(ExportError, match=re.escape(message)):
        from_dict(data | change)
