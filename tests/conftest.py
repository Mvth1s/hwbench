import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from hwbench.collectors.linux import _exec

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
    """Dossiers produits par scripts/capture_fixtures.sh."""
    return sorted(p for p in FIXTURES.iterdir() if p.is_dir())


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
    ) -> None:
        self.files = files or {}
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
        value = self.files.get(str(path))
        return value.strip() if value is not None else None

    def list_dir(self, path: str | Path) -> list[str]:
        prefix = str(path).rstrip("/") + "/"
        return sorted({k[len(prefix) :].split("/")[0] for k in self.files if k.startswith(prefix)})


@pytest.fixture
def fake_system(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeSystem]:
    def install(**kwargs: Any) -> FakeSystem:
        system = FakeSystem(**kwargs)
        for name in ("which", "is_root", "run_text", "run_json", "read_sysfs", "list_dir"):
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
