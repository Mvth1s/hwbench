from statistics import geometric_mean

import pytest
from conftest import TINY

from hwbench.benchmarks.base import BenchOptions, benchmark_classes, known_backends, select
from hwbench.benchmarks.native import cpu
from hwbench.benchmarks.native.cpu import NativeCpuMulti, NativeCpuSingle, logical_cpus
from hwbench.benchmarks.native.workloads import MIB, WORKLOADS, Workload, fingerprint
from hwbench.results import Category

# Changer une charge change les scores : il faut alors incrémenter NATIVE_CPU_VERSION
# (résultats déclarés non comparables) puis mettre à jour cette empreinte.
EXPECTED_FINGERPRINT = "4c7afc925e53e53110ede7e529f6956307405f883d86f240d8214cd06932980a"


def test_workloads_fingerprint_matches_version() -> None:
    assert cpu.NATIVE_CPU_VERSION == "1"
    assert fingerprint(WORKLOADS) == EXPECTED_FINGERPRINT


def test_inputs_are_deterministic() -> None:
    for workload in TINY:
        assert repr(workload.prepare()) == repr(workload.prepare())


def test_execute_returns_amount_of_work() -> None:
    sha, zl, lz, pm = TINY
    assert sha.execute(sha.prepare()) == pytest.approx(2 * 64 * 1024 / MIB)
    assert zl.execute(zl.prepare()) == pytest.approx(64 * 1024 / MIB)
    assert lz.execute(lz.prepare()) == pytest.approx(16 * 1024 / MIB)
    assert pm.execute(pm.prepare()) == 2.0


def test_unknown_workload_raises() -> None:
    with pytest.raises(ValueError):
        Workload("nope", "x", 1, 1).prepare()


def test_registry() -> None:
    names = {cls.name for cls in benchmark_classes()}
    assert {"native-cpu-single", "native-cpu-multi"} <= names
    assert "native" in known_backends()
    assert select([Category.CPU_SINGLE], "native") == [NativeCpuSingle]
    assert select([Category.GPU], "native") == []
    assert [c.name for c in select([Category.CPU_MULTI], "all")] == [
        "native-cpu-multi",
        "sysbench-cpu-multi",
    ]
    assert {"sysbench", "glmark2", "vkmark"} <= known_backends()


def test_single_core_measurement() -> None:
    bench = NativeCpuSingle(workloads=TINY)
    m = bench.run()
    assert set(m.details) == {"sha256", "zlib", "lzma", "powmod"}
    assert all(v > 0 for v in m.details.values())
    assert m.value == pytest.approx(geometric_mean(m.details.values()))
    assert bench.workers is None
    assert bench.detail_units["powmod"] == "op/s"


def test_default_workloads_resolved_at_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpu, "WORKLOADS", TINY)
    assert NativeCpuSingle().workloads is TINY


def test_multi_core_uses_processes_and_sums_rates() -> None:
    bench = NativeCpuMulti(BenchOptions(workers=2), workloads=TINY)
    assert bench.workers == 2
    m = bench.run()
    assert set(m.details) == {"sha256", "zlib", "lzma", "powmod"}
    assert m.value == pytest.approx(geometric_mean(m.details.values()))
    assert m.duration_s > 0


def test_multi_core_default_workers() -> None:
    assert NativeCpuMulti().workers == logical_cpus() >= 1


def test_multi_core_worker_failure_is_reported_quickly() -> None:
    bench = NativeCpuMulti(BenchOptions(workers=2), workloads=(Workload("nope", "x", 1, 1),))
    with pytest.raises(RuntimeError, match="charge inconnue"):
        bench.run()


def test_environment_records_library_versions() -> None:
    env = NativeCpuSingle().environment()
    assert env["python"].split()[1].count(".") == 2
    assert env["openssl"].startswith("OpenSSL") or env["openssl"]
    assert env["zlib"]
