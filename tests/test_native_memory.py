import pytest

from hwbench.benchmarks.base import BenchOptions, select
from hwbench.benchmarks.native import memory
from hwbench.benchmarks.native.memory import (
    MemoryCopy,
    NativeMemoryMulti,
    NativeMemorySingle,
    fingerprint,
)
from hwbench.benchmarks.native.workloads import MIB
from hwbench.results import Category

# Changer la taille, le nombre de copies ou la graine change les scores : il faut alors
# incrémenter NATIVE_MEMORY_VERSION puis mettre à jour cette empreinte.
EXPECTED_FINGERPRINT = "5546f7d6905c4f7d570319d53729bbde8d859f6640794ebee19c631c4a9fc1a3"

TINY_COPY = (MemoryCopy("copy", "MiB/s", size=1 * MIB, repeat=2),)


def test_parameters_fingerprint_matches_version() -> None:
    assert memory.NATIVE_MEMORY_VERSION == "1"
    assert fingerprint(memory.SINGLE, memory.MULTI) == EXPECTED_FINGERPRINT


def test_buffers_exceed_caches() -> None:
    (single,) = memory.SINGLE
    (multi,) = memory.MULTI
    assert single.size >= 128 * MIB and multi.size >= 32 * MIB


def test_copy_returns_copied_mebibytes() -> None:
    (w,) = TINY_COPY
    src, dst = w.prepare()
    assert bytes(src) == bytes(dst)  # destination déjà touchée par la préparation
    assert w.execute((src, dst)) == pytest.approx(2.0)


def test_registry_and_order() -> None:
    assert [c.name for c in select([Category.MEMORY], "native")] == [
        "native-memory-single",
        "native-memory-multi",
    ]


def test_single_measurement_and_cleanup() -> None:
    bench = NativeMemorySingle(workloads=TINY_COPY)
    m = bench.run()
    assert m.value > 0 and m.details == {}
    assert bench.unit == "MiB/s" and bench.workers is None
    assert bench.category is Category.MEMORY and bench.version == "1"
    assert bench._inputs is not None
    bench.cleanup()
    assert bench._inputs is None


def test_multi_measurement_uses_workers() -> None:
    bench = NativeMemoryMulti(BenchOptions(workers=2), workloads=TINY_COPY)
    assert bench.workers == 2
    assert bench.run().value > 0
