"""Conditions communes des benchs GPU : session graphique, résolution, pilote."""

import re

from hwbench.benchmarks.external import _run

# Résolution fixe : le score dépend du nombre de pixels, pas de l'écran de la machine.
RESOLUTION = "1920x1080"
SCENE_SECONDS = 2
TIMEOUT_S = 600

_MESA_RE = re.compile(r"(Mesa \S+)")
_SOFTWARE_RE = re.compile(r"llvmpipe|softpipe|lavapipe|swrast", re.I)


def display_session() -> str | None:
    """« wayland », « x11 » ou None (console, SSH) selon les sockets réellement joignables."""
    if _run.getenv("WAYLAND_DISPLAY"):
        return "wayland"
    if _run.getenv("DISPLAY"):
        return "x11"
    return None


def gl_driver(gl_version: str | None) -> str | None:
    """« 4.6 (Compatibility Profile) Mesa 26.2.3-arch1.1 » -> « Mesa 26.2.3-arch1.1 »."""
    if not gl_version:
        return None
    match = _MESA_RE.search(gl_version)
    if match:
        return match.group(1)
    # NVIDIA propriétaire : « 4.6.0 NVIDIA 550.54.14 »
    parts = gl_version.split(maxsplit=1)
    return parts[1] if len(parts) == 2 else gl_version


def vulkan_driver_version(vendor_id: int | None, raw: int | None) -> str | None:
    """driverVersion Vulkan : encodage propre à chaque fabricant.

    Mesa (RADV, ANV, NVK…) utilise VK_MAKE_VERSION : 10 bits / 10 bits / 12 bits.
    NVIDIA : 10 / 8 / 8 bits (+ 6 bits de build ignorés).
    """
    if raw is None:
        return None
    if vendor_id == 0x10DE:
        return f"{raw >> 22}.{(raw >> 14) & 0xFF}.{(raw >> 6) & 0xFF}"
    return f"{raw >> 22}.{(raw >> 12) & 0x3FF}.{raw & 0xFFF}"


def is_software_renderer(name: str | None) -> bool:
    return bool(name and _SOFTWARE_RE.search(name))


def scene_args(scenes: tuple[str, ...], seconds: int = SCENE_SECONDS) -> list[str]:
    args: list[str] = []
    for scene in scenes:
        args += ["-b", f"{scene}:duration={seconds}"]
    return args
