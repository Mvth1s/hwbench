"""Moteur de règles : une session construite à la main par règle, et aucun faux positif."""

from dataclasses import replace
from pathlib import Path

import pytest
from conftest import COOL_AC_STATE, make_result
from test_scoring import REFERENCE, machine, snapshot

from hwbench.analysis import STATUS_ORDER, FindingCode, Status, analyze
from hwbench.export import MachineExport, build_export, load_export
from hwbench.models import SensorsData, TemperatureReading, Unavailable
from hwbench.results import BenchWarning, MachineState, Result
from hwbench.runner import RunSettings
from hwbench.scoring import score_results

RESULTS = Path(__file__).parents[1] / "results"
BATTERY = MachineState(["powersave"], on_ac=False, cpu_temp_c=45.0, has_battery=True)
BALANCED = MachineState(
    ["powersave"],
    on_ac=True,
    cpu_temp_c=45.0,
    platform_profile="balanced",
    platform_profile_choices=["low-power", "balanced", "performance"],
    energy_performance_preference="balance_performance",
)


def session(results: list[Result], reference=REFERENCE, **snapshot_changes) -> MachineExport:
    scores = score_results(results, reference) if reference else None
    return build_export(replace(snapshot(), **snapshot_changes), "machine", results, scores)


def codes(findings) -> list[FindingCode]:
    return [f.code for f in findings]


def find(findings, code: FindingCode):
    (found,) = [f for f in findings if f.code is code]
    return found


def clean() -> list[Result]:
    """Session irréprochable : secteur, performance, au frais, CV nul."""
    return machine(1.0)


def test_clean_session_has_no_problem() -> None:
    findings = analyze(session(clean()))
    assert not [f for f in findings if f.status in (Status.FIX, Status.CHECK)]
    assert find(findings, FindingCode.REPRODUCIBLE).params["count"] == 6


def test_findings_are_sorted_by_status() -> None:
    results = [
        make_result(
            "native-cpu-single", 100.0, state_before=BATTERY, warnings=[BenchWarning.ON_BATTERY]
        ),
        make_result("native-cpu-multi", 400.0, warnings=[BenchWarning.HIGH_VARIANCE], stdev=40.0),
    ]
    statuses = [f.status for f in analyze(session(results))]
    assert statuses == sorted(statuses, key=STATUS_ORDER.index)
    assert statuses[0] is Status.FIX


# --- conditions ----------------------------------------------------------------------------


def test_on_battery() -> None:
    results = [
        make_result(
            "native-cpu-single", 100.0, state_before=BATTERY, warnings=[BenchWarning.ON_BATTERY]
        )
    ]
    f = find(analyze(session(results)), FindingCode.ON_BATTERY)
    assert f.status is Status.FIX and f.items == [
        {"bench": "native-cpu-single", "category": "cpu_single"}
    ]


def test_power_profile_cites_epp_and_profile() -> None:
    results = [
        make_result(
            "native-cpu-single", 100.0, state_before=BALANCED, warnings=[BenchWarning.POWER_PROFILE]
        )
    ]
    f = find(analyze(session(results)), FindingCode.POWER_PROFILE)
    assert f.status is Status.FIX
    assert f.params["platform_profile"] == "balanced"
    assert f.params["energy_performance_preference"] == "balance_performance"
    assert f.params["best_profile"] == "performance"
    assert f.params["settings"] == ["platform_profile", "energy_performance_preference"]


def test_powersave_governor_alone_is_not_a_problem() -> None:
    # intel_pstate : governor « powersave » avec EPP « performance » = régime normal
    pstate = MachineState(
        ["powersave"], on_ac=True, cpu_temp_c=45.0, energy_performance_preference="performance"
    )
    results = [replace(r, state_before=pstate, state_after=pstate) for r in clean()]
    assert FindingCode.POWER_PROFILE not in codes(analyze(session(results)))


def test_conforming_conditions() -> None:
    f = find(analyze(session(clean())), FindingCode.CONDITIONS_OK)
    assert f.status is Status.OK
    assert f.params == {
        "has_battery": None,
        "platform_profile": "performance",
        "energy_performance_preference": None,
    }


def _states(before: MachineState, after: MachineState) -> list[Result]:
    return [replace(r, state_before=before, state_after=after) for r in clean()]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (BATTERY, BATTERY),  # sur batterie
        (COOL_AC_STATE, replace(COOL_AC_STATE, on_ac=False)),  # débranché pendant la session
        (BALANCED, BALANCED),  # profil non performance
        (replace(COOL_AC_STATE, on_ac=None), COOL_AC_STATE),  # secteur non confirmé
        # ni profil plateforme ni EPP : rien à affirmer
        (MachineState(["powersave"], on_ac=True, cpu_temp_c=40.0),) * 2,
    ],
)
def test_no_conforming_claim_otherwise(before, after) -> None:
    assert FindingCode.CONDITIONS_OK not in codes(analyze(session(_states(before, after))))


