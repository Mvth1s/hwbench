"""python -m hwbench.leaderboard validate FICHIERS… | site [--results DIR] [--out DIR]
| summary [--results DIR] [--new FICHIERS…]"""

import argparse
import json
import os
import sys
from pathlib import Path

from hwbench.leaderboard.site import build_site, load_entries, ranking
from hwbench.leaderboard.validate import validate_file
from hwbench.scoring import load_reference


def _annotation(text: str) -> str:
    """Message d'une commande de workflow GitHub (::error::) : une seule ligne, % échappé."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


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
            # Sous GitHub Actions, chaque problème devient aussi une annotation du job : la
            # notification Discord du refus les relit par l'API (aucun accès aux journaux).
            if os.environ.get("GITHUB_ACTIONS") == "true":
                for problem in problems:
                    message = _annotation(f"{path} : {problem}")
                    print(f"::error title=Soumission refusée::{message}")
        else:
            print(f"✓ {path}")
    if failed:
        print(f"\n{failed} fichier(s) refusé(s) sur {len(files)}.", file=sys.stderr)
    return 1 if failed else 0


def _site(results: Path, out: Path) -> int:
    reference = load_reference()
    if reference is None:
        print("Erreur : pas de référence dans le paquet.", file=sys.stderr)
        return 2
    entries = build_site(results, out, reference)
    print(f"Site écrit dans {out} ({len(entries)} machine(s)).")
    return 0


def _summary(results: Path, new: list[Path] | None) -> int:
    """JSON sur la sortie standard : rang au classement combiné de chaque machine (ou des seules
    machines de --new), pour les notifications. Les machines sans combiné complet ont un rang nul.
    """
    reference = load_reference()
    if reference is None:
        print("Erreur : pas de référence dans le paquet.", file=sys.stderr)
        return 2
    entries, _ = load_entries(results, reference)
    ranked = ranking(entries, None)
    ranks = {entry.slug: (i, points) for i, (entry, points) in enumerate(ranked, 1)}
    wanted = None if new is None else {path.stem for path in new}
    machines = [
        {
            "slug": entry.slug,
            "machine": entry.export.machine,
            "combined": ranks[entry.slug][1] if entry.slug in ranks else None,
            "rank": ranks[entry.slug][0] if entry.slug in ranks else None,
        }
        for entry in entries
        if wanted is None or entry.slug in wanted
    ]
    print(json.dumps({"ranked": len(ranked), "machines": machines}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hwbench.leaderboard")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="valide des exports soumis au classement")
    v.add_argument("files", nargs="+", type=Path)
    site = sub.add_parser("site", help="génère le site statique du classement")
    site.add_argument("--results", type=Path, default=Path("results"))
    site.add_argument("--out", type=Path, default=Path("_site"))
    summary = sub.add_parser("summary", help="rangs au classement combiné, en JSON")
    summary.add_argument("--results", type=Path, default=Path("results"))
    summary.add_argument("--new", nargs="+", type=Path, help="seulement ces fichiers")
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate(args.files)
    if args.command == "summary":
        return _summary(args.results, args.new)
    return _site(args.results, args.out)


if __name__ == "__main__":
    sys.exit(main())
