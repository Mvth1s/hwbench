"""Backend fio, sur les sorties réelles du portable Dell (Samsung 990 EVO Plus, btrfs)."""

from pathlib import Path
from statistics import geometric_mean

import pytest
from conftest import tool_output

from hwbench.benchmarks.base import BenchOptions, select
from hwbench.benchmarks.external import _run, fio
from hwbench.benchmarks.external.fio import Fio
from hwbench.results import Availability, Category, MachineState
from hwbench.runner import RunSettings, run_benchmark

MIB = 1024**2
GIB = 1024**3
COOL = MachineState(["performance"], on_ac=True, cpu_temp_c=40.0)


def outputs() -> dict[str, str]:
    return {
        "fio": tool_output("fio_disk.json"),
        "findmnt": tool_output("findmnt_cache.json"),
        "lsblk": tool_output("lsblk_inverse.json"),
    }


# --- taille du fichier ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "size"),
    [("1G", GIB), ("1GiB", GIB), ("2g", 2 * GIB), ("512M", 512 * MIB), (" 64MiB ", 64 * MIB)],
)
def test_parse_size(text: str, size: int) -> None:
    assert fio.parse_size(text) == size


@pytest.mark.parametrize("text", ["", "1T", "1.5G", "abc", "32M", "-1G"])
def test_parse_size_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        fio.parse_size(text)


def test_size_label() -> None:
    assert fio.size_label(GIB) == "1GiB"
    assert fio.size_label(1536 * MIB) == "1536MiB"


# --- sorties -------------------------------------------------------------------------------


def test_parse_real_output() -> None:
    out = fio.parse_output(tool_output("fio_disk.json"))
    assert out.version == "3.40"
    assert list(out.rates) == ["seq_read", "seq_write", "rand_read_4k", "rand_write_4k"]
    assert all(v > 0 for v in out.rates.values())
    # séquentiel en Mio/s, aléatoire en IOPS (bien plus grands sur un SSD NVMe)
    assert 1000 < out.rates["seq_read"] < 20_000
    assert out.rates["rand_read_4k"] > 10_000
    assert out.duration_s == pytest.approx(4.0, abs=0.1)  # 4 tests de 1 s à la capture


def test_parse_output_tolerates_a_warning_before_the_json() -> None:
    text = "fio: note: both iodepth >= 1 and synchronous I/O engine\n" + tool_output(
        "fio_disk.json"
    )
    assert fio.parse_output(text).version == "3.40"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("pas de json", "JSON introuvable"),
        ("{nope", "JSON illisible"),
        ('{"fio version": "fio-3.40", "jobs": []}', "absent"),
        (
            '{"jobs": [{"jobname": "seq_read", "error": 5, "read": {"bw_bytes": 1}}]}',
            "en erreur",
        ),
        (
            '{"jobs": [{"jobname": "seq_read", "error": 0, "read": {"bw_bytes": 0}}]}',
            "sans débit",
        ),
    ],
)
def test_parse_output_errors(text: str, message: str) -> None:
    with pytest.raises(_run.ToolError, match=message):
        fio.parse_output(text)


def test_mount_and_disk_model() -> None:
    assert fio.parse_mount(tool_output("findmnt_cache.json")) == ("/dev/nvme0n1p3", "btrfs")
    assert fio.parse_disk_model(tool_output("lsblk_inverse.json")) == "Samsung SSD 990 EVO Plus 1TB"
    assert fio.parse_mount("{}") == (None, None)
    assert fio.parse_disk_model("pas du json") is None


# --- backend -------------------------------------------------------------------------------


def test_registry_and_availability(fake_tools) -> None:
    assert [c.name for c in select([Category.DISK], "all")] == ["fio-disk"]
    assert Fio().availability() is Availability.TOOL_MISSING
    fake_tools(outputs=outputs())
    assert Fio().availability() is Availability.AVAILABLE


def test_run_measures_on_a_temp_file_in_the_cache(fake_tools) -> None:
    tools = fake_tools(outputs=outputs())
    bench = Fio()
    m = bench.run()
    rates = fio.parse_output(tool_output("fio_disk.json")).rates
    assert m.details == rates
    assert m.value == pytest.approx(geometric_mean(rates.values()))
    directory = Path("/home/test/.cache/hwbench")
    assert tools.dirs == [directory]
    assert tools.temp_files == [directory / "hwbench-fio-0.tmp"]
    args = next(c for c in tools.calls if c[0] == "fio")
    assert f"--filename={directory / 'hwbench-fio-0.tmp'}" in args
    for option in ("--direct=1", f"--size={GIB}", "--output-format=json", "--ioengine=libaio"):
        assert option in args
    assert args.count("--stonewall") == 3
    assert bench.tool_version() == "3.40"
    assert bench.presentation() == "1GiB"
    assert bench.category is Category.DISK and bench.unit == "index"
    assert bench.detail_units["rand_read_4k"] == "IOPS"
    # le fichier est réutilisé d'un run à l'autre
    bench.run()
    assert len(tools.temp_files) == 1


def test_environment_names_the_disk_but_never_the_path(fake_tools) -> None:
    fake_tools(outputs=outputs())
    bench = Fio()
    bench.run()
    env = bench.environment()
    assert env["filesystem"] == "btrfs"
    assert env["device"] == "Samsung SSD 990 EVO Plus 1TB"
    assert not any("/home" in value or "hwbench-fio" in value for value in env.values())


def test_directory_options(fake_tools) -> None:
    fake_tools(outputs=outputs(), env={"XDG_CACHE_HOME": "/srv/cache"})
    assert Fio().directory() == Path("/srv/cache/hwbench")
    assert Fio(BenchOptions(disk_path=Path("/mnt/data"))).directory() == Path("/mnt/data")


def test_disk_size_option_changes_the_identity(fake_tools) -> None:
    tools = fake_tools(outputs=outputs())
    bench = Fio(BenchOptions(disk_size=512 * MIB))
    bench.run()
    assert f"--size={512 * MIB}" in tools.calls[-1]
    assert bench.presentation() == "512MiB"


def test_not_enough_free_space_writes_nothing(fake_tools) -> None:
    tools = fake_tools(outputs=outputs(), free_bytes=GIB)  # 1 Gio + marge nécessaires
    with pytest.raises(_run.ToolError, match="espace libre insuffisant"):
        Fio().run()
    assert tools.temp_files == []
    assert not any(c[0] == "fio" for c in tools.calls)


def test_cleanup_removes_the_file(fake_tools) -> None:
    tools = fake_tools(outputs=outputs())
    bench = Fio()
    bench.run()
    bench.cleanup()
    assert tools.removed == tools.temp_files
    bench.cleanup()  # sans effet la seconde fois
    assert len(tools.removed) == 1


def test_file_removed_when_fio_fails(fake_tools) -> None:
    outs = outputs()
    del outs["fio"]
    tools = fake_tools(outputs=outs, failing={"fio": "fio: io_u error on file: Invalid argument"})
    with pytest.raises(_run.ToolError, match="Invalid argument"):
        run_benchmark(Fio(), RunSettings(), probe=lambda: COOL)
    assert tools.temp_files and tools.removed == tools.temp_files


def test_file_removed_on_ctrl_c(fake_tools, monkeypatch) -> None:
    tools = fake_tools(outputs=outputs())
    real_run = tools.run

    def interrupted(args, timeout):
        if args[0] == "fio":
            raise KeyboardInterrupt
        return real_run(args, timeout)

    monkeypatch.setattr(_run, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_benchmark(Fio(), RunSettings(), probe=lambda: COOL)
    assert tools.temp_files and tools.removed == tools.temp_files
