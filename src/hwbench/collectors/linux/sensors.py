import re

from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import FanReading, SensorsData, TemperatureReading

HWMON_DIR = "/sys/class/hwmon"
_TEMP_INPUT_RE = re.compile(r"^temp(\d+)_input$")
_FAN_INPUT_RE = re.compile(r"^fan(\d+)_input$")


def _read_int(path: str) -> int | None:
    value = _exec.read_sysfs(path)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _millideg(path: str) -> float | None:
    value = _read_int(path)
    if value is None:
        return None
    celsius = value / 1000
    # certains pilotes (nvme) exposent 0xFFFF-273.15 ≈ 65262 °C comme « pas de seuil »
    return celsius if -60 <= celsius <= 200 else None


_NVME_RE = re.compile(r"^nvme\d+$")


def instance_names(chips: dict[str, str]) -> dict[str, str | None]:
    """hwmonN -> nom distinctif, pour les puces dont le nom n'est pas unique.

    NVMe : le contrôleur cible du lien device (« nvme0 »). Autres (spd5118, une par barrette) :
    « spd5118 #1 », « #2 »… dans l'ordre des périphériques (adresse i2c, chemin PCI).
    """
    counts: dict[str, int] = {}
    for chip in chips.values():
        counts[chip] = counts.get(chip, 0) + 1
    names: dict[str, str | None] = dict.fromkeys(chips)
    duplicates = [h for h, chip in chips.items() if counts[chip] > 1]
    devices = {h: _exec.link_name(f"{HWMON_DIR}/{h}/device") for h in duplicates}
    by_order = sorted(duplicates, key=lambda h: (devices[h] or "", h))
    rank: dict[str, int] = {}
    for hwmon in by_order:
        chip = chips[hwmon]
        rank[chip] = rank.get(chip, 0) + 1
        device = devices[hwmon]
        names[hwmon] = device if device and _NVME_RE.match(device) else f"{chip} #{rank[chip]}"
    return names


def read_hwmon() -> SensorsData:
    temps: list[TemperatureReading] = []
    fans: list[FanReading] = []
    chips = {
        hwmon: _exec.read_sysfs(f"{HWMON_DIR}/{hwmon}/name") or hwmon
        for hwmon in _exec.list_dir(HWMON_DIR)
    }
    instances = instance_names(chips)
    for hwmon, chip in chips.items():
        base = f"{HWMON_DIR}/{hwmon}"
        for entry in _exec.list_dir(base):
            if match := _TEMP_INPUT_RE.match(entry):
                idx = match.group(1)
                temps.append(
                    TemperatureReading(
                        chip=chip,
                        label=_exec.read_sysfs(f"{base}/temp{idx}_label") or f"temp{idx}",
                        current_c=_millideg(f"{base}/temp{idx}_input"),
                        high_c=_millideg(f"{base}/temp{idx}_max"),
                        critical_c=_millideg(f"{base}/temp{idx}_crit"),
                        instance=instances[hwmon],
                    )
                )
            elif match := _FAN_INPUT_RE.match(entry):
                idx = match.group(1)
                fans.append(
                    FanReading(
                        chip=chip,
                        label=_exec.read_sysfs(f"{base}/fan{idx}_label") or f"fan{idx}",
                        rpm=_read_int(f"{base}/fan{idx}_input"),
                        instance=instances[hwmon],
                    )
                )
    return SensorsData(temperatures=temps, fans=fans)


@register("Linux")
class LinuxSensorsCollector(Collector[SensorsData, None]):
    component = "sensors"

    def collect(self, include_identifiers: bool = False) -> ComponentResult[SensorsData, None]:
        return ComponentResult(read_hwmon())
