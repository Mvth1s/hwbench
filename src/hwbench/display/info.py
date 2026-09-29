from collections.abc import Iterable
from statistics import mean

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hwbench.models import (
    BoardData,
    CpuData,
    DiskData,
    GpuData,
    Identifiers,
    MachineSnapshot,
    PowerData,
    RamData,
    SensorsData,
    Unavailable,
)

NA = Text("non disponible", style="dim")

UNAVAILABLE_MESSAGES = {
    Unavailable.NEEDS_ROOT: "relancer avec sudo",
    Unavailable.TOOL_MISSING: "outil absent",
    Unavailable.NO_DATA: "non disponible",
}

INSTALL_HINTS = {
    "dmidecode": "sudo dnf install dmidecode  |  sudo apt install dmidecode",
    "smartctl": "sudo dnf install smartmontools  |  sudo apt install smartmontools",
}


def _v(value: object, suffix: str = "", fmt: str = "{}") -> Text | str:
    if value is None or value == "":
        return NA
    return fmt.format(value) + suffix


def _unavailable(reason: Unavailable, tool: str) -> Text:
    msg = UNAVAILABLE_MESSAGES[reason]
    text = Text(msg, style="yellow")
    if reason is Unavailable.TOOL_MISSING and tool in INSTALL_HINTS:
        text.append(f"  ({INSTALL_HINTS[tool]})", style="dim")
    return text


def _kv_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    return table


def _size(size_bytes: int | None) -> Text | str:
    if size_bytes is None:
        return NA
    value = float(size_bytes)
    for unit in ("o", "Kio", "Mio", "Gio", "Tio"):
        if value < 1024 or unit == "Tio":
            return f"{value:.1f} {unit}" if unit != "o" else f"{int(value)} o"
        value /= 1024
    return NA


def _cache(kb: int | None) -> str | None:
    if kb is None:
        return None
    return f"{kb // 1024} Mio" if kb >= 1024 and kb % 1024 == 0 else f"{kb} Kio"


def render_cpu(cpu: CpuData) -> Panel:
    t = _kv_table()
    t.add_row("Modèle", _v(cpu.model))
    t.add_row("Fabricant", _v(cpu.vendor))
    t.add_row("Architecture", _v(cpu.architecture))
    t.add_row(
        "Cœurs / threads",
        _v(cpu.physical_cores)
        if cpu.logical_cores is None
        else f"{cpu.physical_cores or '?'} / {cpu.logical_cores}",
    )
    if cpu.min_mhz is not None or cpu.max_mhz is not None:
        t.add_row("Fréquence min / max", f"{_mhz(cpu.min_mhz)} / {_mhz(cpu.max_mhz)}")
    else:
        t.add_row("Fréquence min / max", NA)
    current = [c.current_mhz for c in cpu.per_cpu if c.current_mhz is not None]
    t.add_row(
        "Fréquence actuelle",
        f"moy. {mean(current):.0f} MHz (min {min(current):.0f}, max {max(current):.0f})"
        if current
        else NA,
    )
    governors = sorted({c.governor for c in cpu.per_cpu if c.governor})
    t.add_row("Governor", ", ".join(governors) if governors else NA)
    caches = [
        f"{name} {_cache(kb)}"
        for name, kb in (
            ("L1d", cpu.l1d_cache_kb),
            ("L1i", cpu.l1i_cache_kb),
            ("L2", cpu.l2_cache_kb),
            ("L3", cpu.l3_cache_kb),
        )
        if kb is not None
    ]
    t.add_row("Caches", " · ".join(caches) if caches else NA)
    return Panel(t, title="CPU", title_align="left")


def _mhz(value: float | None) -> str:
    return f"{value:.0f} MHz" if value is not None else "?"


def render_ram(ram: RamData) -> Panel:
    parts: list[Table | Text] = []
    t = _kv_table()
    t.add_row("Total", _v(ram.total_gb, " Gio", "{:.1f}"))
    parts.append(t)
    if ram.modules_unavailable is not None:
        t.add_row("Barrettes", _unavailable(ram.modules_unavailable, "dmidecode"))
    elif ram.modules:
        modules = Table(show_edge=False, box=None, header_style="bold")
        for col in ("Slot", "Taille", "Type", "Vitesse", "Fabricant", "Référence"):
            modules.add_column(col)
        for m in ram.modules:
            modules.add_row(
                _v(m.slot),
                _v(m.size_gb, " Gio", "{:g}"),
                _v(m.type),
                _v(m.speed_mts, " MT/s"),
                _v(m.manufacturer),
                _v(m.part_number),
            )
        parts.append(modules)
    return Panel(Group(*parts), title="Mémoire", title_align="left")


def render_gpu(gpu: GpuData) -> Panel:
    t = _kv_table()
    if not gpu.pci_devices:
        t.add_row("Périphérique PCI", NA)
    for i, dev in enumerate(gpu.pci_devices):
        label = "Périphérique PCI" if len(gpu.pci_devices) == 1 else f"Périphérique PCI #{i}"
        t.add_row(label, f"{dev.vendor or '?'} — {dev.model or '?'}")
    t.add_row("OpenGL renderer", _v(gpu.opengl_renderer))
    t.add_row("OpenGL version", _v(gpu.opengl_version))
    t.add_row("Vulkan", _v(gpu.vulkan_device_name))
    if gpu.nvidia_name:
        t.add_row("NVIDIA", gpu.nvidia_name)
        t.add_row("Pilote NVIDIA", _v(gpu.nvidia_driver_version))
        t.add_row("VRAM", _v(gpu.nvidia_vram_mb, " Mio"))
    return Panel(t, title="GPU", title_align="left")


