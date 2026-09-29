import ctypes
import ctypes.util
import multiprocessing as mp
import os
import platform
import ssl
import threading
import zlib
from multiprocessing.synchronize import Barrier
from queue import Empty
from statistics import geometric_mean
from time import perf_counter
from typing import Any

from hwbench.benchmarks.base import Benchmark, BenchOptions, register
from hwbench.benchmarks.native.workloads import WORKLOADS, Workload
from hwbench.results import Category, Measurement

NATIVE_CPU_VERSION = "1"
BARRIER_TIMEOUT_S = 120
WORKER_TIMEOUT_S = 900


def logical_cpus() -> int:
    """CPU logiques réellement utilisables par ce processus (respecte l'affinité)."""
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


def _liblzma_version() -> str | None:
    try:
        name = ctypes.util.find_library("lzma")
        if name is None:
            return None
        lib = ctypes.CDLL(name)
        lib.lzma_version_string.restype = ctypes.c_char_p
        return lib.lzma_version_string().decode()
    except (OSError, AttributeError):
        return None


def native_environment() -> dict[str, str]:
    env = {
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "openssl": ssl.OPENSSL_VERSION,
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
    }
    if (lzma_version := _liblzma_version()) is not None:
        env["liblzma"] = lzma_version
    return env


def run_workloads(workloads: tuple[Workload, ...], inputs: list[Any]) -> dict[str, float]:
    rates: dict[str, float] = {}
    for workload, data in zip(workloads, inputs, strict=True):
        start = perf_counter()
        amount = workload.execute(data)
        rates[workload.key] = amount / (perf_counter() - start)
    return rates


class _NativeCpu(Benchmark):
    backend = "native"
    version = NATIVE_CPU_VERSION
    unit = "pts"
    detail_units = {w.key: w.unit for w in WORKLOADS}

    def __init__(
        self, options: BenchOptions | None = None, workloads: tuple[Workload, ...] | None = None
    ) -> None:
        super().__init__(options)
        self.workloads = workloads or WORKLOADS

    def environment(self) -> dict[str, str]:
        return native_environment()


@register
class NativeCpuSingle(_NativeCpu):
    name = "native-cpu-single"
    category = Category.CPU_SINGLE

    def __init__(
        self, options: BenchOptions | None = None, workloads: tuple[Workload, ...] | None = None
    ) -> None:
        super().__init__(options, workloads)
        self._inputs: list[Any] | None = None

    def run(self) -> Measurement:
        if self._inputs is None:
            self._inputs = [w.prepare() for w in self.workloads]
        start = perf_counter()
        rates = run_workloads(self.workloads, self._inputs)
        return Measurement(
            value=geometric_mean(rates.values()), duration_s=perf_counter() - start, details=rates
        )


def _worker(workloads: tuple[Workload, ...], barrier: Barrier, queue: Any) -> None:
    try:
        inputs = [w.prepare() for w in workloads]
        barrier.wait(BARRIER_TIMEOUT_S)
        queue.put(("ok", run_workloads(workloads, inputs)))
    except BaseException as exc:  # noqa: BLE001 - remonté tel quel au parent
        barrier.abort()  # débloque le parent immédiatement plutôt qu'au timeout
        queue.put(("error", repr(exc)))


@register
class NativeCpuMulti(_NativeCpu):
    """La même charge sur N processus (pas de threads : le GIL sérialiserait le code Python)."""

    name = "native-cpu-multi"
    category = Category.CPU_MULTI

    @property
    def workers(self) -> int:
        return self.options.workers or logical_cpus()

    def run(self) -> Measurement:
        n = self.workers
        # spawn : processus neufs, indépendants de la méthode par défaut (fork/forkserver)
        ctx = mp.get_context("spawn")
        barrier = ctx.Barrier(n + 1)
        queue = ctx.Queue()
        procs = [
            ctx.Process(target=_worker, args=(self.workloads, barrier, queue), daemon=True)
            for _ in range(n)
        ]
        try:
            for proc in procs:
                proc.start()
            barrier.wait(BARRIER_TIMEOUT_S)
            start = perf_counter()
            outcomes = [queue.get(timeout=WORKER_TIMEOUT_S) for _ in range(n)]
            wall = perf_counter() - start
        except (Empty, threading.BrokenBarrierError) as exc:
            try:
                detail = queue.get(timeout=1)[1]
            except Empty:
                detail = "pas de réponse"
            raise RuntimeError(f"échec d'un processus du bench multi-cœur : {detail}") from exc
        finally:
            for proc in procs:
                proc.join(timeout=5)
                if proc.is_alive():
                    proc.terminate()

        errors = [payload for status, payload in outcomes if status == "error"]
        if errors:
            raise RuntimeError(f"échec d'un processus du bench multi-cœur : {errors[0]}")
        # débit agrégé : somme des débits de chaque processus, charge par charge
        rates = {w.key: sum(payload[w.key] for _, payload in outcomes) for w in self.workloads}
        return Measurement(value=geometric_mean(rates.values()), duration_s=wall, details=rates)
