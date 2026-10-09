"""Libellés français affichés : une seule table, partagée par le terminal (display/), le rapport
(report/) et le site du classement (leaderboard/). Les modèles et le JSON gardent les valeurs
brutes ; seuls ces libellés sont traduits.
"""

from hwbench.results import Category

CATEGORY_LABELS = {
    Category.CPU_SINGLE: "CPU single-core",
    Category.CPU_MULTI: "CPU multi-core",
    Category.GPU: "GPU",
    Category.MEMORY: "Mémoire",
    Category.DISK: "Disque",
}

# Noms lisibles des benchs ; un bench inconnu garde son nom technique.
BENCH_LABELS = {
    "native-cpu-single": "CPU single-core (natif)",
    "native-cpu-multi": "CPU multi-core (natif)",
    "sysbench-cpu-single": "CPU single-core (sysbench)",
    "sysbench-cpu-multi": "CPU multi-core (sysbench)",
    "glmark2": "GPU OpenGL (glmark2)",
    "vkmark": "GPU Vulkan (vkmark)",
    "native-memory-single": "Mémoire single (natif)",
    "native-memory-multi": "Mémoire multi (natif)",
    "sysbench-memory-single": "Mémoire single (sysbench)",
    "sysbench-memory-multi": "Mémoire multi (sysbench)",
    "fio-disk": "Disque (fio)",
}

DETAIL_LABELS = {
    "sha256": "SHA-256",
    "zlib": "Compression zlib (niveau 6)",
    "lzma": "Compression LZMA (preset 1)",
    "powmod": "Exponentiation modulaire 2048 bits",
    "seq_read": "Lecture séquentielle (1 Mio, QD8)",
    "seq_write": "Écriture séquentielle (1 Mio, QD8)",
    "rand_read_4k": "Lecture aléatoire 4K (QD32)",
    "rand_write_4k": "Écriture aléatoire 4K (QD32)",
}

# « index » : moyenne géométrique de débits, sans unité. Les points (référence = 1000) sont
# calculés par le scoring et affichés à part.
UNIT_LABELS = {"MiB/s": "Mio/s", "index": "indice brut"}

PROFILE_LABELS = {"platform_profile": "profil plateforme", "energy_performance_preference": "EPP"}

# Conditions des benchs externes : libellé français devant la valeur brute.
ENVIRONMENT_LABELS = {
    "binary": "binaire",
    "session": "session",
    "resolution": "résolution",
    "renderer": "rendu",
    "driver": "pilote",
    "cpu-max-prime": "cpu-max-prime",
    "time": "durée",
    "block-size": "bloc",
    "operation": "opération",
    "filesystem": "système de fichiers",
    "device": "disque",
    "ioengine": "moteur d'E/S",
}

PRESENTATION_LABELS = {
    "offscreen": "hors écran (sans vsync)",
    "headless": "headless, sans affichage (sans vsync)",
    "immediate-requested": "fenêtre, mode immediate demandé (non vérifiable)",
}


def bench_label(name: str) -> str:
    return BENCH_LABELS.get(name, name)


def unit_label(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


def disk_size_label(presentation: str) -> str:
    """« 1GiB » -> « 1 Gio », « 512MiB » -> « 512 Mio » (taille du fichier du bench disque)."""
    for suffix, label in (("GiB", "Gio"), ("MiB", "Mio")):
        if presentation.endswith(suffix):
            return f"{presentation.removesuffix(suffix)} {label}"
    return presentation