def test_software_rendering_and_vsync() -> None:
    results = [
        make_result("glmark2", 100.0, warnings=[BenchWarning.SOFTWARE_RENDERING]),
        make_result("vkmark", 100.0, warnings=[BenchWarning.VSYNC_UNVERIFIED]),
    ]
    findings = analyze(session(results))
    assert find(findings, FindingCode.SOFTWARE_RENDERING).status is Status.FIX
    assert find(findings, FindingCode.VSYNC_UNVERIFIED).items == [
        {"bench": "vkmark", "category": "gpu"}
    ]


# --- mesures -------------------------------------------------------------------------------


def test_hot_start_names_the_previous_test_and_the_threshold() -> None:
    hot = replace(COOL_AC_STATE, cpu_temp_c=74.0)
    results = [
        make_result("native-cpu-single", 100.0),
        make_result("native-cpu-multi", 400.0, state_before=hot, warnings=[BenchWarning.HOT_START]),
    ]
    f = find(analyze(session(results), RunSettings(hot_start_c=72.0)), FindingCode.HOT_START)
    assert f.status is Status.CHECK
    assert f.params == {"threshold_c": 72.0}
    assert f.items == [
        {
            "bench": "native-cpu-multi",
            "category": "cpu_multi",
            "temp_c": 74.0,
            "previous": "native-cpu-single",
        }
    ]


def test_hot_first_test_has_no_previous() -> None:
    hot = replace(COOL_AC_STATE, cpu_temp_c=80.0)
    results = [
        make_result("native-cpu-single", 100.0, state_before=hot, warnings=[BenchWarning.HOT_START])
    ]
    assert find(analyze(session(results)), FindingCode.HOT_START).items[0]["previous"] is None


def test_high_variance_uses_the_session_threshold() -> None:
    results = [
        make_result("vkmark", 100.0, stdev=17.0, warnings=[BenchWarning.HIGH_VARIANCE]),
        make_result("glmark2", 100.0, stdev=2.9),  # sous le seuil : pas cité
    ]
    f = find(
        analyze(session(results), RunSettings(high_variance_cv_percent=3.0)),
        FindingCode.HIGH_VARIANCE,
    )
    assert f.params == {"threshold_percent": 3.0}
    assert f.items == [{"bench": "vkmark", "category": "gpu", "cv_percent": pytest.approx(17.0)}]


def test_warmup_unstable_cites_the_category_cap() -> None:
    results = [
        make_result(
            "native-cpu-multi", 400.0, warmup_stable=False, warnings=[BenchWarning.WARMUP_UNSTABLE]
        )
    ]
    f = find(analyze(session(results)), FindingCode.WARMUP_UNSTABLE)
    assert f.items == [{"bench": "native-cpu-multi", "category": "cpu_multi", "cap_s": 90.0}]


@pytest.mark.parametrize(("stdev", "expected"), [(1.0, True), (1.01, False)])
def test_reproducible_only_when_every_cv_is_under_the_threshold(stdev, expected) -> None:
    results = [
        make_result("native-cpu-single", 100.0, stdev=stdev),
        make_result("native-cpu-multi", 400.0),
    ]
    assert (FindingCode.REPRODUCIBLE in codes(analyze(session(results)))) is expected


def test_no_results_no_reproducible_claim() -> None:
    assert FindingCode.REPRODUCIBLE not in codes(analyze(session([])))


# --- températures --------------------------------------------------------------------------


def coretemp(high: float | None) -> SensorsData:
    return SensorsData([TemperatureReading("coretemp", "Package id 0", 60.0, high, high)])


@pytest.mark.parametrize(
    ("high", "code", "status"),
    [
        (100.0, FindingCode.TEMPERATURE_OK, Status.OK),
        (45.0, FindingCode.TEMPERATURE_REACHED, Status.CHECK),
        (None, FindingCode.TEMPERATURE_MAX, Status.INFO),
    ],
)
def test_temperature_against_the_cpu_sensor_threshold(high, code, status) -> None:
    findings = analyze(session(clean(), sensors=coretemp(high)))
    f = find(findings, code)
    assert f.status is status and f.params == {"max_c": 45.0, "threshold_c": high}


def test_no_temperature_no_claim() -> None:
    unknown = replace(COOL_AC_STATE, cpu_temp_c=None)
    results = [replace(r, state_before=unknown, state_after=unknown) for r in clean()]
    assert not {FindingCode.TEMPERATURE_OK, FindingCode.TEMPERATURE_MAX} & set(
        codes(analyze(session(results)))
    )


# --- information ---------------------------------------------------------------------------


