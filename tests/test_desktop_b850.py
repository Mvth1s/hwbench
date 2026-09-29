"""Desktop B850 capturé (scripts/capture_fixtures.sh, sans root) : cas propres aux desktops."""

import re

import pytest
from conftest import FIXTURES, captured_commands, fixture_text, sysfs_fixture
from typer.testing import CliRunner

from hwbench import cli
from hwbench.collect import collect_snapshot
from hwbench.collectors.linux.gpu import parse_nvidia_smi_csv
from hwbench.machine_state import capture_state
from hwbench.reference import state_issues

DESKTOP = "asrock-b850-riptide-wifi"


@pytest.fixture
def b850(fake_system):
    def install(root: bool = False):
        return fake_system(
            files=sysfs_fixture(f"{DESKTOP}/sysfs.json"),
            commands=captured_commands(FIXTURES / DESKTOP),
            root=root,
        )

    install()
    return install


def test_desktop_without_battery_is_on_ac(b850) -> None:
    snapshot, _ = collect_snapshot(os_name="Linux")
    # seule « batterie » : la souris (hidpp, scope=Device), en décharge
    assert snapshot.power.batteries == []
    assert snapshot.power.on_ac is True
    state = capture_state()
    assert (state.on_ac, state.has_battery) == (True, False)
    assert state_issues(state) == []  # secteur + EPP performance : référence possible


def test_desktop_sensors_are_disambiguated(b850) -> None:
    snapshot, _ = collect_snapshot(os_name="Linux")
    sources = {t.source for t in snapshot.sensors.temperatures}
    assert {"nvme0", "nvme1", "spd5118 #1", "spd5118 #2", "k10temp", "amdgpu"} <= sources
    # hwmon0 pointe vers nvme1 : l'ordre des dossiers hwmon ne fait pas le nom
    hwmon_nvme = [t for t in snapshot.sensors.temperatures if t.chip == "nvme"]
    assert {t.instance for t in hwmon_nvme} == {"nvme0", "nvme1"}
    pairs = [(t.source, t.label) for t in snapshot.sensors.temperatures]
    assert len(pairs) == len(set(pairs))
    assert capture_state().cpu_temp_c is not None  # k10temp Tctl


def test_desktop_cpu_driver_and_epp(b850) -> None:
    snapshot, _ = collect_snapshot(os_name="Linux")
    assert snapshot.cpu.scaling_driver == "amd-pstate-epp"
    assert snapshot.cpu.energy_performance_preference == "performance"
    assert snapshot.power.platform_profile is None


def test_nvidia_smi_without_driver_is_ignored(b850) -> None:
    # nvidia-smi installé sans pilote NVIDIA : message d'erreur sur stdout, code non nul
    assert "NVIDIA-SMI has failed" in fixture_text(f"{DESKTOP}/nvidia_smi.csv")
    assert parse_nvidia_smi_csv(fixture_text(f"{DESKTOP}/nvidia_smi.csv")) == {}
    snapshot, _ = collect_snapshot(os_name="Linux")
    assert snapshot.gpu.nvidia_name is None
    assert snapshot.gpu.vulkan_device_name == "AMD Radeon RX 9070 XT (RADV GFX1201)"


def test_desktop_ram_and_smart_as_root(b850) -> None:
    b850(root=True)
    snapshot, _ = collect_snapshot(os_name="Linux")
    modules = snapshot.ram.modules
    assert modules is not None
    assert [m.slot for m in modules] == ["P0 CHANNEL A / DIMM 1", "P0 CHANNEL B / DIMM 1"]
    assert snapshot.ram.installed_gb == 32.0
    assert snapshot.ram.total_gb is not None and snapshot.ram.total_gb <= 32.0
    disks = {d.name: d for d in snapshot.disks.disks}
    assert set(disks) == {"nvme0n1", "nvme1n1"}
    assert all(d.smart_passed is True for d in disks.values())


def test_desktop_info_display_as_root(b850) -> None:
    b850(root=True)
    result = CliRunner().invoke(cli.app, ["info"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    out = result.output
    assert re.search(
        r"P0 CHANNEL A / DIMM 1 +16 Gio +DDR5 +6000 MT/s \(profil EXPO/XMP, nominal 4800\)", out
    )
    assert "P0 CHANNEL B / DIMM 1" in out and "Corsair" in out
    assert "secteur (pas de batterie)" in out
    assert "nvme0" in out and "spd5118 #2" in out
