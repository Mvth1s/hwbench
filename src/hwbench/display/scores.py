from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hwbench.display.bench import CATEGORY_LABELS
from hwbench.display.fmt import num
from hwbench.results import Availability, BackendId, Category
from hwbench.scoring import BackendScore, CategoryScore, CombinedScore, ScoreIssue, Scores

ISSUE_LABELS = {
    ScoreIssue.NOT_IN_REFERENCE: "absent de la référence",
    ScoreIssue.VERSION_MISMATCH: "version du bench différente de la référence",
    ScoreIssue.TOOL_VERSION_MISMATCH: "version de l'outil différente de la référence",
    ScoreIssue.PRESENTATION_MISMATCH: "mode de présentation différent de la référence",
    ScoreIssue.BACKENDS_DIFFER: "backends différents de la référence",
    ScoreIssue.CATEGORY_NOT_COMPARABLE: "une catégorie n'est pas comparable",
    ScoreIssue.CPU_NOT_MEASURED: "CPU single-core et multi-core requis",
}

AVAILABILITY_LABELS = {
    Availability.AVAILABLE: Text("disponible", style="green"),
    Availability.TOOL_MISSING: Text("outil absent", style="yellow"),
    Availability.NO_DISPLAY: Text("aucune session graphique", style="yellow"),
}

INSTALL_HINTS = {
    "sysbench": "sudo dnf install sysbench  |  sudo apt install sysbench",
    # Debian/Ubuntu découpent glmark2 : glmark2-x11 fournit /usr/bin/glmark2
    "glmark2": "sudo dnf install glmark2  |  sudo apt install glmark2-wayland glmark2-x11",
    "vkmark": "sudo dnf install vkmark  |  sudo apt install vkmark",
}

NOT_COMPARABLE = "non comparable"


def points(value: float) -> str:
    return f"{num(value, 0)} pts"


def backends_label(backends: list[BackendId]) -> str:
    return ", ".join(b.label() for b in backends) or "aucun"


def _not_comparable(issue: ScoreIssue | None) -> Text:
    return Text(f"{NOT_COMPARABLE} ({ISSUE_LABELS[issue]})" if issue else NOT_COMPARABLE, "yellow")


def _backend_row(t: Table, s: BackendScore) -> None:
    value: Text | str = points(s.points) if s.points is not None else _not_comparable(s.issue)
    note = "" if s.official else "  (information, hors score)"
    if s.reference_backend is not None:
        note += f"  référence : {s.reference_backend.label()}"
    t.add_row(f"  {s.backend.label()}", Text.assemble(value, (note, "dim")))


def _category_row(t: Table, c: CategoryScore) -> None:
    label = CATEGORY_LABELS[c.category]
    if c.points is not None:
        t.add_row(label, Text(points(c.points), style="bold"))
    else:
        t.add_row(label, _not_comparable(c.issue))
    if c.issue is ScoreIssue.BACKENDS_DIFFER:
        t.add_row(
            "",
            Text(
                f"mesurés : {backends_label(c.backends)} ; "
                f"référence : {backends_label(c.reference_backends)}",
                style="dim",
            ),
        )


def _combined_row(t: Table, c: CombinedScore) -> None:
    if c.points is None:
        t.add_row("Score combiné", _not_comparable(c.issue))
        return
    weights = " · ".join(
        f"{CATEGORY_LABELS[cat]} {num(100 * w, 0)} %" for cat, w in c.weights.items()
    )
    t.add_row("Score combiné", Text(points(c.points), style="bold green"))
    t.add_row("", Text(f"pondération : {weights}", style="dim"))


def render_scores(scores: Scores) -> Panel:
    ref = scores.reference
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column()
    for category in (Category.CPU_SINGLE, Category.CPU_MULTI, Category.GPU):
        cat = next((c for c in scores.categories if c.category is category), None)
        rows = [s for s in scores.backends if s.category is category]
        if cat is not None:
            _category_row(t, cat)
        elif rows:
            t.add_row(CATEGORY_LABELS[category], Text("pas de backend officiel mesuré", "dim"))
        for s in rows:
            _backend_row(t, s)
    if scores.combined is not None:
        _combined_row(t, scores.combined)

    parts: list[Table | Text] = [t]
    if scores.combined is not None and scores.combined.gpu_missing:
        parts.append(Text("⚠ Score combiné calculé sans GPU (non mesuré).", style="yellow"))
    if ref.forced:
        parts.append(
            Text(
                "⚠ Référence générée avec --force (" + ", ".join(ref.forced_reasons) + ").",
                style="yellow",
            )
        )
    return Panel(
        Group(*parts),
        title=Text(f"Scores · référence {ref.machine} = 1000 pts"),
        title_align="left",
    )


NO_REFERENCE = Text(
    "Pas de fichier de référence : les scores restent des valeurs brutes. "
    "Il se génère sur la machine de référence avec « hwbench reference -o "
    "src/hwbench/data/reference.json ».",
    style="yellow",
)


def render_backends(rows: list[tuple[str, str, Category, Availability]]) -> Table:
    """rows : (nom du bench, backend, catégorie, disponibilité)."""
    t = Table(header_style="bold")
    t.add_column("Bench")
    t.add_column("Backend")
    t.add_column("Catégorie")
    t.add_column("État")
    t.add_column("Installation")
    for name, backend, category, availability in rows:
        hint = INSTALL_HINTS.get(backend, "") if availability is Availability.TOOL_MISSING else ""
        t.add_row(name, backend, CATEGORY_LABELS[category], AVAILABILITY_LABELS[availability], hint)
    return t
