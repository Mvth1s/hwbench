import json
import math
import re
from dataclasses import replace
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
from hwbench.results import (
    BackendId,
    Category,
    Result,
    driver_key,
    gpu_key,
    gpu_name,
    upstream_version,
)
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


@pytest.mark.parametrize(
    "text",
    ["cpu-single=-1", "gpu", "ram=1", "cpu-single=0,cpu-multi=0", "memory=1", "disk=2"],
)
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


RX9070_GL = "AMD Radeon RX 9070 XT (radeonsi, gfx1201, ACO, DRM 3.64, 7.2.7-arch1-1)"
IRIS_GL = "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)"


def _glmark2(value: float, driver: str | None, renderer: str | None = RX9070_GL) -> Result:
    env = {k: v for k, v in (("driver", driver), ("renderer", renderer)) if v}
    return make_result("glmark2", value, version="2", environment=env, **GLMARK2)


def _reference(driver: str | None, renderer: str | None = RX9070_GL):
    return reference_from_dict(
        build_reference([_glmark2(2000.0, driver, renderer)], snapshot(), [])
    )


@pytest.mark.parametrize(
    ("ours", "theirs", "expected"),
    [
        # même version amont, autre révision de paquet : même pilote
        ("Mesa 26.2.4-arch1.2", "Mesa 26.2.4-arch1.1", ("mesa", "26.2.4")),
        ("Mesa 26.2.4", "Mesa 26.2.4-arch1.1", ("mesa", "26.2.4")),  # Fedora
        ("Mesa 26.2.4-1", "Mesa 26.2.4", ("mesa", "26.2.4")),  # Debian
        ("Mesa 25.0.7-0ubuntu0.24.04.1", "Mesa 25.0.7", ("mesa", "25.0.7")),  # Ubuntu
        ("RADV 26.2.4", "RADV 26.2.4", ("radv", "26.2.4")),
        ("NVIDIA 550.54.14", "NVIDIA 550.54.14", ("nvidia", "550.54.14")),
    ],
)
def test_driver_key_ignores_distribution_packaging(ours, theirs, expected) -> None:
    assert driver_key(ours) == driver_key(theirs) == expected


def test_driver_key_keeps_upstream_differences() -> None:
    assert driver_key("Mesa 26.2.4-arch1.1") != driver_key("Mesa 26.2.3-arch1.1")
    assert driver_key("NVIDIA 550.54.14") != driver_key("NVIDIA 560.35.03")
    assert driver_key("Mesa 26.2.4") != driver_key("NVIDIA 26.2.4")
    assert driver_key(None) is None and driver_key("  ") is None


@pytest.mark.parametrize(
    ("renderer", "expected"),
    [
        (RX9070_GL, "amd radeon rx 9070 xt"),
        # le noyau change le renderer OpenGL, pas le GPU
        (RX9070_GL.replace("7.2.7-arch1-1", "7.2.8-arch1-2"), "amd radeon rx 9070 xt"),
        ("AMD Radeon RX 9070 XT (RADV GFX1201)", "amd radeon rx 9070 xt"),
        ("NVIDIA GeForce RTX 3060/PCIe/SSE2", "nvidia geforce rtx 3060"),
        (IRIS_GL, "mesa intel(r) iris(r) xe graphics"),
        (None, None),
    ],
)
def test_gpu_key(renderer, expected) -> None:
    assert gpu_key(renderer) == expected


