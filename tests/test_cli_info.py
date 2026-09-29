import json

import pytest
from conftest import sysfs_fixture
from typer.testing import CliRunner

from hwbench import cli
from hwbench.collect import collect_snapshot

runner = CliRunner()


@pytest.fixture(autouse=True)
def force_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "collect_snapshot",
        lambda include_identifiers=False: collect_snapshot(include_identifiers, os_name="Linux"),
    )


def test_json_and_show_serials_are_incompatible(laptop) -> None:
    system = laptop(root=True)
    result = runner.invoke(cli.app, ["info", "--json", "--show-serials"])
    assert result.exit_code == 2
    assert "incompatibles" in result.output
    assert system.commands_run == []


def test_info_json_contains_no_identifiers(laptop) -> None:
    laptop(root=True)
    result = runner.invoke(cli.app, ["info", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"cpu", "ram", "gpu", "disks", "board", "sensors", "power"}
    assert payload["cpu"]["logical_cores"] == 8
    assert payload["ram"]["modules"][0]["slot"] == "DIMM A"
    assert "FAKE" not in result.output
    assert "fake-host" not in result.output


def test_info_rich_without_root(laptop) -> None:
    laptop(root=False)
    result = runner.invoke(cli.app, ["info"])
    assert result.exit_code == 0, result.output
    assert "Latitude 5420" in result.output
    assert "relancer avec sudo" in result.output
    assert "FAKE" not in result.output
    assert "Identifiants" not in result.output


def test_info_show_serials_displays_identifiers_locally(laptop) -> None:
    laptop(root=True)
    result = runner.invoke(cli.app, ["info", "--show-serials"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "Identifiants" in result.output
    assert "FAKE-SYS-SERIAL" in result.output
    assert "FAKE-NVME-SERIAL-0001" in result.output
    assert "fake-host" in result.output


def test_info_on_bare_desktop_does_not_crash(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"), commands={}, tools=set())
    result = runner.invoke(cli.app, ["info"])
    assert result.exit_code == 0, result.output
    assert "non disponible" in result.output
    assert "outil absent" in result.output
    assert "dnf install" in result.output
