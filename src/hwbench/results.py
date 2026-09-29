"""Modèles des résultats de benchmark, partagés par benchmarks, runner, scoring et affichage."""

from dataclasses import dataclass, field
from enum import StrEnum


class Category(StrEnum):
    CPU_SINGLE = "cpu_single"
    CPU_MULTI = "cpu_multi"
    GPU = "gpu"


class BenchWarning(StrEnum):
    ON_BATTERY = "on_battery"
    HOT_START = "hot_start"
    HIGH_VARIANCE = "high_variance"


@dataclass(frozen=True)
class Measurement:
    """Une exécution d'un benchmark (un run)."""

    value: float
    duration_s: float
    details: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class MachineState:
    governors: list[str]
    on_ac: bool | None
    cpu_temp_c: float | None


@dataclass(frozen=True)
class Result:
    name: str
    category: Category
    backend: str
    version: str
    unit: str
    higher_is_better: bool
    value: float  # médiane des runs
    stdev: float
    runs: list[float]
    warmup_runs: int
    duration_s: float  # durée totale, warm-up compris
    details: dict[str, float]  # médiane par sous-charge
    detail_units: dict[str, str]
    workers: int | None
    environment: dict[str, str]
    state_before: MachineState
    state_after: MachineState
    warnings: list[BenchWarning]

    @property
    def cv_percent(self) -> float:
        return 100.0 * self.stdev / self.value if self.value else 0.0
