"""Textes des constats : chaque code a sa phrase, valeurs et seuils de la session cités."""

from pathlib import Path

import pytest
from test_analysis import RESULTS

from hwbench import labels
from hwbench.analysis import Finding, FindingCode, Status, analyze
from hwbench.display import bench, compare, scores
from hwbench.export import load_export
from hwbench.leaderboard import site
from hwbench.report import texts
from hwbench.report.texts import (
    MULTI_GAIN_MIN,
    STATUS_LABELS,
    bench_label,
    finding_text,
    recommendation,
    recommendations,
    synthesis,
)
from hwbench.results import Category


def test_every_code_and_status_has_a_text() -> None:
    assert set(STATUS_LABELS) == set(Status)
    samples = {
        FindingCode.ON_BATTERY: Finding(
            FindingCode.ON_BATTERY, Status.FIX, items=[{"bench": "vkmark"}]
        ),
        FindingCode.POWER_PROFILE: Finding(
            FindingCode.POWER_PROFILE,
            Status.FIX,
            {
                "settings": ["platform_profile", "energy_performance_preference"],
                "platform_profile": "balanced",
                "energy_performance_preference": "balance_power",
                "best_profile": "performance",
            },
        ),
        FindingCode.CONDITIONS_OK: Finding(
            FindingCode.CONDITIONS_OK,
            Status.OK,
            {
                "has_battery": False,
                "platform_profile": None,
                "energy_performance_preference": "performance",
            },
        ),
        FindingCode.SOFTWARE_RENDERING: Finding(
            FindingCode.SOFTWARE_RENDERING, Status.FIX, items=[{"bench": "glmark2"}]
        ),
        FindingCode.HOT_START: Finding(
            FindingCode.HOT_START,
            Status.CHECK,
            {"threshold_c": 70.0},
            [{"bench": "native-cpu-single", "temp_c": 81.0, "previous": None}],
        ),
        FindingCode.HIGH_VARIANCE: Finding(
            FindingCode.HIGH_VARIANCE,
            Status.CHECK,
            {"threshold_percent": 5.0},
            [{"bench": "vkmark", "cv_percent": 17.0}],
        ),
        FindingCode.WARMUP_UNSTABLE: Finding(
            FindingCode.WARMUP_UNSTABLE,
            Status.CHECK,
            items=[{"bench": "native-cpu-multi", "cap_s": 90.0}],
        ),
        FindingCode.VSYNC_UNVERIFIED: Finding(
            FindingCode.VSYNC_UNVERIFIED, Status.CHECK, items=[{"bench": "vkmark"}]
        ),
        FindingCode.TEMPERATURE_REACHED: Finding(
            FindingCode.TEMPERATURE_REACHED, Status.CHECK, {"max_c": 100.0, "threshold_c": 100.0}
        ),
        FindingCode.REPRODUCIBLE: Finding(
            FindingCode.REPRODUCIBLE,
            Status.OK,
            {"count": 6, "threshold_percent": 1.0, "max_cv_percent": 0.35},
        ),
        FindingCode.TEMPERATURE_OK: Finding(
            FindingCode.TEMPERATURE_OK, Status.OK, {"max_c": 72.0, "threshold_c": 100.0}
        ),
        FindingCode.TEMPERATURE_MAX: Finding(
            FindingCode.TEMPERATURE_MAX, Status.INFO, {"max_c": 68.4, "threshold_c": None}
        ),
        FindingCode.MULTI_FACTOR: Finding(
            FindingCode.MULTI_FACTOR,
            Status.INFO,
            {
                "kind": "memory",
                "backend": "sysbench",
                "factor": 2.05,
                "workers": 8,
                "cores": 4,
                "threads": 8,
            },
        ),
        FindingCode.GPU_NOT_MEASURED: Finding(FindingCode.GPU_NOT_MEASURED, Status.INFO),
        FindingCode.NEEDS_ROOT: Finding(
            FindingCode.NEEDS_ROOT, Status.INFO, {"missing": ["smart"]}
        ),
        FindingCode.NO_REFERENCE: Finding(FindingCode.NO_REFERENCE, Status.INFO),
        FindingCode.NOT_IN_REFERENCE: Finding(
            FindingCode.NOT_IN_REFERENCE, Status.INFO, {"categories": ["memory", "disk"]}
        ),
        FindingCode.DISK_CONTEXT: Finding(
            FindingCode.DISK_CONTEXT,
            Status.INFO,
            {"size": "1GiB", "filesystem": "btrfs", "device": "Samsung SSD 990 EVO Plus 1TB"},
        ),
    }
    assert set(samples) == set(FindingCode)
    texts = {code: finding_text(f) for code, f in samples.items()}
    assert all(t and t.endswith(".") for t in texts.values())
    assert (
        "profil plateforme « balanced » et EPP « balance_power »"
        in texts[FindingCode.POWER_PROFILE]
    )
    assert (
        "à 81 °C" in texts[FindingCode.HOT_START]
        and "juste après" not in texts[FindingCode.HOT_START]
        and texts[FindingCode.HOT_START].startswith("1 test a démarré à 70 °C ou plus")
    )
    assert (
        "CV de 17,0 %" in texts[FindingCode.HIGH_VARIANCE]
        and "seuil de 5 %" in texts[FindingCode.HIGH_VARIANCE]
    )
    assert "2,0 fois plus élevée sur 8 threads" in texts[FindingCode.MULTI_FACTOR]
    assert (
        "fichier de 1 Gio, système de fichiers btrfs et Samsung" in texts[FindingCode.DISK_CONTEXT]
    )
    assert "68 °C" in texts[FindingCode.TEMPERATURE_MAX]
    for code in (
        FindingCode.TEMPERATURE_OK,
        FindingCode.TEMPERATURE_MAX,
        FindingCode.TEMPERATURE_REACHED,
    ):
        assert texts[code].startswith("Température CPU maximale relevée avant et après chaque test")
    assert texts[FindingCode.CONDITIONS_OK] == (
        "Alimentation et réglages d'énergie conformes : sur secteur (pas de batterie) et EPP "
        "« performance », au meilleur réglage disponible, avant et après chaque test."
    )


