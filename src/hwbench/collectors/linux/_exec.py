"""Seul point d'accès au système pour les collecteurs Linux. Les tests mockent ce module."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 10.0


def which(name: str) -> str | None:
    return shutil.which(name)


def is_root() -> bool:
    return os.geteuid() == 0


def run_text(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> str | None:
    if which(args[0]) is None:
        return None
    # LC_ALL=C : sinon une locale fr_FR produit des virgules décimales (« 4400,0000 »).
    env = {**os.environ, "LC_ALL": "C"}
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 and not proc.stdout:
        return None
    return proc.stdout


def run_json(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> Any | None:
    text = run_text(args, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def read_sysfs(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return None


def exists(path: str | Path) -> bool:
    """Distingue un fichier absent d'un fichier présent mais illisible (droits)."""
    return Path(path).exists()


def link_name(path: str | Path) -> str | None:
    """Nom de la cible d'un lien sysfs (ex. hwmonN/device -> « nvme0 »), None si absent."""
    try:
        return Path(path).resolve(strict=True).name
    except OSError:
        return None


def list_dir(path: str | Path) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []
