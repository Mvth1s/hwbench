"""sysbench cpu (recherche de nombres premiers) et memory (lecture séquentielle), single et
multi-thread."""

import re

from hwbench.benchmarks.base import Benchmark, BenchOptions, logical_cpus, register
from hwbench.benchmarks.external import _run
from hwbench.results import Availability, Category, Measurement

SYSBENCH_VERSION = "1"  # à incrémenter si les paramètres ci-dessous changent
RUN_SECONDS = 5
MAX_PRIME = 10_000

# memory : blocs plus gros que les caches (un bloc par thread, --memory-scope=local), lus en
# séquentiel jusqu'à la fin du temps imparti (--memory-total-size démesuré).
SYSBENCH_MEMORY_VERSION = "1"
MEMORY_BLOCK_SINGLE = "128M"
MEMORY_BLOCK_MULTI = "32M"
MEMORY_TOTAL = "100T"

_VERSION_RE = re.compile(r"^sysbench\s+(\S+)", re.M)
_EPS_RE = re.compile(r"events per second:\s*([\d.]+)")
_TOTAL_TIME_RE = re.compile(r"total time:\s*([\d.]+)s")
_MIB_PER_SEC_RE = re.compile(r"MiB transferred \(([\d.]+) MiB/sec\)")


def parse_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def parse_events_per_second(text: str) -> float:
    match = _EPS_RE.search(text)
    if not match:
        raise _run.ToolError("sysbench : « events per second » introuvable dans la sortie")
    return float(match.group(1))


def parse_mib_per_second(text: str) -> float:
    match = _MIB_PER_SEC_RE.search(text)
    if not match:
        raise _run.ToolError("sysbench : « MiB/sec » introuvable dans la sortie")
    return float(match.group(1))


def parse_total_time(text: str) -> float | None:
    match = _TOTAL_TIME_RE.search(text)
    return float(match.group(1)) if match else None


class _Sysbench(Benchmark):
    backend = "sysbench"
    version = SYSBENCH_VERSION
    unit = "events/s"

    def __init__(self, options: BenchOptions | None = None) -> None:
        super().__init__(options)
        self._tool_version: str | None = None

    def availability(self) -> Availability:
        return Availability.AVAILABLE if _run.which("sysbench") else Availability.TOOL_MISSING

    @property
    def threads(self) -> int:
        return 1

    def tool_version(self) -> str | None:
        return self._tool_version

    def environment(self) -> dict[str, str]:
        return {"cpu-max-prime": str(MAX_PRIME), "time": f"{RUN_SECONDS} s"}

    def command(self) -> list[str]:
        return [
            "sysbench",
            "cpu",
            f"--threads={self.threads}",
            f"--time={RUN_SECONDS}",
            f"--cpu-max-prime={MAX_PRIME}",
            "run",
        ]

    def parse_value(self, text: str) -> float:
        return parse_events_per_second(text)

    def run(self) -> Measurement:
        text = _run.output_or_raise(self.command(), timeout=RUN_SECONDS + 60)
        self._tool_version = parse_version(text) or self._tool_version
        return Measurement(
            value=self.parse_value(text),
            duration_s=parse_total_time(text) or float(RUN_SECONDS),
        )


@register
class SysbenchCpuSingle(_Sysbench):
    name = "sysbench-cpu-single"
    category = Category.CPU_SINGLE


@register
class SysbenchCpuMulti(_Sysbench):
    name = "sysbench-cpu-multi"
    category = Category.CPU_MULTI

    @property
    def threads(self) -> int:
        return self.options.workers or logical_cpus()

    @property
    def workers(self) -> int:
        return self.threads


class _SysbenchMemory(_Sysbench):
    category = Category.MEMORY
    version = SYSBENCH_MEMORY_VERSION
    unit = "MiB/s"
    block_size = MEMORY_BLOCK_SINGLE

    def environment(self) -> dict[str, str]:
        return {
            "block-size": self.block_size,
            "operation": "read, seq",
            "time": f"{RUN_SECONDS} s",
        }

    def command(self) -> list[str]:
        return [
            "sysbench",
            "memory",
            f"--threads={self.threads}",
            f"--time={RUN_SECONDS}",
            f"--memory-block-size={self.block_size}",
            f"--memory-total-size={MEMORY_TOTAL}",
            "--memory-scope=local",
            "--memory-oper=read",
            "--memory-access-mode=seq",
            "run",
        ]

    def parse_value(self, text: str) -> float:
        return parse_mib_per_second(text)


@register
class SysbenchMemorySingle(_SysbenchMemory):
    name = "sysbench-memory-single"


@register
class SysbenchMemoryMulti(_SysbenchMemory):
    name = "sysbench-memory-multi"
    block_size = MEMORY_BLOCK_MULTI

    @property
    def threads(self) -> int:
        return self.options.workers or logical_cpus()

    @property
    def workers(self) -> int:
        return self.threads
