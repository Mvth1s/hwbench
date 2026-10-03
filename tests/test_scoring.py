import json
import math
import re
from datetime import UTC, datetime

import pytest
from conftest import make_result
from rich.console import Console

from hwbench import privacy
from hwbench.display.scores import render_scores
from hwbench.models import (
    BoardData,
    CpuData,
    DiskData,
    GpuData,
    MachineSnapshot,
    PowerData,
    RamData,
    SensorsData,
)
from hwbench.reference import build_reference
from hwbench.results import BackendId, Category, Result
from hwbench.scoring import (
    ReferenceError,
    ScoreIssue,
    load_reference,
    normalize,
    parse_weights,
    reference_from_dict,
    score_results,
)

GLMARK2 = dict(tool_version="2023.01", presentation="offscreen")
VKMARK = dict(tool_version="2025.01", presentation="headless")
SYSBENCH = dict(tool_version="1.0.20")


def reference_results() -> list[Result]:
    """Mesures de la « machine de référence » de ces tests."""
    return [
        make_result("native-cpu-single", 100.0),
        make_result("native-cpu-multi", 400.0),
        make_result("sysbench-cpu-single", 1000.0, **SYSBENCH),
        make_result("sysbench-cpu-multi", 8000.0, **SYSBENCH),
        make_result("glmark2", 2000.0, version="2", **GLMARK2),
        make_result("vkmark", 5000.0, version="2", **VKMARK),
    ]


def snapshot() -> MachineSnapshot:
    return MachineSnapshot(
        cpu=CpuData(model="11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz"),
        ram=RamData(),
        gpu=GpuData(opengl_renderer="Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)"),
        disks=DiskData(),
        board=BoardData(system_vendor="Dell Inc.", product_name="Latitude 5420"),
        sensors=SensorsData(),
        power=PowerData(on_ac=True),
    )


def payload(forced_reasons: list[str] | None = None) -> dict:
    return build_reference(
        reference_results(), snapshot(), forced_reasons or [], now=datetime(2026, 9, 29, tzinfo=UTC)
    )


REFERENCE = reference_from_dict(payload())


def machine(factor: float = 2.0, **only: bool) -> list[Result]:
    """Une machine « factor » fois plus rapide que la référence sur tout."""
    return [
        make_result(
            r.name,
            r.value * factor,
            version=r.version,
            tool_version=r.tool_version,
            presentation=r.presentation,
        )
        for r in reference_results()
        if only.get(r.name, True)
    ]


def test_reference_itself_scores_1000_everywhere() -> None:
    scores = score_results(reference_results(), REFERENCE)
    assert all(s.points == pytest.approx(1000) for s in scores.backends)
    assert [c.points for c in scores.categories] == [pytest.approx(1000)] * 3
    assert scores.combined is not None
    assert scores.combined.points == pytest.approx(1000)
    assert not scores.combined.gpu_missing


def test_twice_as_fast_is_2000() -> None:
    scores = score_results(machine(2.0), REFERENCE)
    assert scores.combined is not None and scores.combined.points == pytest.approx(2000)


def test_lower_is_better_is_inverted() -> None:
    ref = make_result("native-cpu-single", 10.0, higher_is_better=False)
    ours = make_result("native-cpu-single", 5.0, higher_is_better=False)
    reference = reference_from_dict(build_reference([ref], snapshot(), []))
    assert normalize(ours, reference).points == pytest.approx(2000)


def test_cpu_category_counts_native_only() -> None:
    results = machine(1.0)
    results = [
        make_result(r.name, r.value * 3, **SYSBENCH) if r.backend == "sysbench" else r
        for r in results
    ]
    scores = score_results(results, REFERENCE)
    single = next(c for c in scores.categories if c.category is Category.CPU_SINGLE)
    assert single.points == pytest.approx(1000)  # sysbench x3 n'y change rien
    assert [b.name for b in single.backends] == ["native-cpu-single"]
    sysbench = next(s for s in scores.backends if s.backend.name == "sysbench-cpu-single")
    assert (sysbench.official, sysbench.points) == (False, pytest.approx(3000))


