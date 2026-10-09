"""Bande passante mémoire native : copie de gros buffers, en un processus et en N processus.

La copie passe par memoryview (dst[:] = src) : CPython la fait en C (memcpy), le temps mesuré
est celui de la copie et non de l'interpréteur. Les buffers dépassent les caches : 128 Mio en
single (256 Mio avec la destination), 32 Mio par processus en multi (le total dépasse le cache
L3 dès quelques processus). Les pages sont touchées pendant la préparation, hors chrono.
Le débit compte les octets copiés (pas lus + écrits), en Mio/s. Toute modification des
paramètres change l'empreinte (`fingerprint`) et impose d'incrémenter NATIVE_MEMORY_VERSION.
"""

import hashlib
import platform
from dataclasses import dataclass
from time import perf_counter

from hwbench.benchmarks.base import Benchmark, BenchOptions, logical_cpus, register
from hwbench.benchmarks.native.cpu import run_parallel, run_workloads
from hwbench.benchmarks.native.workloads import MIB, SEED, random_bytes
from hwbench.results import Category, Measurement

NATIVE_MEMORY_VERSION = "1"


@dataclass(frozen=True)
class MemoryCopy:
    """Même interface qu'une charge CPU (key, unit, prepare, execute) : run_workloads et
    run_parallel l'exécutent telle quelle."""

    key: str
    unit: str
    size: int  # octets par buffer (source et destination)
    repeat: int

    def prepare(self) -> tuple[memoryview, memoryview]:
        src = bytearray(random_bytes(self.size, SEED + 3))
        dst = bytearray(self.size)
        dst[:] = src  # pages de la destination allouées et touchées hors chrono
        return memoryview(src), memoryview(dst)

    def execute(self, data: tuple[memoryview, memoryview]) -> float:
        src, dst = data
        for _ in range(self.repeat):
            dst[:] = src
        return self.repeat * self.size / MIB


# Par run sur un i5-1145G7 (DDR4-3200, double canal) : ~0,2 s en single, ~0,7 s sur 8 processus
SINGLE: tuple[MemoryCopy, ...] = (MemoryCopy("copy", "MiB/s", size=128 * MIB, repeat=24),)
MULTI: tuple[MemoryCopy, ...] = (MemoryCopy("copy", "MiB/s", size=32 * MIB, repeat=32),)


def fingerprint(single: tuple[MemoryCopy, ...], multi: tuple[MemoryCopy, ...]) -> str:
    """Paramètres et graine des deux variantes (le contenu des buffers en dépend seul)."""
    params = [(w.key, w.unit, w.size, w.repeat) for w in (*single, *multi)]
    return hashlib.sha256(repr((params, SEED + 3)).encode()).hexdigest()


class _NativeMemory(Benchmark):
    backend = "native"
    category = Category.MEMORY
    version = NATIVE_MEMORY_VERSION
    unit = "MiB/s"

    def environment(self) -> dict[str, str]:
        return {"python": f"{platform.python_implementation()} {platform.python_version()}"}


@register
class NativeMemorySingle(_NativeMemory):
    name = "native-memory-single"

    def __init__(
        self, options: BenchOptions | None = None, workloads: tuple[MemoryCopy, ...] | None = None
    ) -> None:
        super().__init__(options)
        self.workloads = workloads or SINGLE
        self._inputs: list[tuple[memoryview, memoryview]] | None = None

    def run(self) -> Measurement:
        if self._inputs is None:
            self._inputs = [w.prepare() for w in self.workloads]
        start = perf_counter()
        rates = run_workloads(self.workloads, self._inputs)
        return Measurement(value=rates["copy"], duration_s=perf_counter() - start)

    def cleanup(self) -> None:
        self._inputs = None  # libère les buffers (256 Mio) dès la fin du bench


@register
class NativeMemoryMulti(_NativeMemory):
    """La même copie sur N processus : bande passante agrégée (somme des débits)."""

    name = "native-memory-multi"

    def __init__(
        self, options: BenchOptions | None = None, workloads: tuple[MemoryCopy, ...] | None = None
    ) -> None:
        super().__init__(options)
        self.workloads = workloads or MULTI

    @property
    def workers(self) -> int:
        return self.options.workers or logical_cpus()

    def run(self) -> Measurement:
        rates, wall = run_parallel(self.workloads, self.workers, "mémoire multi-processus")
        return Measurement(value=rates["copy"], duration_s=wall)
