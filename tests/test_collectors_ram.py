import pytest
from conftest import LAPTOP, fixture_text, laptop_commands, laptop_sysfs

from hwbench.collectors.linux.ram import (
    LinuxRamCollector,
    _parse_size_gb,
    parse_dmidecode_memory,
    parse_meminfo_total_gb,
    slot_labels,
)
from hwbench.models import Unavailable


def test_parse_dmidecode_skips_empty_slots_and_non_memory_devices() -> None:
    blocks = parse_dmidecode_memory(fixture_text("dmidecode_memory_v36.txt"))
    assert [b["Locator"] for b in blocks] == ["DIMM A", "DIMM B"]


def test_parse_meminfo() -> None:
    assert parse_meminfo_total_gb("MemTotal:       16777216 kB\n") == pytest.approx(16.0)
    assert parse_meminfo_total_gb("garbage") is None


def test_modules_as_root(laptop) -> None:
    laptop(root=True)
    result = LinuxRamCollector().collect()
    ram = result.data
    assert ram.total_gb == pytest.approx(15.34, abs=0.01)
    assert ram.modules_unavailable is None
    assert ram.modules is not None and len(ram.modules) == 2
    b, a = ram.modules  # dmidecode liste DIMM B avant DIMM A sur cette machine
    assert (b.slot, b.size_gb, b.type) == ("DIMM B", 8.0, "DDR4")
    assert (b.speed_mts, b.rated_speed_mts) == (2667, 2667)
    assert (b.manufacturer, b.part_number) == ("Kingston", "HP26D4S9S8ME-8")
    # vitesse configurée prioritaire, vitesse nominale conservée à part
    assert (a.slot, a.speed_mts, a.rated_speed_mts) == ("DIMM A", 2667, 3200)
    assert (a.manufacturer, a.part_number) == ("SK Hynix", "HMAA1GS6CJR6N-XN")
    assert ram.installed_gb == 16.0
    assert result.identifiers is None


def test_legacy_dmidecode_decodes_raw_jedec_code(fake_system) -> None:
    fake_system(
        commands={("dmidecode", "-t", "memory"): fixture_text("dmidecode_memory_v36.txt")},
        root=True,
    )
    modules = LinuxRamCollector().collect().data.modules
    assert modules is not None
    assert [m.manufacturer for m in modules] == ["SK Hynix", "SK Hynix"]


DMIDECODE_37_GIB = """# dmidecode 3.7
Handle 0x1000, DMI type 16, 23 bytes
Physical Memory Array
\tMaximum Capacity: 256 GiB

Handle 0x1100, DMI type 17, 92 bytes
Memory Device
\tSize: 8 GiB
\tLocator: DIMM A
\tType: DDR4
\tSpeed: 3200 MT/s
\tConfigured Memory Speed: 2667 MT/s

Handle 0x1101, DMI type 17, 92 bytes
Memory Device
\tSize: 8192 MiB
\tLocator: DIMM B
\tType: DDR4
\tSpeed: 2667 MT/s
\tConfigured Memory Speed: 2667 MT/s

Handle 0x1102, DMI type 17, 92 bytes
Memory Device
\tSize: 512 KiB
\tLocator: CACHE
"""


def test_dmidecode_37_binary_units(fake_system) -> None:
    fake_system(
        files={"/proc/meminfo": "MemTotal: 15988000 kB"},
        commands={("dmidecode", "-t", "memory"): DMIDECODE_37_GIB},
        root=True,
    )
    ram = LinuxRamCollector().collect().data
    assert ram.modules is not None
    a, b, cache = ram.modules
    assert (a.size_gb, a.speed_mts, a.rated_speed_mts) == (8.0, 2667, 3200)
    assert (b.size_gb, b.speed_mts, b.rated_speed_mts) == (8.0, 2667, 2667)
    assert cache.size_gb == pytest.approx(512 / 1024 / 1024)
    assert ram.installed_gb == pytest.approx(16.0 + 512 / 1024 / 1024)


@pytest.mark.parametrize(
    ("size", "expected_gb"),
    [("8 GB", 8.0), ("8 GiB", 8.0), ("8192 MB", 8.0), ("8192 MiB", 8.0), ("1 TiB", 1024.0)],
)
def test_size_units(size: str, expected_gb: float) -> None:
    text = f"Handle 0x1, DMI type 17\nMemory Device\n\tSize: {size}\n\tLocator: X\n"
    (block,) = parse_dmidecode_memory(text)
    assert _parse_size_gb(block["Size"]) == expected_gb


def test_empty_dmidecode_gives_empty_list(fake_system) -> None:
    fake_system(commands={("dmidecode", "-t", "memory"): "# dmidecode 3.7\n"}, root=True)
    ram = LinuxRamCollector().collect().data
    assert ram.modules == []
    assert ram.installed_gb is None


def test_identifiers_only_when_requested(laptop) -> None:
    laptop(root=True)
    result = LinuxRamCollector().collect(include_identifiers=True)
    assert result.identifiers is not None
    assert [(m.slot, m.serial, m.asset_tag) for m in result.identifiers] == [
        ("DIMM B", "FAKE-0001", "FAKE-0002"),
        ("DIMM A", "FAKE-0003", "FAKE-0004"),
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
    fake_system(files=laptop_sysfs(), commands=commands, root=True)
    ram = LinuxRamCollector().collect().data
    assert ram.modules_unavailable is Unavailable.TOOL_MISSING


# Capture réelle du desktop B850 (AM5) : deux barrettes « DIMM 1 » sur les canaux A et B, deux
# slots « DIMM 0 » vides, profil EXPO 6000 MT/s sur des modules nominaux 4800.
B850 = "asrock-b850-riptide-wifi"


def test_duplicate_locators_use_bank_locator() -> None:
    blocks = parse_dmidecode_memory(fixture_text(f"{B850}/dmidecode_memory.txt"))
    assert slot_labels(blocks) == ["P0 CHANNEL A / DIMM 1", "P0 CHANNEL B / DIMM 1"]


def test_unique_locators_stay_short() -> None:
    blocks = parse_dmidecode_memory(fixture_text(f"{LAPTOP}/dmidecode_memory.txt"))
    assert slot_labels(blocks) == ["DIMM B", "DIMM A"]


def test_expo_profile_speed(fake_system) -> None:
    text = fixture_text(f"{B850}/dmidecode_memory.txt")
    fake_system(commands={("dmidecode", "-t", "memory"): text}, root=True)
    result = LinuxRamCollector().collect(include_identifiers=True)
    modules = result.data.modules
    assert modules is not None
    assert [(m.slot, m.speed_mts, m.rated_speed_mts) for m in modules] == [
        ("P0 CHANNEL A / DIMM 1", 6000, 4800),
        ("P0 CHANNEL B / DIMM 1", 6000, 4800),
    ]
    assert {m.manufacturer for m in modules} == {"Corsair"}  # Bank 3, Hex 0x9E
    assert result.data.installed_gb == 32.0
    assert result.identifiers is not None
    assert [i.slot for i in result.identifiers] == [m.slot for m in modules]