def test_gpu_category_is_geometric_mean_of_its_backends() -> None:
    results = machine(1.0)
    results = [
        make_result("glmark2", 8000.0, version="2", **GLMARK2) if r.name == "glmark2" else r
        for r in results
    ]  # glmark2 x4, vkmark x1
    gpu = next(
        c for c in score_results(results, REFERENCE).categories if c.category is Category.GPU
    )
    assert gpu.points == pytest.approx(math.sqrt(4000 * 1000))
    assert [b.name for b in gpu.backends] == ["glmark2", "vkmark"]


def test_gpu_with_fewer_backends_than_reference_is_not_comparable() -> None:
    """Règle 2 : pas de moyenne silencieuse sur ce qui est installé."""
    scores = score_results(machine(2.0, vkmark=False), REFERENCE)
    gpu = next(c for c in scores.categories if c.category is Category.GPU)
    assert (gpu.points, gpu.issue) == (None, ScoreIssue.BACKENDS_DIFFER)
    assert [b.name for b in gpu.backends] == ["glmark2"]
    assert [b.name for b in gpu.reference_backends] == ["glmark2", "vkmark"]
    # glmark2 reste noté seul, pour information
    glmark2 = next(s for s in scores.backends if s.backend.name == "glmark2")
    assert glmark2.points == pytest.approx(2000)
    assert scores.combined is not None
    assert (scores.combined.points, scores.combined.issue) == (
        None,
        ScoreIssue.CATEGORY_NOT_COMPARABLE,
    )


def test_without_gpu_combined_is_cpu_only_and_flagged() -> None:
    results = machine(2.0, glmark2=False, vkmark=False)
    combined = score_results(results, REFERENCE).combined
    assert combined is not None
    assert combined.points == pytest.approx(2000)
    assert combined.gpu_missing
    assert set(combined.weights) == {Category.CPU_SINGLE, Category.CPU_MULTI}
    assert [b.name for b in combined.backends] == ["native-cpu-single", "native-cpu-multi"]


def test_combined_needs_both_cpu_categories() -> None:
    combined = score_results(machine(2.0, **{"native-cpu-multi": False}), REFERENCE).combined
    assert combined is not None
    assert (combined.points, combined.issue) == (None, ScoreIssue.CPU_NOT_MEASURED)


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        (dict(version="3"), ScoreIssue.VERSION_MISMATCH),
        (dict(tool_version="2021.02"), ScoreIssue.TOOL_VERSION_MISMATCH),
        (dict(presentation="immediate-requested"), ScoreIssue.PRESENTATION_MISMATCH),
    ],
)
def test_backend_identity_mismatch(changes: dict, issue: ScoreIssue) -> None:
    identity = dict(version="2", **GLMARK2) | changes
    ours = make_result("glmark2", 4000.0, **identity)
    score = normalize(ours, REFERENCE)
    assert (score.points, score.issue) == (None, issue)
    assert score.reference_backend == BackendId("glmark2", "2", "2023.01", "offscreen")
    # et la catégorie GPU devient non comparable, pas moyennée sur vkmark seul
    results = [r for r in machine(1.0) if r.name != "glmark2"] + [ours]
    gpu = next(
        c for c in score_results(results, REFERENCE).categories if c.category is Category.GPU
    )
    assert (gpu.points, gpu.issue) == (None, issue)


def test_backend_absent_from_reference() -> None:
    reference = reference_from_dict(build_reference(reference_results()[:2], snapshot(), []))
    score = normalize(make_result("vkmark", 1.0, version="2", **VKMARK), reference)
    assert (score.points, score.issue) == (None, ScoreIssue.NOT_IN_REFERENCE)


def test_weights() -> None:
    results = [
        make_result("native-cpu-single", 100.0),  # 1000 pts
        make_result("native-cpu-multi", 1600.0),  # 4000 pts
    ]
    combined = score_results(results, REFERENCE, parse_weights("cpu-single=1,cpu-multi=3")).combined
    assert combined is not None
    assert combined.points == pytest.approx(1000**0.25 * 4000**0.75)
    assert combined.weights == {Category.CPU_SINGLE: 0.25, Category.CPU_MULTI: 0.75}


