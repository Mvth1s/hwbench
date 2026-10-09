import json
import re
from datetime import UTC, datetime

import pytest
from conftest import make_result
from test_scoring import REFERENCE, machine

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
    assert data["schema_version"] == EXPORT_SCHEMA_VERSION == 2
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