@pytest.mark.parametrize(
    ("ours", "theirs", "differs"),
    [
        ("Mesa 26.2.4-arch1.1", "Mesa 26.2.3-arch1.1", True),
        ("Mesa 26.2.3-arch1.2", "Mesa 26.2.3-arch1.1", False),  # simple reconstruction du paquet
        ("Mesa 26.2.3", "Mesa 26.2.3-arch1.1", False),  # même pilote, empaqueté par Fedora
        (None, "Mesa 26.2.3-arch1.1", False),
        ("Mesa 26.2.4-arch1.1", None, False),
    ],
)
def test_gpu_driver_on_the_reference_gpu(ours, theirs, differs) -> None:
    newer_kernel = RX9070_GL.replace("7.2.7-arch1-1", "7.2.8-arch1-2")
    score = normalize(_glmark2(3000.0, ours, newer_kernel), _reference(theirs))
    # noté quel que soit le pilote : seul BackendId décide de la comparabilité
    assert (score.points, score.issue) == (pytest.approx(1500), None)
    assert score.same_gpu
    assert score.driver_differs is differs
    assert score.driver_info is False


def test_other_gpu_driver_is_neutral_information() -> None:
    score = normalize(_glmark2(1000.0, "Mesa 25.0.7-1", IRIS_GL), _reference("Mesa 26.2.3-arch1.1"))
    assert score.points == pytest.approx(500)
    assert not score.same_gpu and not score.driver_differs
    assert score.driver_info


def _panel(scores) -> str:
    console = Console(width=200, record=True)
    console.print(render_scores(scores))
    return console.export_text()


def test_scores_panel_warns_only_on_the_reference_gpu() -> None:
    reference = _reference("Mesa 26.2.3-arch1.1")
    out = _panel(score_results([_glmark2(2000.0, "Mesa 26.2.4-arch1.1")], reference))
    assert "1000 pts" in out
    assert (
        "⚠ glmark2 : pilote Mesa 26.2.4-arch1.1 (référence : Mesa 26.2.3-arch1.1, même GPU)" in out
    )
    # reconstruction du paquet seulement : rien
    out = _panel(score_results([_glmark2(2000.0, "Mesa 26.2.3-arch1.2")], reference))
    assert "pilote" not in out


def test_scores_panel_other_gpu_shows_driver_without_warning() -> None:
    reference = _reference("Mesa 26.2.3-arch1.1")
    out = _panel(score_results([_glmark2(800.0, "Mesa 25.0.7-1", IRIS_GL)], reference))
    assert "glmark2 : pilote Mesa 25.0.7-1 (référence : Mesa 26.2.3-arch1.1, autre GPU)" in out
    assert "⚠ glmark2" not in out


@pytest.mark.parametrize(
    ("renderer", "expected"),
    [
        (RX9070_GL, "AMD Radeon RX 9070 XT"),
        ("NVIDIA GeForce RTX 3060/PCIe/SSE2", "NVIDIA GeForce RTX 3060"),
        (IRIS_GL, "Mesa Intel(R) Iris(R) Xe Graphics"),
        (None, None),
    ],
)
def test_gpu_name_keeps_original_case(renderer, expected) -> None:
    assert gpu_name(renderer) == expected
    assert gpu_key(renderer) == (expected.lower() if expected else None)


# --- Mémoire et disque : catégories d'information, hors score combiné ----------------------

FIO = dict(tool_version="3.38", presentation="1GiB")


def info_results(factor: float = 1.0) -> list[Result]:
    return [
        make_result("native-memory-single", 10_000.0 * factor),
        make_result("native-memory-multi", 40_000.0 * factor),
        make_result("sysbench-memory-single", 12_000.0 * factor, **SYSBENCH),
        make_result("fio-disk", 5_000.0 * factor, **FIO),
    ]


def test_memory_and_disk_stay_raw_without_reference_entries() -> None:
    scores = score_results(machine(2.0) + info_results(), REFERENCE)
    by_cat = {c.category: c for c in scores.categories}
    assert by_cat[Category.MEMORY].points is None
    assert by_cat[Category.MEMORY].issue is ScoreIssue.NOT_IN_REFERENCE
    assert by_cat[Category.DISK].issue is ScoreIssue.NOT_IN_REFERENCE
    # le combiné ne bouge pas
    assert scores.combined is not None and scores.combined.points == pytest.approx(2000)
    assert set(scores.combined.weights) == {Category.CPU_SINGLE, Category.CPU_MULTI, Category.GPU}


