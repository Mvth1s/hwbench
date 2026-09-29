"""Charges CPU déterministes : mêmes entrées sur toutes les machines, travail fixe.

Le temps est dominé par du code C (OpenSSL, zlib, liblzma, entiers longs de CPython) pour
limiter l'effet de la version de l'interpréteur. Toute modification des paramètres ou des
entrées change l'empreinte (`fingerprint`) et impose d'incrémenter la version du bench.
"""

import hashlib
import lzma
import random
import zlib
from dataclasses import dataclass
from typing import Any

SEED = 0x687762656E6368  # « hwbench »
MIB = 1024 * 1024


def random_bytes(size: int, seed: int) -> bytes:
    return random.Random(seed).randbytes(size)


def text_like(size: int, seed: int) -> bytes:
    """Texte pseudo-aléatoire compressible (vocabulaire fixe), pour zlib et lzma."""
    rng = random.Random(seed)
    letters = "abcdefghijklmnopqrstuvwxyz"
    vocabulary = ["".join(rng.choices(letters, k=rng.randint(2, 10))) for _ in range(4096)]
    words = rng.choices(vocabulary, k=size // 4)
    return " ".join(words).encode()[:size]


@dataclass(frozen=True)
class Workload:
    key: str
    unit: str
    size: int
    repeat: int

    def prepare(self) -> Any:
        match self.key:
            case "sha256":
                return random_bytes(self.size, SEED)
            case "zlib" | "lzma":
                return text_like(self.size, SEED + 1)
            case "powmod":
                rng = random.Random(SEED + 2)
                bits = self.size
                modulus = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
                return rng.getrandbits(bits) % modulus, rng.getrandbits(bits), modulus
        raise ValueError(f"charge inconnue : {self.key}")

    def execute(self, data: Any) -> float:
        """Exécute la charge ; renvoie la quantité de travail dans l'unité de `unit`."""
        match self.key:
            case "sha256":
                for _ in range(self.repeat):
                    hashlib.sha256(data).digest()
                return self.repeat * len(data) / MIB
            case "zlib":
                for _ in range(self.repeat):
                    zlib.compress(data, 6)
                return self.repeat * len(data) / MIB
            case "lzma":
                for _ in range(self.repeat):
                    lzma.compress(data, preset=1)
                return self.repeat * len(data) / MIB
            case "powmod":
                base, exponent, modulus = data
                for _ in range(self.repeat):
                    pow(base, exponent, modulus)
                return float(self.repeat)
        raise ValueError(f"charge inconnue : {self.key}")


WORKLOADS: tuple[Workload, ...] = (
    # ~0,4 s chacune sur un i5-1145G7 ; entrées ≤ 4 Mio pour limiter la mémoire en multi-cœur
    Workload("sha256", "MiB/s", size=4 * MIB, repeat=160),
    Workload("zlib", "MiB/s", size=4 * MIB, repeat=8),
    Workload("lzma", "MiB/s", size=1 * MIB, repeat=6),
    Workload("powmod", "op/s", size=2048, repeat=16),
)


def fingerprint(workloads: tuple[Workload, ...]) -> str:
    digest = hashlib.sha256()
    for w in workloads:
        digest.update(repr((w.key, w.unit, w.size, w.repeat)).encode())
        digest.update(repr(w.prepare()).encode() if w.key == "powmod" else w.prepare())
    return digest.hexdigest()
