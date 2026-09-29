from conftest import laptop_sysfs, sysfs_fixture

from hwbench.collectors.linux.board import LinuxBoardCollector, parse_dmi_date

IDENTIFIER_FILES = (
    "product_uuid",
    "product_serial",
    "board_serial",
    "chassis_serial",
    "board_asset_tag",
    "chassis_asset_tag",
)


def test_board_data(laptop) -> None:
    laptop()
    data = LinuxBoardCollector().collect().data
    assert (data.system_vendor, data.product_name) == ("Dell Inc.", "Latitude 5420")
    assert data.product_version is None
    assert (data.board_vendor, data.board_name) == ("Dell Inc.", "0M51J7")
    assert (data.bios_vendor, data.bios_version, data.bios_date) == (
        "Dell Inc.",
        "1.56.0",
        "2026-06-30",
    )


def test_identifier_files_not_read_by_default(laptop) -> None:
    system = laptop()
    result = LinuxBoardCollector().collect()
    assert result.identifiers is None
    read = " ".join(system.paths_read)
    for name in IDENTIFIER_FILES:
        assert name not in read
    assert "/proc/sys/kernel/hostname" not in system.paths_read


def test_identifiers_when_requested(laptop) -> None:
    laptop()
    ids = LinuxBoardCollector().collect(include_identifiers=True).identifiers
    assert ids is not None
    assert ids.hostname == "fake-host"
    assert ids.product_serial == "FAKE-SYS-SERIAL"
    assert ids.board_serial == "FAKE-BOARD-SERIAL"
    assert ids.chassis_asset_tag is None
    assert ids.board_asset_tag is None


def test_parse_dmi_date() -> None:
    assert parse_dmi_date("06/30/2026") == "2026-06-30"
    assert parse_dmi_date("12/31/99") == "1999-12-31"
    assert parse_dmi_date("2026-06-30") is None
    assert parse_dmi_date("garbage") is None
    assert parse_dmi_date(None) is None


def test_placeholders_become_none(fake_system) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"))
    data = LinuxBoardCollector().collect().data
    assert data.system_vendor is None
    assert data.product_name is None
    assert data.board_name == "B550M Pro4"


def test_unreadable_serials_are_none(fake_system) -> None:
    files = {k: v for k, v in laptop_sysfs().items() if "serial" not in k}
    fake_system(files=files)
    ids = LinuxBoardCollector().collect(include_identifiers=True).identifiers
    assert ids is not None
    assert (ids.product_serial, ids.board_serial, ids.chassis_serial) == (None, None, None)
