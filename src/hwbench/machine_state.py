"""État de la machine relevé autour d'un benchmark (réglages d'énergie, secteur, température)."""

from hwbench.collectors import get_collector
from hwbench.models import CpuData, PowerData, SensorsData
from hwbench.results import MachineState


def cpu_temperature(sensors: SensorsData) -> float | None:
    sensor = sensors.cpu_sensor()
    return sensor.current_c if sensor is not None else None


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
