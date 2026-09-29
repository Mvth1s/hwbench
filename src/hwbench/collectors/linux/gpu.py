import re
import shlex

from hwbench.collectors.base import Collector, ComponentResult, register
from hwbench.collectors.linux import _exec
from hwbench.models import GpuData, PciGpu

_DISPLAY_CLASS_RE = re.compile(r"\[03[0-9a-f]{2}\]$", re.IGNORECASE)
_TRAILING_ID_RE = re.compile(r"\s*\[[0-9a-f]{4}\]$", re.IGNORECASE)


def _strip_id(value: str) -> str:
    return _TRAILING_ID_RE.sub("", value).strip()


def parse_lspci_mm(text: str) -> list[PciGpu]:
    """Format `lspci -mm -nn` : slot "classe [cccc]" "vendeur [vvvv]" "device [dddd]" ..."""
    gpus: list[PciGpu] = []
    for line in text.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if len(tokens) < 4 or not _DISPLAY_CLASS_RE.search(tokens[1]):
            continue
        gpus.append(PciGpu(vendor=_strip_id(tokens[2]) or None, model=_strip_id(tokens[3]) or None))
    return gpus


def parse_glxinfo(text: str) -> dict[str, str]:
    wanted = {
        "OpenGL vendor string": "opengl_vendor",
        "OpenGL renderer string": "opengl_renderer",
        "OpenGL version string": "opengl_version",
    }
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key in wanted and value.strip():
            out[wanted[key]] = value.strip()
    return out


def parse_vulkaninfo_summary(text: str) -> str | None:
    for line in text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == "deviceName":
            return value.strip() or None
    return None


def parse_nvidia_smi_csv(text: str) -> dict[str, str | int]:
    line = next((ln for ln in text.splitlines() if ln.strip()), None)
    if line is None:
        return {}
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return {}
    out: dict[str, str | int] = {"nvidia_name": parts[0], "nvidia_driver_version": parts[1]}
    if parts[2].isdigit():
        out["nvidia_vram_mb"] = int(parts[2])
    return out


@register("Linux")
class LinuxGpuCollector(Collector[GpuData, None]):
    component = "gpu"

    def collect(self, include_identifiers: bool = False) -> ComponentResult[GpuData, None]:
        lspci = _exec.run_text(["lspci", "-mm", "-nn"])
        fields: dict[str, object] = {"pci_devices": parse_lspci_mm(lspci) if lspci else []}

        glx = _exec.run_text(["glxinfo", "-B"])
        if glx:
            fields.update(parse_glxinfo(glx))

        vk = _exec.run_text(["vulkaninfo", "--summary"])
        if vk:
            fields["vulkan_device_name"] = parse_vulkaninfo_summary(vk)

        smi = _exec.run_text(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ]
        )
        if smi:
            fields.update(parse_nvidia_smi_csv(smi))

        return ComponentResult(GpuData(**fields))  # type: ignore[arg-type]
