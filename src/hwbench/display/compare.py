from rich.console import Group
from rich.table import Table
from rich.text import Text

from hwbench.compare import Cell, CompareWarning, Comparison, Incomparable, Notice
from hwbench.display.bench import CATEGORY_LABELS, UNIT_LABELS
from hwbench.display.fmt import compact, measure, num
from hwbench.display.scores import ISSUE_LABELS
from hwbench.export import MachineExport

INCOMPARABLE_LABELS = {
    Incomparable.MISSING: "absent",
    Incomparable.IDENTITY_DIFFERS: "version différente",
    Incomparable.NO_REFERENCE: "exporté sans référence",
    Incomparable.REFERENCE_DIFFERS: "autre référence",
    Incomparable.BACKENDS_DIFFER: "backends différents",
    Incomparable.WEIGHTS_DIFFER: "pondérations différentes",
}

ABSENT = Text("—", style="dim")


def _cell(cell: Cell, text: str) -> Text:
    """Valeur + écart à la base, ou la raison pour laquelle il n'y a pas d'écart."""
    if cell.value is None:
        if cell.issue is Incomparable.NOT_SCORED:
            reason = ISSUE_LABELS[cell.score_issue] if cell.score_issue else ""
            return Text(f"non comparable ({reason})" if reason else "non comparable", "yellow")
        if cell.issue in (Incomparable.MISSING, None):
            return ABSENT
        return Text(INCOMPARABLE_LABELS[cell.issue], style="dim")
    out = Text(text)
    if cell.delta_percent is not None:
        sign = "+" if cell.delta_percent > 0 else ""
        style = {True: "green", False: "red", None: "dim"}[cell.better]
        out.append(f"  {sign}{num(cell.delta_percent)} %", style=style)
    elif cell.issue is not None:
        out.append(f"  non comparé ({INCOMPARABLE_LABELS[cell.issue]})", style="yellow")
    return out


def _table(labels: list[str], first: str) -> Table:
    t = Table(header_style="bold", show_lines=False)
    t.add_column(first, style="bold cyan", no_wrap=True)
    for i, label in enumerate(labels):
        t.add_column(f"{label}" + (" (base)" if i == 0 else ""))
    return t


def _ram(export: MachineExport) -> str:
    ram = export.snapshot.ram
    size = ram.installed_gb if ram.installed_gb is not None else ram.total_gb
    return f"{compact(round(size, 1))} Gio" if size is not None else "?"


def render_machines(comparison: Comparison, labels: list[str]) -> Table:
    t = _table(labels, "Machine")
    exports = comparison.exports
    rows = [
        ("Modèle", [e.machine for e in exports]),
        ("CPU", [e.snapshot.cpu.model or "?" for e in exports]),
        (
            "GPU",
            [
                e.snapshot.gpu.opengl_renderer or e.snapshot.gpu.vulkan_device_name or "?"
                for e in exports
            ],
        ),
        ("RAM", [_ram(e) for e in exports]),
        ("Exporté le", [e.created[:10] for e in exports]),
        ("hwbench", [e.hwbench_version for e in exports]),
        (
            "Référence",
            [
                f"{e.reference.machine} ({e.reference.digest})" if e.reference else "aucune"
                for e in exports
            ],
        ),
    ]
    for label, values in rows:
        t.add_row(label, *values)
    return t


def render_score_rows(comparison: Comparison, labels: list[str]) -> Table:
    t = _table(labels, "Score (points)")
    for row in comparison.scores:
        label = "Score combiné" if row.category is None else CATEGORY_LABELS[row.category]
        t.add_row(label, *(_cell(c, f"{num(c.value or 0, 0)} pts") for c in row.cells))
    return t


def render_bench_rows(comparison: Comparison, labels: list[str]) -> Table:
    t = _table(labels, "Bench (valeur brute)")
    for row in comparison.benches:
        unit = UNIT_LABELS.get(row.unit, row.unit)
        t.add_row(row.name, *(_cell(c, f"{measure(c.value or 0)} {unit}") for c in row.cells))
    return t


def notice_message(notice: Notice) -> str:
    match notice.code:
        case CompareWarning.BENCH_VERSION_DIFFERS:
            return (
                f"{notice.subject} : version du bench, de l'outil ou mode de présentation "
                "différents entre les fichiers ; mesures non comparées."
            )
        case CompareWarning.REFERENCE_DIFFERS:
            return "Fichiers notés contre des références différentes : points non comparés."
        case CompareWarning.FORCED_REFERENCE:
            return f"{notice.subject} : noté contre une référence générée avec --force."


def render_comparison(comparison: Comparison, labels: list[str]) -> Group:
    parts: list[Table | Text] = [render_machines(comparison, labels)]
    if comparison.scores:
        parts.append(render_score_rows(comparison, labels))
    parts.append(render_bench_rows(comparison, labels))
    parts += [Text(f"⚠ {notice_message(n)}", style="yellow") for n in comparison.warnings]
    return Group(*parts)