@pytest.mark.parametrize("text", ["cpu-single=-1", "gpu", "ram=1", "cpu-single=0,cpu-multi=0"])
def test_invalid_weights(text: str) -> None:
    with pytest.raises(ValueError):
        parse_weights(text)


def test_reference_file_roundtrip(tmp_path) -> None:
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(payload(["power_unknown", "warmup_unstable:vkmark"])))
    reference = load_reference(path)
    assert reference is not None
    assert reference.machine == "Dell Inc. Latitude 5420"
    assert reference.forced and reference.forced_reasons == [
        "power_unknown",
        "warmup_unstable:vkmark",
    ]
    assert reference.find("vkmark").id == BackendId("vkmark", "2", "2025.01", "headless")
    assert reference.find("native-cpu-multi").backend == "native"


def test_reference_payload_content() -> None:
    data = payload()
    assert data["schema_version"] == 1 and data["forced"] is False
    assert data["created"] == "2026-09-29T00:00:00+00:00"
    entry = next(b for b in data["benchmarks"] if b["name"] == "glmark2")
    assert entry["presentation"] == "offscreen" and entry["tool_version"] == "2023.01"
    assert "burst" in entry and entry["warmup_stable"] is True


@pytest.mark.parametrize(
    "broken",
    [{"schema_version": 99}, {"schema_version": 1, "machine": "x"}],
)
def test_invalid_reference_is_rejected(broken: dict) -> None:
    with pytest.raises(ReferenceError):
        reference_from_dict(broken)


def test_reference_digest_identifies_content_not_formatting() -> None:
    data = payload()
    same = json.loads(json.dumps(data, indent=4))
    other = payload(["power_unknown"])
    assert reference_from_dict(data).digest == reference_from_dict(same).digest
    assert reference_from_dict(data).digest != reference_from_dict(other).digest
    digest = reference_from_dict(data).digest
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert privacy.scrub(digest) == digest
    info = reference_from_dict(data).info()
    assert (info.machine, info.digest) == ("Dell Inc. Latitude 5420", digest)


def _glmark2(value: float, driver: str | None) -> Result:
    env = {"driver": driver} if driver else {}
    return make_result("glmark2", value, version="2", environment=env, **GLMARK2)


@pytest.mark.parametrize(
    ("ours", "theirs", "differs"),
    [
        ("Mesa 26.2.4-arch1.1", "Mesa 26.2.3-arch1.1", True),
        ("Mesa 26.2.3-arch1.1", "Mesa 26.2.3-arch1.1", False),
        (None, "Mesa 26.2.3-arch1.1", False),  # pilote inconnu : rien à signaler
        ("Mesa 26.2.4-arch1.1", None, False),
    ],
)
def test_gpu_driver_is_information_not_identity(ours, theirs, differs) -> None:
    reference = reference_from_dict(build_reference([_glmark2(2000.0, theirs)], snapshot(), []))
    assert reference.find("glmark2").driver == theirs
    score = normalize(_glmark2(3000.0, ours), reference)
    # noté quel que soit le pilote : seul BackendId décide de la comparabilité
    assert (score.points, score.issue) == (pytest.approx(1500), None)
    assert (score.driver, score.reference_driver) == (ours, theirs)
    assert score.driver_differs is differs


def test_scores_panel_warns_about_another_driver() -> None:
    reference = reference_from_dict(
        build_reference([_glmark2(2000.0, "Mesa 26.2.3-arch1.1")], snapshot(), [])
    )
    scores = score_results([_glmark2(2000.0, "Mesa 26.2.4-arch1.1")], reference)
    console = Console(width=200, record=True)
    console.print(render_scores(scores))
    out = console.export_text()
    assert "1000 pts" in out
    assert "glmark2 : pilote Mesa 26.2.4-arch1.1 (référence : Mesa 26.2.3-arch1.1)" in out
    same = score_results([_glmark2(2000.0, "Mesa 26.2.3-arch1.1")], reference)
    console = Console(width=200, record=True)
    console.print(render_scores(same))
    assert "pilote" not in console.export_text()
