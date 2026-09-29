"""Génération du fichier de référence du scoring (machine de référence = 1000 points).

La référence mesure le régime soutenu : sur secteur, profil d'énergie « performance »,
warm-up stabilisé. Sinon elle est refusée, sauf --force, qui le note dans le fichier.
"""

from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from hwbench import __version__, privacy
from hwbench.models import MachineSnapshot
from hwbench.results import MachineState, Result
from hwbench.scoring import REFERENCE_SCHEMA_VERSION


class ReferenceIssue(StrEnum):
    NOT_ON_AC = "not_on_ac"
    POWER_UNKNOWN = "power_unknown"
    POWER_PROFILE = "power_profile"
    PROFILE_UNKNOWN = "profile_unknown"
    WARMUP_UNSTABLE = "warmup_unstable"


def state_issues(state: MachineState) -> list[ReferenceIssue]:
    issues: list[ReferenceIssue] = []
    if state.on_ac is None:
        issues.append(ReferenceIssue.POWER_UNKNOWN)
    elif not state.on_ac:
        issues.append(ReferenceIssue.NOT_ON_AC)
    if state.platform_profile is None and state.energy_performance_preference is None:
        issues.append(ReferenceIssue.PROFILE_UNKNOWN)
    elif state.throttling_settings():
        issues.append(ReferenceIssue.POWER_PROFILE)
    return issues


def results_issues(results: list[Result]) -> list[tuple[ReferenceIssue, str]]:
    """Problèmes relevés pendant les benchs : (code, nom du bench)."""
    issues: list[tuple[ReferenceIssue, str]] = []
    for r in results:
        if not r.warmup_stable:
            issues.append((ReferenceIssue.WARMUP_UNSTABLE, r.name))
        for issue in state_issues(r.state_after):
            issues.append((issue, r.name))
    return issues


def machine_label(snapshot: MachineSnapshot) -> str:
    board = snapshot.board
    parts = [p for p in (board.system_vendor, board.product_name) if p]
    if not parts:
        parts = [p for p in (board.board_vendor, board.board_name) if p]
    return " ".join(parts) or "machine inconnue"


def build_reference(
    results: list[Result],
    snapshot: MachineSnapshot,
    forced_reasons: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "hwbench_version": __version__,
        "created": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "machine": machine_label(snapshot),
        "cpu": snapshot.cpu.model,
        "gpu": snapshot.gpu.opengl_renderer or snapshot.gpu.vulkan_device_name,
        "forced": bool(forced_reasons),
        "forced_reasons": forced_reasons,
        "benchmarks": [
            {
                "name": r.name,
                "backend": r.backend,
                "category": r.category.value,
                "version": r.version,
                "tool_version": r.tool_version,
                "unit": r.unit,
                "higher_is_better": r.higher_is_better,
                "value": r.value,  # médiane en régime soutenu ; le burst n'est jamais noté
                "stdev": r.stdev,
                "runs": r.runs,
                "burst": r.burst,
                "warmup_stable": r.warmup_stable,
                "environment": r.environment,
                "state_before": asdict(r.state_before),
                "state_after": asdict(r.state_after),
            }
            for r in results
        ],
    }
    return privacy.scrub(payload)
