import json
import re

import pytest
from conftest import laptop_commands, laptop_sysfs, sysfs_fixture
from rich.console import Console
from typer.testing import CliRunner

from hwbench import cli
from hwbench.collect import collect_snapshot
from hwbench.display.fmt import compact, num
from hwbench.display.info import render_power, render_ram
from hwbench.models import Battery, PowerData, RamData, RamModule

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
    assert payload["ram"]["modules"][0]["slot"] == "DIMM B"
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
    assert "FAKE-0005" in result.output
    assert "fake-host" in result.output


def test_show_serials_as_root_empty_asset_tag_is_not_set(laptop) -> None:
    """Régression : en root, un asset tag vide ne doit pas demander sudo."""
    laptop(root=True)
    result = runner.invoke(cli.app, ["info", "--show-serials"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    lines = {line.split("  ")[0].strip("│ "): line for line in result.output.splitlines()}
    assert "non renseigné" in lines["Asset tag châssis"]
    assert "sudo" not in lines["Asset tag châssis"]
    assert "sudo" not in lines["Serial système"]


def test_show_serials_without_root_asks_sudo_only_for_unreadable(fake_system) -> None:
    serials = {f"/sys/class/dmi/id/{f}" for f in ("product_serial", "board_serial")}
    files = {k: v for k, v in laptop_sysfs().items() if k not in serials}
    fake_system(files=files, commands=laptop_commands(), unreadable=serials)
    result = runner.invoke(cli.app, ["info", "--show-serials"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    lines = {line.split("  ")[0].strip("│ "): line for line in result.output.splitlines()}
    assert "relancer avec sudo" in lines["Serial système"]
    assert "FAKE-CHASSIS-SERIAL" in lines["Serial châssis"]
    assert "non renseigné" in lines["Asset tag carte mère"]


def test_info_on_bare_desktop_does_not_crash(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"), commands={}, tools=set())
    result = runner.invoke(cli.app, ["info"])
    assert result.exit_code == 0, result.output
    assert "non disponible" in result.output
    assert "outil absent" in result.output
    assert "dnf install" in result.output


def _render(renderable) -> str:
    console = Console(width=200, record=True)
    console.print(renderable)
    return console.export_text()


def test_ram_empty_module_list_is_not_silent() -> None:
    out = _render(render_ram(RamData(total_gb=15.3, modules=[])))
    assert "aucune barrette détectée" in out


def test_ram_installed_and_configured_speed() -> None:
    module = RamModule("DIMM A", 8.0, "DDR4", 2667, None, None, rated_speed_mts=3200)
    out = _render(render_ram(RamData(total_gb=15.3, installed_gb=16.0, modules=[module])))
    assert "Installée" in out and "16 Gio" in out
    assert "2667 MT/s (max 3200)" in out


def test_bios_date_displayed_in_french_format(laptop) -> None:
    laptop()
    result = runner.invoke(cli.app, ["info"], env={"COLUMNS": "200"})
    assert "30/06/2026" in result.output


def test_battery_without_cycle_counter() -> None:
    battery = Battery("BAT0", 79, "Not charging", 59.3, 59.3, None)
    out = _render(render_power(PowerData(on_ac=True, batteries=[battery])))
    assert "cycles non disponibles" in out


def test_rich_output_uses_french_decimals_and_labels(laptop) -> None:
    laptop(root=True)
    result = runner.invoke(cli.app, ["info"], env={"COLUMNS": "200"})
    out = result.output
    assert "15,3 Gio" in out  # MemTotal
    assert "931,5 Gio" in out  # disque
    assert "37,9 °C" in out  # nvme Composite 37,85
    assert "59,3 Wh" in out
    assert "2667 MT/s (max 3200)" in out
    assert "Kingston" in out and "SK Hynix" in out
    assert "80AD000080AD" not in out
    assert "pas en charge" in out and "Not charging" not in out
    # nos nombres suivis d'une unité ; les libellés fabricant (« 2.60GHz ») restent intacts
    assert not re.search(r"\d\.\d+ (Gio|Mio|Kio|°C|Wh|MHz|%)", out)


def test_json_keeps_standard_numbers(laptop) -> None:
    laptop(root=True)
    payload = json.loads(runner.invoke(cli.app, ["info", "--json"]).output)
    assert isinstance(payload["ram"]["total_gb"], float)
    assert payload["power"]["batteries"][0]["status"] == "Not charging"
    assert payload["board"]["bios_date"] == "2026-06-30"


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("Charging", "en charge"),
        ("Discharging", "en décharge"),
        ("Not charging", "pas en charge"),
        ("Full", "pleine"),
        ("Unknown", "état inconnu"),
        (None, "état inconnu"),
    ],
)
def test_battery_status_translation(status: str | None, label: str) -> None:
    battery = Battery("BAT0", 50, status, None, None, None)
    out = _render(render_power(PowerData(on_ac=False, batteries=[battery])))
    assert f"· {label} ·" in out


@pytest.mark.parametrize(
    ("value", "decimals", "expected"), [(15.34, 1, "15,3"), (37.85, 0, "38"), (2.0, 2, "2,00")]
)
def test_num(value: float, decimals: int, expected: str) -> None:
    assert num(value, decimals) == expected


def test_compact() -> None:
    assert compact(8.0) == "8"
    assert compact(8.5) == "8,5"


def test_render_power_desktop_without_battery() -> None:
    out = _render(render_power(PowerData(on_ac=True)))
    assert re.search(r"Alimentation +secteur \(pas de batterie\)", out)


def test_render_power_profile_only_when_present() -> None:
    assert "Profil plateforme" not in _render(render_power(PowerData(on_ac=True)))
    out = _render(render_power(PowerData(on_ac=True, platform_profile="performance")))
    assert re.search(r"Profil plateforme +performance", out)
