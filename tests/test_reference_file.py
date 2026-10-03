"""Le vrai fichier de référence du paquet (src/hwbench/data/reference.json, desktop B850)."""

import json
import re
from importlib import resources

from conftest import COOL_AC_STATE, make_result
from test_fixtures_privacy import _live_identifiers
from test_scoring import snapshot

from hwbench import privacy
from hwbench.benchmarks.external.glmark2 import GLMARK2_VERSION
from hwbench.benchmarks.external.sysbench import SYSBENCH_VERSION
from hwbench.benchmarks.external.vkmark import VKMARK_VERSION
from hwbench.benchmarks.native.cpu import NATIVE_CPU_VERSION
from hwbench.reference import build_reference
from hwbench.results import Category
from hwbench.scoring import load_reference

EXPECTED = {
    "native-cpu-single": (Category.CPU_SINGLE, NATIVE_CPU_VERSION, None),
    "native-cpu-multi": (Category.CPU_MULTI, NATIVE_CPU_VERSION, None),
    "sysbench-cpu-single": (Category.CPU_SINGLE, SYSBENCH_VERSION, None),
    "sysbench-cpu-multi": (Category.CPU_MULTI, SYSBENCH_VERSION, None),
    "glmark2": (Category.GPU, GLMARK2_VERSION, "offscreen"),
    "vkmark": (Category.GPU, VKMARK_VERSION, "headless"),
}


def raw_reference() -> str:
    return resources.files("hwbench").joinpath("data/reference.json").read_text(encoding="utf-8")


def test_reference_loads_with_all_categories_and_benches() -> None:
    reference = load_reference()
    assert reference is not None
    assert reference.machine == "ASRock B850 Riptide WiFi"
    assert not reference.forced and reference.forced_reasons == []
    assert {e.category for e in reference.entries} == set(Category)
    assert {e.id.name for e in reference.entries} == set(EXPECTED)


def test_reference_matches_current_protocol_versions() -> None:
    """Incrémenter la version d'un bench impose de régénérer la référence."""
    reference = load_reference()
    assert reference is not None
    for name, (category, version, presentation) in EXPECTED.items():
        entry = reference.find(name)
        assert entry is not None
        assert (entry.category, entry.id.version, entry.id.presentation) == (
            category,
            version,
            presentation,
        ), f"{name} : référence obsolète, relancer `hwbench reference`"
        assert entry.value > 0


def test_reference_was_measured_in_steady_state() -> None:
    data = json.loads(raw_reference())
    assert data["forced"] is False and data["forced_reasons"] == []
    for bench in data["benchmarks"]:
        assert bench["warmup_stable"] is True
        for state in (bench["state_before"], bench["state_after"]):
            assert state["on_ac"] is True
            assert state["energy_performance_preference"] in (None, "performance")
            assert state["platform_profile"] in (None, "performance")


def _strings(obj: object) -> list[str]:
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in [str(k), *_strings(v)]]
    if isinstance(obj, list):
        return [s for item in obj for s in _strings(item)]
    return [obj] if isinstance(obj, str) else []


def test_reference_contains_no_identifier() -> None:
    text = raw_reference()
    data = json.loads(text)
    # déjà passé par privacy.scrub : un second passage ne change rien, rien n'a été masqué
    assert privacy.scrub(data) == data
    assert privacy.REDACTED not in text
    # motifs appliqués aux chaînes seulement : les décimales d'un écart-type ressemblent à un EUI-64
    for value in _strings(data):
        for pattern in privacy.SENSITIVE_VALUE_PATTERNS:
            assert not pattern.search(value), (pattern.pattern, value)
        assert not re.search(r"\b[0-9a-f]{32}\b", value, re.I)  # UUID GPU sans tirets
    for value in _live_identifiers():
        assert value.lower() not in text.lower()


def test_build_reference_scrubs_identifiers() -> None:
    leaky = make_result(
        "native-cpu-single",
        100.0,
        environment={"serial": "ABC123", "note": "carte aa:bb:cc:dd:ee:ff"},
        state_before=COOL_AC_STATE,
    )
    bench = build_reference([leaky], snapshot(), [])["benchmarks"][0]
    assert bench["environment"]["serial"] == privacy.REDACTED
    assert "aa:bb:cc:dd:ee:ff" not in bench["environment"]["note"]
