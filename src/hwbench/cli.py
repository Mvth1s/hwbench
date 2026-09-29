import json
from dataclasses import asdict
from enum import StrEnum
from typing import Annotated

import typer
from rich.console import Console

from hwbench import privacy
from hwbench.benchmarks.base import BenchOptions, known_backends, select
from hwbench.collect import collect_snapshot
from hwbench.display.bench import CATEGORY_LABELS, render_result, warning_message
from hwbench.display.info import render_info
from hwbench.machine_state import capture_state
from hwbench.results import Category
from hwbench.runner import MIN_RUNS, run_benchmark, start_warnings

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

PHASE_LABELS = {"warmup": "warm-up", "run": "run"}


@app.command()
def bench(
    target: Annotated[Target, typer.Argument(help="Catégorie à mesurer.")] = Target.ALL,
    backend: Annotated[
        str,
        typer.Option("--backend", help="native, nom d'un outil, ou all (tous les disponibles)."),
    ] = "all",
    runs: Annotated[
        int, typer.Option("--runs", min=MIN_RUNS, help="Runs mesurés (médiane), après warm-up.")
    ] = MIN_RUNS,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers", min=1, help="Processus du bench multi-cœur (défaut : CPU logiques)."
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

    initial = capture_state()
    for warning in start_warnings(initial):
        console.print(f"[yellow]⚠ {warning_message(warning, initial.cpu_temp_c)}[/yellow]")

    options = BenchOptions(workers=workers)
    done = 0
    for cls in classes:
        instance = cls(options)
        label = f"{CATEGORY_LABELS[cls.category]} · {cls.backend}"
        if not instance.is_available():
            console.print(f"[yellow]{label} : indisponible, ignoré.[/yellow]")
            continue
        try:
            with console.status(f"{label} : préparation…") as status:

                def progress(
                    phase: str, index: int, total: int, status=status, label=label
                ) -> None:
                    status.update(f"{label} : {PHASE_LABELS[phase]} {index}/{total}…")

                result = run_benchmark(instance, runs, probe=capture_state, progress=progress)
        except KeyboardInterrupt:
            console.print("[red]Interrompu.[/red]")
            raise typer.Exit(code=130) from None
        console.print(render_result(result))
        done += 1

    if done == 0:
        raise typer.Exit(code=1)
