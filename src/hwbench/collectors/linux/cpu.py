import re
from dataclasses import replace
from typing import Any

from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import CpuCoreState, CpuData

SYS_CPU = "/sys/devices/system/cpu"
_CPU_DIR_RE = re.compile(r"^cpu(\d+)$")
_SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([KMG]i?B?)?", re.IGNORECASE)
_SIZE_FACTOR_KB = {"k": 1, "m": 1024, "g": 1024 * 1024}


def _flatten_lscpu(entries: list[dict[str, Any]]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for entry in entries:
        name = str(entry.get("field", "")).strip().rstrip(":")
        data = entry.get("data")
        if name and data is not None:
            flat.setdefault(name, str(data))
        flat.update(
            {k: v for k, v in _flatten_lscpu(entry.get("children") or []).items() if k not in flat}
        )
    return flat


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_cache_kb(value: str | None) -> int | None:
    """« 384 KiB », « 10 MiB », « 48 KiB (1 instance) », « 512K » -> KiB."""
    if not value:
        return None
    match = _SIZE_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "B").lower()[0]
    if unit == "b":
        return int(number // 1024)
    return int(number * _SIZE_FACTOR_KB[unit])


def parse_lscpu(payload: dict[str, Any]) -> CpuData:
    f = _flatten_lscpu(payload.get("lscpu", []))
    sockets = _to_int(f.get("Socket(s)"))
    cores_per_socket = _to_int(f.get("Core(s) per socket"))
    physical = sockets * cores_per_socket if sockets and cores_per_socket else None
    return CpuData(
        vendor=f.get("Vendor ID"),
        model=f.get("Model name"),
        architecture=f.get("Architecture"),
        sockets=sockets,
        physical_cores=physical,
        logical_cores=_to_int(f.get("CPU(s)")),
        threads_per_core=_to_int(f.get("Thread(s) per core")),
        min_mhz=_to_float(f.get("CPU min MHz")),
        max_mhz=_to_float(f.get("CPU max MHz")),
        l1d_cache_kb=parse_cache_kb(f.get("L1d cache")),
        l1i_cache_kb=parse_cache_kb(f.get("L1i cache")),
        l2_cache_kb=parse_cache_kb(f.get("L2 cache")),
        l3_cache_kb=parse_cache_kb(f.get("L3 cache")),
    )


def parse_proc_cpuinfo(text: str) -> CpuData:
    blocks = [b for b in text.strip().split("\n\n") if b.strip()]
    first: dict[str, str] = {}
    core_ids: set[tuple[str, str]] = set()
    sockets: set[str] = set()
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        if not first:
            first = fields
        phys = fields.get("physical id", "0")
        sockets.add(phys)
        if "core id" in fields:
            core_ids.add((phys, fields["core id"]))
    logical = len(blocks) or None
    physical = len(core_ids) or None
    return CpuData(
        vendor=first.get("vendor_id"),
        model=first.get("model name"),
        sockets=len(sockets) or None,
        physical_cores=physical,
        logical_cores=logical,
        threads_per_core=logical // physical if logical and physical else None,
        l3_cache_kb=parse_cache_kb(first.get("cache size")),
    )


def read_per_cpu_state() -> list[CpuCoreState]:
    states: list[CpuCoreState] = []
    for entry in _exec.list_dir(SYS_CPU):
        match = _CPU_DIR_RE.match(entry)
        if not match:
            continue
        base = f"{SYS_CPU}/{entry}/cpufreq"
        khz = _to_int(_exec.read_sysfs(f"{base}/scaling_cur_freq"))
        states.append(
            CpuCoreState(
                cpu=int(match.group(1)),
                current_mhz=khz / 1000 if khz is not None else None,
                governor=_exec.read_sysfs(f"{base}/scaling_governor"),
            )
        )
    return sorted(states, key=lambda s: s.cpu)


def _py_cpuinfo_brand() -> str | None:
    try:
        import cpuinfo

        return cpuinfo.get_cpu_info().get("brand_raw") or None
    except Exception:
        return None


@register("Linux")
class LinuxCpuCollector(Collector[CpuData, None]):
    component = "cpu"

    def collect(self, include_identifiers: bool = False) -> ComponentResult[CpuData, None]:
        payload = _exec.run_json(["lscpu", "-J"])
        if isinstance(payload, dict):
            data = parse_lscpu(payload)
        else:
            text = _exec.read_sysfs("/proc/cpuinfo")
            data = parse_proc_cpuinfo(text) if text else CpuData()

        updates: dict[str, Any] = {
            "per_cpu": read_per_cpu_state(),
            # réglés par cœur mais uniformes en pratique : cpu0 suffit
            "scaling_driver": _exec.read_sysfs(f"{SYS_CPU}/cpu0/cpufreq/scaling_driver") or None,
            "energy_performance_preference": _exec.read_sysfs(
                f"{SYS_CPU}/cpu0/cpufreq/energy_performance_preference"
            )
            or None,
        }
        if data.model is None:
            updates["model"] = _py_cpuinfo_brand()
        return ComponentResult(data=replace(data, **updates))