def test_memory_and_disk_scored_when_in_reference_but_never_combined() -> None:
    reference = reference_from_dict(
        build_reference(reference_results() + info_results(), snapshot(), [])
    )
    results = machine(2.0) + [
        make_result("native-memory-single", 20_000.0),  # 2000 pts
        make_result("native-memory-multi", 320_000.0),  # 8000 pts
        make_result("sysbench-memory-single", 1.0, **SYSBENCH),  # information
        make_result("fio-disk", 500.0, **FIO),  # 100 pts
    ]
    scores = score_results(results, reference)
    by_cat = {c.category: c for c in scores.categories}
    assert by_cat[Category.MEMORY].points == pytest.approx(4000)  # √(2000 × 8000)
    assert by_cat[Category.DISK].points == pytest.approx(100)
    sysbench_memory = next(b for b in scores.backends if b.backend.name == "sysbench-memory-single")
    assert not sysbench_memory.official
    assert scores.combined is not None and scores.combined.points == pytest.approx(2000)


def test_disk_size_is_part_of_the_identity() -> None:
    reference = reference_from_dict(build_reference(info_results(), snapshot(), []))
    other_size = make_result("fio-disk", 5_000.0, tool_version="3.38", presentation="4GiB")
    score = normalize(other_size, reference)
    assert (score.points, score.issue) == (None, ScoreIssue.PRESENTATION_MISMATCH)


def test_memory_only_has_no_combined_score() -> None:
    scores = score_results(info_results(), REFERENCE)
    assert scores.combined is None


def _panel_text(scores) -> str:
    console = Console(width=200, record=True)
    console.print(render_scores(scores))
    return console.export_text()


def test_scores_panel_info_categories() -> None:
    raw = _panel_text(score_results(machine(2.0) + info_results(), REFERENCE))
    assert "Mémoire" in raw and "valeurs brutes (pas encore dans la référence)" in raw
    reference = reference_from_dict(
        build_reference(reference_results() + info_results(), snapshot(), [])
    )
    scored = _panel_text(score_results(machine(2.0) + info_results(2.0), reference))
    assert re.search(r"Disque +2000 pts  \(information, hors score combiné\)", scored)
    assert re.search(r"Mémoire +2000 pts  \(information, hors score combiné\)", scored)


# --- fio : version de l'outil hors identité, même règle que le pilote GPU ----------------

EVO = "Samsung SSD 990 EVO Plus 1TB"
SN850 = "WD_BLACK SN850X 2000GB"


def _fio(value: float, tool: str | None, device: str | None = EVO) -> Result:
    env = {"filesystem": "btrfs", **({"device": device} if device else {})}
    return make_result("fio-disk", value, tool_version=tool, presentation="1GiB", environment=env)


def _fio_reference(tool: str = "3.42", device: str | None = EVO):
    return reference_from_dict(build_reference([_fio(2000.0, tool, device)], snapshot(), []))


def test_fio_tool_version_is_recorded_but_not_part_of_the_identity() -> None:
    reference = _fio_reference()
    entry = reference.find("fio-disk")
    assert entry.id == BackendId("fio-disk", "1", None, "1GiB")
    assert (entry.tool_version, entry.device) == ("3.42", EVO)
    result = _fio(1000.0, "3.40")
    assert result.tool_version == "3.40" and result.backend_id.tool_version is None


def test_sysbench_memory_tool_version_stays_in_the_identity() -> None:
    ref_result = make_result("sysbench-memory-single", 9000.0, tool_version="1.0.20")
    reference = reference_from_dict(build_reference([ref_result], snapshot(), []))
    assert reference.find("sysbench-memory-single").id.tool_version == "1.0.20"
    score = normalize(replace(ref_result, tool_version="1.1.0"), reference)
    assert (score.points, score.issue) == (None, ScoreIssue.TOOL_VERSION_MISMATCH)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.0.20", "1.0.20"),
        ("1.0.20-1472a05", "1.0.20"),  # build git (Arch)
        ("1.0.20+ds-8", "1.0.20"),  # Debian
        ("2025.01", "2025.01"),
        (" 3.42 ", "3.42"),
        ("git-1472a05", "git-1472a05"),  # pas de version numérotée : chaîne brute
        (None, None),
    ],
)
def test_upstream_version(raw, expected) -> None:
    assert upstream_version(raw) == expected


