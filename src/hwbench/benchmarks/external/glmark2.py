"""glmark2 (OpenGL 2.0) : rendu hors écran, résolution fixe, binaire adapté à la session."""

import re
from dataclasses import dataclass

from hwbench.benchmarks.base import Benchmark, register
from hwbench.benchmarks.external import _gpu, _run
from hwbench.results import Availability, BenchWarning, Category, Measurement

GLMARK2_VERSION = "1"  # à incrémenter si les scènes, leur durée ou la résolution changent

# Sous-ensemble fixe des scènes par défaut de glmark2 (une variante par scène).
SCENES = (
    "build:use-vbo=true",
    "texture:texture-filter=linear",
    "shading:shading=phong",
    "bump:bump-render=high-poly",
    "effect2d",
    "pulsar",
    "desktop",
    "jellyfish",
    "terrain",
    "refract",
)

# Binaires par session, par ordre de préférence. Sous Wayland, glmark2 (X11) passe par
# XWayland : acceptable en repli, et relevé dans le résultat.
BINARIES: dict[str | None, tuple[tuple[str, str], ...]] = {
    "wayland": (("glmark2-wayland", "wayland"), ("glmark2", "x11")),
    "x11": (("glmark2", "x11"),),
    None: (("glmark2-drm", "drm"),),
}
ALL_BINARIES = ("glmark2-wayland", "glmark2", "glmark2-drm")

_VERSION_RE = re.compile(r"^\s*glmark2\s+(\S+)\s*$", re.M)
_HEADER_RE = re.compile(r"^\s*(GL_VENDOR|GL_RENDERER|GL_VERSION|Surface Size):\s*(.+?)\s*$", re.M)
_SCENE_RE = re.compile(r"^\[(\w+)\]\s.*?FPS:\s*(\d+(?:\.\d+)?)", re.M)
_SCORE_RE = re.compile(r"glmark2 Score:\s*(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Glmark2Output:
    version: str | None
    renderer: str | None
    gl_version: str | None
    scene_fps: list[tuple[str, float]]
    score: float


def parse_output(text: str) -> Glmark2Output:
    score = _SCORE_RE.search(text)
    if not score:
        raise _run.ToolError("glmark2 : « glmark2 Score » introuvable dans la sortie")
    header = dict(_HEADER_RE.findall(text))
    version = _VERSION_RE.search(text)
    return Glmark2Output(
        version=version.group(1) if version else None,
        renderer=header.get("GL_RENDERER"),
        gl_version=header.get("GL_VERSION"),
        scene_fps=[(name, float(fps)) for name, fps in _SCENE_RE.findall(text)],
        score=float(score.group(1)),
    )


def choose_binary() -> tuple[str, str] | None:
    """(binaire, plateforme) adapté à la session courante, ou None."""
    for binary, platform in BINARIES[_gpu.display_session()]:
        if _run.which(binary):
            return binary, platform
    return None


@register
class Glmark2(Benchmark):
    name = "glmark2"
    category = Category.GPU
    backend = "glmark2"
    version = GLMARK2_VERSION
    unit = "fps"
    detail_units = {scene: "fps" for scene in SCENES}

    def __init__(self, options=None) -> None:
        super().__init__(options)
        self._last: Glmark2Output | None = None
        self._binary = choose_binary()

    def availability(self) -> Availability:
        if self._binary is not None:
            return Availability.AVAILABLE
        if any(_run.which(b) for b in ALL_BINARIES):
            return Availability.NO_DISPLAY
        return Availability.TOOL_MISSING

    def command(self) -> list[str]:
        if self._binary is None:
            raise _run.ToolError("glmark2 : aucun binaire adapté à la session")
        # --off-screen : rendu dans un FBO, jamais présenté -> pas de vsync, pas de fenêtre
        return [
            self._binary[0],
            "--off-screen",
            "--size",
            _gpu.RESOLUTION,
            *_gpu.scene_args(SCENES),
        ]

    def run(self) -> Measurement:
        text = _run.output_or_raise(self.command(), timeout=_gpu.TIMEOUT_S)
        out = parse_output(text)
        if len(out.scene_fps) != len(SCENES):
            raise _run.ToolError(
                f"glmark2 : {len(out.scene_fps)} scènes mesurées sur {len(SCENES)} attendues"
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
        env = {"resolution": _gpu.RESOLUTION, "presentation": "offscreen"}
        if self._binary:
            env |= {"binary": self._binary[0], "session": self._binary[1]}
        if self._last:
            if self._last.renderer:
                env["renderer"] = self._last.renderer
            if driver := _gpu.gl_driver(self._last.gl_version):
                env["driver"] = driver
        return env

    def warnings(self) -> list[BenchWarning]:
        if self._last and _gpu.is_software_renderer(self._last.renderer):
            return [BenchWarning.SOFTWARE_RENDERING]
        return []
