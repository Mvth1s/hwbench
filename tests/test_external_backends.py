"""Backends externes, sur les sorties réelles de tests/fixtures/tools/ (desktop B850)."""

import pytest
from conftest import tool_output

from hwbench.benchmarks.base import BenchOptions
from hwbench.benchmarks.external import _gpu, _run, glmark2, sysbench, vkmark
from hwbench.benchmarks.external.glmark2 import Glmark2
from hwbench.benchmarks.external.sysbench import SysbenchCpuMulti, SysbenchCpuSingle
from hwbench.benchmarks.external.vkmark import Vkmark
from hwbench.results import Availability, BenchWarning, MachineState
from hwbench.runner import RunSettings, run_benchmark

WAYLAND = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":1"}
X11 = {"DISPLAY": ":0"}
HEADLESS_PLUGIN = {"/usr/lib/vkmark/headless.so"}
COOL = MachineState(["performance"], on_ac=True, cpu_temp_c=40.0)


# --- sysbench ----------------------------------------------------------------------------


def test_sysbench_parsing() -> None:
    text = tool_output("sysbench_cpu_multi.txt")
    assert sysbench.parse_version(text) == "1.0.20"
    assert sysbench.parse_events_per_second(text) > 0
    assert sysbench.parse_total_time(text) == pytest.approx(2.0, abs=0.1)


def test_sysbench_missing_value_is_an_error() -> None:
    with pytest.raises(_run.ToolError, match="events per second"):
        sysbench.parse_events_per_second("sysbench 1.0.20\nnothing here\n")


def test_sysbench_single_run(fake_tools) -> None:
    tools = fake_tools(outputs={"sysbench": tool_output("sysbench_cpu_1thread.txt")})
    bench = SysbenchCpuSingle()
    assert bench.availability() is Availability.AVAILABLE
    m = bench.run()
    assert m.value == sysbench.parse_events_per_second(tool_output("sysbench_cpu_1thread.txt"))
    assert "--threads=1" in tools.calls[0] and tools.calls[0][-1] == "run"
    assert bench.tool_version() == "1.0.20"
    assert bench.workers is None


def test_sysbench_multi_uses_workers(fake_tools) -> None:
    tools = fake_tools(outputs={"sysbench": tool_output("sysbench_cpu_multi.txt")})
    bench = SysbenchCpuMulti(BenchOptions(workers=6))
    bench.run()
    assert "--threads=6" in tools.calls[0]
    assert bench.workers == 6


def test_sysbench_missing_and_failing(fake_tools) -> None:
    assert SysbenchCpuSingle().availability() is Availability.TOOL_MISSING
    fake_tools(failing={"sysbench": "FATAL: invalid option"})
    with pytest.raises(_run.ToolError, match="invalid option"):
        SysbenchCpuSingle().run()


# --- glmark2 -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["glmark2-wayland_offscreen.txt", "glmark2_offscreen.txt"])
def test_glmark2_parsing(name: str) -> None:
    out = glmark2.parse_output(tool_output(name))
    assert out.version == "2023.01"
    assert out.renderer and "radeonsi" in out.renderer
    assert out.gl_version and "Mesa 26.2.3" in out.gl_version
    assert [scene for scene, _ in out.scene_fps] == [
        "effect2d",
        "effect2d",
        "desktop",
        "desktop",
        "jellyfish",
        "terrain",
        "shadow",
        "refract",
    ]
    assert out.score > 0


def test_glmark2_without_score_is_an_error() -> None:
    with pytest.raises(_run.ToolError, match="glmark2 Score"):
        glmark2.parse_output("glmark2 2023.01\nError: main: Could not initialize canvas\n")


@pytest.mark.parametrize(
    ("env", "installed", "expected"),
    [
        (WAYLAND, {"glmark2-wayland", "glmark2", "glmark2-drm"}, ("glmark2-wayland", "wayland")),
        # sous Wayland sans la variante native : glmark2 X11 via XWayland
        (WAYLAND, {"glmark2"}, ("glmark2", "x11")),
        (X11, {"glmark2-wayland", "glmark2"}, ("glmark2", "x11")),
        ({}, {"glmark2-wayland", "glmark2-drm"}, ("glmark2-drm", "drm")),
        ({}, {"glmark2-wayland", "glmark2"}, None),
    ],
)
def test_glmark2_binary_follows_session(fake_tools, env, installed, expected) -> None:
    fake_tools(outputs=dict.fromkeys(installed, ""), env=env)
    assert glmark2.choose_binary() == expected


def test_glmark2_availability(fake_tools) -> None:
    assert Glmark2().availability() is Availability.TOOL_MISSING
    fake_tools(outputs={"glmark2-wayland": ""}, env={})
    assert Glmark2().availability() is Availability.NO_DISPLAY


def test_glmark2_run_offscreen_4k(fake_tools) -> None:
    tools = fake_tools(
        outputs={"glmark2-wayland": tool_output("glmark2-wayland_offscreen.txt")}, env=WAYLAND
    )
    bench = Glmark2()
    m = bench.run()
    cmd = tools.calls[0]
    assert cmd[:4] == ["glmark2-wayland", "--off-screen", "--size", "3840x2160"]
    assert "effect2d:kernel=1,1,1,1,1;1,1,1,1,1;1,1,1,1,1;:duration=3" in cmd
    assert list(m.details) == list(glmark2.SCENES)
    assert m.details["terrain"] < m.details["jellyfish"]
    assert bench.tool_version() == "2023.01"
    assert bench.presentation() == "offscreen"
    env = bench.environment()
    assert env["binary"] == "glmark2-wayland" and env["session"] == "wayland"
    assert env["resolution"] == "3840x2160"
    assert env["driver"] == "Mesa 26.2.3-arch1.1"
    assert bench.warnings() == []


