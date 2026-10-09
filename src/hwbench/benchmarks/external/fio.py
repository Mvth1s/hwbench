"""fio : débits disque en lecture et écriture séquentielles (1 Mio, QD8) et aléatoires 4K
(QD32), en E/S directes (direct=1, sans cache de pages).

Un run = une invocation de fio, les 4 tests enchaînés (stonewall), RUN_SECONDS chacun, sur un
fichier temporaire de taille bornée (1 Gio par défaut, --disk-size) dans le dossier choisi
(--disk-path, défaut ~/.cache/hwbench). L'espace libre est vérifié avant la première écriture ;
le fichier est supprimé par cleanup(), que le runner appelle même en cas d'erreur ou de Ctrl+C.
La taille du fichier fait partie de l'identité du bench (champ presentation, ex. « 1GiB ») :
deux tailles différentes ne se comparent pas (cache SLC des SSD).

Valeur = moyenne géométrique des 4 résultats (indice sans unité) ; détails en Mio/s et IOPS.
Le chemin du fichier n'est jamais relevé (il contient le nom de l'utilisateur) : seuls le type
de système de fichiers et le modèle du disque le sont.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import geometric_mean
from typing import Any

from hwbench.benchmarks.base import Benchmark, BenchOptions, register
from hwbench.benchmarks.external import _run
from hwbench.results import Availability, Category, Measurement

FIO_VERSION = "1"  # à incrémenter si les tests, leur durée ou leurs paramètres changent
RUN_SECONDS = 2
IOENGINE = "libaio"
MIB = 1024**2
GIB = 1024**3
MIN_SIZE = 64 * MIB
FREE_MARGIN = 256 * MIB  # laissé libre en plus du fichier de test
FILE_PREFIX = "hwbench-fio-"


@dataclass(frozen=True)
class FioJob:
    key: str
    rw: str
    bs: str
    iodepth: int
    unit: str  # MiB/s (séquentiel) ou IOPS (aléatoire 4K)


JOBS: tuple[FioJob, ...] = (
    FioJob("seq_read", "read", "1M", 8, "MiB/s"),
    FioJob("seq_write", "write", "1M", 8, "MiB/s"),
    FioJob("rand_read_4k", "randread", "4k", 32, "IOPS"),
    FioJob("rand_write_4k", "randwrite", "4k", 32, "IOPS"),
)


# --- Taille du fichier -----------------------------------------------------------------------

_SIZE_RE = re.compile(r"^\s*(\d+)\s*([MG])(?:i?B)?\s*$", re.IGNORECASE)


def parse_size(text: str) -> int:
    """« 1G », « 1GiB », « 512M » -> octets (unités binaires). Minimum 64 Mio."""
    match = _SIZE_RE.match(text)
    if not match:
        raise ValueError(f"taille invalide « {text} » (ex. 1G, 512M)")
    size = int(match.group(1)) * (GIB if match.group(2).upper() == "G" else MIB)
    if size < MIN_SIZE:
        raise ValueError(f"taille trop petite « {text} » (minimum 64M)")
    return size


def size_label(size: int) -> str:
    """Identité de la taille : « 1GiB », « 1536MiB »."""
    return f"{size // GIB}GiB" if size % GIB == 0 else f"{size // MIB}MiB"


# --- Sortie de fio ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FioOutput:
    version: str | None
    rates: dict[str, float]  # clé du test -> Mio/s ou IOPS
    duration_s: float


def parse_output(text: str) -> FioOutput:
    """JSON de --output-format=json (fio peut écrire des avertissements avant l'accolade)."""
    start = text.find("{")
    if start < 0:
        raise _run.ToolError("fio : sortie JSON introuvable")
    try:
        data: dict[str, Any] = json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise _run.ToolError(f"fio : JSON illisible ({exc.msg})") from exc
    jobs = {job.get("jobname"): job for job in data.get("jobs", [])}
    rates: dict[str, float] = {}
    duration_ms = 0.0
    for spec in JOBS:
        job = jobs.get(spec.key)
        if job is None:
            raise _run.ToolError(f"fio : test « {spec.key} » absent de la sortie")
        if job.get("error"):
            raise _run.ToolError(f"fio : test « {spec.key} » en erreur (code {job['error']})")
        side = job.get("read" if "read" in spec.rw else "write") or {}
        if spec.unit == "IOPS":
            value = float(side.get("iops", 0.0))
        else:
            bw_bytes = side.get("bw_bytes")
            value = (
                float(bw_bytes) if bw_bytes is not None else float(side.get("bw", 0)) * 1024
            ) / MIB
        if not math.isfinite(value) or value <= 0:
            raise _run.ToolError(f"fio : test « {spec.key} » sans débit mesuré")
        rates[spec.key] = value
        duration_ms += float(job.get("job_runtime") or side.get("runtime") or 0)
    raw_version = str(data.get("fio version", ""))
    version = raw_version.removeprefix("fio-") or None
    return FioOutput(version, rates, duration_ms / 1000)


def parse_mount(text: str) -> tuple[str | None, str | None]:
    """findmnt -J : (périphérique source sans sous-volume « [/home] », type de fs)."""
    try:
        fs = json.loads(text)["filesystems"][0]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None, None
    source = re.sub(r"\[.*\]$", "", str(fs.get("source") or "")) or None
    return source, fs.get("fstype")


def parse_disk_model(text: str) -> str | None:
    """lsblk -J -s (arbre inversé : partition -> … -> disque) : modèle du premier disque."""
    try:
        stack = list(json.loads(text)["blockdevices"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    while stack:
        node = stack.pop(0)
        if node.get("type") == "disk" and node.get("model"):
            return str(node["model"]).strip()
        stack += node.get("children") or []
    return None


# --- Backend ---------------------------------------------------------------------------------


@register
class Fio(Benchmark):
    name = "fio-disk"
    category = Category.DISK
    backend = "fio"
    version = FIO_VERSION
    unit = "index"  # moyenne géométrique de Mio/s et d'IOPS : sans unité
    detail_units = {job.key: job.unit for job in JOBS}

    def __init__(self, options: BenchOptions | None = None) -> None:
        super().__init__(options)
        self._file: Path | None = None
        self._tool_version: str | None = None
        self._environment: dict[str, str] = {}

    def availability(self) -> Availability:
        return Availability.AVAILABLE if _run.which("fio") else Availability.TOOL_MISSING

    def tool_version(self) -> str | None:
        return self._tool_version

    def presentation(self) -> str:
        return size_label(self.options.disk_size)

    def environment(self) -> dict[str, str]:
        return {"ioengine": IOENGINE, "time": f"{RUN_SECONDS} s par test", **self._environment}

    def notice(self) -> str:
        size = size_label(self.options.disk_size).replace("GiB", " Gio").replace("MiB", " Mio")
        return (
            f"fichier de test de {size} dans {self.directory()}, "
            "supprimé à la fin (même en cas d'erreur ou de Ctrl+C)"
        )

    def directory(self) -> Path:
        if self.options.disk_path is not None:
            return self.options.disk_path
        cache = _run.getenv("XDG_CACHE_HOME")
        return (Path(cache) if cache else _run.home() / ".cache") / "hwbench"

    def command(self, filename: str) -> list[str]:
        args = [
            "fio",
            "--output-format=json",
            f"--filename={filename}",
            f"--size={self.options.disk_size}",
            "--direct=1",
            f"--ioengine={IOENGINE}",
            "--time_based=1",
            f"--runtime={RUN_SECONDS}",
            "--randrepeat=1",
        ]
        for i, job in enumerate(JOBS):
            args += [f"--name={job.key}"]
            if i:
                args += ["--stonewall"]  # un test après l'autre, jamais en parallèle
            args += [f"--rw={job.rw}", f"--bs={job.bs}", f"--iodepth={job.iodepth}"]
        return args

    def _prepare(self) -> Path:
        directory = self.directory()
        _run.make_dirs(directory)
        free = _run.disk_free(directory)
        needed = self.options.disk_size + FREE_MARGIN
        if free < needed:
            raise _run.ToolError(
                f"fio : espace libre insuffisant dans {directory} ({free // MIB} Mio libres, "
                f"{needed // MIB} Mio nécessaires) ; choisir un autre dossier (--disk-path) "
                "ou une taille plus petite (--disk-size)"
            )
        self._environment = self._describe(directory)
        return _run.temp_file(directory, FILE_PREFIX)

    def _describe(self, directory: Path) -> dict[str, str]:
        """Type de système de fichiers et modèle du disque sous le dossier (sans le chemin)."""
        env: dict[str, str] = {}
        if not _run.which("findmnt"):
            return env
        mount = _run.run(["findmnt", "-J", "-T", str(directory), "-o", "SOURCE,FSTYPE"], 10)
        source, fstype = parse_mount(mount.stdout) if mount.returncode == 0 else (None, None)
        if fstype:
            env["filesystem"] = fstype
        if source and source.startswith("/dev/") and _run.which("lsblk"):
            tree = _run.run(["lsblk", "-J", "-s", "-o", "NAME,MODEL,TYPE", source], 10)
            model = parse_disk_model(tree.stdout) if tree.returncode == 0 else None
            if model:
                env["device"] = model
        return env

    def run(self) -> Measurement:
        if self._file is None:
            self._file = self._prepare()
        # mise en place du fichier au premier run (écriture complète) : timeout large
        text = _run.output_or_raise(self.command(str(self._file)), timeout=300)
        out = parse_output(text)
        self._tool_version = out.version or self._tool_version
        return Measurement(
            value=geometric_mean(out.rates.values()),
            duration_s=out.duration_s or float(RUN_SECONDS * len(JOBS)),
            details=out.rates,
        )

    def cleanup(self) -> None:
        if self._file is not None:
            _run.remove(self._file)
            self._file = None
