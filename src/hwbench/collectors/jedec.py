"""Décodage des fabricants de mémoire JEDEC JEP106 (banque + code, bit de parité inclus)."""

import re

# Source de chaque entrée : JEP106BB (JEDEC, 2020), lue dans sa transcription par i2c-tools
# (eeprom/decode-dimms, commit « Update the list of vendors to Jedec JEP106BB », livré
# dans i2c-tools 4.2 à 4.4). Table indexée par banque puis par code sans bit de parité ;
# le libellé officiel figure en commentaire quand le nom affiché est abrégé.
# N'ajouter une entrée que si elle est vérifiable dans une révision JEP106 citée ici.
JEDEC_MANUFACTURERS: dict[tuple[int, int], str] = {
    (1, 0x2C): "Micron",  # JEP106BB : « Micron Technology »
    (1, 0xAD): "SK Hynix",  # JEP106BB : « SK Hynix (former Hyundai Electronics) »
    (1, 0xCE): "Samsung",  # JEP106BB : « Samsung »
    (2, 0x4F): "Transcend",  # JEP106BB : « Transcend Information »
    (2, 0x98): "Kingston",  # JEP106BB : « Kingston »
    (3, 0x9E): "Corsair",  # JEP106BB : « Corsair »
    (4, 0x0B): "Nanya",  # JEP106BB : « Nanya Technology »
    (5, 0xCB): "ADATA",  # JEP106BB : « A-DATA Technology »
    (5, 0xCD): "G.Skill",  # JEP106BB : « G Skill Intl »
    (5, 0xEF): "Team Group",  # JEP106BB : « Team Group Inc. »
    (6, 0x02): "Patriot",  # JEP106BB : « Patriot Memory » (≠ Patriot Scientific, banque 5)
    (6, 0x9B): "Crucial",  # JEP106BB : « Crucial Technology »
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
