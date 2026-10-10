import json
import os
from dataclasses import asdict
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.text import Text

from hwbench import __version__, privacy
from hwbench.benchmarks.base import BenchOptions, known_backends, select
from hwbench.benchmarks.external.fio import parse_size
from hwbench.collect import collect_snapshot
from hwbench.compare import compare
from hwbench.display.bench import (
    CATEGORY_LABELS,
    cooldown_message,
    render_failure,
    render_result,
    warning_message,
)
from hwbench.display.compare import render_comparison
from hwbench.display.fmt import num
from hwbench.display.info import render_info
from hwbench.display.scores import (
    AVAILABILITY_LABELS,
    NO_REFERENCE,
    render_backends,
    render_scores,
)
from hwbench.export import ExportError, MachineExport, build_export, load_export, write_export
from hwbench.machine_state import capture_state
from hwbench.reference import (
    ReferenceIssue,
    build_reference,
    machine_label,
    results_issues,
    state_issues,
)
from hwbench.report import render_report
from hwbench.results import Availability, BenchWarning, Category, MachineState, Result
from hwbench.runner import (
    MIN_RUNS,
    CooldownOutcome,
    RunSettings,
    cool_down,
    run_benchmark,
    start_warnings,
)
from hwbench.scoring import (
    DEFAULT_WEIGHTS,
    ReferenceError,
    Scores,
    load_reference,
    parse_weights,
    score_results,
)

app = typer.Typer(
    help="Inventaire matériel et benchmarks notés.",
    no_args_is_help=True,
    add_completion=True,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"hwbench {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Affiche la version et quitte.",
        ),
    ] = False,
) -> None:
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

    # markup=False : les chaînes du firmware et des pilotes ne sont jamais du balisage rich
    render_info(Console(markup=False), snapshot, identifiers)


class Target(StrEnum):
    CPU_SINGLE = "cpu-single"
    CPU_MULTI = "cpu-multi"
    GPU = "gpu"
    MEMORY = "memory"
    DISK = "disk"
    ALL = "all"


TARGET_CATEGORIES = {
    Target.CPU_SINGLE: [Category.CPU_SINGLE],
    Target.CPU_MULTI: [Category.CPU_MULTI],
    Target.GPU: [Category.GPU],
    Target.MEMORY: [Category.MEMORY],
    Target.DISK: [Category.DISK],
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
    typer.Option(
        "--workers",
        min=1,
        help="Parallélisme du CPU multi-core et de la mémoire (défaut : CPU logiques).",
    ),
]
MaxWarmupOption = Annotated[
    float | None,
    typer.Option(
        "--max-warmup",
        min=0,
        help=(
            "Plafond du warm-up en secondes (défaut : 30 single-core et mémoire, "
            "90 CPU multi-core et GPU, 60 disque)."
        ),
    ),
]
DiskSizeOption = Annotated[
    str,
    typer.Option(
        "--disk-size",
        help="Taille du fichier de test du bench disque (ex. 1G, 512M ; minimum 64M). Une "
        "autre taille que 1G n'est pas comparable à la référence.",
    ),
]
DiskPathOption = Annotated[
    Path | None,
    typer.Option(
        "--disk-path",
        file_okay=False,
        help="Dossier du fichier de test du bench disque (défaut : ~/.cache/hwbench).",
    ),
]


ReportOption = Annotated[
    bool,
    typer.Option(
        "--report",
        help="Écrit aussi la session en JSON et son rapport HTML (dossier des rapports).",
    ),
]
ReportDirOption = Annotated[
    Path | None,
    typer.Option(
        "--report-dir",
        file_okay=False,
        help="Dossier des rapports (défaut : ~/.local/share/hwbench/reports).",
    ),
]


def reports_dir() -> Path:
    """$XDG_DATA_HOME/hwbench/reports, soit ~/.local/share/hwbench/reports par défaut."""
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hwbench" / "reports"


