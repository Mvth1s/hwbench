from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import BoardData, BoardIdentifiers

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


def _dmi(name: str) -> str | None:
    value = _exec.read_sysfs(f"{DMI_DIR}/{name}")
    if value is None or value.strip().lower() in _PLACEHOLDERS:
        return None
    return value.strip()


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
            bios_date=_dmi("bios_date"),
        )
        if not include_identifiers:
            return ComponentResult(data)
        ids = BoardIdentifiers(
            hostname=_exec.read_sysfs("/proc/sys/kernel/hostname"),
            product_uuid=_dmi("product_uuid"),
            product_serial=_dmi("product_serial"),
            board_serial=_dmi("board_serial"),
            chassis_serial=_dmi("chassis_serial"),
            board_asset_tag=_dmi("board_asset_tag"),
            chassis_asset_tag=_dmi("chassis_asset_tag"),
        )
        return ComponentResult(data, ids)
