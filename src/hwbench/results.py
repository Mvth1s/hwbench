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
    POWER_PROFILE = "power_profile"
    WARMUP_UNSTABLE = "warmup_unstable"


@dataclass(frozen=True)
class Measurement:
    """Une exécution d'un benchmark (un run)."""

    value: float
    duration_s: float
    details: dict[str, float] = field(default_factory=dict)


# Du plus économe au plus performant (valeurs du noyau, ABI platform_profile).
PLATFORM_PROFILE_ORDER = (
    "low-power",
    "cool",
    "quiet",
    "balanced",
    "balanced-performance",
    "performance",
)


@dataclass(frozen=True)
class MachineState:
    governors: list[str]
    on_ac: bool | None
    cpu_temp_c: float | None
    platform_profile: str | None = None
    platform_profile_choices: list[str] = field(default_factory=list)
    energy_performance_preference: str | None = None

    def throttling_settings(self) -> list[str]:
        """Réglages d'énergie qui brident le CPU : noms des champs concernés, vide si aucun.

        platform_profile vaut « performance » ou, faute de ce choix sur la machine, le plus
        performant proposé. « custom » (réglé hors noyau) et les valeurs absentes ne sont pas
        jugés.
        """
        issues: list[str] = []
        profile = self.platform_profile
        if profile is not None and profile != "custom" and profile != self._best_profile():
            issues.append("platform_profile")
        epp = self.energy_performance_preference
        if epp is not None and epp != "performance":
            issues.append("energy_performance_preference")
        return issues

    def _best_profile(self) -> str:
        known = [c for c in self.platform_profile_choices if c in PLATFORM_PROFILE_ORDER]
        return max(known, key=PLATFORM_PROFILE_ORDER.index, default="performance")


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
    warmup_runs: int  # itérations de warm-up, run à froid compris
    warmup_s: float
    warmup_stable: bool  # 2 itérations consécutives dans la tolérance avant le plafond
    # Premier run, à froid : pic avant chauffe/turbo soutenu. Informatif, jamais noté.
    burst: float
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