def test_bench_labels() -> None:
    assert bench_label("glmark2") == "GPU OpenGL (glmark2)"
    assert bench_label("inconnu-v9") == "inconnu-v9"


def test_no_sentence_mentions_the_governor() -> None:
    for name in ("dell-latitude-5420", "asrock-b850-riptide-wifi"):
        for sentence in synthesis(analyze(load_export(RESULTS / f"{name}.json"))):
            assert "governor" not in sentence.lower()


def test_dell_synthesis() -> None:
    sentences = synthesis(analyze(load_export(RESULTS / "dell-latitude-5420.json")))
    assert sentences[:3] == [
        "4 tests ont démarré à 70 °C ou plus (seuil de départ chaud), chacun juste après un "
        "autre test : CPU single-core (sysbench) à 71 °C, CPU multi-core (sysbench) à 72 °C, "
        "GPU OpenGL (glmark2) à 72 °C et GPU Vulkan (vkmark) à 70 °C.",
        "Mesures instables pour 2 tests : GPU OpenGL (glmark2) avec un CV de 8,8 % et GPU "
        "Vulkan (vkmark) avec un CV de 17,0 %, au-delà du seuil de 5 %. Ces scores sont à "
        "confirmer.",
        "Alimentation et réglages d'énergie conformes : sur secteur, profil plateforme "
        "« performance » et EPP « performance », au meilleur réglage disponible, avant et "
        "après chaque test.",
    ]
    assert sentences[3] == (
        "Température CPU maximale relevée avant et après chaque test : 72 °C, sous le seuil "
        "haut du capteur (100 °C)."
    )
    # un seul facteur multi-cœur en synthèse (natif CPU), sysbench reste dans sa section
    assert sum("fois plus vite" in s for s in sentences) == 1
    assert len(sentences) == 5


