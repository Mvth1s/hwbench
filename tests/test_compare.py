from dataclasses import replace
from datetime import UTC, datetime

import pytest
from conftest import make_result
from test_scoring import REFERENCE, machine, payload, snapshot

from hwbench.compare import CompareWarning, Incomparable, compare
from hwbench.export import MachineExport, build_export
from hwbench.results import Category, Result
from hwbench.scoring import (
    DEFAULT_WEIGHTS,
    Reference,
    ScoreIssue,
    parse_weights,
    reference_from_dict,
    score_results,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def export(
    results: list[Result],
    name: str = "machine",
    reference: Reference | None = REFERENCE,
    weights=DEFAULT_WEIGHTS,
) -> MachineExport:
    scores = score_results(results, reference, weights) if reference else None
    return build_export(snapshot(), name, results, scores, now=NOW)


def row(comparison, name: str):
    return next(r for r in comparison.benches if r.name == name)


def score_row(comparison, category: Category | None):
    return next(r for r in comparison.scores if r.category is category)


def test_needs_two_exports() -> None:
    with pytest.raises(ValueError):
        compare([export(machine(1.0))])


def test_bench_deltas_against_the_first_file() -> None:
    c = compare([export(machine(1.0), "a"), export(machine(1.5), "b"), export(machine(0.5), "c")])
    single = row(c, "native-cpu-single")
    assert [cell.value for cell in single.cells] == [100.0, 150.0, 50.0]
    assert single.cells[0].delta_percent is None  # la base
    assert single.cells[1].delta_percent == pytest.approx(50.0) and single.cells[1].better
    assert single.cells[2].delta_percent == pytest.approx(-50.0)
    assert single.cells[2].better is False
    assert c.warnings == []


def test_lower_is_better_flips_the_verdict() -> None:
    a = [make_result("native-cpu-single", 10.0, higher_is_better=False)]
    b = [make_result("native-cpu-single", 8.0, higher_is_better=False)]
    cell = row(compare([export(a, reference=None), export(b, reference=None)]), "native-cpu-single")
    assert cell.cells[1].delta_percent == pytest.approx(-20.0)
    assert cell.cells[1].better is True


def test_bench_rows_follow_category_order_native_first() -> None:
    c = compare([export(machine(1.0)), export(machine(2.0))])
    assert [r.name for r in c.benches] == [
        "native-cpu-single",
        "sysbench-cpu-single",
        "native-cpu-multi",
        "sysbench-cpu-multi",
        "glmark2",
        "vkmark",
    ]


@pytest.mark.parametrize(
    "changes",
    [dict(version="3"), dict(tool_version="2021.02"), dict(presentation="immediate-requested")],
)
def test_bench_with_another_identity_is_not_compared(changes) -> None:
    other = [replace(r, **changes) if r.name == "glmark2" else r for r in machine(2.0)]
    c = compare([export(machine(1.0)), export(other)])
    cell = row(c, "glmark2").cells[1]
    assert (cell.value, cell.delta_percent, cell.issue) == (
        4000.0,
        None,
        Incomparable.IDENTITY_DIFFERS,
    )
    assert [(w.code, w.subject) for w in c.warnings] == [
        (CompareWarning.BENCH_VERSION_DIFFERS, "glmark2")
    ]


def test_missing_bench_on_either_side() -> None:
    without_vkmark = [r for r in machine(1.0) if r.name != "vkmark"]
    c = compare([export(without_vkmark), export(machine(1.0))])
    cells = row(c, "vkmark").cells
    assert cells[0].issue is Incomparable.MISSING
    assert (cells[1].value, cells[1].issue) == (5000.0, Incomparable.MISSING)


def test_scores_compared_when_same_reference_and_composition() -> None:
    c = compare([export(machine(1.0)), export(machine(2.0))])
    combined = score_row(c, None).cells
    assert [cell.value for cell in combined] == [pytest.approx(1000), pytest.approx(2000)]
    assert combined[1].delta_percent == pytest.approx(100.0)
    assert [r.category for r in c.scores] == [*Category, None]


def test_gpu_score_over_another_backend_list_is_not_comparable() -> None:
    """Règle 2 : GPU et combiné calculés sur des listes différentes -> non comparables."""
    # sans vkmark, le GPU est déjà non comparable à la référence dans son propre export
    c = compare([export(machine(1.0)), export([r for r in machine(1.0) if r.name != "vkmark"])])
    gpu = score_row(c, Category.GPU).cells[1]
    assert (gpu.issue, gpu.score_issue) == (Incomparable.NOT_SCORED, ScoreIssue.BACKENDS_DIFFER)
    assert score_row(c, None).cells[1].issue is Incomparable.NOT_SCORED


def test_cpu_only_combined_is_not_compared_with_a_full_one() -> None:
    cpu_only = [r for r in machine(2.0) if r.category is not Category.GPU]
    c = compare([export(machine(1.0)), export(cpu_only)])
    combined = score_row(c, None).cells[1]
    assert combined.value == pytest.approx(2000)  # valeur affichée…
    assert combined.issue is Incomparable.BACKENDS_DIFFER  # …mais pas d'écart calculé
    assert score_row(c, Category.GPU).cells[1].issue is Incomparable.MISSING


def test_scores_against_another_reference_are_not_compared() -> None:
    other_ref = reference_from_dict(payload(["power_unknown"]))
    c = compare([export(machine(1.0)), export(machine(1.0), reference=other_ref)])
    assert score_row(c, Category.CPU_SINGLE).cells[1].issue is Incomparable.REFERENCE_DIFFERS
    codes = [w.code for w in c.warnings]
    assert CompareWarning.REFERENCE_DIFFERS in codes
    assert CompareWarning.FORCED_REFERENCE in codes  # la seconde référence est forcée


def test_combined_with_other_weights_is_not_compared() -> None:
    heavy_cpu = parse_weights("cpu-single=2,cpu-multi=2,gpu=1")
    c = compare([export(machine(1.0)), export(machine(1.0), weights=heavy_cpu)])
    assert score_row(c, None).cells[1].issue is Incomparable.WEIGHTS_DIFFER
    assert score_row(c, Category.GPU).cells[1].delta_percent == pytest.approx(0.0)


def test_export_without_reference_has_no_points() -> None:
    c = compare([export(machine(1.0)), export(machine(2.0), reference=None)])
    assert score_row(c, Category.CPU_SINGLE).cells[1].issue is Incomparable.NO_REFERENCE
    # les benchs bruts restent comparables, eux
    assert row(c, "native-cpu-single").cells[1].delta_percent == pytest.approx(100.0)


RX9070 = "AMD Radeon RX 9070 XT (radeonsi, gfx1201, ACO, DRM 3.64, 7.2.7-arch1-1)"
RX9070_NEW_KERNEL = RX9070.replace("7.2.7-arch1-1", "7.2.8-arch1-2")
IRIS = "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)"


def with_driver(results: list[Result], driver: str | None, renderer: str | None = RX9070):
    env = {k: v for k, v in (("driver", driver), ("renderer", renderer)) if v}
    return [replace(r, environment=env) if r.name == "glmark2" else r for r in results]


def driver_notices(c):
    return [(w.subject, w.values) for w in c.warnings if w.code is CompareWarning.DRIVER_DIFFERS]


def test_same_gpu_other_driver_is_flagged_but_still_compared() -> None:
    a = with_driver(machine(1.0), "Mesa 26.2.3-arch1.1")
    b = with_driver(machine(1.1), "Mesa 26.2.4-arch1.1", RX9070_NEW_KERNEL)  # noyau mis à jour
    c = compare([export(a), export(b)])
    assert row(c, "glmark2").cells[1].delta_percent == pytest.approx(10.0)
    assert driver_notices(c) == [("glmark2", ["Mesa 26.2.3-arch1.1", "Mesa 26.2.4-arch1.1"])]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Mesa 26.2.3-arch1.1", "Mesa 26.2.3-arch1.1"),
        ("Mesa 26.2.3-arch1.1", "Mesa 26.2.3-arch1.2"),  # reconstruction du paquet Arch
        ("Mesa 26.2.3-arch1.1", "Mesa 26.2.3"),  # même pilote empaqueté par Fedora
        ("Mesa 26.2.3-arch1.1", None),
    ],
)
def test_same_upstream_or_unknown_driver_is_not_flagged(first, second) -> None:
    c = compare(
        [export(with_driver(machine(1.0), first)), export(with_driver(machine(1.0), second))]
    )
    assert c.warnings == []


def test_other_gpu_other_driver_is_expected_not_flagged() -> None:
    desktop = with_driver(machine(1.0), "Mesa 26.2.4-arch1.1")
    laptop = with_driver(machine(0.3), "Mesa 25.0.7-1", IRIS)
    nvidia = with_driver(machine(1.2), "NVIDIA 550.54.14", "NVIDIA GeForce RTX 3060/PCIe/SSE2")
    assert compare([export(desktop), export(laptop), export(nvidia)]).warnings == []


def test_only_files_sharing_the_gpu_are_listed() -> None:
    c = compare(
        [
            export(with_driver(machine(1.0), "Mesa 26.2.3-arch1.1")),
            export(with_driver(machine(0.3), "Mesa 25.0.7-1", IRIS)),
            export(with_driver(machine(1.0), "Mesa 26.2.4-arch1.1")),
        ]
    )
    assert driver_notices(c) == [("glmark2", ["Mesa 26.2.3-arch1.1", None, "Mesa 26.2.4-arch1.1"])]
