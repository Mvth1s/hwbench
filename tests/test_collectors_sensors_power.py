import pytest
from conftest import sysfs_fixture

from hwbench.collectors.linux.power import LinuxPowerCollector
from hwbench.collectors.linux.sensors import LinuxSensorsCollector


def test_hwmon_temperatures_and_fans(laptop) -> None:
    laptop()
    data = LinuxSensorsCollector().collect().data
    by_label = {(t.chip, t.label): t for t in data.temperatures}
    composite = by_label[("nvme", "Composite")]
    assert (composite.current_c, composite.high_c, composite.critical_c) == (37.85, 81.85, 84.85)
    assert by_label[("coretemp", "Package id 0")].current_c == 64.0
    assert by_label[("dell_smm", "temp1")].current_c == 61.0
    assert [(f.chip, f.label, f.rpm) for f in data.fans] == [("dell_smm", "Processor Fan", 1628)]


def test_hwmon_sentinel_threshold_is_dropped(laptop) -> None:
    laptop()
    data = LinuxSensorsCollector().collect().data
    sensor1 = next(t for t in data.temperatures if t.label == "Sensor 1")
    assert sensor1.current_c == 45.85
    assert sensor1.high_c is None


def test_no_hwmon(fake_system) -> None:
    fake_system(files={})
    data = LinuxSensorsCollector().collect().data
    assert data.temperatures == [] and data.fans == []


def test_laptop_battery_and_ac(laptop) -> None:
    laptop()
    power = LinuxPowerCollector().collect().data
    assert power.on_ac is True
    # la batterie de souris (scope=Device) est ignorée
    (bat,) = power.batteries
    assert bat.name == "BAT0"
    assert (bat.percent, bat.status, bat.cycle_count) == (79, "Not charging", 0)
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


def test_desktop_without_power_supply(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"))
    power = LinuxPowerCollector().collect().data
    assert power.on_ac is None
    assert power.batteries == []
