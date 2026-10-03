"""Captures SVG des commandes pour le README (docs/images/), à partir de leur vraie sortie.

Usage : .venv/bin/python scripts/readme_screenshots.py info|bench|compare [args…]
  info              hwbench info
  bench             hwbench bench --backend native
  compare A B       hwbench compare A B (exports de `hwbench export`)

La sortie colorée (ANSI) est relue par rich et enregistrée en SVG : aucun identifiant n'y entre
(pas de --show-serials) ; vérifier quand même le fichier avant de le committer.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

WIDTH = 100
OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
HWBENCH = Path(sys.executable).parent / "hwbench"

# Ligne d'état transitoire (spinner rich) : un vrai terminal l'efface, une capture la garde
# à chaque image. « CPU single-core · native : warm-up 2 (plafond 30 s)… »
STATUS_LINE = re.compile(r" : (préparation|warm-up \d+ \(plafond [^)]*\)|run \d+/\d+)…\s*$")

COMMANDS = {
    "info": (["info"], "hwbench info"),
    "bench": (["bench", "--backend", "native"], "hwbench bench --backend native"),
    "compare": (["compare"], "hwbench compare"),
}


def main() -> None:
    name, extra = sys.argv[1], sys.argv[2:]
    args, title = COMMANDS[name]
    env = os.environ | {"FORCE_COLOR": "1", "TERM": "xterm-256color", "COLUMNS": str(WIDTH)}
    proc = subprocess.run(
        [str(HWBENCH), *args, *extra], env=env, capture_output=True, text=True, check=True
    )
    console = Console(record=True, width=WIDTH, file=open(os.devnull, "w"))  # noqa: SIM115
    lines = [
        line
        for line in proc.stdout.splitlines()
        if not STATUS_LINE.search(Text.from_ansi(line).plain)
    ]
    console.print(Text.from_ansi("\n".join(lines)))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.svg"
    console.save_svg(str(path), title=" ".join([title, *(Path(a).name for a in extra)]))
    print(path)


if __name__ == "__main__":
    main()
