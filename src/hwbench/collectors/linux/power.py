from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import Battery, PowerData

POWER_SUPPLY_DIR = "/sys/class/power_supply"
PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"
_AC_TYPES = {"Mains", "USB"}


def _read_int(path: str) -> int | None:
    value = _exec.read_sysfs(path)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _capacity_wh(base: str, kind: str) -> float | None:
    """kind = "full" ou "full_design". energy_* en µWh ; sinon charge_* (µAh) × tension (µV)."""
    energy = _read_int(f"{base}/energy_{kind}")
    if energy is not None:
        return energy / 1_000_000
    charge = _read_int(f"{base}/charge_{kind}")
    voltage = _read_int(f"{base}/voltage_min_design")
    if charge is not None and voltage:
        return charge * voltage / 1e12
    return None


def read_battery(name: str) -> Battery:
    base = f"{POWER_SUPPLY_DIR}/{name}"
    return Battery(
        name=name,
        percent=_read_int(f"{base}/capacity"),
        status=_exec.read_sysfs(f"{base}/status"),
        design_capacity_wh=_capacity_wh(base, "full_design"),
        full_capacity_wh=_capacity_wh(base, "full"),
        # beaucoup de firmwares (Dell notamment) exposent 0 faute de compteur réel
        cycle_count=_read_int(f"{base}/cycle_count") or None,
    )


def read_power_supply() -> PowerData:
    batteries: list[Battery] = []
    ac_states: list[bool] = []
    for name in _exec.list_dir(POWER_SUPPLY_DIR):
        base = f"{POWER_SUPPLY_DIR}/{name}"
        # scope=Device : batterie de souris/manette, pas celle de la machine
        if _exec.read_sysfs(f"{base}/scope") == "Device":
            continue
        kind = _exec.read_sysfs(f"{base}/type")
        if kind == "Battery":
            batteries.append(read_battery(name))
        elif kind in _AC_TYPES:
            online = _read_int(f"{base}/online")
            if online is not None:
                ac_states.append(online == 1)

    if ac_states:
        on_ac: bool | None = any(ac_states)
    elif batteries:
        on_ac = not any(b.status == "Discharging" for b in batteries)
    else:
        on_ac = None
    choices = _exec.read_sysfs(f"{PLATFORM_PROFILE}_choices")
    return PowerData(
        on_ac=on_ac,
        batteries=batteries,
        platform_profile=_exec.read_sysfs(PLATFORM_PROFILE) or None,
        platform_profile_choices=choices.split() if choices else [],
    )


@register("Linux")
class LinuxPowerCollector(Collector[PowerData, None]):
    component = "power"

    def collect(self, include_identifiers: bool = False) -> ComponentResult[PowerData, None]:
        return ComponentResult(read_power_supply())
