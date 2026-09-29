"""Le repo est public : aucune fixture ne doit contenir un identifiant réel."""

import json
import re
import socket
from pathlib import Path
from typing import Any

import pytest

from hwbench.privacy import SENSITIVE_KEY_RE

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_FILES = sorted(p for p in FIXTURES.rglob("*") if p.is_file())

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
EMPTY_VALUES = {
    "",
    "not specified",
    "unknown",
    "none",
    "not provided",
    "default string",
    "to be filled by o.e.m.",
}

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
# UUID sans tirets (ex. « Device UUID » de vkmark, UUID du GPU)
HEX_UUID_RE = re.compile(r"\b[0-9a-f]{32}\b", re.I)
MAC_RE = re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.I)
TEXT_IDENTIFIER_LINE_RE = re.compile(
    r"^\s*(serial number|asset tag|uuid|device uuid|\w*uuid|serial)\s*[:=]\s*(.*?)\s*$",
    re.I | re.M,
)


def is_fake(value: str) -> bool:
    v = value.strip()
    all_zero = bool(v) and set(v.replace("-", "")) == {"0"}
    return v.lower() in EMPTY_VALUES or "fake" in v.lower() or all_zero


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_no_real_uuid_or_mac(path: Path) -> None:
    text = path.read_text()
    assert set(UUID_RE.findall(text)) <= {ZERO_UUID}
    assert all(is_fake(u) for u in HEX_UUID_RE.findall(text))
    assert MAC_RE.findall(text) == []


@pytest.mark.parametrize(
    "path",
    [p for p in FIXTURE_FILES if p.suffix != ".json"],
    ids=lambda p: str(p.relative_to(FIXTURES)),
)
def test_text_identifier_lines_are_fake(path: Path) -> None:
    for match in TEXT_IDENTIFIER_LINE_RE.finditer(path.read_text()):
        assert is_fake(match.group(2)), f"{path.name}: {match.group(0).strip()!r}"


def _sensitive_leaves(obj: Any, sensitive: bool = False) -> list[tuple[bool, Any]]:
    if isinstance(obj, dict):
        leaves: list[tuple[bool, Any]] = []
        for k, v in obj.items():
            key_sensitive = sensitive or bool(SENSITIVE_KEY_RE.search(str(k)))
            if isinstance(v, dict) and key_sensitive:
                # wwn / eui64 : seule la partie « id » identifie l'unité (naa/oui = type/fabricant)
                leaves += [(True, v.get(part)) for part in ("id", "ext_id") if part in v]
            else:
                leaves += _sensitive_leaves(v, key_sensitive)
        return leaves
    if isinstance(obj, list):
        return [leaf for item in obj for leaf in _sensitive_leaves(item, sensitive)]
    return [(sensitive, obj)]


@pytest.mark.parametrize(
    "path",
    [p for p in FIXTURE_FILES if p.suffix == ".json"],
    ids=lambda p: str(p.relative_to(FIXTURES)),
)
def test_json_identifier_values_are_fake(path: Path) -> None:
    for sensitive, value in _sensitive_leaves(json.loads(path.read_text())):
        if not sensitive or value is None:
            continue
        if isinstance(value, int):
            assert value == 0, f"{path.name}: identifiant numérique non nul {value}"
        else:
            assert is_fake(str(value)), f"{path.name}: {value!r}"


def _live_identifiers() -> list[str]:
    found: list[str] = []
    hostname = socket.gethostname()
    if len(hostname) >= 4 and hostname not in {"localhost", "fedora"}:
        found.append(hostname)
    for name in ("product_uuid", "product_serial", "board_serial", "chassis_serial"):
        try:
            value = Path(f"/sys/class/dmi/id/{name}").read_text().strip()
        except OSError:
            continue
        if value and not is_fake(value):
            found.append(value)
    for addr in Path("/sys/class/net").glob("*/address"):
        try:
            mac = addr.read_text().strip()
        except OSError:
            continue
        if mac and mac != "00:00:00:00:00:00":
            found.append(mac)
    return found


def test_fixtures_do_not_contain_this_machine_identifiers() -> None:
    live = _live_identifiers()
    for path in FIXTURE_FILES:
        text = path.read_text().lower()
        for value in live:
            assert value.lower() not in text, (
                f"{path.name} contient un identifiant de cette machine"
            )