@pytest.mark.parametrize("raw", ["1.0.20-1472a05", "1.0.20+ds-8"])
def test_build_suffix_keeps_sysbench_comparable(raw) -> None:
    reference = reference_from_dict(
        build_reference(
            [make_result("sysbench-cpu-single", 9000.0, tool_version="1.0.20")], snapshot(), []
        )
    )
    result = make_result("sysbench-cpu-single", 4500.0, tool_version=raw)
    assert result.tool_version == raw  # chaîne brute conservée
    assert result.backend_id == BackendId("sysbench-cpu-single", "1", "1.0.20", None)
    score = normalize(result, reference)
    assert (score.points, score.issue) == (pytest.approx(500), None)
    assert score.tool_build_differs and not score.tool_differs and not score.tool_info
    out = _panel(score_results([result], reference))
    assert f"sysbench-cpu-single : outil {raw} (référence : 1.0.20, même version amont)" in out
    assert "⚠ sysbench" not in out


def test_same_build_says_nothing() -> None:
    result = make_result("sysbench-cpu-single", 9000.0, tool_version="1.0.20")
    reference = reference_from_dict(build_reference([result], snapshot(), []))
    assert not normalize(result, reference).tool_build_differs
    assert "même version amont" not in _panel(score_results([result], reference))


def test_other_upstream_version_stays_not_comparable() -> None:
    reference = reference_from_dict(
        build_reference(
            [make_result("sysbench-cpu-single", 9000.0, tool_version="1.0.20")], snapshot(), []
        )
    )
    score = normalize(
        make_result("sysbench-cpu-single", 9000.0, tool_version="1.0.21-abc"), reference
    )
    assert (score.points, score.issue) == (None, ScoreIssue.TOOL_VERSION_MISMATCH)


def test_same_disk_other_fio_version_is_scored_and_flagged() -> None:
    score = normalize(_fio(3000.0, "3.40"), _fio_reference())
    assert (score.points, score.issue) == (pytest.approx(1500), None)
    assert score.same_device and score.tool_differs and not score.tool_info
    out = _panel(score_results([_fio(3000.0, "3.40")], _fio_reference()))
    assert "⚠ fio-disk : outil 3.40 (référence : 3.42, même disque)" in out


@pytest.mark.parametrize("device", [f"  {EVO.lower()} ", EVO])
def test_same_disk_same_fio_version_says_nothing(device) -> None:
    score = normalize(_fio(2000.0, "3.42", device), _fio_reference())
    assert score.same_device and not score.tool_differs and not score.tool_info
    assert "outil" not in _panel(score_results([_fio(2000.0, "3.42", device)], _fio_reference()))


@pytest.mark.parametrize("device", [SN850, None])
def test_other_disk_shows_fio_version_as_information(device) -> None:
    score = normalize(_fio(1000.0, "3.40", device), _fio_reference())
    assert score.points == pytest.approx(500)
    assert not score.same_device and not score.tool_differs and score.tool_info
    out = _panel(score_results([_fio(1000.0, "3.40", device)], _fio_reference()))
    assert "fio-disk : outil 3.40 (référence : 3.42, autre disque)" in out
    assert "⚠ fio-disk" not in out


def test_tool_rule_does_not_apply_to_gpu_backends() -> None:
    score = normalize(_glmark2(2000.0, "Mesa 26.2.3"), _reference("Mesa 26.2.3"))
    assert not score.tool_differs and not score.tool_info
    # version brute relevée (même build que la référence), aucun disque
    assert score.tool_version == "2023.01" and score.device is None
    assert not score.tool_build_differs
