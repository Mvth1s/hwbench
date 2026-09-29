"""vkmark (Vulkan) : plugin headless (aucune présentation) si installé, sinon fenêtre en
mode de présentation « immediate », demandé mais non vérifiable (vkmark ne l'affiche pas).
"""

import re
from dataclasses import dataclass

from hwbench.benchmarks.base import Benchmark, register
from hwbench.benchmarks.external import _gpu, _run
from hwbench.results import Availability, BenchWarning, Category, Measurement

VKMARK_VERSION = "1"  # à incrémenter si les scènes, leur durée ou la résolution changent

SCENES = (
    "vertex",
    "texture",
    "shading:shading=gouraud",
    "shading:shading=phong",
    "effect2d",
    "desktop",
    "cube",
    "clear",
)

# vkmark n'expose pas son dossier de plugins : emplacements des paquets usuels.
PLUGIN_DIRS = (
    "/usr/lib/vkmark",
    "/usr/lib64/vkmark",
    "/usr/lib/x86_64-linux-gnu/vkmark",
    "/usr/lib/aarch64-linux-gnu/vkmark",
    "/usr/local/lib/vkmark",
    "/usr/local/lib64/vkmark",
)
WINSYS_BY_SESSION = {"wayland": "wayland", "x11": "xcb"}

_VERSION_RE = re.compile(r"^\s*vkmark\s+(\S+)\s*$", re.M)
# Device UUID volontairement absent : identifiant du GPU, jamais relevé.
_HEADER_RE = re.compile(r"^\s*(Vendor ID|Device Name|Driver Version):\s*(.+?)\s*$", re.M)
_SCENE_RE = re.compile(r"^\[(\w+)\]\s.*?FPS:\s*(\d+(?:\.\d+)?)", re.M)
_SCORE_RE = re.compile(r"vkmark Score:\s*(\d+(?:\.\d+)?)")
_DRIVER_NAME_RE = re.compile(r"\((\w+)[^)]*\)\s*$")


@dataclass(frozen=True)
class VkmarkOutput:
    version: str | None
    vendor_id: int | None
    device_name: str | None
    driver_version: int | None
    scene_fps: list[tuple[str, float]]
    score: float


def _int(value: str | None, base: int = 10) -> int | None:
    try:
        return int(value, base) if value is not None else None
    except ValueError:
        return None


def parse_output(text: str) -> VkmarkOutput:
    score = _SCORE_RE.search(text)
    if not score:
        raise _run.ToolError("vkmark : « vkmark Score » introuvable dans la sortie")
    header = dict(_HEADER_RE.findall(text))
    version = _VERSION_RE.search(text)
    return VkmarkOutput(
        version=version.group(1) if version else None,
        vendor_id=_int(header.get("Vendor ID"), 16),
        device_name=header.get("Device Name"),
        driver_version=_int(header.get("Driver Version")),
        scene_fps=[(name, float(fps)) for name, fps in _SCENE_RE.findall(text)],
        score=float(score.group(1)),
    )


def vulkan_driver(out: VkmarkOutput) -> str | None:
    """« AMD Radeon RX 9070 XT (RADV GFX1201) » + 109060099 -> « RADV 26.2.3 »."""
    version = _gpu.vulkan_driver_version(out.vendor_id, out.driver_version)
    match = _DRIVER_NAME_RE.search(out.device_name or "")
    name = match.group(1) if match else None
    parts = [p for p in (name, version) if p]
    return " ".join(parts) or None


def has_headless_plugin() -> bool:
    return any(_run.exists(f"{d}/headless.so") for d in PLUGIN_DIRS)


@register
class Vkmark(Benchmark):
    name = "vkmark"
    category = Category.GPU
    backend = "vkmark"
    version = VKMARK_VERSION
    unit = "fps"
    detail_units = {scene: "fps" for scene in SCENES}

    def __init__(self, options=None) -> None:
        super().__init__(options)
        self._last: VkmarkOutput | None = None
        self._headless = has_headless_plugin()
        self._session = _gpu.display_session()

    def availability(self) -> Availability:
        if not _run.which("vkmark"):
            return Availability.TOOL_MISSING
        if not self._headless and self._session not in WINSYS_BY_SESSION:
            return Availability.NO_DISPLAY
        return Availability.AVAILABLE

    @property
    def winsys(self) -> str:
        return "headless" if self._headless else WINSYS_BY_SESSION[self._session or ""]

    def command(self) -> list[str]:
        args = ["vkmark", "--winsys", self.winsys, "--size", _gpu.RESOLUTION]
        if not self._headless:
            # à l'écran : on demande « immediate » (sans vsync), sans pouvoir le vérifier
            args += ["--present-mode", "immediate"]
        return args + _gpu.scene_args(SCENES)

    def run(self) -> Measurement:
        text = _run.output_or_raise(self.command(), timeout=_gpu.TIMEOUT_S)
        out = parse_output(text)
        if len(out.scene_fps) != len(SCENES):
            raise _run.ToolError(
                f"vkmark : {len(out.scene_fps)} scènes mesurées sur {len(SCENES)} attendues"
            )
        self._last = out
        return Measurement(
            value=out.score,
            duration_s=float(len(SCENES) * _gpu.SCENE_SECONDS),
            details={scene: fps for scene, (_, fps) in zip(SCENES, out.scene_fps, strict=True)},
        )

    def tool_version(self) -> str | None:
        return self._last.version if self._last else None

    def environment(self) -> dict[str, str]:
        env = {
            "binary": "vkmark",
            "session": self.winsys,
            "resolution": _gpu.RESOLUTION,
            "presentation": "headless" if self._headless else "immediate-requested",
        }
        if self._last:
            if self._last.device_name:
                env["renderer"] = self._last.device_name
            if driver := vulkan_driver(self._last):
                env["driver"] = driver
        return env

    def warnings(self) -> list[BenchWarning]:
        warnings: list[BenchWarning] = []
        if not self._headless:
            warnings.append(BenchWarning.VSYNC_UNVERIFIED)
        if self._last and _gpu.is_software_renderer(self._last.device_name):
            warnings.append(BenchWarning.SOFTWARE_RENDERING)
        return warnings
