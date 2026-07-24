"""Formal scenario oracle discovery and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import FORMAL_SCENARIO_ROOT, SCENARIO_MANIFEST_NAME
from gateway_conformance.scenario.closure import ScenarioClosure
from gateway_conformance.scenario.validate import load_validated_scenario, validate_scenario

FORMAL_DATA_SCENARIO_REL_PATH = Path("data") / "canonical-row-hashes" / "mixed-scalars"
AUTHORIZED_FORMAL_SCENARIO_IDS = frozenset({"data.canonical-row-hashes.mixed-scalars"})


def discover_formal_scenarios() -> list[Path]:
    """Return authorized formal scenario roots; fail closed on any extra scenario.yaml."""

    if not FORMAL_SCENARIO_ROOT.is_dir():
        raise ConformanceValidationError("formal scenario root is missing")

    discovered: list[Path] = []
    for manifest_path in sorted(FORMAL_SCENARIO_ROOT.rglob(SCENARIO_MANIFEST_NAME)):
        rel_parent = manifest_path.parent.relative_to(FORMAL_SCENARIO_ROOT)
        if rel_parent == FORMAL_DATA_SCENARIO_REL_PATH:
            discovered.append(manifest_path.parent)
            continue
        raise ConformanceValidationError(f"unauthorized formal scenario at {rel_parent.as_posix()}")

    authorized = FORMAL_SCENARIO_ROOT / FORMAL_DATA_SCENARIO_REL_PATH
    if authorized not in discovered:
        raise ConformanceValidationError("authorized formal data scenario is missing")

    if len(discovered) != 1:
        raise ConformanceValidationError("formal scenario root must contain exactly one scenario")

    return discovered


def validate_formal_scenario_oracle() -> list[dict[str, Any]]:
    """Discover and validate every authorized formal scenario."""

    manifests: list[dict[str, Any]] = []
    for root in discover_formal_scenarios():
        manifest = validate_scenario(root)
        scenario_id = str(manifest["scenario_id"])
        if scenario_id not in AUTHORIZED_FORMAL_SCENARIO_IDS:
            raise ConformanceValidationError(f"unauthorized formal scenario_id: {scenario_id}")
        manifests.append(manifest)
    return manifests


def load_formal_scenario() -> tuple[dict[str, Any], ScenarioClosure]:
    """Load the single authorized formal scenario closure."""

    roots = discover_formal_scenarios()
    if len(roots) != 1:
        raise ConformanceValidationError("expected exactly one formal scenario")
    return load_validated_scenario(roots[0])
