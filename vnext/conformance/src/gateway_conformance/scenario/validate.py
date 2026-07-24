"""Scenario manifest read-only validation entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.golden.validate import validate_golden_bindings
from gateway_conformance.sanitize import sanitize_message
from gateway_conformance.schemas import validate_scenario_manifest
from gateway_conformance.scenario.closure import ScenarioClosure, load_scenario_closure
from gateway_conformance.scenario.digest import assert_digest_closure
from gateway_conformance.scenario.identity import (
    assert_binding_references,
    assert_id_path_reversible,
    assert_manifest_ordering,
)
from gateway_conformance.scenario.policy import (
    assert_fault_legality,
    assert_provenance_policy,
    assert_recovery_legality,
)


def _validate_loaded_closure(closure: ScenarioClosure) -> dict[str, Any]:
    manifest = closure.manifest
    validate_scenario_manifest(manifest)
    assert_id_path_reversible(manifest, closure.root)
    assert_manifest_ordering(manifest)
    assert_binding_references(manifest)
    assert_provenance_policy(manifest)
    assert_fault_legality(manifest)
    assert_recovery_legality(manifest)
    validate_golden_bindings(manifest, closure.golden_envelopes)
    assert_digest_closure(closure)
    return manifest


def validate_scenario(root: Path) -> dict[str, Any]:
    """Validate a scenario directory without writing or blessing fixture content."""
    try:
        return _validate_loaded_closure(load_scenario_closure(root))
    except ValidationError as exc:
        raise ConformanceValidationError(sanitize_message(exc.message)) from exc
    except ConformanceValidationError:
        raise
    except Exception as exc:
        raise ConformanceValidationError(sanitize_message(str(exc))) from exc


def load_validated_scenario(root: Path) -> tuple[dict[str, Any], ScenarioClosure]:
    """Load and validate a scenario, returning the same closure snapshot."""
    try:
        closure = load_scenario_closure(root)
        manifest = _validate_loaded_closure(closure)
    except ValidationError as exc:
        raise ConformanceValidationError(sanitize_message(exc.message)) from exc
    except ConformanceValidationError:
        raise
    except Exception as exc:
        raise ConformanceValidationError(sanitize_message(str(exc))) from exc
    return manifest, closure
