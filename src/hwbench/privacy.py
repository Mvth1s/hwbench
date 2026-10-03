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


# Clés connues comme non sensibles, avec le format exact de leur valeur : seule une valeur
# conforme échappe au filtrage (une clé autorisée ne doit pas devenir une fuite).
NON_SENSITIVE_KEYS: dict[str, re.Pattern[str]] = {
    # empreinte du fichier de référence du scoring (sha256 du JSON canonique)
    "digest": re.compile(r"sha256:[0-9a-f]{64}"),
}


def is_allowed(key: str, value: Any) -> bool:
    pattern = NON_SENSITIVE_KEYS.get(key)
    return pattern is not None and isinstance(value, str) and pattern.fullmatch(value) is not None


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(key))


def scrub_string(value: str) -> str:
    for pattern in SENSITIVE_VALUE_PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def _scrub_item(key: str, value: Any) -> Any:
    if is_sensitive_key(key) and value is not None:
        return REDACTED
    if is_allowed(key, value):
        return value
    return scrub(value)


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _scrub_item(str(k), v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return scrub_string(obj)
    return obj