def test_synthesis_limit() -> None:
    findings = analyze(load_export(Path(RESULTS) / "dell-latitude-5420.json"))
    assert len(synthesis(findings, limit=2)) == 2


def test_one_label_table_for_terminal_report_and_site() -> None:
    for module in (bench, scores, compare, site):
        assert module.CATEGORY_LABELS is labels.CATEGORY_LABELS
    assert texts.bench_label is labels.bench_label
    assert labels.CATEGORY_LABELS[Category.CPU_MULTI] == "CPU multi-core"
    assert all("cœur" not in label for label in labels.BENCH_LABELS.values())


def test_recommendations_give_exact_commands() -> None:
    findings = analyze(load_export(RESULTS / "dell-latitude-5420.json"))
    recs = recommendations(findings)
    commands = [c for r in recs for c in r.commands]
    # tests chauds dans plusieurs catégories : toutes ; instables : les deux GPU
    assert commands == [
        "hwbench bench all",
        "hwbench bench gpu --runs 5",
        'sudo "$(command -v hwbench)" info',
    ]
    assert not any(c.startswith("sudo hwbench") for c in commands)


def test_power_profile_recommendation_uses_the_best_available_profile() -> None:
    f = Finding(
        FindingCode.POWER_PROFILE,
        Status.FIX,
        {
            "settings": ["platform_profile"],
            "platform_profile": "balanced",
            "energy_performance_preference": None,
            "best_profile": "balanced-performance",
        },
    )
    rec = recommendation(f)
    assert rec is not None and rec.commands[0] == "powerprofilesctl set balanced-performance"


def test_no_recommendation_for_information() -> None:
    assert recommendation(Finding(FindingCode.REPRODUCIBLE, Status.OK)) is None
    assert recommendation(Finding(FindingCode.NO_REFERENCE, Status.INFO)) is None


def _factor(kind: str, single: float, multi: float, backend: str = "native") -> str:
    return finding_text(
        Finding(
            FindingCode.MULTI_FACTOR,
            Status.INFO,
            {
                "kind": kind,
                "backend": backend,
                "factor": multi / single,
                "single_value": single,
                "multi_value": multi,
                "unit": "MiB/s" if kind == "memory" else "index",
                "workers": 8,
                "cores": 4,
                "threads": 8,
            },
        )
    )


def test_multi_factor_below_one_never_claims_a_gain() -> None:
    text = _factor("memory", 13729.0, 13545.0)
    assert text == (
        "La bande passante mémoire (bench natif) ne progresse pas en multi-processus : 13545 "
        "Mio/s sur 8 processus contre 13729 sur un seul (4 cœurs / 8 threads)."
    )


@pytest.mark.parametrize("multi", [100.0, 105.0, 109.9])
def test_multi_factor_close_to_one_never_claims_a_gain(multi: float) -> None:
    for kind, backend in (("cpu", "native"), ("cpu", "sysbench"), ("memory", "native")):
        text = _factor(kind, 100.0, multi, backend)
        assert "ne progresse pas" in text
        assert "fois" not in text and "plus élevée" not in text and "plus vite" not in text
    assert "en multi-thread : " in _factor("cpu", 100.0, multi, "sysbench")


def test_multi_factor_above_the_threshold_keeps_the_gain_sentence() -> None:
    assert MULTI_GAIN_MIN == 1.1
    assert _factor("cpu", 100.0, 300.0) == (
        "Le processeur (bench natif) va 3,0 fois plus vite sur 8 processus que sur un seul "
        "(4 cœurs / 8 threads)."
    )
    assert "1,5 fois plus élevée" in _factor("memory", 10_000.0, 15_000.0)
    assert "1,1 fois plus vite" in _factor("cpu", 100.0, 110.0)  # seuil inclus
