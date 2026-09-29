"""Modèles de données publics. Aucun identifiant (serial, UUID, MAC, hostname) ici."""

from dataclasses import dataclass, field
from enum import StrEnum


class Unavailable(StrEnum):
    NEEDS_ROOT = "needs_root"
    TOOL_MISSING = "tool_missing"
    NO_DATA = "no_data"


@dataclass(frozen=True)
class CpuCoreState:
    cpu: int
    current_mhz: float | None
    governor: str | None


@dataclass(frozen=True)
class CpuData:
    vendor: str | None = None
    model: str | None = None
    architecture: str | None = None
    sockets: int | None = None
    physical_cores: int | None = None
    logical_cores: int | None = None
    threads_per_core: int | None = None
    min_mhz: float | None = None
    max_mhz: float | None = None
    l1d_cache_kb: int | None = None
    l1i_cache_kb: int | None = None
    l2_cache_kb: int | None = None
    l3_cache_kb: int | None = None
    per_cpu: list[CpuCoreState] = field(default_factory=list)
    scaling_driver: str | None = None  # cpu0 : « amd-pstate-epp », « intel_pstate »…
    # EPP de cpu0 (intel_pstate / amd-pstate en mode actif) : « performance », « balance_power »…
    energy_performance_preference: str | None = None


@dataclass(frozen=True)
class RamModule:
    slot: str | None
    size_gb: float | None
    type: str | None
    speed_mts: int | None
    manufacturer: str | None
    part_number: str | None
    rated_speed_mts: int | None = None


@dataclass(frozen=True)
class RamData:
    total_gb: float | None = None
    installed_gb: float | None = None
    modules: list[RamModule] | None = None
    modules_unavailable: Unavailable | None = None


@dataclass(frozen=True)
class PciGpu:
    vendor: str | None
    model: str | None


@dataclass(frozen=True)
class GpuData:
    pci_devices: list[PciGpu] = field(default_factory=list)
    opengl_vendor: str | None = None
    opengl_renderer: str | None = None
    opengl_version: str | None = None
    vulkan_device_name: str | None = None
    nvidia_name: str | None = None
    nvidia_driver_version: str | None = None
    nvidia_vram_mb: int | None = None


@dataclass(frozen=True)
class Disk:
    name: str
    size_bytes: int | None
    model: str | None
    type: str | None
    rotational: bool | None
    transport: str | None
    smart_passed: bool | None = None
    temperature_c: float | None = None


@dataclass(frozen=True)
class DiskData:
    disks: list[Disk] = field(default_factory=list)
    smart_unavailable: Unavailable | None = None


@dataclass(frozen=True)
class BoardData:
    system_vendor: str | None = None
    product_name: str | None = None
    product_version: str | None = None
    board_vendor: str | None = None
    board_name: str | None = None
    bios_vendor: str | None = None
    bios_version: str | None = None
    bios_date: str | None = None  # ISO 8601 (YYYY-MM-DD)


@dataclass(frozen=True)
class TemperatureReading:
    chip: str  # nom brut de la puce hwmon (« nvme », « k10temp »)
    label: str
    current_c: float | None
    high_c: float | None
    critical_c: float | None
    # nom distinctif quand plusieurs puces portent le même nom : « nvme1 », « spd5118 #2 »
    instance: str | None = None

    @property
    def source(self) -> str:
        return self.instance or self.chip


@dataclass(frozen=True)
class FanReading:
    chip: str
    label: str
    rpm: int | None
    instance: str | None = None

    @property
    def source(self) -> str:
        return self.instance or self.chip


@dataclass(frozen=True)
class SensorsData:
    temperatures: list[TemperatureReading] = field(default_factory=list)
    fans: list[FanReading] = field(default_factory=list)


@dataclass(frozen=True)
class Battery:
    name: str
    percent: int | None
    status: str | None
    design_capacity_wh: float | None
    full_capacity_wh: float | None
    cycle_count: int | None

    @property
    def health_percent(self) -> float | None:
        if not self.design_capacity_wh or self.full_capacity_wh is None:
            return None
        return 100.0 * self.full_capacity_wh / self.design_capacity_wh


@dataclass(frozen=True)
class PowerData:
    on_ac: bool | None = None
    batteries: list[Battery] = field(default_factory=list)
    # /sys/firmware/acpi/platform_profile : « performance », « balanced », « quiet »…
    platform_profile: str | None = None
    platform_profile_choices: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MachineSnapshot:
    cpu: CpuData
    ram: RamData
    gpu: GpuData
    disks: DiskData
    board: BoardData
    sensors: SensorsData
    power: PowerData


# --- Identifiants : structures séparées, jamais référencées par MachineSnapshot ---

# None = champ lu mais vide ou valeur bidon du firmware (« non renseigné ») ;
# Unavailable = champ illisible (NEEDS_ROOT sans root, NO_DATA si absent).
IdentifierValue = str | Unavailable | None


@dataclass(frozen=True)
class BoardIdentifiers:
    hostname: IdentifierValue = None
    product_uuid: IdentifierValue = None
    product_serial: IdentifierValue = None
    board_serial: IdentifierValue = None
    chassis_serial: IdentifierValue = None
    board_asset_tag: IdentifierValue = None
    chassis_asset_tag: IdentifierValue = None


@dataclass(frozen=True)
class RamModuleIdentifiers:
    slot: str | None
    serial: str | None
    asset_tag: str | None


@dataclass(frozen=True)
class DiskIdentifiers:
    name: str
    serial: str | None
    wwn: str | None
    eui64: str | None
    nguid: str | None


@dataclass(frozen=True)
class Identifiers:
    board: BoardIdentifiers | None = None
    ram_modules: list[RamModuleIdentifiers] | None = None
    disks: list[DiskIdentifiers] | None = None
