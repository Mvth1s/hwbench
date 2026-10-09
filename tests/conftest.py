import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hwbench.benchmarks.external import _run
from hwbench.benchmarks.native.memory import MemoryCopy
from hwbench.benchmarks.native.workloads import Workload
from hwbench.collectors.linux import _exec
from hwbench.results import Category, MachineState, Result

# Charges natives réduites : mêmes chemins de code, en quelques millisecondes.
TINY = (
    Workload("sha256", "MiB/s", size=64 * 1024, repeat=2),
    Workload("zlib", "MiB/s", size=64 * 1024, repeat=1),
    Workload("lzma", "MiB/s", size=16 * 1024, repeat=1),
    Workload("powmod", "op/s", size=256, repeat=2),
)

FIXTURES = Path(__file__).parent / "fixtures"

LSBLK_ARGS = ("lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,ROTA,TRAN")
NVIDIA_SMI_ARGS = (
    "nvidia-smi",
    "--query-gpu=name,driver_version,memory.total",
    "--format=csv,noheader,nounits",
)


CAPTURED_FILES = {
    "lscpu.json": ("lscpu", "-J"),
    "lsblk.json": LSBLK_ARGS,
    "lspci_mm.txt": ("lspci", "-mm", "-nn"),
    "glxinfo_B.txt": ("glxinfo", "-B"),
    "vulkaninfo_summary.txt": ("vulkaninfo", "--summary"),
    "nvidia_smi.csv": NVIDIA_SMI_ARGS,
    "dmidecode_memory.txt": ("dmidecode", "-t", "memory"),
    "smartctl_version.txt": ("smartctl", "--version"),
}


def captured_machine_dirs() -> list[Path]:
    """Dossiers produits par scripts/capture_fixtures.sh (tools/ = sorties des benchs externes)."""
    return sorted(p for p in FIXTURES.iterdir() if (p / "sysfs.json").is_file())


def captured_commands(machine: Path) -> dict[tuple[str, ...], str]:
    commands = {
        args: (machine / name).read_text()
        for name, args in CAPTURED_FILES.items()
        if (machine / name).exists()
    }
    for f in machine.glob("smartctl_*.json"):
        disk = f.stem.removeprefix("smartctl_")
        commands[("smartctl", "-j", "-a", f"/dev/{disk}")] = f.read_text()
    return commands


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def sysfs_fixture(name: str) -> dict[str, str]:
    return json.loads(fixture_text(name))


