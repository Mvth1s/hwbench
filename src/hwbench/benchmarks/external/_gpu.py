"""Conditions communes des benchs GPU : session graphique, résolution, scènes, pilote.

Choix des scènes (étude du 2026-09-29, RX 9070 XT, Mesa 26.2.3, rendu hors écran) : une scène
n'est gardée que si son FPS baisse d'au moins x1,8 entre 1080p et 4K (4 fois plus de pixels),
c'est-à-dire si son coût suit le nombre de pixels : elle mesure le GPU, pas le CPU ni le pilote.
Les scènes simples de glmark2 (build, texture, shading, bump) plafonnent vers 15 000 FPS en
1080p quelle que soit la scène (x1,1 à x1,6) ; celles de vkmark vers 35 000 (x1,0 à x1,5).
Détail des mesures dans le README (« Choix des scènes GPU »).
"""

import re

from hwbench.benchmarks.external import _run

# Résolution fixe et élevée : le score dépend du GPU, pas de l'écran de la machine.
RESOLUTION = "3840x2160"
SCENE_SECONDS = 3
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


def scene_args(scenes: dict[str, str], seconds: int = SCENE_SECONDS) -> list[str]:
    """scenes : clé courte -> description « scène(:option=valeur)* » de l'outil."""
    args: list[str] = []
    for spec in scenes.values():
        args += ["-b", f"{spec}:duration={seconds}"]
    return args
