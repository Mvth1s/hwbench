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
from hwbench.display.fmt import num
from hwbench.display.info import render_info
from hwbench.machine_state import capture_state
from hwbench.results import Category
from hwbench.runner import MIN_RUNS, RunSettings, run_benchmark, start_warnings

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
    max_warmup: Annotated[
        float | None,
        typer.Option(
            "--max-warmup",
            min=0,
            help="Plafond du warm-up en secondes (défaut : 30 single-core, 90 multi-cœur).",
        ),
    ] = None,
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
        console.print(render_result(result))
        done += 1

    if done == 0:
        raise typer.Exit(code=1)
