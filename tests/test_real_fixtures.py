"""Rejoue les collecteurs sur chaque machine capturée par scripts/capture_fixtures.sh.

Les assertions sont génériques (valables pour n'importe quelle machine) : elles vérifient
qu'une vraie sortie est comprise, pas des valeurs précises.
"""

import json
from pathlib import Path

import pytest
from conftest import captured_commands, captured_machine_dirs

from hwbench.collect import collect_snapshot
from hwbench.models import MachineSnapshot

MACHINES = captured_machine_dirs()

pytestmark = pytest.mark.skipif(not MACHINES, reason="aucune fixture capturée")


@pytest.fixture(params=MACHINES, ids=lambda p: p.name)
def machine(request: pytest.FixtureRequest) -> Path:
    return request.param


@pytest.fixture
def snapshot(machine: Path, fake_system) -> MachineSnapshot:
    files = json.loads((machine / "sysfs.json").read_text())
    fake_system(files=files, commands=captured_commands(machine), root=True)
    snap, _ = collect_snapshot(os_name="Linux")
    return snap


def test_cpu(snapshot: MachineSnapshot) -> None:
    cpu = snapshot.cpu
    assert cpu.model
    assert cpu.logical_cores and cpu.logical_cores >= 1
    assert cpu.physical_cores and cpu.physical_cores <= cpu.logical_cores
    assert cpu.per_cpu


def test_ram_modules_when_dmidecode_captured(machine: Path, snapshot: MachineSnapshot) -> None:
    ram = snapshot.ram
    assert ram.total_gb and ram.total_gb > 0
    if not (machine / "dmidecode_memory.txt").exists():
        pytest.skip("dmidecode non capturé")
    assert ram.modules, "dmidecode capturé mais aucune barrette comprise"
    for module in ram.modules:
        assert module.size_gb and module.size_gb > 0
        assert module.speed_mts
    assert ram.installed_gb is not None
    # MemTotal exclut la mémoire réservée (firmware, iGPU) : toujours <= installée
    assert ram.total_gb <= ram.installed_gb


def test_disks_and_smart(machine: Path, snapshot: MachineSnapshot) -> None:
    assert snapshot.disks.disks
    for disk in snapshot.disks.disks:
        assert disk.size_bytes and disk.size_bytes > 0
        if (machine / f"smartctl_{disk.name}.json").exists():
            assert disk.smart_passed is not None


def test_gpu(machine: Path, snapshot: MachineSnapshot) -> None:
    if (machine / "lspci_mm.txt").exists():
        assert snapshot.gpu.pci_devices
    if (machine / "glxinfo_B.txt").exists():
        assert snapshot.gpu.opengl_renderer


def test_board_and_bios_date(snapshot: MachineSnapshot) -> None:
    board = snapshot.board
    assert board.system_vendor or board.board_vendor
    if board.bios_date is not None:
        assert len(board.bios_date) == 10 and board.bios_date[4] == "-"


def test_sensors(snapshot: MachineSnapshot) -> None:
    for reading in snapshot.sensors.temperatures:
        assert reading.current_c is None or -60 <= reading.current_c <= 200