def write_report(session: MachineExport, directory: Path, now: datetime) -> tuple[Path, Path]:
    """Session en JSON puis rapport HTML rendu depuis ce JSON relu (sa seule source).

    Nom = horodatage local à la seconde ; un suffixe -2, -3… évite d'écraser un rapport.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    name, n = stamp, 1
    while (directory / f"{name}.json").exists() or (directory / f"{name}.html").exists():
        n += 1
        name = f"{stamp}-{n}"
    json_path, html_path = directory / f"{name}.json", directory / f"{name}.html"
    write_export(session, json_path)
    html_path.write_text(render_report(load_export(json_path)), encoding="utf-8")
    return json_path, html_path


def _print_report(console: Console, paths: tuple[Path, Path]) -> None:
    console.print("Rapport enregistré :")
    console.print(Text(f"  JSON  {paths[0]}"))
    console.print(Text(f"  HTML  {paths[1]}"))


def _bench_options(workers: int | None, disk_size: str, disk_path: Path | None) -> BenchOptions:
    try:
        size = parse_size(disk_size)
    except ValueError as exc:
        typer.echo(f"Erreur : --disk-size : {exc}.", err=True)
        raise typer.Exit(code=2) from None
    return BenchOptions(workers=workers, disk_size=size, disk_path=disk_path)


def _cool_down(console: Console, category: Category, settings: RunSettings) -> float:
    """Pause avant une catégorie (--cooldown) ; renvoie la durée effective."""
    label = f"{CATEGORY_LABELS[category]} · refroidissement"
    target = num(settings.hot_start_c, 0)
    with console.status(f"{label}…") as status:

        def progress(elapsed: float, temp: float | None) -> None:
            if temp is None:
                status.update(f"{label} : {num(elapsed, 0)}/{num(settings.cooldown_s, 0)} s…")
            else:
                status.update(
                    f"{label} : CPU {num(temp, 0)} °C, objectif sous {target} °C "
                    f"({num(elapsed, 0)}/{num(settings.cooldown_timeout_s, 0)} s)…"
                )

        cooldown = cool_down(settings, probe=capture_state, progress=progress)
    warn = cooldown.outcome in (CooldownOutcome.TIMEOUT, CooldownOutcome.NO_SENSOR)
    message = f"{label} : {cooldown_message(cooldown, settings)}"
    console.print(Text(f"⚠ {message}", "yellow") if warn else Text(message, "dim"))
    return cooldown.waited_s


def _run_all(
    console: Console, classes: list, settings: RunSettings, options: BenchOptions
) -> list[Result]:
    """Lance chaque bench disponible ; un bench qui échoue est signalé et sauté.

    --cooldown : pause à chaque changement de catégorie (durée fixe), ou avant chaque catégorie,
    la première comprise (auto, sans attente si le CPU est déjà sous le seuil).
    """
    results: list[Result] = []
    previous: Category | None = None
    for cls in classes:
        instance = cls(options)
        label = f"{CATEGORY_LABELS[cls.category]} · {cls.name}"
        availability = instance.availability()
        if availability is not Availability.AVAILABLE:
            reason = AVAILABILITY_LABELS[availability].plain
            console.print(f"[yellow]{label} : indisponible ({reason}), ignoré.[/yellow]")
            continue
        if (notice := instance.notice()) is not None:
            # le chemin vient de l'utilisateur : jamais interprété comme balisage rich
            console.print(Text(f"{label} : {notice}.", style="dim"))
        new_category = cls.category is not previous
        first = previous is None
        previous = cls.category
        try:
            waited = 0.0
            if new_category and (settings.cooldown_auto or (settings.cooldown_s and not first)):
                waited = _cool_down(console, cls.category, settings)
            with console.status(f"{label} : préparation…") as status:
                cap = settings.warmup_cap(cls.category)

                def progress(
                    phase: str, index: int, total: int | None, status=status, label=label, cap=cap
                ) -> None:
                    if phase == "warmup":
                        status.update(f"{label} : warm-up {index} (plafond {num(cap, 0)} s)…")
                    else:
                        status.update(f"{label} : run {index}/{total}…")

                result = run_benchmark(
                    instance, settings, probe=capture_state, progress=progress, cooldown_s=waited
                )
        except KeyboardInterrupt:
            console.print("[red]Interrompu.[/red]")
            raise typer.Exit(code=130) from None
        except RuntimeError as exc:
            console.print(render_failure(cls.category, cls.name, cls.version, str(exc)))
            continue
        console.print(render_result(result))
        results.append(result)
    return results


TargetArg = Annotated[Target, typer.Argument(help="Catégorie à mesurer.")]
BackendOption = Annotated[
    str, typer.Option("--backend", help="native, nom d'un outil, ou all (tous les disponibles).")
]
ToleranceOption = Annotated[
    float,
    typer.Option(
        "--warmup-tolerance",
        min=0,
        help="Écart max (%) entre 2 itérations consécutives pour déclarer le warm-up stable.",
    ),
]
MaxCvOption = Annotated[
    float,
    typer.Option("--max-cv", min=0, help="Seuil (%) de l'avertissement « mesures instables »."),
]
ReliableCvOption = Annotated[
    float,
    typer.Option(
        "--reliable-cv",
        min=0,
        help="Seuil (%) sous lequel le rapport juge les mesures très reproductibles.",
    ),
]
HotStartOption = Annotated[
    float, typer.Option("--hot-start", help="Température CPU (°C) de départ jugée trop chaude.")
]
CooldownOption = Annotated[
    str | None,
    typer.Option(
        "--cooldown",
        metavar="SECONDES|auto",
        help=(
            "Pause entre les catégories : durée fixe en secondes, ou « auto » (avant chaque "
            "catégorie, attendre que le CPU passe sous le seuil --hot-start)."
        ),
    ),
]
CooldownTimeoutOption = Annotated[
    float,
    typer.Option("--cooldown-timeout", min=0, help="Attente maximale (s) d'un --cooldown auto."),
]
CooldownStallOption = Annotated[
    float,
    typer.Option(
        "--cooldown-stall",
        min=0,
        help=(
            "--cooldown auto : fenêtre (s) sur laquelle une baisse trop faible arrête l'attente "
            "(0 : jamais, attendre le seuil ou --cooldown-timeout)."
        ),
    ),
]
CooldownStallDeltaOption = Annotated[
    float,
    typer.Option(
        "--cooldown-stall-delta",
        min=0,
        help="--cooldown auto : baisse minimale (°C) attendue sur la fenêtre --cooldown-stall.",
    ),
]
WeightsOption = Annotated[
    str | None,
    typer.Option(
        "--weights", help="Pondération du score combiné, ex. « cpu-single=1,cpu-multi=1,gpu=1 »."
    ),
]


def parse_cooldown(value: str | None) -> tuple[float, bool]:
    """« auto » -> (0, True) ; « 30 » -> (30.0, False) ; None -> pas de pause."""
    if value is None:
        return 0.0, False
    if value.strip().lower() == "auto":
        return 0.0, True
    try:
        seconds = float(value.replace(",", "."))
    except ValueError:
        seconds = -1.0
    if not 0 <= seconds < float("inf"):
        raise ValueError(f"« {value} » : nombre de secondes ou « auto » attendu")
    return seconds, False


def _settings(
    runs: int,
    max_warmup: float | None,
    tolerance: float,
    max_cv: float,
    hot_start: float,
    reliable_cv: float = DEFAULTS.reliable_cv_percent,
    cooldown: str | None = None,
    cooldown_timeout: float = DEFAULTS.cooldown_timeout_s,
    cooldown_stall: float = DEFAULTS.cooldown_stall_s,
    cooldown_stall_delta: float = DEFAULTS.cooldown_stall_delta_c,
) -> RunSettings:
    try:
        cooldown_s, cooldown_auto = parse_cooldown(cooldown)
    except ValueError as exc:
        typer.echo(f"Erreur : --cooldown : {exc}.", err=True)
        raise typer.Exit(code=2) from None
    return RunSettings(
        runs=runs,
        max_warmup_s=max_warmup,
        warmup_tolerance_percent=tolerance,
        high_variance_cv_percent=max_cv,
        hot_start_c=hot_start,
        reliable_cv_percent=reliable_cv,
        cooldown_s=cooldown_s,
        cooldown_auto=cooldown_auto,
        cooldown_timeout_s=cooldown_timeout,
        cooldown_stall_s=cooldown_stall,
        cooldown_stall_delta_c=cooldown_stall_delta,
    )


def upfront_warnings(state: MachineState, settings: RunSettings) -> list[BenchWarning]:
    """Contrôle global avant les benchs. Avec --cooldown auto, la température de départ n'y
    figure pas : l'attente précède chaque catégorie (la première comprise), sa ligne cite la
    température atteinte et chaque panneau relève l'état après l'attente."""
    warnings = start_warnings(state, settings)
    if settings.cooldown_auto:
        warnings = [w for w in warnings if w is not BenchWarning.HOT_START]
    return warnings


def _bench_session(
    console: Console,
    target: Target,
    backend: str,
    settings: RunSettings,
    options: BenchOptions,
    weights: str | None,
) -> tuple[list[Result], Scores | None]:
    """Benchs + scores, partagé par `bench` et `export`."""
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

    initial = capture_state()
    for warning in upfront_warnings(initial, settings):
        console.print(f"[yellow]⚠ {warning_message(warning, initial)}[/yellow]")

    results = _run_all(console, classes, settings, options)
    if not results:
        raise typer.Exit(code=1)

    try:
        reference = load_reference()
    except ReferenceError as exc:
        console.print(f"[red]Référence illisible : {exc}[/red]")
        return results, None
    if reference is None:
        console.print(NO_REFERENCE)
        return results, None
    scores = score_results(results, reference, weight_map)
    console.print(render_scores(scores))
    return results, scores


@app.command()
def bench(
    target: TargetArg = Target.ALL,
    backend: BackendOption = "all",
    runs: RunsOption = MIN_RUNS,
    workers: WorkersOption = None,
    max_warmup: MaxWarmupOption = None,
    warmup_tolerance: ToleranceOption = DEFAULTS.warmup_tolerance_percent,
    max_cv: MaxCvOption = DEFAULTS.high_variance_cv_percent,
    hot_start: HotStartOption = DEFAULTS.hot_start_c,
    reliable_cv: ReliableCvOption = DEFAULTS.reliable_cv_percent,
    cooldown: CooldownOption = None,
    cooldown_timeout: CooldownTimeoutOption = DEFAULTS.cooldown_timeout_s,
    cooldown_stall: CooldownStallOption = DEFAULTS.cooldown_stall_s,
    cooldown_stall_delta: CooldownStallDeltaOption = DEFAULTS.cooldown_stall_delta_c,
    weights: WeightsOption = None,
    disk_size: DiskSizeOption = "1G",
    disk_path: DiskPathOption = None,
    report: ReportOption = False,
    report_dir: ReportDirOption = None,
) -> None:
    """Lance les benchmarks notés.

    Avec --report : session en JSON et rapport HTML dans le dossier des rapports. Bench
    interrompu ou sans résultat : aucun fichier.
    """
    console = Console()
    settings = _settings(
        runs,
        max_warmup,
        warmup_tolerance,
        max_cv,
        hot_start,
        reliable_cv,
        cooldown,
        cooldown_timeout,
        cooldown_stall,
        cooldown_stall_delta,
    )
    options = _bench_options(workers, disk_size, disk_path)
    results, scores = _bench_session(console, target, backend, settings, options, weights)
    if report:
        snapshot, _ = collect_snapshot()
        session = build_export(
            snapshot, machine_label(snapshot), results, scores, settings=settings
        )
        _print_report(console, write_report(session, report_dir or reports_dir(), datetime.now()))


@app.command()
def export(
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Fichier JSON à écrire (écrasé s'il existe).")
    ],
    target: TargetArg = Target.ALL,
    backend: BackendOption = "all",
    runs: RunsOption = MIN_RUNS,
    workers: WorkersOption = None,
    max_warmup: MaxWarmupOption = None,
    warmup_tolerance: ToleranceOption = DEFAULTS.warmup_tolerance_percent,
    max_cv: MaxCvOption = DEFAULTS.high_variance_cv_percent,
    hot_start: HotStartOption = DEFAULTS.hot_start_c,
    reliable_cv: ReliableCvOption = DEFAULTS.reliable_cv_percent,
    cooldown: CooldownOption = None,
    cooldown_timeout: CooldownTimeoutOption = DEFAULTS.cooldown_timeout_s,
    cooldown_stall: CooldownStallOption = DEFAULTS.cooldown_stall_s,
    cooldown_stall_delta: CooldownStallDeltaOption = DEFAULTS.cooldown_stall_delta_c,
    weights: WeightsOption = None,
    disk_size: DiskSizeOption = "1G",
    disk_path: DiskPathOption = None,
    report: ReportOption = False,
    report_dir: ReportDirOption = None,
) -> None:
    """Lance les benchmarks et exporte le tout en JSON pour `hwbench compare`.

    L'export contient les composants (sans aucun identifiant), les résultats et les scores.
    """
    console = Console()
    settings = _settings(
        runs,
        max_warmup,
        warmup_tolerance,
        max_cv,
        hot_start,
        reliable_cv,
        cooldown,
        cooldown_timeout,
        cooldown_stall,
        cooldown_stall_delta,
    )
    options = _bench_options(workers, disk_size, disk_path)
    results, scores = _bench_session(console, target, backend, settings, options, weights)
    snapshot, _ = collect_snapshot()
    session = build_export(snapshot, machine_label(snapshot), results, scores, settings=settings)
    write_export(session, output)
    console.print(Text(f"Export écrit : {output} ({len(results)} benchs)"))
    if report:
        _print_report(console, write_report(session, report_dir or reports_dir(), datetime.now()))


@app.command("report")
def report_cmd(
    file: Annotated[
        Path, typer.Argument(help="Session ou export JSON (hwbench export, --report).")
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Fichier HTML (défaut : même nom, extension .html)."),
    ] = None,
) -> None:
    """Rapport HTML autonome (hors ligne, imprimable) à partir d'un fichier JSON."""
    out = output or file.with_suffix(".html")
    if out.resolve() == file.resolve():
        typer.echo(
            "Erreur : le rapport écraserait le fichier JSON (-o pour un autre nom).", err=True
        )
        raise typer.Exit(code=2)
    try:
        session = load_export(file)
    except ExportError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=2) from None
    out.write_text(render_report(session), encoding="utf-8")
    Console().print(Text(f"Rapport écrit : {out}"))


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
    """Mesure la machine de référence du scoring (= 1000 points).

    Exige secteur, profil d'énergie « performance » et warm-up stabilisé ; sinon refuse
    d'écrire le fichier, sauf --force (noté dans le fichier).
    """
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


@app.command("compare")
def compare_cmd(
    files: Annotated[
        list[Path],
        typer.Argument(help="Exports de `hwbench export` ; le premier sert de base."),
    ],
) -> None:
    """Compare des exports côte à côte : écarts en pourcentage par rapport au premier."""
    if len(files) < 2:
        typer.echo("Erreur : au moins deux fichiers à comparer.", err=True)
        raise typer.Exit(code=2)
    try:
        exports = [load_export(f) for f in files]
    except ExportError as exc:
        typer.echo(f"Erreur : {exc}", err=True)
        raise typer.Exit(code=2) from None
    Console().print(render_comparison(compare(exports), [f.stem for f in files]))
