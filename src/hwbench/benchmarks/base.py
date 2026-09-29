from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from hwbench.results import Category, Measurement


@dataclass(frozen=True)
class BenchOptions:
    workers: int | None = None  # None = nombre de CPU logiques utilisables


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

    def is_available(self) -> bool:
        return True

    def environment(self) -> dict[str, str]:
        return {}

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
    import hwbench.benchmarks.native  # noqa: F401

    return list(_REGISTRY)


def known_backends() -> set[str]:
    return {cls.backend for cls in benchmark_classes()}


def select(categories: Iterable[Category], backend: str) -> list[type[Benchmark]]:
    wanted = set(categories)
    return [
        cls
        for cls in benchmark_classes()
        if cls.category in wanted and backend in ("all", cls.backend)
    ]
