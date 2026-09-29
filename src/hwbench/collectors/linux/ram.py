import re

import psutil

from hwbench.collectors import jedec
from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import RamData, RamModule, RamModuleIdentifiers, Unavailable

_EMPTY_VALUES = {"", "unknown", "not specified", "not provided", "none", "no module installed"}
# dmidecode < 3.7 écrit « GB », >= 3.7 « GiB » ; dans les deux cas ce sont des puissances de 1024
_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKMGT])i?B$")
_SIZE_TO_GB = {"k": 1 / (1024 * 1024), "K": 1 / (1024 * 1024), "M": 1 / 1024, "G": 1.0, "T": 1024.0}
_SPEED_RE = re.compile(r"^(\d+)\s*(MT/s|MHz)$")


def _clean(value: str | None) -> str | None:
    if value is None or value.strip().lower() in _EMPTY_VALUES:
        return None
    return value.strip()


def parse_meminfo_total_gb(text: str) -> float | None:
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) / (1024 * 1024)
    return None


def _parse_size_gb(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    match = _SIZE_RE.match(value)
    if not match:
        return None
    return float(match.group(1)) * _SIZE_TO_GB[match.group(2)]


def _parse_speed(value: str | None) -> int | None:
    value = _clean(value)
    if value is None:
        return None
    match = _SPEED_RE.match(value)
    return int(match.group(1)) if match else None


def parse_dmidecode_memory(text: str) -> list[dict[str, str]]:
    """Blocs « Memory Device » (DMI type 17) peuplés, sous forme clé -> valeur brute."""
    devices: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.splitlines() if line.strip()]
        if not any(line.strip() == "Memory Device" for line in lines[:2]):
            continue
        fields: dict[str, str] = {}
        for line in lines:
            if not line.startswith(("\t", " ")):
                continue
            key, sep, value = line.strip().partition(":")
            if sep and value.strip():
                fields.setdefault(key.strip(), value.strip())
        if _parse_size_gb(fields.get("Size")) is None:
            continue
        devices.append(fields)
    return devices


def slot_labels(blocks: list[dict[str, str]]) -> list[str | None]:
    """Locator seul s'il est unique ; sinon « Bank Locator / Locator ».

    Sur AM5 par exemple, les deux barrettes sont « DIMM 1 », sur « P0 CHANNEL A » et « B ».
    """
    locators = [_clean(b.get("Locator")) for b in blocks]
    labels: list[str | None] = []
    for block, locator in zip(blocks, locators, strict=True):
        bank = _clean(block.get("Bank Locator"))
        if locator is None or (locators.count(locator) > 1 and bank):
            labels.append(" / ".join(p for p in (bank, locator) if p) or None)
        else:
            labels.append(locator)
    return labels


def module_from_fields(fields: dict[str, str], slot: str | None = None) -> RamModule:
    # SMBIOS : « Speed » = vitesse nominale (JEDEC) ; « Configured Memory Speed » = appliquée,
    # supérieure à la nominale avec un profil EXPO/XMP.
    rated = _parse_speed(fields.get("Speed"))
    configured = _parse_speed(fields.get("Configured Memory Speed")) or rated
    return RamModule(
        slot=slot if slot is not None else _clean(fields.get("Locator")),
        size_gb=_parse_size_gb(fields.get("Size")),
        type=_clean(fields.get("Type")),
        speed_mts=configured,
        rated_speed_mts=rated,
        manufacturer=jedec.manufacturer_name(
            _clean(fields.get("Module Manufacturer ID")), _clean(fields.get("Manufacturer"))
        ),
        part_number=_clean(fields.get("Part Number")),
    )


def identifiers_from_fields(
    fields: dict[str, str], slot: str | None = None
) -> RamModuleIdentifiers:
    return RamModuleIdentifiers(
        slot=slot if slot is not None else _clean(fields.get("Locator")),
        serial=_clean(fields.get("Serial Number")),
        asset_tag=_clean(fields.get("Asset Tag")),
    )


def _total_gb() -> float | None:
    text = _exec.read_sysfs("/proc/meminfo")
    total = parse_meminfo_total_gb(text) if text else None
    if total is None:
        try:
            total = psutil.virtual_memory().total / (1024**3)
        except Exception:
            return None
    return total


@register("Linux")
class LinuxRamCollector(Collector[RamData, list[RamModuleIdentifiers]]):
    component = "ram"

    def collect(
        self, include_identifiers: bool = False
    ) -> ComponentResult[RamData, list[RamModuleIdentifiers]]:
        total = _total_gb()
        if _exec.which("dmidecode") is None:
            return ComponentResult(
                RamData(total_gb=total, modules_unavailable=Unavailable.TOOL_MISSING)
            )
        if not _exec.is_root():
            return ComponentResult(
                RamData(total_gb=total, modules_unavailable=Unavailable.NEEDS_ROOT)
            )
        text = _exec.run_text(["dmidecode", "-t", "memory"])
        if text is None:
            return ComponentResult(RamData(total_gb=total, modules_unavailable=Unavailable.NO_DATA))

        blocks = parse_dmidecode_memory(text)
        slots = slot_labels(blocks)
        modules = [module_from_fields(b, s) for b, s in zip(blocks, slots, strict=True)]
        sizes = [m.size_gb for m in modules]
        installed = sum(s for s in sizes if s is not None) if sizes and None not in sizes else None
        data = RamData(total_gb=total, installed_gb=installed, modules=modules)
        ids = (
            [identifiers_from_fields(b, s) for b, s in zip(blocks, slots, strict=True)]
            if include_identifiers
            else None
        )
        return ComponentResult(data, ids)
