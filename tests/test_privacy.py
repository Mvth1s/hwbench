import dataclasses
import hashlib
import json
import typing
from dataclasses import asdict

import pytest
from conftest import make_result
from test_scoring import REFERENCE, snapshot

from hwbench import privacy
from hwbench.collect import collect_snapshot
from hwbench.export import build_export, load_export, to_dict, write_export
from hwbench.models import MachineSnapshot
from hwbench.scoring import score_results

FAKE_IDENTIFIER_VALUES = (
    "FAKE-SYS-SERIAL",
    "FAKE-BOARD-SERIAL",
    "FAKE-CHASSIS-SERIAL",
    "FAKE-0001",
    "FAKE-0002",
    "FAKE-0003",
    "FAKE-0004",
    "FAKE-0005",
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
    assert identifiers.disks and identifiers.disks[0].serial == "FAKE-0005"
    assert identifiers.ram_modules and identifiers.ram_modules[0].serial == "FAKE-0001"


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


SHA256 = "sha256:" + hashlib.sha256(b"reference").hexdigest()


def test_digest_key_is_allowed() -> None:
    assert len(SHA256) == 7 + 64
    assert privacy.scrub({"digest": SHA256}) == {"digest": SHA256}
    nested = {"reference": {"machine": "ASRock B850 Riptide WiFi", "digest": SHA256}}
    assert privacy.scrub(nested) == nested


def test_same_hash_under_a_sensitive_key_is_redacted() -> None:
    assert privacy.scrub({"serial": SHA256}) == {"serial": privacy.REDACTED}
    assert privacy.scrub({"board_serial": SHA256[7:]}) == {"board_serial": privacy.REDACTED}


@pytest.mark.parametrize(
    "value",
    [
        "aa:bb:cc:dd:ee:ff",  # adresse MAC
        "123e4567-e89b-12d3-a456-426614174000",  # UUID
        "sha256:" + "a" * 32,  # pas un sha256 complet : 32 hex = motif NGUID
        SHA256 + " 0123456789abcdef",  # sha256 suivi d'autre chose
    ],
)
def test_allowed_key_with_unexpected_value_is_still_scrubbed(value: str) -> None:
    """L'allowlist porte sur la clé ET le format : « digest » n'est pas une porte ouverte."""
    scrubbed = privacy.scrub({"digest": value})["digest"]
    assert scrubbed != value
    assert privacy.REDACTED in scrubbed


def test_export_keeps_the_full_reference_digest(tmp_path) -> None:
    results = [make_result("native-cpu-single", 100.0)]
    export = build_export(snapshot(), "x", results, score_results(results, REFERENCE))
    assert to_dict(export)["reference"]["digest"] == REFERENCE.digest
    path = tmp_path / "e.json"
    write_export(export, path)
    loaded = load_export(path)
    assert loaded.reference is not None and loaded.reference.digest == REFERENCE.digest
    assert len(REFERENCE.digest) == len("sha256:") + 64
