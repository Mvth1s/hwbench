from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hwbench.display.bench import CATEGORY_LABELS
from hwbench.display.fmt import num
from hwbench.results import COMBINED_CATEGORIES, Availability, BackendId, Category
from hwbench.scoring import BackendScore, CategoryScore, CombinedScore, ScoreIssue, Scores

ISSUE_LABELS = {
    ScoreIssue.NOT_IN_REFERENCE: "absent de la référence",
    ScoreIssue.VERSION_MISMATCH: "version du bench différente de la référence",
    ScoreIssue.TOOL_VERSION_MISMATCH: "version de l'outil différente de la référence",
    ScoreIssue.PRESENTATION_MISMATCH: (
        "mode de présentation (ou taille du fichier disque) différent de la référence"
    ),
    ScoreIssue.BACKENDS_DIFFER: "backends différents de la référence",
    ScoreIssue.BACKENDS_INCOMPLETE: "backends de la référence non mesurés",
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
    "fio": "sudo dnf install fio  |  sudo apt install fio",
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


INFO_NOTE = "  (information, hors score combiné)"


def _category_row(t: Table, c: CategoryScore) -> None:
    label = CATEGORY_LABELS[c.category]
    info = c.category not in COMBINED_CATEGORIES
    if c.points is not None:
        t.add_row(
            label, Text.assemble((points(c.points), "bold"), (INFO_NOTE if info else "", "dim"))
        )
    elif c.issue is ScoreIssue.BACKENDS_INCOMPLETE:
        t.add_row(label, Text(f"incomplet ({', '.join(c.missing)} non mesuré)", "yellow"))
    elif info and c.issue is ScoreIssue.NOT_IN_REFERENCE:
        # pas encore dans la référence : les valeurs brutes des benchs font foi
        t.add_row(label, Text("valeurs brutes (pas encore dans la référence)", "dim"))
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


def driver_notice(bench: str, driver: str | None, reference_driver: str | None) -> str:
    """Même GPU que la référence, autre pilote : avertissement, jamais bloquant."""
    return (
        f"⚠ {bench} : pilote {driver} (référence : {reference_driver}, même GPU). Score "
        "calculé quand même ; un changement de pilote peut faire varier le résultat."
    )


def driver_info(bench: str, driver: str | None, reference_driver: str | None) -> str:
    """Autre GPU que la référence : le pilote est une simple information."""
    reference = f" (référence : {reference_driver}, autre GPU)" if reference_driver else ""
    return f"{bench} : pilote {driver}{reference}"


def tool_notice(s: BackendScore) -> str:
    """Même disque que la référence, autre version de l'outil : avertissement, jamais bloquant."""
    return (
        f"⚠ {s.backend.name} : outil {s.tool_version} (référence : {s.reference_tool_version}, "
        "même disque). Score calculé quand même ; un changement de version de l'outil peut faire "
        "varier le résultat."
    )


def tool_info(s: BackendScore) -> str:
    """Autre disque que la référence : la version de l'outil est une simple information."""
    reference = s.reference_tool_version
    suffix = f" (référence : {reference}, autre disque)" if reference else ""
    return f"{s.backend.name} : outil {s.tool_version}{suffix}"


def tool_build_info(s: BackendScore) -> str:
    """Même version amont que la référence, autre build : simple information."""
    return (
        f"{s.backend.name} : outil {s.tool_version} "
        f"(référence : {s.reference_tool_version}, même version amont)"
    )


def gpu_missing_notice(scores: Scores) -> str:
    """Combiné calculé sans GPU : non mesuré, ou incomplet (backend de la référence en échec,
    absent ou non supporté par le matériel)."""
    gpu = next((c for c in scores.categories if c.category is Category.GPU), None)
    if gpu is not None and gpu.issue is ScoreIssue.BACKENDS_INCOMPLETE:
        return (
            f"Score combiné calculé sans GPU : {', '.join(gpu.missing)} non mesuré (en échec, "
            "absent ou non supporté sur cette machine). Score partiel, non classé."
        )
    return "Score combiné calculé sans GPU (non mesuré)."


def render_scores(scores: Scores) -> Panel:
    ref = scores.reference
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column()
    for category in Category:
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
        parts.append(Text(f"⚠ {gpu_missing_notice(scores)}", style="yellow"))
    for s in scores.backends:
        if s.driver_differs:
            parts.append(
                Text(driver_notice(s.backend.name, s.driver, s.reference_driver), style="yellow")
            )
        elif s.driver_info:
            parts.append(
                Text(driver_info(s.backend.name, s.driver, s.reference_driver), style="dim")
            )
        if s.tool_differs:
            parts.append(Text(tool_notice(s), style="yellow"))
        elif s.tool_info:
            parts.append(Text(tool_info(s), style="dim"))
        elif s.tool_build_differs:
            parts.append(Text(tool_build_info(s), style="dim"))
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
