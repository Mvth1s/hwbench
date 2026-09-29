"""État de la machine relevé autour d'un benchmark (réglages d'énergie, secteur, température)."""

from hwbench.collectors import get_collector
from hwbench.models import CpuData, PowerData, SensorsData
from hwbench.results import MachineState

# (puce hwmon, libellés par ordre de préférence) ; "*" = n'importe quel capteur de la puce
_CPU_SENSORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("coretemp", ("Package id 0", "Package id 1")),
    ("k10temp", ("Tdie", "Tctl")),
    ("zenpower", ("Tdie", "Tctl")),
    ("cpu_thermal", ("*",)),
)


def cpu_temperature(sensors: SensorsData) -> float | None:
    for chip, labels in _CPU_SENSORS:
        readings = [t for t in sensors.temperatures if t.chip == chip and t.current_c is not None]
        for label in labels:
            matching = [t.current_c for t in readings if label in ("*", t.label)]
            if matching:
                return max(v for v in matching if v is not None)
    return None


def state_from(cpu: CpuData, power: PowerData, sensors: SensorsData) -> MachineState:
    return MachineState(
        governors=sorted({c.governor for c in cpu.per_cpu if c.governor}),
        on_ac=power.on_ac,
        cpu_temp_c=cpu_temperature(sensors),
        platform_profile=power.platform_profile,
        platform_profile_choices=list(power.platform_profile_choices),
        energy_performance_preference=cpu.energy_performance_preference,
        has_battery=bool(power.batteries),
    )


def capture_state() -> MachineState:
    return state_from(
        get_collector("cpu").collect().data,
        get_collector("power").collect().data,
        get_collector("sensors").collect().data,
    )