def render_disks(data: DiskData) -> Panel:
    t = Table(show_edge=False, box=None, header_style="bold")
    for col in ("Nom", "Modèle", "Taille", "Type", "Bus", "SMART", "Temp."):
        t.add_column(col)
    for d in data.disks:
        if data.smart_unavailable is not None:
            smart: Text | str = _unavailable(data.smart_unavailable, "smartctl")
        elif d.smart_passed is None:
            smart = NA
        else:
            smart = Text("OK", style="green") if d.smart_passed else Text("ÉCHEC", style="bold red")
        kind = NA if d.rotational is None else ("HDD" if d.rotational else "SSD")
        t.add_row(
            d.name,
            _v(d.model),
            _size(d.size_bytes),
            kind,
            _v(d.transport),
            smart,
            _v(d.temperature_c, " °C", "{:.0f}"),
        )
    body: Table | Text = t if data.disks else NA
    return Panel(body, title="Disques", title_align="left")


def render_board(board: BoardData) -> Panel:
    t = _kv_table()
    t.add_row("Machine", _join(board.system_vendor, board.product_name, board.product_version))
    t.add_row("Carte mère", _join(board.board_vendor, board.board_name))
    t.add_row("BIOS", _join(board.bios_vendor, board.bios_version, board.bios_date))
    return Panel(t, title="Machine / carte mère", title_align="left")


def _join(*values: str | None) -> Text | str:
    present = [v for v in values if v]
    return " · ".join(present) if present else NA


def render_sensors(sensors: SensorsData) -> Panel:
    parts: list[Table | Text] = []
    if sensors.temperatures:
        t = Table(show_edge=False, box=None, header_style="bold")
        for col in ("Puce", "Capteur", "Actuel", "Haut", "Critique"):
            t.add_column(col)
        for r in sensors.temperatures:
            t.add_row(
                r.chip,
                r.label,
                _v(r.current_c, " °C", "{:.1f}"),
                _v(r.high_c, " °C", "{:.0f}"),
                _v(r.critical_c, " °C", "{:.0f}"),
            )
        parts.append(t)
    if sensors.fans:
        f = Table(show_edge=False, box=None, header_style="bold")
        for col in ("Puce", "Ventilateur", "Vitesse"):
            f.add_column(col)
        for fan in sensors.fans:
            f.add_row(fan.chip, fan.label, _v(fan.rpm, " tr/min"))
        parts.append(f)
    return Panel(Group(*parts) if parts else NA, title="Capteurs", title_align="left")


def render_power(power: PowerData) -> Panel:
    t = _kv_table()
    ac = NA if power.on_ac is None else ("secteur" if power.on_ac else "batterie")
    t.add_row("Alimentation", ac)
    if not power.batteries:
        t.add_row("Batterie", Text("aucune", style="dim"))
    for b in power.batteries:
        health = b.health_percent
        t.add_row(
            f"Batterie {b.name}",
            f"{_plain(b.percent, ' %')} · {b.status or '?'} · santé "
            f"{f'{health:.0f} %' if health is not None else '?'} "
            f"({_plain(b.full_capacity_wh, ' Wh', '{:.1f}')} / "
            f"{_plain(b.design_capacity_wh, ' Wh', '{:.1f}')}) · "
            f"{_plain(b.cycle_count, ' cycles')}",
        )
    return Panel(t, title="Alimentation", title_align="left")


def _plain(value: object, suffix: str = "", fmt: str = "{}") -> str:
    return "?" if value is None else fmt.format(value) + suffix


def render_identifiers(ids: Identifiers) -> Panel:
    t = _kv_table()
    missing = Text("non lisible (relancer avec sudo)", style="yellow")
    if ids.board is not None:
        for label, value in (
            ("Hostname", ids.board.hostname),
            ("UUID produit", ids.board.product_uuid),
            ("Serial système", ids.board.product_serial),
            ("Serial carte mère", ids.board.board_serial),
            ("Serial châssis", ids.board.chassis_serial),
            ("Asset tag carte mère", ids.board.board_asset_tag),
            ("Asset tag châssis", ids.board.chassis_asset_tag),
        ):
            t.add_row(label, value or missing)
    for m in ids.ram_modules or []:
        t.add_row(f"RAM {m.slot or '?'}", m.serial or missing)
    for d in ids.disks or []:
        details = [
            f"serial {d.serial}" if d.serial else None,
            f"WWN {d.wwn}" if d.wwn else None,
            f"EUI-64 {d.eui64}" if d.eui64 else None,
            f"NGUID {d.nguid}" if d.nguid else None,
        ]
        t.add_row(f"Disque {d.name}", " · ".join(x for x in details if x) or missing)
    return Panel(
        t,
        title="Identifiants — affichage local uniquement, jamais exportés",
        title_align="left",
        border_style="red",
    )


def render_info(
    console: Console, snapshot: MachineSnapshot, identifiers: Identifiers | None = None
) -> None:
    panels: Iterable[Panel] = (
        render_board(snapshot.board),
        render_cpu(snapshot.cpu),
        render_ram(snapshot.ram),
        render_gpu(snapshot.gpu),
        render_disks(snapshot.disks),
        render_sensors(snapshot.sensors),
        render_power(snapshot.power),
    )
    for panel in panels:
        console.print(panel)
    if identifiers is not None:
        console.print(render_identifiers(identifiers))
