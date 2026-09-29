from conftest import NVIDIA_SMI_ARGS, fixture_text, laptop_commands

from hwbench.collectors.linux.gpu import (
    LinuxGpuCollector,
    parse_glxinfo,
    parse_lspci_mm,
    parse_nvidia_smi_csv,
    parse_vulkaninfo_summary,
)
from hwbench.models import PciGpu


def test_lspci_keeps_only_display_controllers() -> None:
    gpus = parse_lspci_mm(fixture_text("dell-inc-latitude-5420/lspci_mm.txt"))
    assert gpus == [PciGpu("Intel Corporation", "TigerLake-LP GT2 [Iris Xe Graphics]")]


def test_lspci_3d_controller_and_garbage() -> None:
    text = (
        '01:00.0 "3D controller [0302]" "NVIDIA Corporation [10de]" "GA106M [GeForce RTX 3060 '
        'Mobile / Max-Q] [2560]" -ra1 "Dell [1028]" "Device [0a20]"\n'
        'garbage "unterminated\n'
    )
    assert parse_lspci_mm(text) == [
        PciGpu("NVIDIA Corporation", "GA106M [GeForce RTX 3060 Mobile / Max-Q]")
    ]


def test_glxinfo() -> None:
    info = parse_glxinfo(fixture_text("dell-inc-latitude-5420/glxinfo_B.txt"))
    assert info["opengl_vendor"] == "Intel"
    assert info["opengl_renderer"] == "Mesa Intel(R) Iris(R) Xe Graphics (TGL GT2)"
    assert info["opengl_version"] == "4.6 (Compatibility Profile) Mesa 26.2.2"


def test_vulkaninfo_first_device() -> None:
    assert (
        parse_vulkaninfo_summary(fixture_text("dell-inc-latitude-5420/vulkaninfo_summary.txt"))
        == "Intel(R) Iris(R) Xe Graphics (TGL GT2)"
    )


def test_nvidia_smi_csv() -> None:
    assert parse_nvidia_smi_csv(fixture_text("nvidia_smi.csv")) == {
        "nvidia_name": "NVIDIA GeForce RTX 3060",
        "nvidia_driver_version": "580.95.05",
        "nvidia_vram_mb": 12288,
    }
    assert parse_nvidia_smi_csv("") == {}


def test_collect_all_sources(fake_system) -> None:
    commands = laptop_commands() | {NVIDIA_SMI_ARGS: fixture_text("nvidia_smi.csv")}
    fake_system(commands=commands)
    gpu = LinuxGpuCollector().collect().data
    assert len(gpu.pci_devices) == 1
    assert gpu.opengl_renderer is not None
    assert gpu.vulkan_device_name is not None
    assert gpu.nvidia_vram_mb == 12288


def test_collect_without_any_tool(fake_system) -> None:
    fake_system(commands={}, tools=set())
    gpu = LinuxGpuCollector().collect().data
    assert gpu.pci_devices == []
    assert gpu.opengl_renderer is None
    assert gpu.nvidia_name is None
