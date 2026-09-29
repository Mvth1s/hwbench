"""Filet de sécurité appliqué à toute sortie JSON.

Les collecteurs ne placent déjà aucun identifiant dans MachineSnapshot ; ce module
rattrape ce qui passerait quand même (nouveau champ, régression, sortie d'outil brute).
"""

import re
from typing import Any

REDACTED = "[redacted]"

SENSITIVE_KEY_RE = re.compile(
    r"(serial|uuid|guid|nguid|eui|wwn|asset_?tag|hostname|mac_?addr|mac$)", re.IGNORECASE
)

SENSITIVE_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # adresse MAC
    re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.IGNORECASE),
    # UUID
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),
    # EUI-64 / NGUID / WWN en hexadécimal long (16 ou 32 chiffres, éventuellement séparés)
    re.compile(r"\b(?:eui\.|naa\.)?[0-9a-f]{16}(?:[0-9a-f]{16})?\b", re.IGNORECASE),
)


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(key))


def scrub_string(value: str) -> str:
    for pattern in SENSITIVE_VALUE_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: (REDACTED if is_sensitive_key(str(k)) and v is not None else scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list | tuple):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return scrub_string(obj)
    return obj
