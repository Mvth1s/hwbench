import json

from conftest import fixture_text, sysfs_fixture

from hwbench.collectors.linux import cpu
from hwbench.collectors.linux.cpu import (
    LinuxCpuCollector,
    parse_cache_kb,
    parse_lscpu,
    parse_proc_cpuinfo,
)


def test_parse_lscpu_real_output() -> None:
    data = parse_lscpu(json.loads(fixture_text("dell-inc-latitude-5420/lscpu.json")))
    assert data.model == "11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz"
    assert data.vendor == "GenuineIntel"
    assert data.architecture == "x86_64"
    assert (data.sockets, data.physical_cores, data.logical_cores) == (1, 4, 8)
    assert data.threads_per_core == 2
    assert data.max_mhz == 4400.0
    assert data.min_mhz == 400.0
    assert (data.l1d_cache_kb, data.l1i_cache_kb) == (192, 128)
    assert (data.l2_cache_kb, data.l3_cache_kb) == (5 * 1024, 8 * 1024)


def test_parse_lscpu_tolerates_missing_fields() -> None:
    data = parse_lscpu({"lscpu": [{"field": "Architecture:", "data": "aarch64"}]})
    assert data.architecture == "aarch64"
    assert data.model is None
    assert data.physical_cores is None


def test_parse_cache_kb_variants() -> None:
    assert parse_cache_kb("384 KiB (8 instances)") == 384
    assert parse_cache_kb("10 MiB") == 10 * 1024
    assert parse_cache_kb("8192 KB") == 8192
    assert parse_cache_kb("512K") == 512
    assert parse_cache_kb(None) is None
    assert parse_cache_kb("n/a") is None


def test_parse_proc_cpuinfo_fallback() -> None:
    data = parse_proc_cpuinfo(fixture_text("proc_cpuinfo.txt"))
    assert data.model == "11th Gen Intel(R) Core(TM) i5-1145G7 @ 2.60GHz"
    assert (data.logical_cores, data.physical_cores, data.threads_per_core) == (4, 2, 2)
    assert data.l3_cache_kb == 8192


def test_collect_reads_per_cpu_frequency_and_governor(laptop) -> None:
    laptop()
    data = LinuxCpuCollector().collect().data
    assert [c.cpu for c in data.per_cpu] == list(range(8))
    assert data.per_cpu[0].current_mhz == 3999.959
    assert {c.governor for c in data.per_cpu} == {"performance"}


def test_collect_falls_back_to_proc_cpuinfo_without_lscpu(fake_system) -> None:
    files = {"/proc/cpuinfo": fixture_text("proc_cpuinfo.txt")}
    fake_system(files=files, commands={}, tools=set())
    data = LinuxCpuCollector().collect().data
    assert data.logical_cores == 4
    assert data.per_cpu == []


def test_collect_uses_py_cpuinfo_when_model_unknown(fake_system, monkeypatch) -> None:
    fake_system(files=sysfs_fixture("sysfs_desktop.json"), commands={}, tools=set())
    monkeypatch.setattr(cpu, "_py_cpuinfo_brand", lambda: "Fallback CPU")
    assert LinuxCpuCollector().collect().data.model == "Fallback CPU"


def test_collect_never_crashes_on_empty_system(fake_system, monkeypatch) -> None:
    fake_system(files={}, commands={}, tools=set())
    monkeypatch.setattr(cpu, "_py_cpuinfo_brand", lambda: None)
    result = LinuxCpuCollector().collect()
    assert result.data.model is None
    assert result.identifiers is None
