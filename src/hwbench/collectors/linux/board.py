from datetime import datetime

from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import BoardData, BoardIdentifiers, IdentifierValue, Unavailable

DMI_DIR = "/sys/class/dmi/id"

_PLACEHOLDERS = {
    "",
    "default string",
    "to be filled by o.e.m.",
    "not specified",
    "not applicable",
    "system product name",
    "system manufacturer",
    "system version",
    "none",
    "0",
}


def _clean(value: str | None) -> str | None:
    if value is None or value.strip().lower() in _PLACEHOLDERS:
        return None
    return value.strip()


def _dmi(name: str) -> str | None:
    return _clean(_exec.read_sysfs(f"{DMI_DIR}/{name}"))


def _identifier(path: str) -> IdentifierValue:
    """Valeur, None si vide ou bidon, ou la raison pour laquelle le fichier est illisible."""
    value = _exec.read_sysfs(path)
    if value is not None:
        return _clean(value)
    if _exec.exists(path) and not _exec.is_root():
        return Unavailable.NEEDS_ROOT
    return Unavailable.NO_DATA


def parse_dmi_date(value: str | None) -> str | None:
    """DMI (SMBIOS) impose MM/DD/YYYY ; les très vieux BIOS écrivent MM/DD/YY."""
    if value is None:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


@register("Linux")
class LinuxBoardCollector(Collector[BoardData, BoardIdentifiers]):
    component = "board"

    def collect(
        self, include_identifiers: bool = False
    ) -> ComponentResult[BoardData, BoardIdentifiers]:
        data = BoardData(
            system_vendor=_dmi("sys_vendor"),
            product_name=_dmi("product_name"),
            product_version=_dmi("product_version"),
            board_vendor=_dmi("board_vendor"),
            board_name=_dmi("board_name"),
            bios_vendor=_dmi("bios_vendor"),
            bios_version=_dmi("bios_version"),
            bios_date=parse_dmi_date(_dmi("bios_date")),
        )
        if not include_identifiers:
            return ComponentResult(data)
        ids = BoardIdentifiers(
            hostname=_identifier("/proc/sys/kernel/hostname"),
            **{
                name: _identifier(f"{DMI_DIR}/{name}")
                for name in (
                    "product_uuid",
                    "product_serial",
                    "board_serial",
                    "chassis_serial",
                    "board_asset_tag",
                    "chassis_asset_tag",
                )
            },
        )
        return ComponentResult(data, ids)
