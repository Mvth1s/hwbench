import json
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from hwbench import privacy
from hwbench.benchmarks.base import BenchOptions, known_backends, select
from hwbench.collect import collect_snapshot
from hwbench.display.bench import CATEGORY_LABELS, render_result, warning_message
from hwbench.display.fmt import num
from hwbench.display.info import render_info
from hwbench.display.scores import (
    AVAILABILITY_LABELS,
    NO_REFERENCE,
    render_backends,
    render_scores,
)
from hwbench.machine_state import capture_state
from hwbench.reference import ReferenceIssue, build_reference, results_issues, state_issues
from hwbench.results import Availability, Category, Result
from hwbench.runner import MIN_RUNS, RunSettings, run_benchmark, start_warnings
from hwbench.scoring import (
    DEFAULT_WEIGHTS,
    ReferenceError,
    load_reference,
    parse_weights,
    score_results,
)

app = typer.Typer(
    help="Inventaire matériel et benchmarks notés.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    pass


@app.command()
def info(
    as_json: Annotated[
        bool, typer.Option("--json", help="Sortie JSON (sans aucun identifiant).")
    ] = False,
    show_serials: Annotated[
        bool,
        typer.Option(
            "--show-serials",
            help="Affiche numéros de série, UUID et hostname à l'écran (local uniquement).",
        ),
    ] = False,
) -> None:
    """Affiche les composants de la machine."""
    if as_json and show_serials:
        typer.echo(
            "Erreur : --json et --show-serials sont incompatibles "
            "(les identifiants ne sont jamais exportés).",
            err=True,
        )
        raise typer.Exit(code=2)

    snapshot, identifiers = collect_snapshot(include_identifiers=show_serials)

    if as_json:
        typer.echo(json.dumps(privacy.scrub(asdict(snapshot)), indent=2, ensure_ascii=False))
        return

    render_info(Console(), snapshot, identifiers)


class Target(StrEnum):
    CPU_SINGLE = "cpu-single"
    CPU_MULTI = "cpu-multi"
    GPU = "gpu"
    ALL = "all"


TARGET_CATEGORIES = {
    Target.CPU_SINGLE: [Category.CPU_SINGLE],
    Target.CPU_MULTI: [Category.CPU_MULTI],
    Target.GPU: [Category.GPU],
    Target.ALL: list(Category),
}

DEFAULTS = RunSettings()

REFERENCE_ISSUE_MESSAGES = {
    ReferenceIssue.NOT_ON_AC: "la machine n'est pas sur secteur",
    ReferenceIssue.POWER_UNKNOWN: "alimentation inconnue (secteur non confirmé)",
    ReferenceIssue.POWER_PROFILE: "profil d'énergie non « performance »",
    ReferenceIssue.PROFILE_UNKNOWN: "profil d'énergie inconnu (ni platform_profile ni EPP)",
    ReferenceIssue.WARMUP_UNSTABLE: "warm-up non stabilisé",
}

RunsOption = Annotated[
    int, typer.Option("--runs", min=MIN_RUNS, help="Runs mesurés (médiane), après warm-up.")
]
WorkersOption = Annotated[
    int | None,
    typer.Option("--workers", min=1, help="Parallélisme du multi-cœur (défaut : CPU logiques)."),
]
MaxWarmupOption = Annotated[
    float | None,
    typer.Option(
        "--max-warmup",
        min=0,
        help="Plafond du warm-up en secondes (défaut : 30 single-core, 90 multi-cœur et GPU).",
    ),
]


def _run_all(
    console: Console, classes: list, settings: RunSettings, options: BenchOptions
) -> list[Result]:
    """Lance chaque bench disponible ; un bench qui échoue est signalé et sauté."""
    results: list[Result] = []
    for cls in classes:
        instance = cls(options)
        label = f"{CATEGORY_LABELS[cls.category]} · {cls.backend}"
        availability = instance.availability()
        if availability is not Availability.AVAILABLE:
            reason = AVAILABILITY_LABELS[availability].plain
            console.print(f"[yellow]{label} : indisponible ({reason}), ignoré.[/yellow]")
            continue
        try:
            with console.status(f"{label} : préparation…") as status:
                cap = settings.warmup_cap(cls.category)

                def progress(
                    phase: str, index: int, total: int | None, status=status, label=label, cap=cap
                ) -> None:
                    if phase == "warmup":
                        status.update(f"{label} : warm-up {index} (plafond {num(cap, 0)} s)…")
                    else:
                        status.update(f"{label} : run {index}/{total}…")

                result = run_benchmark(instance, settings, probe=capture_state, progress=progress)
        except KeyboardInterrupt:
            console.print("[red]Interrompu.[/red]")
            raise typer.Exit(code=130) from None
        except RuntimeError as exc:
            console.print(f"[red]{label} : échec, ignoré. {exc}[/red]")
            continue
        console.print(render_result(result))
        results.append(result)
    return results


@app.command()
def bench(
    target: Annotated[Target, typer.Argument(help="Catégorie à mesurer.")] = Target.ALL,
    backend: Annotated[
        str,
        typer.Option("--backend", help="native, nom d'un outil, ou all (tous les disponibles)."),
    ] = "all",
    runs: RunsOption = MIN_RUNS,
    workers: WorkersOption = None,
    max_warmup: MaxWarmupOption = None,
    warmup_tolerance: Annotated[
        float,
        typer.Option(
            "--warmup-tolerance",
            min=0,
            help="Écart max (%) entre 2 itérations consécutives pour déclarer le warm-up stable.",
        ),
    ] = DEFAULTS.warmup_tolerance_percent,
    max_cv: Annotated[
        float,
        typer.Option("--max-cv", min=0, help="Seuil (%) de l'avertissement « mesures instables »."),
    ] = DEFAULTS.high_variance_cv_percent,
    hot_start: Annotated[
        float,
        typer.Option("--hot-start", help="Température CPU (°C) de départ jugée trop chaude."),
    ] = DEFAULTS.hot_start_c,
    weights: Annotated[
        str | None,
        typer.Option(
            "--weights",
            help="Pondération du score combiné, ex. « cpu-single=1,cpu-multi=1,gpu=1 ».",
        ),
    ] = None,
) -> None:
    """Lance les benchmarks notés."""
    console = Console()
    backends = known_backends()
    if backend != "all" and backend not in backends:
        typer.echo(
            f"Erreur : backend « {backend} » inconnu (disponibles : "
            f"{', '.join(sorted(backends))}, all).",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        weight_map = parse_weights(weights) if weights is not None else DEFAULT_WEIGHTS
    except ValueError as exc:
        typer.echo(f"Erreur : {exc}.", err=True)
        raise typer.Exit(code=2) from None

    categories = TARGET_CATEGORIES[target]
    classes = select(categories, backend)
    for category in categories:
        if not any(cls.category is category for cls in classes):
            reason = (
                "aucun backend disponible"
                if backend == "all"
                else f"le backend « {backend} » ne couvre pas cette catégorie"
            )
            console.print(f"[yellow]{CATEGORY_LABELS[category]} : {reason}.[/yellow]")

    settings = RunSettings(
        runs=runs,
        max_warmup_s=max_warmup,
        warmup_tolerance_percent=warmup_tolerance,
        high_variance_cv_percent=max_cv,
        hot_start_c=hot_start,
    )
    initial = capture_state()
    for warning in start_warnings(initial, settings):
        console.print(f"[yellow]⚠ {warning_message(warning, initial)}[/yellow]")

    results = _run_all(console, classes, settings, BenchOptions(workers=workers))
    if not results:
        raise typer.Exit(code=1)

    try:
        reference = load_reference()
    except ReferenceError as exc:
        console.print(f"[red]Référence illisible : {exc}[/red]")
        return
    if reference is None:
        console.print(NO_REFERENCE)
        return
    console.print(render_scores(score_results(results, reference, weight_map)))


@app.command()
def backends() -> None:
    """Liste les backends de benchmark et leur disponibilité."""
    rows = [
        (cls.name, cls.backend, cls.category, cls().availability())
        for cls in select(list(Category), "all")
    ]
    Console().print(render_backends(rows))


def _print_issues(console: Console, issues: list[str], header: str) -> None:
    console.print(f"[red]{header}[/red]")
    for issue in issues:
        console.print(f"[red]  • {issue}[/red]")


@app.command()
def reference(
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Fichier JSON de référence à écrire.")
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Écrit la référence malgré les conditions non remplies (noté dans le fichier).",
        ),
    ] = False,
    runs: RunsOption = MIN_RUNS,
    workers: WorkersOption = None,
    max_warmup: MaxWarmupOption = None,
) -> None:
    """Mesure la machine de référence (= 1000 points) : secteur, profil performance, régime
    soutenu. Refuse d'écrire le fichier si une condition n'est pas remplie, sauf --force."""
    console = Console()
    initial = capture_state()
    before = state_issues(initial)
    if before and not force:
        _print_issues(
            console,
            [REFERENCE_ISSUE_MESSAGES[i] for i in before],
            "Référence refusée avant les mesures (--force pour passer outre) :",
        )
        raise typer.Exit(code=1)

    settings = RunSettings(runs=runs, max_warmup_s=max_warmup)
    classes = select(list(Category), "all")
    results = _run_all(console, classes, settings, BenchOptions(workers=workers))
    measured = {r.name for r in results}
    for cls in classes:
        if cls.name not in measured:
            console.print(f"[yellow]{cls.name} : absent de la référence.[/yellow]")
    if not results:
        raise typer.Exit(code=1)

    during = results_issues(results)
    if during and not force:
        _print_issues(
            console,
            [f"{name} : {REFERENCE_ISSUE_MESSAGES[i]}" for i, name in during],
            "Référence refusée, fichier non écrit (--force pour passer outre) :",
        )
        raise typer.Exit(code=1)

    reasons = [i.value for i in before] + [f"{i.value}:{name}" for i, name in during]
    snapshot, _ = collect_snapshot()
    payload = build_reference(results, snapshot, reasons)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    note = " [yellow](forcée : " + ", ".join(reasons) + ")[/yellow]" if reasons else ""
    console.print(f"Référence écrite : {output} ({len(results)} benchs){note}")
