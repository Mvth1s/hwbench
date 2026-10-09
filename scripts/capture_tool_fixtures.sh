#!/usr/bin/env bash
# Capture les sorties réelles de sysbench, glmark2 et vkmark pour tests/fixtures/tools/.
#
# Usage : scripts/capture_tool_fixtures.sh   (sans sudo, depuis une session graphique)
#   Les lignes de commande viennent des backends eux-mêmes (hwbench.benchmarks.external),
#   seules les durées sont raccourcies (scènes 1 s, sysbench memory 2 s, fio 1 s par test sur
#   un fichier de 64 Mio, supprimé ensuite) : les fixtures suivent le vrai protocole.
#   L'UUID du GPU affiché par vkmark (« Device UUID ») est remplacé par des zéros.
#
# Bash obligatoire : les tableaux gardent intacts les arguments contenant « ; » ou « : ».
set -euo pipefail
export LC_ALL=C

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/tests/fixtures/tools"
PYTHON="$REPO/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
mkdir -p "$OUT"

have() { command -v "$1" >/dev/null 2>&1; }

# Ligne de commande d'un backend, un argument par ligne, durées raccourcies.
backend_command() {
    "$PYTHON" - "$1" <<'EOF'
import sys
from hwbench.benchmarks.external.glmark2 import Glmark2
from hwbench.benchmarks.external.sysbench import SysbenchMemoryMulti, SysbenchMemorySingle
from hwbench.benchmarks.external.vkmark import Vkmark
from hwbench.benchmarks.base import BenchOptions
from hwbench.benchmarks.external.fio import Fio
if sys.argv[1] == "fio":
    # fichier de 64 Mio, nom relatif (lancé depuis son dossier) : aucun chemin personnel
    for arg in Fio(BenchOptions(disk_size=64 * 1024**2)).command(sys.argv[2]):
        print(arg.replace("--runtime=2", "--runtime=1"))
    sys.exit()
bench = {
    "glmark2": Glmark2,
    "vkmark": Vkmark,
    "sysbench-memory-single": SysbenchMemorySingle,
    "sysbench-memory-multi": SysbenchMemoryMulti,
}[sys.argv[1]]()
for arg in bench.command():
    print(arg.replace(":duration=3", ":duration=1").replace("--time=5", "--time=2"))
EOF
}

# capture <fichier> <commande...>
capture() {
    local out="$1"; shift
    if have "$1"; then
        "$@" >"$OUT/$out" 2>&1 || echo "  !!  $out : code $? (sortie conservée)"
        echo "  ok  $out"
    else
        echo "  --  $out (absent : $1)"
    fi
}

echo "sysbench :"
capture sysbench_cpu_1thread.txt sysbench cpu --threads=1 --time=2 --cpu-max-prime=10000 run
capture sysbench_cpu_multi.txt sysbench cpu --threads="$(nproc)" --time=2 --cpu-max-prime=10000 run
mapfile -t cmd < <(backend_command sysbench-memory-single)
capture sysbench_memory_1thread.txt "${cmd[@]}"
mapfile -t cmd < <(backend_command sysbench-memory-multi)
capture sysbench_memory_multi.txt "${cmd[@]}"

echo "glmark2 (binaire choisi selon la session) :"
mapfile -t cmd < <(backend_command glmark2)
capture "${cmd[0]}_offscreen.txt" "${cmd[@]}"
if [[ "${cmd[0]}" != glmark2 && -n "${DISPLAY:-}" ]]; then
    # variante X11 (XWayland) : même protocole, autre binaire
    capture glmark2_offscreen.txt glmark2 "${cmd[@]:1}"
fi

echo "vkmark :"
mapfile -t cmd < <(backend_command vkmark)
capture vkmark_headless.txt "${cmd[@]}"
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
    # repli sans plugin headless : fenêtre Wayland, mode immediate demandé
    scenes=()
    for arg in "${cmd[@]}"; do [[ "$arg" == effect2d:* ]] && scenes+=(-b "$arg"); done
    capture vkmark_wayland_immediate.txt vkmark --winsys wayland --present-mode immediate \
        --size 3840x2160 "${scenes[@]}"
fi

echo "fio (fichier de 64 Mio dans ~/.cache/hwbench, supprimé ensuite) :"
# pas /tmp : souvent un tmpfs, qui refuse les E/S directes (direct=1)
FIO_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/hwbench"
FIO_FILE="hwbench-fio-capture.tmp"
mkdir -p "$FIO_DIR"
mapfile -t cmd < <(backend_command fio "$FIO_FILE")
(cd "$FIO_DIR" && capture fio_disk.json "${cmd[@]}")
rm -f -- "$FIO_DIR/$FIO_FILE"
# système de fichiers et disque sous ce dossier (sorties JSON, sans serial)
capture findmnt_cache.json findmnt -J -T "$FIO_DIR" -o SOURCE,FSTYPE
source="$(findmnt -n -T "$FIO_DIR" -o SOURCE | sed 's/\[.*\]$//')"
capture lsblk_inverse.json lsblk -J -s -o NAME,MODEL,TYPE "$source"

sed -i -E 's/(Device UUID: +)[0-9a-fA-F]{32}/\100000000000000000000000000000000/' "$OUT"/vkmark_*.txt
echo "Fixtures écrites dans $OUT"
