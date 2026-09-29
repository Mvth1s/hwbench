from hwbench.collectors import get_collector
from hwbench.models import Identifiers, MachineSnapshot


def collect_snapshot(
    include_identifiers: bool = False, os_name: str | None = None
) -> tuple[MachineSnapshot, Identifiers | None]:
    results = {
        name: get_collector(name, os_name).collect(include_identifiers)
        for name in ("cpu", "ram", "gpu", "disk", "board", "sensors", "power")
    }
    snapshot = MachineSnapshot(
        cpu=results["cpu"].data,
        ram=results["ram"].data,
        gpu=results["gpu"].data,
        disks=results["disk"].data,
        board=results["board"].data,
        sensors=results["sensors"].data,
        power=results["power"].data,
    )
    if not include_identifiers:
        return snapshot, None
    identifiers = Identifiers(
        board=results["board"].identifiers,
        ram_modules=results["ram"].identifiers,
        disks=results["disk"].identifiers,
    )
    return snapshot, identifiers
