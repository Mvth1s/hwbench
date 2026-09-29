"""sysbench cpu (recherche de nombres premiers), single et multi-thread."""

import re

from hwbench.benchmarks.base import Benchmark, BenchOptions, logical_cpus, register
from hwbench.benchmarks.external import _run
from hwbench.results import Availability, Category, Measurement

SYSBENCH_VERSION = "1"  # à incrémenter si les paramètres ci-dessous changent
RUN_SECONDS = 5
MAX_PRIME = 10_000

_VERSION_RE = re.compile(r"^sysbench\s+(\S+)", re.M)
_EPS_RE = re.compile(r"events per second:\s*([\d.]+)")
_TOTAL_TIME_RE = re.compile(r"total time:\s*([\d.]+)s")


def parse_version(text: str) -> str | None:
    match = _VERSION_RE.search(text)
    return match.group(1) if match else None


def parse_events_per_second(text: str) -> float:
    match = _EPS_RE.search(text)
    if not match:
        raise _run.ToolError("sysbench : « events per second » introuvable dans la sortie")
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

    def run(self) -> Measurement:
        args = [
            "sysbench",
            "cpu",
            f"--threads={self.threads}",
            f"--time={RUN_SECONDS}",
            f"--cpu-max-prime={MAX_PRIME}",
            "run",
        ]
        text = _run.output_or_raise(args, timeout=RUN_SECONDS + 60)
        self._tool_version = parse_version(text) or self._tool_version
        return Measurement(
            value=parse_events_per_second(text),
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