def test_glmark2_missing_scene_is_an_error(fake_tools) -> None:
    text = tool_output("glmark2-wayland_offscreen.txt")
    truncated = "\n".join(line for line in text.splitlines() if not line.startswith("[terrain]"))
    fake_tools(outputs={"glmark2-wayland": truncated}, env=WAYLAND)
    with pytest.raises(_run.ToolError, match="7 scènes mesurées sur 8"):
        Glmark2().run()


def test_glmark2_software_rendering_warns(fake_tools) -> None:
    text = tool_output("glmark2-wayland_offscreen.txt").replace(
        "AMD Radeon RX 9070 XT (radeonsi,", "llvmpipe (LLVM 20.1.8, 256 bits) (x,"
    )
    fake_tools(outputs={"glmark2-wayland": text}, env=WAYLAND)
    bench = Glmark2()
    bench.run()
    assert bench.warnings() == [BenchWarning.SOFTWARE_RENDERING]


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("4.6 (Compatibility Profile) Mesa 26.2.3-arch1.1", "Mesa 26.2.3-arch1.1"),
        ("4.6.0 NVIDIA 550.54.14", "NVIDIA 550.54.14"),
        (None, None),
    ],
)
def test_gl_driver(version: str | None, expected: str | None) -> None:
    assert _gpu.gl_driver(version) == expected


# --- vkmark ------------------------------------------------------------------------------


def test_vkmark_parsing_never_keeps_the_gpu_uuid() -> None:
    out = vkmark.parse_output(tool_output("vkmark_headless.txt"))
    assert out.version == "2025.01"
    assert (out.vendor_id, out.driver_version) == (0x1002, 109060099)
    assert out.device_name == "AMD Radeon RX 9070 XT (RADV GFX1201)"
    assert [scene for scene, _ in out.scene_fps] == ["effect2d", "effect2d"]
    assert "uuid" not in repr(out).lower()


def test_vulkan_driver_versions() -> None:
    out = vkmark.parse_output(tool_output("vkmark_headless.txt"))
    assert vkmark.vulkan_driver(out) == "RADV 26.2.3"  # = Mesa 26.2.3 de glmark2
    # NVIDIA 550.54.14 : 10/8/8 bits
    nvidia = (550 << 22) | (54 << 14) | (14 << 6)
    assert _gpu.vulkan_driver_version(0x10DE, nvidia) == "550.54.14"


def test_vkmark_headless_when_plugin_installed(fake_tools) -> None:
    tools = fake_tools(
        outputs={"vkmark": tool_output("vkmark_headless.txt")}, env={}, files=HEADLESS_PLUGIN
    )
    bench = Vkmark()
    assert bench.availability() is Availability.AVAILABLE
    m = bench.run()
    cmd = tools.calls[0]
    assert cmd[:5] == ["vkmark", "--winsys", "headless", "--size", "3840x2160"]
    assert "--present-mode" not in cmd
    assert list(m.details) == ["effect2d-blur", "effect2d-edge"]
    assert bench.presentation() == "headless"
    assert bench.warnings() == []
    env = bench.environment()
    assert env["driver"] == "RADV 26.2.3"
    assert "uuid" not in " ".join(env).lower()


@pytest.mark.parametrize(("env", "winsys"), [(WAYLAND, "wayland"), (X11, "xcb")])
def test_vkmark_window_fallback_requests_immediate(fake_tools, env, winsys) -> None:
    tools = fake_tools(outputs={"vkmark": tool_output("vkmark_wayland_immediate.txt")}, env=env)
    bench = Vkmark()
    bench.run()
    cmd = tools.calls[0]
    assert cmd[1:3] == ["--winsys", winsys]
    assert cmd[cmd.index("--present-mode") + 1] == "immediate"
    assert bench.presentation() == "immediate-requested"
    assert bench.warnings() == [BenchWarning.VSYNC_UNVERIFIED]


def test_vkmark_availability(fake_tools) -> None:
    assert Vkmark().availability() is Availability.TOOL_MISSING
    fake_tools(outputs={"vkmark": ""}, env={})
    assert Vkmark().availability() is Availability.NO_DISPLAY
    fake_tools(outputs={"vkmark": ""}, env={}, files=HEADLESS_PLUGIN)
    assert Vkmark().availability() is Availability.AVAILABLE


# --- à travers le runner -----------------------------------------------------------------


def test_runner_records_tool_version_and_presentation(fake_tools) -> None:
    fake_tools(outputs={"vkmark": tool_output("vkmark_wayland_immediate.txt")}, env=WAYLAND)
    result = run_benchmark(Vkmark(), RunSettings(max_warmup_s=0), probe=lambda: COOL)
    assert (result.tool_version, result.presentation) == ("2025.01", "immediate-requested")
    assert result.backend_id.presentation == "immediate-requested"
    assert BenchWarning.VSYNC_UNVERIFIED in result.warnings
    assert result.environment["renderer"] == "AMD Radeon RX 9070 XT (RADV GFX1201)"
