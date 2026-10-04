"""Modèles des résultats de benchmark, partagés par benchmarks, runner, scoring et affichage."""

import re
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
    VSYNC_UNVERIFIED = "vsync_unverified"  # présentation à l'écran, mode non vérifiable
    SOFTWARE_RENDERING = "software_rendering"  # llvmpipe / lavapipe : le CPU fait le rendu


class Availability(StrEnum):
    AVAILABLE = "available"
    TOOL_MISSING = "tool_missing"
    NO_DISPLAY = "no_display"  # outil graphique sans session Wayland/X11 ni variante DRM


_UPSTREAM_VERSION_RE = re.compile(r"\d+(?:\.\d+)+")


def driver_key(driver: str | None) -> tuple[str, str] | None:
    """Pilote ramené à (nom, version amont), sans la révision du paquet de la distribution.

    « Mesa 26.2.4-arch1.1 », « Mesa 26.2.4-arch1.2 », « Mesa 26.2.4 » (Fedora) et
    « Mesa 26.2.4-1 » (Debian) -> ("mesa", "26.2.4") ; « NVIDIA 550.54.14 » ->
    ("nvidia", "550.54.14"). La chaîne brute reste celle affichée.
    """
    if not driver or not driver.strip():
        return None
    match = _UPSTREAM_VERSION_RE.search(driver)
    if match is None:
        return driver.strip().lower(), ""
    return driver[: match.start()].strip().lower(), match.group(0)


def gpu_key(renderer: str | None) -> str | None:
    """Nom du GPU sans les détails volatils du renderer (pilote, noyau, DRM, bus).

    « AMD Radeon RX 9070 XT (radeonsi, gfx1201, ACO, DRM 3.64, 7.2.7-arch1-1) » et
    « AMD Radeon RX 9070 XT (RADV GFX1201) » -> « amd radeon rx 9070 xt » ;
    « NVIDIA GeForce RTX 3060/PCIe/SSE2 » -> « nvidia geforce rtx 3060 ».
    """
    if not renderer:
        return None
    # « (… » précédé d'une espace : détails du pilote ; « Intel(R) » (collé) fait partie du nom
    name = re.split(r"\s+\(|/", renderer, maxsplit=1)[0].strip().lower()
    return name or None


@dataclass(frozen=True)
class BackendId:
    """Ce qui rend deux mesures comparables : même bench, même version, même version d'outil,
    même mode de présentation (hors écran, headless, à l'écran)."""

    name: str
    version: str
    tool_version: str | None = None
    presentation: str | None = None

    def label(self) -> str:
        extra = [f"outil {self.tool_version}" if self.tool_version else None, self.presentation]
        return ", ".join([f"{self.name} v{self.version}", *filter(None, extra)])


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
    has_battery: bool | None = None  # False : desktop, secteur par construction

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
    tool_version: str | None  # version de l'outil externe (None pour le natif)
    presentation: str | None  # GPU : offscreen, headless, immediate-requested
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
    def backend_id(self) -> BackendId:
        return BackendId(self.name, self.version, self.tool_version, self.presentation)

    @property
    def cv_percent(self) -> float:
        return 100.0 * self.stdev / self.value if self.value else 0.0
