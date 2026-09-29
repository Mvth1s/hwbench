import os
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from hwbench.results import Availability, BenchWarning, Category, Measurement


@dataclass(frozen=True)
class BenchOptions:
    workers: int | None = None  # None = nombre de CPU logiques utilisables


def logical_cpus() -> int:
    """CPU logiques réellement utilisables par ce processus (respecte l'affinité)."""
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


class Benchmark(ABC):
    """Un backend (natif ou outil externe) pour une catégorie.

    `run()` renvoie une seule mesure ; le warm-up, les répétitions, la médiane et l'état
    de la machine sont gérés par `hwbench.runner`, identiquement pour tous les backends.
    """

    name: ClassVar[str]
    category: ClassVar[Category]
    backend: ClassVar[str]
    version: ClassVar[str]
    unit: ClassVar[str]
    higher_is_better: ClassVar[bool] = True
    detail_units: ClassVar[dict[str, str]] = {}

    def __init__(self, options: BenchOptions | None = None) -> None:
        self.options = options or BenchOptions()

    def availability(self) -> Availability:
        return Availability.AVAILABLE

    def is_available(self) -> bool:
        return self.availability() is Availability.AVAILABLE

    def tool_version(self) -> str | None:
        """Version de l'outil externe ; appelée après les runs (peut venir de leur sortie)."""
        return None

    def environment(self) -> dict[str, str]:
        return {}

    def warnings(self) -> list[BenchWarning]:
        """Avertissements propres au backend, connus après les runs (ex. vsync non coupée)."""
        return []

    @property
    def workers(self) -> int | None:
        return None

    @abstractmethod
    def run(self) -> Measurement: ...


_REGISTRY: list[type[Benchmark]] = []


def register(cls: type[Benchmark]) -> type[Benchmark]:
    _REGISTRY.append(cls)
    return cls


def benchmark_classes() -> list[type[Benchmark]]:
    import hwbench.benchmarks.external  # noqa: F401
    import hwbench.benchmarks.native  # noqa: F401

    return list(_REGISTRY)


def known_backends() -> set[str]:
    return {cls.backend for cls in benchmark_classes()}


def select(categories: Iterable[Category], backend: str) -> list[type[Benchmark]]:
    """Benchs voulus, par catégorie (single, multi, GPU) puis natif d'abord."""
    wanted = set(categories)
    order = list(Category)
    return sorted(
        (
            cls
            for cls in benchmark_classes()
            if cls.category in wanted and backend in ("all", cls.backend)
        ),
        key=lambda cls: (order.index(cls.category), cls.backend != "native", cls.name),
    )
