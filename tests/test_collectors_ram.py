import pytest
from conftest import fixture_text, laptop_commands, sysfs_fixture

from hwbench.collectors.linux.ram import (
    LinuxRamCollector,
    parse_dmidecode_memory,
    parse_meminfo_total_gb,
)
from hwbench.models import Unavailable


def test_parse_dmidecode_skips_empty_slots_and_non_memory_devices() -> None:
    blocks = parse_dmidecode_memory(fixture_text("dmidecode_memory.txt"))
    assert [b["Locator"] for b in blocks] == ["DIMM A", "DIMM B"]


def test_parse_meminfo() -> None:
    assert parse_meminfo_total_gb("MemTotal:       16777216 kB\n") == pytest.approx(16.0)
    assert parse_meminfo_total_gb("garbage") is None


def test_modules_as_root(laptop) -> None:
    laptop(root=True)
    result = LinuxRamCollector().collect()
    ram = result.data
    assert ram.total_gb == pytest.approx(15.27, abs=0.01)
    assert ram.modules_unavailable is None
    assert ram.modules is not None and len(ram.modules) == 2
    a, b = ram.modules
    assert (a.slot, a.size_gb, a.type, a.speed_mts) == ("DIMM A", 8.0, "DDR4", 3200)
    assert a.part_number == "HMA81GS6DJR8N-XN"
    # vitesse configurée prioritaire sur la vitesse nominale
    assert b.speed_mts == 2933
    assert result.identifiers is None


def test_identifiers_only_when_requested(laptop) -> None:
    laptop(root=True)
    result = LinuxRamCollector().collect(include_identifiers=True)
    assert result.identifiers is not None
    assert [(m.slot, m.serial, m.asset_tag) for m in result.identifiers] == [
        ("DIMM A", "FAKE0001", "FAKE-ASSET-0001"),
        ("DIMM B", "FAKE0002", None),
    ]


def test_without_root_does_not_run_dmidecode(laptop) -> None:
    system = laptop(root=False)
    ram = LinuxRamCollector().collect().data
    assert ram.modules is None
    assert ram.modules_unavailable is Unavailable.NEEDS_ROOT
    assert ram.total_gb is not None
    assert not any(cmd[0] == "dmidecode" for cmd in system.commands_run)


def test_without_dmidecode(fake_system) -> None:
    commands = {k: v for k, v in laptop_commands().items() if k[0] != "dmidecode"}
    fake_system(files=sysfs_fixture("sysfs_laptop.json"), commands=commands, root=True)
    ram = LinuxRamCollector().collect().data
    assert ram.modules_unavailable is Unavailable.TOOL_MISSING
