"""Décodage des fabricants de mémoire JEDEC JEP106 (banque + code, bit de parité inclus)."""

import re

JEDEC_MANUFACTURERS: dict[tuple[int, int], str] = {
    (1, 0x2C): "Micron",
    (1, 0xAD): "SK Hynix",
    (1, 0xCE): "Samsung",
    (2, 0x4F): "Transcend",
    (2, 0x98): "Kingston",
    (3, 0x9E): "Corsair",
    (4, 0x0B): "Nanya",
    (5, 0xCB): "ADATA",
    (5, 0xCD): "G.Skill",
    (5, 0xEF): "Team Group",
    (6, 0x02): "Patriot",
    (6, 0x9B): "Crucial",
}

_MODULE_ID_RE = re.compile(r"Bank\s+(\d+),\s*Hex\s+0x([0-9a-f]{2})", re.IGNORECASE)
_RAW_HEX_RE = re.compile(r"^([0-9a-f]{2})([0-9a-f]{2})(?:[0-9a-f]{2})*$", re.IGNORECASE)


def from_module_id(value: str | None) -> str | None:
    """« Bank 2, Hex 0x98 » (champ Module Manufacturer ID de dmidecode)."""
    match = _MODULE_ID_RE.search(value or "")
    if not match:
        return None
    return JEDEC_MANUFACTURERS.get((int(match.group(1)), int(match.group(2), 16)))


def from_raw_code(value: str | None) -> str | None:
    """« 01980000802C » : 1er octet = nb de codes de continuation (bit 7 = parité), 2e = code."""
    match = _RAW_HEX_RE.match((value or "").strip())
    if not match:
        return None
    bank = (int(match.group(1), 16) & 0x7F) + 1
    return JEDEC_MANUFACTURERS.get((bank, int(match.group(2), 16)))


def manufacturer_name(module_id: str | None, raw: str | None) -> str | None:
    """Nom lisible si le code est connu, sinon la valeur brute telle quelle."""
    return from_module_id(module_id) or from_raw_code(raw) or raw
