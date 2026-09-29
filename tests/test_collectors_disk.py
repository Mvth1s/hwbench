import json

from conftest import LSBLK_ARGS, fixture_text, laptop_commands

from hwbench.collectors.linux.disk import (
    LinuxDiskCollector,
    parse_lsblk,
    parse_smart_health,
    parse_smart_identifiers,
    smartctl_supports_json,
)
from hwbench.models import Unavailable


def test_lsblk_modern_skips_zram_and_partitions() -> None:
    disks = parse_lsblk(json.loads(fixture_text("dell-inc-latitude-5420/lsblk.json")))
    assert [d.name for d in disks] == ["nvme0n1"]
    d = disks[0]
    assert d.size_bytes == 1000204886016
    assert d.model == "Samsung SSD 990 EVO Plus 1TB"
    assert (d.rotational, d.transport) == (False, "nvme")


def test_lsblk_legacy_string_values() -> None:
    disks = parse_lsblk(json.loads(fixture_text("lsblk_legacy.json")))
    assert [d.name for d in disks] == ["sda"]
    assert disks[0].size_bytes == 1000204886016
    assert disks[0].rotational is True


def test_smartctl_json_support_detection() -> None:
    assert smartctl_supports_json("smartctl 7.5 2025-04-30 r5714")
    assert not smartctl_supports_json("smartctl 6.6 2017-11-05 r4594")
    assert not smartctl_supports_json("garbage")


def test_smart_health() -> None:
    assert parse_smart_health(
        json.loads(fixture_text("dell-inc-latitude-5420/smartctl_nvme0n1.json"))
    ) == (True, 38.0)
    assert parse_smart_health(json.loads(fixture_text("smartctl_sata_failed.json"))) == (
        False,
        44.0,
    )
    assert parse_smart_health({}) == (None, None)


def test_smart_identifiers_nvme_and_sata() -> None:
    nvme = parse_smart_identifiers(
        "nvme0n1", json.loads(fixture_text("dell-inc-latitude-5420/smartctl_nvme0n1.json"))
    )
    assert nvme.serial == "FAKE-0005"
    assert nvme.eui64 == "002538 0000000000"
    assert nvme.nguid is None
    assert nvme.wwn is None
    sata = parse_smart_identifiers("sda", json.loads(fixture_text("smartctl_sata_failed.json")))
    assert sata.wwn == "5 0014ee 000000000"
    assert sata.eui64 is None


def test_collect_as_root_adds_health(laptop) -> None:
    laptop(root=True)
    result = LinuxDiskCollector().collect()
    assert result.identifiers is None
    (disk,) = result.data.disks
    assert (disk.smart_passed, disk.temperature_c) == (True, 38.0)
    assert result.data.smart_unavailable is None


def test_collect_identifiers_when_requested(laptop) -> None:
    laptop(root=True)
    result = LinuxDiskCollector().collect(include_identifiers=True)
    assert result.identifiers is not None
    assert [i.serial for i in result.identifiers] == ["FAKE-0005"]


def test_collect_without_root_skips_smartctl(laptop) -> None:
    system = laptop(root=False)
    data = LinuxDiskCollector().collect(include_identifiers=True).data
    assert data.smart_unavailable is Unavailable.NEEDS_ROOT
    assert data.disks[0].smart_passed is None
    assert not any(cmd[0] == "smartctl" for cmd in system.commands_run)


def test_collect_with_old_smartctl(fake_system) -> None:
    commands = laptop_commands() | {("smartctl", "--version"): "smartctl 6.6 2017-11-05 r4594"}
    fake_system(commands=commands, root=True)
    data = LinuxDiskCollector().collect().data
    assert data.smart_unavailable is Unavailable.NO_DATA


def test_collect_without_smartctl(fake_system) -> None:
    fake_system(commands={LSBLK_ARGS: fixture_text("dell-inc-latitude-5420/lsblk.json")}, root=True)
    data = LinuxDiskCollector().collect().data
    assert data.smart_unavailable is Unavailable.TOOL_MISSING
    assert len(data.disks) == 1
