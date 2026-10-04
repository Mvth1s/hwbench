"""python -m hwbench.leaderboard validate FICHIERS… | site [--results DIR] [--out DIR]"""

import argparse
import sys
from pathlib import Path

from hwbench.leaderboard.validate import validate_file
from hwbench.scoring import load_reference


def _validate(files: list[Path]) -> int:
    reference = load_reference()
    if reference is None:
        print("Erreur : pas de référence dans le paquet.", file=sys.stderr)
        return 2
    failed = 0
    for path in files:
        problems = validate_file(path, reference)
        if problems:
            failed += 1
            print(f"✗ {path}")
            for problem in problems:
                print(f"    - {problem}")
        else:
            print(f"✓ {path}")
    if failed:
        print(f"\n{failed} fichier(s) refusé(s) sur {len(files)}.", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hwbench.leaderboard")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="valide des exports soumis au classement")
    v.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.files)
    return 2


if __name__ == "__main__":
    sys.exit(main())
