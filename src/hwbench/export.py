"""Export JSON versionné d'une machine (composants filtrés + résultats + scores) et relecture.

La relecture reconstruit les dataclasses des modèles : compare et l'affichage ne manipulent
jamais le JSON brut. Les identifiants n'y figurent jamais (MachineSnapshot n'en contient pas) et
tout passe en plus par privacy.scrub.
"""

import dataclasses
import json
import types
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from hwbench import __version__, privacy
from hwbench.models import MachineSnapshot
from hwbench.results import Result
from hwbench.runner import RunSettings
from hwbench.scoring import BackendScore, CategoryScore, CombinedScore, ReferenceInfo, Scores

# 2 : empreinte de référence complète (sha256, 64 hex) au lieu de 12 caractères
# 3 : réglages des mesures (RunSettings : seuils, runs, warm-up) dans le champ « settings »
# 4 : refroidissement entre catégories (RunSettings.cooldown_*, Result.cooldown_s)
EXPORT_SCHEMA_VERSION = 4
# Schémas relus. Un export de schéma 2 n'a pas de réglages : settings vaut None, et le rapport
# utilise les réglages par défaut en le signalant. Schémas 2 et 3 : pas de refroidissement
# (valeurs par défaut des champs, 0 s).
READABLE_SCHEMA_VERSIONS = (2, 3, 4)


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class MachineExport:
    schema_version: int
    hwbench_version: str
    created: str  # ISO 8601, UTC
    machine: str
    snapshot: MachineSnapshot
    results: list[Result]
    reference: ReferenceInfo | None = None  # None : pas de référence au moment de l'export
    backend_scores: list[BackendScore] = field(default_factory=list)
    categories: list[CategoryScore] = field(default_factory=list)
    combined: CombinedScore | None = None
    settings: RunSettings | None = None  # None : export de schéma 2, réglages non enregistrés


def build_export(
    snapshot: MachineSnapshot,
    machine: str,
    results: list[Result],
    scores: Scores | None,
    now: datetime | None = None,
    settings: RunSettings | None = None,
) -> MachineExport:
    return MachineExport(
        schema_version=EXPORT_SCHEMA_VERSION,
        hwbench_version=__version__,
        created=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        machine=machine,
        snapshot=snapshot,
        results=results,
        reference=scores.reference.info() if scores else None,
        backend_scores=scores.backends if scores else [],
        categories=scores.categories if scores else [],
        combined=scores.combined if scores else None,
        settings=settings,
    )


# --- Sérialisation ---------------------------------------------------------------------


def _plain(obj: Any) -> Any:
    """asdict() garde les enums et les clés d'enum : JSON veut des chaînes."""
    if isinstance(obj, dict):
        return {(k.value if isinstance(k, Enum) else k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_plain(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


def to_dict(export: MachineExport) -> dict[str, Any]:
    return privacy.scrub(_plain(asdict(export)))


def write_export(export: MachineExport, path: Path) -> None:
    text = json.dumps(to_dict(export), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


# --- Relecture -------------------------------------------------------------------------


def _build(tp: Any, value: Any, where: str) -> Any:
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        options = get_args(tp)
        if value is None and type(None) in options:
            return None
        errors = []
        for option in (o for o in options if o is not type(None)):
            try:
                return _build(option, value, where)
            except ExportError as exc:
                errors.append(str(exc))
        raise ExportError(errors[0] if errors else f"{where} : valeur inattendue {value!r}")
    if origin is list:
        if not isinstance(value, list):
            raise ExportError(f"{where} : liste attendue")
        (item,) = get_args(tp)
        return [_build(item, v, f"{where}[{i}]") for i, v in enumerate(value)]
    if origin is dict:
        if not isinstance(value, dict):
            raise ExportError(f"{where} : objet attendu")
        key_tp, value_tp = get_args(tp)
        return {
            _build(key_tp, k, where): _build(value_tp, v, f"{where}.{k}") for k, v in value.items()
        }
    if dataclasses.is_dataclass(tp):
        if not isinstance(value, dict):
            raise ExportError(f"{where} : objet attendu")
        hints = get_type_hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.name in value:
                kwargs[f.name] = _build(hints[f.name], value[f.name], f"{where}.{f.name}")
            elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                raise ExportError(f"{where}.{f.name} : champ manquant")
        try:
            return tp(**kwargs)
        except ValueError as exc:  # validation du modèle (RunSettings.__post_init__)
            raise ExportError(f"{where} : {exc}") from exc
    if isinstance(tp, type) and issubclass(tp, Enum):
        try:
            return tp(value)
        except ValueError as exc:
            raise ExportError(f"{where} : valeur inconnue {value!r}") from exc
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ExportError(f"{where} : nombre attendu")
        return float(value)
    if tp in (int, str, bool):
        if not isinstance(value, tp) or (tp is int and isinstance(value, bool)):
            raise ExportError(f"{where} : {tp.__name__} attendu")
        return value
    if tp is Any:
        return value
    raise ExportError(f"{where} : type non pris en charge {tp!r}")


def from_dict(payload: Any) -> MachineExport:
    if not isinstance(payload, dict):
        raise ExportError("export invalide : objet JSON attendu")
    version = payload.get("schema_version")
    if version not in READABLE_SCHEMA_VERSIONS or isinstance(version, bool):
        expected = ", ".join(str(v) for v in READABLE_SCHEMA_VERSIONS)
        raise ExportError(f"schéma d'export {version!r} non pris en charge (attendu : {expected})")
    if version == 2 and "settings" in payload:
        raise ExportError("export : champ « settings » inattendu dans un schéma 2")
    return _build(MachineExport, payload, "export")


def load_export(path: Path) -> MachineExport:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExportError(f"{path} : {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ExportError(f"{path} : JSON invalide ({exc.msg}, ligne {exc.lineno})") from exc
    try:
        return from_dict(payload)
    except ExportError as exc:
        raise ExportError(f"{path} : {exc}") from exc