class FakeSystem:
    """Remplace hwbench.collectors.linux._exec : aucune commande ni lecture réelle."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        commands: dict[tuple[str, ...], str] | None = None,
        tools: set[str] | None = None,
        root: bool = False,
        unreadable: set[str] | None = None,
    ) -> None:
        self.files = files or {}
        # présents mais illisibles (ex. serials DMI en 0400 sans root)
        self.unreadable = unreadable or set()
        self.commands = commands or {}
        self.tools = tools if tools is not None else {cmd[0] for cmd in self.commands}
        self.root = root
        self.commands_run: list[tuple[str, ...]] = []
        self.paths_read: list[str] = []

    def which(self, name: str) -> str | None:
        return f"/usr/bin/{name}" if name in self.tools else None

    def is_root(self) -> bool:
        return self.root

    def run_text(self, args: list[str], timeout: float = 0) -> str | None:
        self.commands_run.append(tuple(args))
        if args[0] not in self.tools:
            return None
        return self.commands.get(tuple(args))

    def run_json(self, args: list[str], timeout: float = 0) -> Any | None:
        text = self.run_text(args, timeout)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def read_sysfs(self, path: str | Path) -> str | None:
        self.paths_read.append(str(path))
        if str(path) in self.unreadable:
            return None
        value = self.files.get(str(path))
        return value.strip() if value is not None else None

    def link_name(self, path: str | Path) -> str | None:
        # liens sysfs capturés sous la clé « <chemin>@link » (valeur = nom de la cible)
        return self.files.get(f"{path}@link")

    def exists(self, path: str | Path) -> bool:
        return str(path) in self.files or str(path) in self.unreadable

    def list_dir(self, path: str | Path) -> list[str]:
        prefix = str(path).rstrip("/") + "/"
        return sorted({k[len(prefix) :].split("/")[0] for k in self.files if k.startswith(prefix)})


@pytest.fixture
def fake_system(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeSystem]:
    def install(**kwargs: Any) -> FakeSystem:
        system = FakeSystem(**kwargs)
        for name in (
            "which",
            "is_root",
            "run_text",
            "run_json",
            "read_sysfs",
            "exists",
            "link_name",
            "list_dir",
        ):
            monkeypatch.setattr(_exec, name, getattr(system, name))
        return system

    return install


# Capture réelle (scripts/capture_fixtures.sh) d'une Dell Latitude 5420, root compris.
LAPTOP = "dell-inc-latitude-5420"


def laptop_commands() -> dict[tuple[str, ...], str]:
    return captured_commands(FIXTURES / LAPTOP)


def laptop_sysfs() -> dict[str, str]:
    return sysfs_fixture(f"{LAPTOP}/sysfs.json")


@pytest.fixture
def laptop(fake_system: Callable[..., FakeSystem]) -> Callable[..., FakeSystem]:
    def install(root: bool = False) -> FakeSystem:
        return fake_system(files=laptop_sysfs(), commands=laptop_commands(), root=root)

    return install


# --- Outils externes des benchs (sysbench, glmark2, vkmark) ---------------------------

TOOLS = FIXTURES / "tools"

# Copies mémoire réduites (1 Mio) : à patcher dans memory.SINGLE et memory.MULTI.
TINY_MEMORY = (MemoryCopy("copy", "MiB/s", size=1024 * 1024, repeat=2),)


def tool_output(name: str) -> str:
    return (TOOLS / name).read_text()


class FakeTools:
    """Remplace hwbench.benchmarks.external._run : aucun outil réellement lancé.

    outputs : binaire -> sortie (ou liste de sorties rendues tour à tour, la dernière répétée).
    failing : binaire -> stderr d'un échec (code 1).
    free_bytes : espace libre simulé ; fichiers temporaires et suppressions sont enregistrés.
    """

    def __init__(
        self,
        outputs: dict[str, str | list[str]] | None = None,
        env: dict[str, str] | None = None,
        files: set[str] | None = None,
        failing: dict[str, str] | None = None,
        free_bytes: int = 500 * 1024**3,
    ) -> None:
        self.outputs = outputs or {}
        self.env = env or {}
        self.files = files or set()
        self.failing = failing or {}
        self.calls: list[list[str]] = []
        # système de fichiers simulé (bench disque)
        self.free_bytes = free_bytes
        self.dirs: list[Path] = []
        self.temp_files: list[Path] = []
        self.removed: list[Path] = []

    def which(self, name: str) -> str | None:
        known = name in self.outputs or name in self.failing
        return f"/usr/bin/{name}" if known else None

    def getenv(self, name: str) -> str | None:
        return self.env.get(name) or None

    def exists(self, path: str) -> bool:
        return path in self.files

    def home(self) -> Path:
        return Path("/home/test")

    def make_dirs(self, path: Path) -> None:
        self.dirs.append(path)

    def disk_free(self, path: Path) -> int:
        return self.free_bytes

    def temp_file(self, directory: Path, prefix: str) -> Path:
        path = directory / f"{prefix}{len(self.temp_files)}.tmp"
        self.temp_files.append(path)
        return path

    def remove(self, path: Path) -> None:
        self.removed.append(path)

    def run(self, args: list[str], timeout: float) -> _run.Completed:
        self.calls.append(list(args))
        if args[0] in self.failing:
            return _run.Completed(1, "", self.failing[args[0]])
        out = self.outputs[args[0]]
        if isinstance(out, list):
            out = out.pop(0) if len(out) > 1 else out[0]
        return _run.Completed(0, out, "")


def _install_tools(monkeypatch: pytest.MonkeyPatch, tools: FakeTools) -> FakeTools:
    for name in (
        "which",
        "getenv",
        "exists",
        "run",
        "home",
        "make_dirs",
        "disk_free",
        "temp_file",
        "remove",
    ):
        monkeypatch.setattr(_run, name, getattr(tools, name))
    return tools


@pytest.fixture(autouse=True)
def no_external_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Par défaut, aucun outil externe : les tests ne lancent jamais le vrai glmark2."""
    _install_tools(monkeypatch, FakeTools())


@pytest.fixture
def fake_tools(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeTools]:
    def install(**kwargs: Any) -> FakeTools:
        return _install_tools(monkeypatch, FakeTools(**kwargs))

    return install


# --- Résultats de bench fabriqués (scoring, référence, affichage) ------------------------

COOL_AC_STATE = MachineState(
    ["performance"], on_ac=True, cpu_temp_c=45.0, platform_profile="performance"
)


def make_result(
    name: str,
    value: float,
    *,
    backend: str | None = None,
    category: Category | None = None,
    version: str = "1",
    tool_version: str | None = None,
    presentation: str | None = None,
    **overrides: Any,
) -> Result:
    """Result minimal ; backend et catégorie déduits du nom (« native-cpu-multi », « vkmark »,
    « sysbench-memory-single », « fio-disk »)."""
    if backend is None:
        backend = "native" if name.startswith("native-") else name.split("-")[0]
    if category is None:
        category = (
            Category.MEMORY
            if "-memory-" in name
            else Category.DISK
            if name.startswith("fio")
            else Category.CPU_SINGLE
            if name.endswith("single")
            else Category.CPU_MULTI
            if name.endswith("multi")
            else Category.GPU
        )
    base: dict[str, Any] = dict(
        name=name,
        category=category,
        backend=backend,
        version=version,
        tool_version=tool_version,
        presentation=presentation,
        unit="index",
        higher_is_better=True,
        value=value,
        stdev=0.0,
        runs=[value] * 3,
        warmup_runs=2,
        warmup_s=1.0,
        warmup_stable=True,
        burst=value,
        duration_s=4.0,
        details={},
        detail_units={},
        workers=None,
        environment={},
        state_before=COOL_AC_STATE,
        state_after=COOL_AC_STATE,
        warnings=[],
    )
    return Result(**(base | overrides))
