import pytest
from conftest import LAPTOP, fixture_text

from hwbench.collectors import jedec
from hwbench.collectors.linux.ram import module_from_fields, parse_dmidecode_memory


@pytest.mark.parametrize(
    ("module_id", "expected"),
    [
        ("Bank 1, Hex 0xCE", "Samsung"),
        ("Bank 1, Hex 0xAD", "SK Hynix"),
        ("Bank 1, Hex 0x2C", "Micron"),
        ("Bank 2, Hex 0x98", "Kingston"),
        ("Bank 3, Hex 0x9E", "Corsair"),
        ("Bank 4, Hex 0x0B", "Nanya"),
        ("Bank 5, Hex 0xCB", "ADATA"),
        ("Bank 5, Hex 0xCD", "G.Skill"),
        ("Bank 6, Hex 0x9B", "Crucial"),
        ("Bank 9, Hex 0x42", None),
        ("Unknown", None),
        (None, None),
    ],
)
def test_from_module_id(module_id: str | None, expected: str | None) -> None:
    assert jedec.from_module_id(module_id) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("80AD000080AD", "SK Hynix"),  # continuation 0 avec bit de parité -> banque 1
        ("01980000802C", "Kingston"),  # module Kingston, puces Micron (802C) ignorées
        ("80CE", "Samsung"),
        ("859B", "Crucial"),
        ("029E", "Corsair"),
        ("04CD", "G.Skill"),
        ("Samsung", None),
        ("", None),
    ],
)
def test_from_raw_code(raw: str, expected: str | None) -> None:
    assert jedec.from_raw_code(raw) == expected


def test_unknown_code_keeps_raw_value() -> None:
    assert jedec.manufacturer_name("Bank 9, Hex 0x42", "0842000000") == "0842000000"
    assert jedec.manufacturer_name(None, "Samsung") == "Samsung"
    assert jedec.manufacturer_name(None, None) is None


def test_real_capture_manufacturers() -> None:
    blocks = parse_dmidecode_memory(fixture_text(f"{LAPTOP}/dmidecode_memory.txt"))
    modules = {m.slot: m.manufacturer for m in map(module_from_fields, blocks)}
    assert modules == {"DIMM A": "SK Hynix", "DIMM B": "Kingston"}