def test_multi_factor_per_backend_with_cores() -> None:
    cpu = replace(snapshot().cpu, physical_cores=4, logical_cores=8)
    results = [
        make_result("native-cpu-single", 100.0),
        make_result("native-cpu-multi", 300.0, workers=8),
        make_result("native-memory-single", 10_000.0, unit="MiB/s"),
        make_result("native-memory-multi", 15_000.0, unit="MiB/s", workers=8),
    ]
    found = [f for f in analyze(session(results, cpu=cpu)) if f.code is FindingCode.MULTI_FACTOR]
    assert [(f.params["kind"], f.params["factor"]) for f in found] == [
        ("cpu", pytest.approx(3.0)),
        ("memory", pytest.approx(1.5)),
    ]
    assert found[0].params | {"factor": 0} == {
        "kind": "cpu",
        "backend": "native",
        "factor": 0,
        "single_value": 100.0,
        "multi_value": 300.0,
        "unit": "index",
        "workers": 8,
        "cores": 4,
        "threads": 8,
    }


def test_no_multi_factor_without_both_halves() -> None:
    results = [make_result("native-cpu-single", 100.0)]
    assert FindingCode.MULTI_FACTOR not in codes(analyze(session(results)))


def test_needs_root_and_no_reference() -> None:
    ram = replace(snapshot().ram, modules_unavailable=Unavailable.NEEDS_ROOT)
    findings = analyze(session(clean(), reference=None, ram=ram))
    assert find(findings, FindingCode.NEEDS_ROOT).params == {"missing": ["ram_modules"]}
    assert FindingCode.NO_REFERENCE in codes(findings)
    assert FindingCode.NO_REFERENCE not in codes(analyze(session(clean())))


def test_gpu_not_measured() -> None:
    cpu_only = [r for r in clean() if r.name.startswith(("native", "sysbench"))]
    assert FindingCode.GPU_NOT_MEASURED in codes(analyze(session(cpu_only)))
    assert FindingCode.GPU_NOT_MEASURED not in codes(analyze(session(clean())))


def test_memory_and_disk_outside_the_reference() -> None:
    results = clean() + [
        make_result("native-memory-single", 10_000.0),
        make_result(
            "fio-disk",
            9_000.0,
            tool_version="3.40",
            presentation="1GiB",
            environment={"filesystem": "btrfs", "device": "Samsung SSD 990 EVO Plus 1TB"},
        ),
    ]
    findings = analyze(session(results))
    assert find(findings, FindingCode.NOT_IN_REFERENCE).params == {"categories": ["memory", "disk"]}
    assert find(findings, FindingCode.DISK_CONTEXT).params == {
        "size": "1GiB",
        "filesystem": "btrfs",
        "device": "Samsung SSD 990 EVO Plus 1TB",
    }


# --- vraies sessions de results/ -----------------------------------------------------------


def test_real_dell_session() -> None:
    findings = analyze(load_export(RESULTS / "dell-latitude-5420.json"))
    assert codes(findings) == [
        FindingCode.HOT_START,
        FindingCode.HIGH_VARIANCE,
        FindingCode.CONDITIONS_OK,
        FindingCode.TEMPERATURE_OK,
        FindingCode.MULTI_FACTOR,
        FindingCode.MULTI_FACTOR,
        FindingCode.NEEDS_ROOT,
    ]
    assert [i["bench"] for i in find(findings, FindingCode.HIGH_VARIANCE).items] == [
        "glmark2",
        "vkmark",
    ]


def test_real_b850_session_is_clean() -> None:
    findings = analyze(load_export(RESULTS / "asrock-b850-riptide-wifi.json"))
    assert not [f for f in findings if f.status in (Status.FIX, Status.CHECK)]
    assert FindingCode.REPRODUCIBLE in codes(findings)
    # k10temp n'expose pas de seuil : maximum seul, sans jugement
    assert FindingCode.TEMPERATURE_MAX in codes(findings)


def test_threshold_findings_use_the_given_settings_not_the_stored_warnings() -> None:
    """Le site applique les seuils par défaut : un avertissement enregistré avec un seuil plus
    strict ne compte pas, et un fichier sans avertissement enregistré est quand même jugé."""
    warm = replace(COOL_AC_STATE, cpu_temp_c=66.0)
    results = [
        # mesuré avec --hot-start 60 et --max-cv 2 : avertissements enregistrés
        make_result(
            "native-cpu-single",
            100.0,
            stdev=3.0,
            state_before=warm,
            warnings=[BenchWarning.HOT_START, BenchWarning.HIGH_VARIANCE],
        ),
        # retouché : aucun avertissement enregistré malgré un CV de 12 % et 75 °C au départ
        make_result(
            "native-cpu-multi",
            100.0,
            stdev=12.0,
            state_before=replace(COOL_AC_STATE, cpu_temp_c=75.0),
        ),
    ]
    findings = analyze(session(results), RunSettings())
    assert [i["bench"] for i in find(findings, FindingCode.HOT_START).items] == ["native-cpu-multi"]
    assert [i["bench"] for i in find(findings, FindingCode.HIGH_VARIANCE).items] == [
        "native-cpu-multi"
    ]
    strict = analyze(session(results), RunSettings(hot_start_c=60.0, high_variance_cv_percent=2.0))
    assert len(find(strict, FindingCode.HOT_START).items) == 2
