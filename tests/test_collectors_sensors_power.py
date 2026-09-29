import pytest
from conftest import sysfs_fixture

from hwbench.collectors.linux.power import LinuxPowerCollector
from hwbench.collectors.linux.sensors import LinuxSensorsCollector
from hwbench.machine_state import cpu_temperature


def test_hwmon_temperatures_and_fans(laptop) -> None:
    laptop()
    data = LinuxSensorsCollector().collect().data
    by_label = {(t.chip, t.label): t for t in data.temperatures}
    composite = by_label[("nvme", "Composite")]
    assert (composite.current_c, composite.high_c, composite.critical_c) == (37.85, 80.85, 84.85)
    assert by_label[("coretemp", "Package id 0")].current_c == 68.0
    assert by_label[("dell_smm", "temp1")].current_c == 54.0
    assert [(f.chip, f.label, f.rpm) for f in data.fans] == [("dell_smm", "fan1", 2404)]


def test_hwmon_sentinel_threshold_is_dropped(laptop) -> None:
    laptop()
    data = LinuxSensorsCollector().collect().data
    sensor1 = next(t for t in data.temperatures if t.label == "Sensor 1")
    assert sensor1.current_c == 37.85
    assert sensor1.high_c is None


def test_no_hwmon(fake_system) -> None:
    fake_system(files={})
    data = LinuxSensorsCollector().collect().data
    assert data.temperatures == [] and data.fans == []


def test_laptop_battery_and_ac(laptop) -> None:
    laptop()
    power = LinuxPowerCollector().collect().data
    assert power.on_ac is True
    (bat,) = power.batteries
    assert bat.name == "BAT0"
    # cycle_count = 0 côté firmware signifie « pas de compteur »
    assert (bat.percent, bat.status, bat.cycle_count) == (79, "Not charging", None)
    # charge_* (µAh) × voltage_min_design (µV)
    assert bat.design_capacity_wh == pytest.approx(59.28)
    assert bat.health_percent == pytest.approx(100.0)


def test_energy_based_battery_on_battery_power(fake_system) -> None:
    fake_system(
        files={
            "/sys/class/power_supply/BAT1/type": "Battery",
            "/sys/class/power_supply/BAT1/status": "Discharging",
            "/sys/class/power_supply/BAT1/capacity": "42",
            "/sys/class/power_supply/BAT1/energy_full": "45000000",
            "/sys/class/power_supply/BAT1/energy_full_design": "50000000",
            "/sys/class/power_supply/ADP1/type": "Mains",
            "/sys/class/power_supply/ADP1/online": "0",
        }
    )
    power = LinuxPowerCollector().collect().data
    assert power.on_ac is False
    (bat,) = power.batteries
    assert (bat.full_capacity_wh, bat.design_capacity_wh) == (45.0, 50.0)
    assert bat.health_percent == pytest.approx(90.0)
    assert bat.cycle_count is None


def test_peripheral_battery_is_ignored(fake_system) -> None:
    fake_system(
        files={
            "/sys/class/power_supply/hidpp_battery_0/type": "Battery",
            "/sys/class/power_supply/hidpp_battery_0/scope": "Device",
            "/sys/class/power_supply/hidpp_battery_0/capacity": "55",
        }
    )
    power = LinuxPowerCollector().collect().data
    assert power.batteries == []
    # batterie de souris seulement (cas du desktop B850) : pas de batterie système -> secteur
    assert power.on_ac is True


def test_labelled_fan(fake_system) -> None:
    fake_system(
        files={
            "/sys/class/hwmon/hwmon5/name": "dell_smm",
            "/sys/class/hwmon/hwmon5/fan1_input": "1628",
            "/sys/class/hwmon/hwmon5/fan1_label": "Processor Fan",
        }
    )
    fans = LinuxSensorsCollector().collect().data.fans
    assert [(f.label, f.rpm) for f in fans] == [("Processor Fan", 1628)]


def test_desktop_without_power_supply(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"))
    power = LinuxPowerCollector().collect().data
    assert power.on_ac is True
    assert power.batteries == []


PROFILE = "/sys/firmware/acpi/platform_profile"


def test_platform_profile(fake_system) -> None:
    fake_system(
        files={PROFILE: "balanced\n", f"{PROFILE}_choices": "low-power balanced performance\n"}
    )
    power = LinuxPowerCollector().collect().data
    assert power.platform_profile == "balanced"
    assert power.platform_profile_choices == ["low-power", "balanced", "performance"]


def test_no_platform_profile(laptop) -> None:
    laptop()
    power = LinuxPowerCollector().collect().data
    assert power.platform_profile is None and power.platform_profile_choices == []


def _hwmon(n: int, name: str, device: str, temp_mc: int, label: str | None = None) -> dict:
    base = f"/sys/class/hwmon/hwmon{n}"
    files = {
        f"{base}/name": name,
        f"{base}/device@link": device,
        f"{base}/temp1_input": str(temp_mc),
    }
    if label:
        files[f"{base}/temp1_label"] = label
    return files


# Disposition du desktop B850 : hwmon0 -> nvme1, hwmon1 -> nvme0, deux spd5118 sur i2c-2
B850_HWMON = (
    _hwmon(0, "nvme", "nvme1", 41850, "Composite")
    | _hwmon(1, "nvme", "nvme0", 38850, "Composite")
    | _hwmon(2, "k10temp", "0000:00:18.3", 45125, "Tctl")
    | _hwmon(5, "spd5118", "2-0051", 36500)
    | _hwmon(6, "spd5118", "2-0053", 37250)
)


def test_same_named_chips_are_disambiguated(fake_system) -> None:
    fake_system(files=B850_HWMON)
    temps = LinuxSensorsCollector().collect().data.temperatures
    by_source = {t.source: t for t in temps}
    assert set(by_source) == {"nvme0", "nvme1", "k10temp", "spd5118 #1", "spd5118 #2"}
    assert by_source["nvme0"].current_c == 38.85  # hwmon1, pas hwmon0
    assert by_source["spd5118 #1"].current_c == 36.5  # 2-0051 avant 2-0053
    assert by_source["k10temp"].instance is None
    # le nom brut reste celui de la puce : machine_state trouve toujours le CPU
    assert {t.chip for t in temps} == {"nvme", "k10temp", "spd5118"}


def test_cpu_temperature_still_found_with_duplicates(fake_system) -> None:
    fake_system(files=B850_HWMON)
    assert cpu_temperature(LinuxSensorsCollector().collect().data) == 45.125


def test_duplicates_without_device_link_use_index(fake_system) -> None:
    files = {k: v for k, v in B850_HWMON.items() if not k.endswith("@link")}
    fake_system(files=files)
    sources = sorted(t.source for t in LinuxSensorsCollector().collect().data.temperatures)
    assert sources == ["k10temp", "nvme #1", "nvme #2", "spd5118 #1", "spd5118 #2"]
