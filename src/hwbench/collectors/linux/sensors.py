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


def read_hwmon() -> SensorsData:
    temps: list[TemperatureReading] = []
    fans: list[FanReading] = []
    for hwmon in _exec.list_dir(HWMON_DIR):
        base = f"{HWMON_DIR}/{hwmon}"
        chip = _exec.read_sysfs(f"{base}/name") or hwmon
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
                    )
                )
            elif match := _FAN_INPUT_RE.match(entry):
                idx = match.group(1)
                fans.append(
                    FanReading(
                        chip=chip,
                        label=_exec.read_sysfs(f"{base}/fan{idx}_label") or f"fan{idx}",
                        rpm=_read_int(f"{base}/fan{idx}_input"),
                    )
                )
    return SensorsData(temperatures=temps, fans=fans)


@register("Linux")
class LinuxSensorsCollector(Collector[SensorsData, None]):
    component = "sensors"

    def collect(self, include_identifiers: bool = False) -> ComponentResult[SensorsData, None]:
        return ComponentResult(read_hwmon())
