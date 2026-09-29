"""Seul point d'accès au système pour les backends externes. Les tests mockent ce module.

Pendant de collectors/linux/_exec.py, mais un bench qui échoue doit le dire : run() lève
ToolError au lieu de renvoyer None.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


def which(name: str) -> str | None:
    return shutil.which(name)


def getenv(name: str) -> str | None:
    return os.environ.get(name) or None


def exists(path: str) -> bool:
    return Path(path).exists()


def run(args: list[str], timeout: float) -> Completed:
    # LC_ALL=C : sinon une locale fr_FR produit des virgules décimales.
    env = {**os.environ, "LC_ALL": "C"}
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{args[0]} : pas de réponse après {timeout:.0f} s") from exc
    except OSError as exc:
        raise ToolError(f"{args[0]} : {exc}") from exc
    return Completed(proc.returncode, proc.stdout, proc.stderr)


def output_or_raise(args: list[str], timeout: float) -> str:
    """Sortie standard, ou ToolError avec la fin de stderr si l'outil échoue."""
    done = run(args, timeout)
    if done.returncode != 0:
        tail = " / ".join((done.stderr or done.stdout).strip().splitlines()[-3:])
        raise ToolError(f"{args[0]} a échoué (code {done.returncode}) : {tail}")
    return done.stdout
