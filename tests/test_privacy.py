import dataclasses
import json
import typing
from dataclasses import asdict

from hwbench import privacy
from hwbench.collect import collect_snapshot
from hwbench.models import MachineSnapshot

FAKE_IDENTIFIER_VALUES = (
    "FAKE-SYS-SERIAL",
    "FAKE-BOARD-SERIAL",
    "FAKE-CHASSIS-SERIAL",
    "FAKE-ASSET-TAG",
    "FAKE0001",
    "FAKE0002",
    "FAKE-NVME-SERIAL-0001",
    "fake-host",
    "00000000-0000-0000-0000-000000000000",
)


def _dataclass_field_names(cls: type, seen: set[type] | None = None) -> set[str]:
    seen = seen or set()
    if cls in seen:
        return set()
    seen.add(cls)
    names: set[str] = set()
    for f in dataclasses.fields(cls):
        names.add(f.name)
        hints = typing.get_type_hints(cls)[f.name]
        for arg in (
            hints,
            *typing.get_args(hints),
            *sum(map(typing.get_args, typing.get_args(hints)), ()),
        ):
            if dataclasses.is_dataclass(arg):
                names |= _dataclass_field_names(arg, seen)
    return names


def test_machine_snapshot_has_no_identifier_fields() -> None:
    names = _dataclass_field_names(MachineSnapshot)
    assert "serial" not in " ".join(names)
    assert not [n for n in names if privacy.is_sensitive_key(n)]


def test_snapshot_never_contains_identifiers_even_when_collected(laptop) -> None:
    laptop(root=True)
    snapshot, identifiers = collect_snapshot(include_identifiers=True, os_name="Linux")
    dumped = json.dumps(asdict(snapshot))
    for value in FAKE_IDENTIFIER_VALUES:
        assert value not in dumped
    assert identifiers is not None
    assert identifiers.board is not None and identifiers.board.product_serial == "FAKE-SYS-SERIAL"
    assert identifiers.disks and identifiers.disks[0].serial == "FAKE-NVME-SERIAL-0001"
    assert identifiers.ram_modules and identifiers.ram_modules[0].serial == "FAKE0001"


def test_no_identifiers_collected_by_default(laptop) -> None:
    laptop(root=True)
    _, identifiers = collect_snapshot(os_name="Linux")
    assert identifiers is None


def test_scrub_sensitive_keys() -> None:
    data = {
        "model": "Samsung SSD",
        "serial_number": "S6Z2NF0W123456",
        "nested": [{"product_uuid": "abc", "hostname": "box", "mac_address": "x"}],
        "asset_tag": None,
    }
    out = privacy.scrub(data)
    assert out["model"] == "Samsung SSD"
    assert out["serial_number"] == privacy.REDACTED
    assert out["nested"][0] == {
        "product_uuid": privacy.REDACTED,
        "hostname": privacy.REDACTED,
        "mac_address": privacy.REDACTED,
    }
    assert out["asset_tag"] is None


def test_scrub_sensitive_values_under_innocent_keys() -> None:
    out = privacy.scrub(
        {
            "note": "iface 3c:52:82:aa:bb:cc up",
            "id": "4c4c4544-0042-3510-8052-b4c04f4e4d33",
            "raw": "eui.0025385b21b0a1c2",
            "nguid_like": "0025385b21b0a1c20025385b21b0a1c2",
        }
    )
    assert out["note"] == f"iface {privacy.REDACTED} up"
    assert out["id"] == privacy.REDACTED
    assert out["raw"] == privacy.REDACTED
    assert out["nguid_like"] == privacy.REDACTED


def test_scrub_keeps_ordinary_hardware_strings() -> None:
    values = {
        "model": "11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz",
        "gpu": "TigerLake-LP GT2 [Iris Xe Graphics]",
        "bios_date": "06/30/2026",
        "size": 1000204886016,
        "opengl": "4.6 (Compatibility Profile) Mesa 26.2.2",
    }
    assert privacy.scrub(values) == values
