import re
from dataclasses import replace
from typing import Any

from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import Disk, DiskData, DiskIdentifiers, Unavailable

_SMARTCTL_VERSION_RE = re.compile(r"smartctl\s+(\d+)\.(\d+)")
_SKIPPED_PREFIXES = ("zram", "loop", "ram")


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _to_bool(value: Any) -> bool | None:
    # lsblk récent émet des booléens JSON, les anciens des chaînes "0"/"1"
    if isinstance(value, bool):
        return value
    if value in ("0", "1"):
        return value == "1"
    return None


def _clean(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def parse_lsblk(payload: dict[str, Any]) -> list[Disk]:
    disks: list[Disk] = []
    for dev in payload.get("blockdevices", []):
        name = dev.get("name")
        if dev.get("type") != "disk" or not name or name.startswith(_SKIPPED_PREFIXES):
            continue
        disks.append(
            Disk(
                name=name,
                size_bytes=_to_int(dev.get("size")),
                model=_clean(dev.get("model")),
                type=dev.get("type"),
                rotational=_to_bool(dev.get("rota")),
                transport=_clean(dev.get("tran")),
            )
        )
    return disks


def smartctl_supports_json(version_text: str) -> bool:
    match = _SMARTCTL_VERSION_RE.search(version_text)
    return bool(match) and int(match.group(1)) >= 7


def parse_smart_health(payload: dict[str, Any]) -> tuple[bool | None, float | None]:
    status = payload.get("smart_status")
    passed = status.get("passed") if isinstance(status, dict) else None
    temp = payload.get("temperature")
    current = temp.get("current") if isinstance(temp, dict) else None
    return (
        passed if isinstance(passed, bool) else None,
        float(current) if isinstance(current, int | float) else None,
    )


def _format_wwn(wwn: Any) -> str | None:
    if not isinstance(wwn, dict):
        return None
    try:
        return f"{wwn['naa']:x} {wwn['oui']:06x} {wwn['id']:09x}"
    except (KeyError, TypeError, ValueError):
        return None


def _format_eui64(eui: Any) -> str | None:
    if not isinstance(eui, dict):
        return None
    try:
        return f"{eui['oui']:06x} {eui['ext_id']:010x}"
    except (KeyError, TypeError, ValueError):
        return None


def parse_smart_identifiers(name: str, payload: dict[str, Any]) -> DiskIdentifiers:
    namespaces = payload.get("nvme_namespaces") or []
    ns0 = namespaces[0] if namespaces and isinstance(namespaces[0], dict) else {}
    return DiskIdentifiers(
        name=name,
        serial=_clean(payload.get("serial_number")),
        wwn=_format_wwn(payload.get("wwn")),
        eui64=_format_eui64(ns0.get("eui64")),
        nguid=_clean(ns0.get("nguid")),
    )


@register("Linux")
class LinuxDiskCollector(Collector[DiskData, list[DiskIdentifiers]]):
    component = "disk"

    def collect(
        self, include_identifiers: bool = False
    ) -> ComponentResult[DiskData, list[DiskIdentifiers]]:
        payload = _exec.run_json(["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,ROTA,TRAN"])
        disks = parse_lsblk(payload) if isinstance(payload, dict) else []

        reason = self._smart_unavailable_reason()
        if reason is not None:
            return ComponentResult(DiskData(disks=disks, smart_unavailable=reason))

        enriched: list[Disk] = []
        ids: list[DiskIdentifiers] = []
        for disk in disks:
            smart = _exec.run_json(["smartctl", "-j", "-a", f"/dev/{disk.name}"])
            if not isinstance(smart, dict):
                enriched.append(disk)
                continue
            passed, temp = parse_smart_health(smart)
            enriched.append(replace(disk, smart_passed=passed, temperature_c=temp))
            if include_identifiers:
                ids.append(parse_smart_identifiers(disk.name, smart))
        return ComponentResult(DiskData(disks=enriched), ids if include_identifiers else None)

    @staticmethod
    def _smart_unavailable_reason() -> Unavailable | None:
        if _exec.which("smartctl") is None:
            return Unavailable.TOOL_MISSING
        if not _exec.is_root():
            return Unavailable.NEEDS_ROOT
        version = _exec.run_text(["smartctl", "--version"])
        if not version or not smartctl_supports_json(version):
            return Unavailable.NO_DATA
        return None
