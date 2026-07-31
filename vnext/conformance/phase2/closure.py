"""Offline closure, traceability and schema validation for Phase 2 WP0-R3."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_conformance.sanitize import sanitize_message
from gateway_conformance.strict_yaml import StrictYAMLValidationError, loads_strict_yaml_bytes

from phase1_protection import verify_phase1_protection
from router import KNOWN_GATES

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
GATE_ATTEMPT_SCHEMA_FILE = "gate-attempt-v1.json"
CLOSURE_SCHEMA_FILE = "closure-v1.json"

TRACEABILITY_REL = (
    "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
)
FORMAL_ROOT_REL = "docs/backend-vnext/refactoring/formal"

EXPECTED_PLAN_ID = "gateway-vnext.phase-2-implementation-design-and-delivery-plan"
EXPECTED_TRACEABILITY_STATUS = "accepted"
EXPECTED_DECISION_TOTAL = 148
EXPECTED_DECISION_ACCEPTED = 141
EXPECTED_DECISION_SUPERSEDED = 7
EXPECTED_DECISION_OPEN = 0

EXPECTED_BLOCKERS: dict[str, str] = {
    "F0-B1": "user-confirmed-rounds-cdr-consumer-check-and-formalization",
    "F0-B2": "formal-supersession",
    "F0-B3": "this-traceability-file",
    "F0-B4": "formal/plans/phase-2-f0-validation-report.md",
}

FORMAL_MARKER_OWNERS: tuple[str, ...] = (
    "formal/plans/phase-2-implementation-design-and-delivery-plan.md",
    "formal/plans/phase-2-f0-validation-report.md",
)

ACTIVE_STATIC_GATE = "P2-PR-STATIC"
WP0_REQUIRED_CHECKS: tuple[str, ...] = (
    "static.ruff",
    "static.mypy",
    "static.pytest",
    "static.lock.conformance",
    "static.closure",
)

WP0_ACTIVE_REQUIREMENT: dict[str, Any] = {
    "gate_name": "P2-PR-STATIC",
    "activation": "active",
    "required_check_ids": list(WP0_REQUIRED_CHECKS),
}

INACTIVE_GATES = frozenset({"P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"})
EXTERNAL_GATES = frozenset({"PR-CORRECTNESS", "PR-NATIVE"})
FORBIDDEN_PASS_STATUSES = frozenset({"DELEGATED", "NOT_EXECUTED", "UNSUPPORTED", "skip", "xfail"})
ALLOWED_BLOCK_REASONS = frozenset(
    {
        "python_unavailable",
        "uv_unavailable",
        "worktree_snapshot_blocked",
        "tracked_worktree_unavailable",
    }
)
FORBIDDEN_BLOCKED_MARKERS = frozenset(
    {
        "assertion_failed",
        "schema.",
        "cleanup",
        "check:",
    }
)

KNOWN_WORK_PACKAGES: frozenset[str] = frozenset(
    {
        "F0",
        "WP0",
        "WP1",
        "WP2",
        "WP3",
        "WP4",
        "WP5",
        "WP6",
        "WP7",
        "WP8",
        "WP9",
    }
)

_TRACEABILITY_TOP_KEYS = frozenset(
    {
        "schema_version",
        "plan_id",
        "status",
        "as_of",
        "decision_summary",
        "requirements",
        "superseded_decisions",
        "blocking_register",
    }
)
_REQUIREMENT_KEYS = frozenset(
    {
        "requirement_id",
        "description",
        "decision_ids",
        "formal_owners",
        "work_packages",
        "gates",
        "evidence",
    }
)
_SUPERSEDED_KEYS = frozenset({"decision_id", "superseded_by"})
_BLOCKER_KEYS = frozenset({"id", "status", "evidence"})
_SUMMARY_KEYS = frozenset({"total", "accepted", "superseded", "open"})

_DECISION_ID_PATTERN = re.compile(r"^P2-R\d+-D\d+$")
_REQUIREMENT_ID_PATTERN = re.compile(r"^P2-REQ-[A-Z0-9-]+$")
_FORMAL_UNRESOLVED_RE = re.compile(r"\bUNRESOLVED\b")
_TEMPORARY_OWNER_MARKERS = ("temporary/", "docs/backend-vnext/refactoring/temporary/")

EXPECTED_REQUIREMENT_MAPPINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "P2-REQ-GOVERNANCE": {
        "decision_ids": (
            "P2-R0-D02",
            "P2-R0-D04",
            "P2-R0-D05",
            "P2-R0-D06",
            "P2-R0-D07",
            "P2-R0-D08",
        ),
        "formal_owners": (
            "formal/architecture/architecture-and-refactoring-plan.md",
            "formal/contracts/repository-service.md",
            "formal/plans/phase-2-implementation-design-and-delivery-plan.md",
        ),
        "work_packages": ("F0", "WP0", "WP5", "WP7", "WP9"),
        "gates": ("P2-PR-STATIC", "P2-PR-CONTRACT", "P2-PHASE-EXIT-CONTAINER"),
        "evidence": (
            "formal-closure-manifest",
            "architecture-import-boundary",
            "current-versioned-independence",
            "exact-candidate-signoff",
        ),
    },
    "P2-REQ-ARCHITECTURE": {
        "decision_ids": (
            "P2-R1-D01",
            "P2-R1-D02",
            "P2-R1-D03",
            "P2-R1-D04",
            "P2-R1-D05",
            "P2-R1-D06",
            "P2-R1-D09",
            "P2-R1-D10",
            "P2-R1-D11",
            "P2-R1-D12",
            "P2-R1-D13",
            "P2-R1-D14",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/adr/0008-generic-dual-store-and-caller-selected-rigor.md",
        ),
        "work_packages": ("WP0", "WP1", "WP3", "WP4", "WP5", "WP6", "WP7", "WP9"),
        "gates": ("P2-PR-STATIC", "P2-PR-CONTRACT", "P2-PHASE-EXIT-CONTAINER"),
        "evidence": (
            "three-package-dependency-report",
            "local-remote-canonical-observations",
            "store-scoped-concurrency",
            "auth-audit-redaction-matrix",
        ),
    },
    "P2-REQ-API-IDENTITY": {
        "decision_ids": (
            "P2-R2-D01",
            "P2-R2-D02",
            "P2-R2-D03",
            "P2-R2-D04",
            "P2-R2-D05",
            "P2-R2-D06",
            "P2-R2-D07",
            "P2-R2-D09",
            "P2-R2-D10",
            "P2-R2-D13",
            "P2-R2-D14",
            "P2-R2-D15",
            "P2-R2-D16",
            "P2-R2-D17",
            "P2-R2-D18",
            "P2-R2-D19",
            "P2-R2-D20",
            "P2-R2-D21",
            "P2-R2-D22",
            "P2-R2-D23",
            "P2-R2-D24",
            "P2-R2-D25",
            "P2-R2-D26",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/contract-taxonomy-and-ownership.md",
        ),
        "work_packages": ("WP1", "WP4", "WP5", "WP6", "WP7", "WP8"),
        "gates": ("P2-PR-STATIC", "P2-PR-CONTRACT"),
        "evidence": (
            "wire-schema-snapshots",
            "opaque-identity-relations",
            "current-api-transaction-observations",
            "authorization-coverage-inventory",
        ),
    },
    "P2-REQ-READ-DATA-PLANE": {
        "decision_ids": (
            "P2-R3-D01",
            "P2-R3-D02",
            "P2-R3-D03",
            "P2-R3-D04",
            "P2-R3-D05",
            "P2-R3-D06",
            "P2-R3-D07",
            "P2-R3-D08",
            "P2-R3-D09",
            "P2-R3-D10",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/shared-canonical-encoding.md",
        ),
        "work_packages": ("WP1", "WP5", "WP6"),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY"),
        "evidence": (
            "framed-arrow-goldens",
            "pinned-snapshot-race-tests",
            "stream-backpressure-cancel",
            "parquet-artifact-integrity",
            "raw-diff-fallback",
        ),
    },
    "P2-REQ-STORAGE-RUNTIME": {
        "decision_ids": (
            "P2-R4-D01",
            "P2-R4-D02",
            "P2-R4-D03",
            "P2-R4-D04",
            "P2-R4-D05",
            "P2-R4-D06",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/canonical-storage-and-repository-boundary.md",
            "formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md",
        ),
        "work_packages": ("WP2", "WP3", "WP6", "WP7", "WP8"),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"),
        "evidence": (
            "provider-feasibility-manifest",
            "canonical-replay-roundtrip",
            "cli-server-owner-exclusion",
            "registry-disk-reconciliation",
            "repository-aggregate-restore",
        ),
    },
    "P2-REQ-WRITE-JOURNAL": {
        "decision_ids": (
            "P2-R5-D01",
            "P2-R5-D02",
            "P2-R5-D03",
            "P2-R5-D04",
            "P2-R5-D05",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/external-effect-and-recovery.md",
        ),
        "work_packages": ("WP4", "WP5", "WP7"),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY"),
        "evidence": (
            "operation-journal-state-matrix",
            "idempotency-collision-and-compaction",
            "fencing-takeover",
            "ref-publication-evidence",
            "current-transaction-marker",
        ),
    },
    "P2-REQ-FAILURE-RECOVERY": {
        "decision_ids": (
            "P2-R6-D01",
            "P2-R6-D02",
            "P2-R6-D03",
            "P2-R6-D04",
            "P2-R6-D05",
            "P2-R6-D06",
            "P2-R6-D07",
            "P2-R6-D08",
            "P2-R6-D09",
            "P2-R6-D10",
            "P2-R6-D11",
            "P2-R6-D12",
            "P2-R6-D13",
            "P2-R6-D14",
            "P2-R6-D15",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/external-effect-and-recovery.md",
            "formal/contracts/business-lifecycle-and-state.md",
            "formal/adr/0003-external-effect-reconciliation.md",
            "formal/adr/0008-generic-dual-store-and-caller-selected-rigor.md",
        ),
        "work_packages": ("WP4", "WP5", "WP6", "WP7"),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY"),
        "evidence": (
            "effect-classification-crash-matrix",
            "none-structural-full-matrix",
            "checked-lww-matrix",
            "exact-latest-at-start-matrix",
            "verification-failed-applied",
            "authority-contradiction-quarantine",
        ),
    },
    "P2-REQ-RETENTION-MAINTENANCE": {
        "decision_ids": (
            "P2-R7-D01",
            "P2-R7-D02",
            "P2-R7-D03",
            "P2-R7-D04",
            "P2-R7-D05",
            "P2-R7-D06",
        ),
        "formal_owners": ("formal/contracts/repository-service.md",),
        "work_packages": ("WP8",),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"),
        "evidence": (
            "retention-root-inventory",
            "exact-gc-plan-checkpoints",
            "manifested-backup-restore",
            "incarnation-policy-activation",
            "delete-tombstone-purge",
        ),
    },
    "P2-REQ-SECURITY-RESOURCE": {
        "decision_ids": (
            "P2-R8-D01",
            "P2-R8-D02",
            "P2-R8-D03",
            "P2-R8-D04",
            "P2-R8-D05",
            "P2-R8-D06",
            "P2-R8-D07",
            "P2-R8-D08",
            "P2-R8-D09",
            "P2-R8-D10",
        ),
        "formal_owners": ("formal/contracts/repository-service.md",),
        "work_packages": ("WP1", "WP3", "WP4", "WP5", "WP6", "WP7", "WP8", "WP9"),
        "gates": (
            "P2-PR-STATIC",
            "P2-PR-CONTRACT",
            "P2-PR-RECOVERY",
            "P2-PHASE-EXIT-CONTAINER",
        ),
        "evidence": (
            "route-action-authorization-inventory",
            "artifact-and-parser-negative-matrix",
            "finite-resource-policy",
            "redaction-scan",
            "restored-restricted-policy",
            "container-hardening-inspection",
        ),
    },
    "P2-REQ-OPERATIONS": {
        "decision_ids": (
            "P2-R9-D01",
            "P2-R9-D02",
            "P2-R9-D03",
            "P2-R9-D04",
            "P2-R9-D05",
            "P2-R9-D06",
            "P2-R9-D07",
            "P2-R9-D08",
            "P2-R9-D09",
        ),
        "formal_owners": (
            "formal/contracts/repository-service.md",
            "formal/contracts/performance-measurement-and-baseline.md",
        ),
        "work_packages": ("WP2", "WP3", "WP4", "WP6", "WP7", "WP8", "WP9"),
        "gates": ("P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"),
        "evidence": (
            "typed-telemetry-and-audit",
            "readiness-degradation",
            "runtime-build-environment-identity",
            "verification-keyed-capacity-series",
            "durable-root-lock-epoch",
            "fair-reconciliation-cadence",
        ),
    },
    "P2-REQ-GATES": {
        "decision_ids": (
            "P2-R10-D01",
            "P2-R10-D02",
            "P2-R10-D03",
            "P2-R10-D04",
            "P2-R10-D05",
            "P2-R10-D06",
            "P2-R10-D07",
            "P2-R10-D08",
            "P2-R10-D09",
            "P2-R10-D10",
            "P2-R10-D11",
            "P2-R10-D12",
            "P2-R10-D13",
        ),
        "formal_owners": (
            "formal/contracts/fixture-oracle-and-conformance.md",
            "formal/contracts/repository-service.md",
            "formal/plans/phase-2-implementation-design-and-delivery-plan.md",
        ),
        "work_packages": ("WP0", "WP1", "WP2", "WP4", "WP5", "WP6", "WP7", "WP8", "WP9"),
        "gates": (
            "P2-PR-STATIC",
            "P2-PR-CONTRACT",
            "P2-PR-RECOVERY",
            "P2-PHASE-EXIT-CONTAINER",
        ),
        "evidence": (
            "required-cell-coverage",
            "immutable-attempts",
            "typed-fault-receipts",
            "compatibility-snapshots",
            "phase1-protected-identity",
            "production-tls-container-exit",
        ),
    },
    "P2-REQ-DELIVERY": {
        "decision_ids": (
            "P2-R11-D01",
            "P2-R11-D02",
            "P2-R11-D03",
            "P2-R11-D04",
            "P2-R11-D05",
            "P2-R11-D06",
            "P2-R11-D07",
            "P2-R11-D08",
            "P2-R11-D09",
            "P2-R11-D10",
            "P2-R11-D11",
            "P2-R11-D12",
            "P2-R11-D13",
            "P2-R11-D14",
            "P2-R11-D15",
            "P2-R11-D16",
            "P2-R11-D17",
            "P2-R11-D18",
            "P2-R11-D19",
            "P2-R11-D20",
            "P2-R11-D21",
            "P2-R11-D22",
            "P2-R11-D23",
            "P2-R11-D24",
            "P2-R11-D25",
            "P2-R11-D26",
        ),
        "formal_owners": ("formal/plans/phase-2-implementation-design-and-delivery-plan.md",),
        "work_packages": (
            "F0",
            "WP0",
            "WP1",
            "WP2",
            "WP3",
            "WP4",
            "WP5",
            "WP6",
            "WP7",
            "WP8",
            "WP9",
        ),
        "gates": (
            "P2-PR-STATIC",
            "P2-PR-CONTRACT",
            "P2-PR-RECOVERY",
            "P2-PHASE-EXIT-CONTAINER",
        ),
        "evidence": (
            "revision-entry-exit-records",
            "physical-owner-report",
            "consumer-ready-checkpoint",
            "runbook-and-capacity-profile",
            "exact-candidate-signoff",
        ),
    },
}


class ClosureErrorCode(StrEnum):
    SCHEMA_UNKNOWN_FIELD = "schema.unknown_field"
    SCHEMA_MISSING_REQUIRED = "schema.missing_required"
    SCHEMA_MISMATCH = "schema.mismatch"
    SCHEMA_MALFORMED_REVISION = "schema.malformed_revision"
    SCHEMA_MALFORMED_DIGEST = "schema.malformed_digest"
    SCHEMA_MALFORMED_ATTEMPT_ID = "schema.malformed_attempt_id"
    SCHEMA_MALFORMED_PATH = "schema.malformed_path"
    SCHEMA_INVALID_BLOCKED_STATUS = "schema.invalid_blocked_status"
    SCHEMA_UNKNOWN_GATE = "schema.unknown_gate"
    SCHEMA_UNKNOWN_STATUS = "schema.unknown_status"
    SCHEMA_UNKNOWN_ACTIVATION = "schema.unknown_activation"
    SCHEMA_DUPLICATE_ATTEMPT = "schema.duplicate_attempt"
    SCHEMA_DUPLICATE_GATE = "schema.duplicate_gate"
    SCHEMA_DUPLICATE_EVIDENCE = "schema.duplicate_evidence"
    SCHEMA_DUPLICATE_OBSERVATION = "schema.duplicate_observation"
    SCHEMA_DUPLICATE_BINDING = "schema.duplicate_binding"
    SCHEMA_IDENTITY_MISMATCH = "schema.identity_mismatch"
    SCHEMA_PASS_LAUNDERING = "schema.pass_laundering"
    SCHEMA_INACTIVE_GATE_PASS = "schema.inactive_gate_pass"
    SCHEMA_EMPTY_REQUIRED_PASS = "schema.empty_required_pass"
    SCHEMA_STRICT_YAML = "schema.strict_yaml"
    CLOSURE_CROSS_CANDIDATE = "closure.cross_candidate"
    CLOSURE_CROSS_ENVIRONMENT = "closure.cross_environment"
    CLOSURE_MISSING_REQUIRED = "closure.missing_required"
    CLOSURE_DUPLICATE_ATTEMPT_ID = "closure.duplicate_attempt_id"
    CLOSURE_SUPERSESSION_CYCLE = "closure.supersession_cycle"
    CLOSURE_SUPERSESSION_ORPHAN = "closure.supersession_orphan"
    CLOSURE_FAIL_ERASED = "closure.fail_erased"
    CLOSURE_INVALID_REQUIREMENTS = "closure.invalid_requirements"
    CLOSURE_IDENTITY_MISMATCH = "closure.identity_mismatch"
    CLOSURE_INACTIVE_SUMMARY = "closure.inactive_summary"
    CLOSURE_SUMMARY_EXTRA = "closure.summary_extra"
    CLOSURE_SUPERSESSION_FORK = "closure.supersession_fork"
    CLOSURE_SUPERSESSION_CROSS_GATE = "closure.supersession_cross_gate"
    CLOSURE_EXTERNAL_PASS = "closure.external_pass"
    CLOSURE_INACTIVE_PASS = "closure.inactive_pass"
    CLOSURE_SUMMARY_MISMATCH = "closure.summary_mismatch"
    CLOSURE_SUMMARY_ORPHAN_ATTEMPT = "closure.summary_orphan_attempt"
    CLOSURE_SUMMARY_WRONG_GATE = "closure.summary_wrong_gate"
    CLOSURE_SUMMARY_HISTORY_MISMATCH = "closure.summary_history_mismatch"
    CLOSURE_SUMMARY_DUPLICATE_ATTEMPT = "closure.summary_duplicate_attempt"
    CLOSURE_DECLARED_STATUS_MISMATCH = "closure.declared_status_mismatch"
    CLOSURE_CHECK_OBSERVATION_MISSING = "closure.check_observation_missing"
    CLOSURE_INVALID_INPUT = "closure.invalid_input"
    TRACEABILITY_SCHEMA = "traceability.schema"
    TRACEABILITY_SUMMARY_DRIFT = "traceability.summary_drift"
    TRACEABILITY_DECISION_MISSING = "traceability.decision_missing"
    TRACEABILITY_DECISION_DUPLICATE = "traceability.decision_duplicate"
    TRACEABILITY_SUPERSEDED_IN_REQUIREMENT = "traceability.superseded_in_requirement"
    TRACEABILITY_SUPERSEDED_MAPPING = "traceability.superseded_mapping"
    TRACEABILITY_BLOCKER_OPEN = "traceability.blocker_open"
    TRACEABILITY_BLOCKER_MISSING = "traceability.blocker_missing"
    TRACEABILITY_BLOCKER_MISMATCH = "traceability.blocker_mismatch"
    TRACEABILITY_BLOCKER_DUPLICATE = "traceability.blocker_duplicate"
    TRACEABILITY_UNKNOWN_GATE = "traceability.unknown_gate"
    TRACEABILITY_UNKNOWN_WP = "traceability.unknown_wp"
    TRACEABILITY_EMPTY_MAPPING = "traceability.empty_mapping"
    TRACEABILITY_OWNER_MISSING = "traceability.owner_missing"
    TRACEABILITY_OWNER_INVALID = "traceability.owner_invalid"
    TRACEABILITY_TEMPORARY_OWNER = "traceability.temporary_owner"
    TRACEABILITY_LEDGER_MISMATCH = "traceability.ledger_mismatch"
    TRACEABILITY_LEDGER_DUPLICATE = "traceability.ledger_duplicate"
    TRACEABILITY_SUPERSEDED_DUPLICATE = "traceability.superseded_duplicate"
    TRACEABILITY_OWNER_ESCAPE = "traceability.owner_escape"
    TRACEABILITY_FORMAL_UNRESOLVED = "traceability.formal_unresolved"
    TRACEABILITY_UNKNOWN_FIELD = "traceability.unknown_field"
    TRACEABILITY_MAPPING_MISMATCH = "traceability.mapping_mismatch"
    PHASE1_PROTECTION = "phase1.protection.failed"


@dataclass(frozen=True, slots=True)
class LintResult:
    ok: bool
    diagnostics: tuple[str, ...]


def _repo_root_from_default() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _schema_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for name in (GATE_ATTEMPT_SCHEMA_FILE, CLOSURE_SCHEMA_FILE):
        document = _load_json(SCHEMA_DIR / name)
        resources.append(
            (document["$id"], Resource.from_contents(document, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


@lru_cache(maxsize=2)
def _validator(schema_file: str) -> Draft202012Validator:
    document = _load_json(SCHEMA_DIR / schema_file)
    return Draft202012Validator(document, registry=_schema_registry())


def loads_document_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(ClosureErrorCode.SCHEMA_MISMATCH.value) from exc
    if not isinstance(parsed, dict):
        raise ValueError(ClosureErrorCode.SCHEMA_MISMATCH.value)
    return parsed


def loads_document_yaml_bytes(raw: bytes) -> dict[str, Any]:
    try:
        parsed: dict[str, Any] = loads_strict_yaml_bytes(raw)
    except StrictYAMLValidationError as exc:
        raise ValueError(ClosureErrorCode.SCHEMA_STRICT_YAML.value) from exc
    return parsed


def _schema_error_code(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    if error.validator == "uniqueItems" and "evidence_ids" in path:
        return ClosureErrorCode.SCHEMA_DUPLICATE_EVIDENCE.value
    if error.validator == "uniqueItems" and "attempt_ids" in path:
        return ClosureErrorCode.SCHEMA_DUPLICATE_ATTEMPT.value
    if "revision" in path:
        return ClosureErrorCode.SCHEMA_MALFORMED_REVISION.value
    if "digest" in path:
        return ClosureErrorCode.SCHEMA_MALFORMED_DIGEST.value
    if "attempt_id" in path:
        return ClosureErrorCode.SCHEMA_MALFORMED_ATTEMPT_ID.value
    if "path" in path:
        return ClosureErrorCode.SCHEMA_MALFORMED_PATH.value
    if error.validator == "maxLength" and "attempt_id" in path:
        return ClosureErrorCode.SCHEMA_MALFORMED_ATTEMPT_ID.value
    if "gate_name" in path:
        return ClosureErrorCode.SCHEMA_UNKNOWN_GATE.value
    if "status" in path or "aggregate_status" in path:
        return ClosureErrorCode.SCHEMA_UNKNOWN_STATUS.value
    if "activation" in path:
        return ClosureErrorCode.SCHEMA_UNKNOWN_ACTIVATION.value
    if error.validator == "required":
        return ClosureErrorCode.SCHEMA_MISSING_REQUIRED.value
    if error.validator == "additionalProperties":
        return ClosureErrorCode.SCHEMA_UNKNOWN_FIELD.value
    return ClosureErrorCode.SCHEMA_MISMATCH.value


def _expected_gate_activation(gate_name: str) -> str:
    if gate_name == ACTIVE_STATIC_GATE:
        return "active"
    if gate_name in INACTIVE_GATES:
        return "inactive"
    if gate_name in EXTERNAL_GATES:
        return "external"
    return "unknown"


def _normalize_wp0_requirement(requirement: dict[str, Any]) -> dict[str, Any]:
    check_ids = requirement.get("required_check_ids", [])
    if not isinstance(check_ids, list):
        check_ids = []
    return {
        "gate_name": requirement.get("gate_name"),
        "activation": requirement.get("activation"),
        "required_check_ids": list(check_ids),
    }


def _validate_wp0_active_requirements(
    active_requirements: list[Any], *, attempts: list[dict[str, Any]]
) -> list[str]:
    diagnostics: list[str] = []
    if not attempts:
        diagnostics.append(ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value)
    if not isinstance(active_requirements, list) or len(active_requirements) != 1:
        diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_REQUIREMENTS.value)
        return diagnostics
    requirement = active_requirements[0]
    if not isinstance(requirement, dict):
        diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_REQUIREMENTS.value)
        return diagnostics
    if _normalize_wp0_requirement(requirement) != WP0_ACTIVE_REQUIREMENT:
        diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_REQUIREMENTS.value)
    return diagnostics


def _has_duplicate_key(items: Any, key_name: str) -> bool:
    if not isinstance(items, list):
        return False
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get(key_name)
        if not isinstance(key, str):
            continue
        if key in seen:
            return True
        seen.add(key)
    return False


def _is_canonical_posix_relative_path(path: str) -> bool:
    if not path or path.startswith("/") or "\\" in path:
        return False
    if "\x00" in path or any(ord(char) < 32 for char in path):
        return False
    if path.startswith("./") or "/./" in path or path.endswith("/.") or path == ".":
        return False
    segments = path.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            return False
    return True


def _path_binding_diagnostics(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    path_fields: list[Any] = []
    env_binding = document.get("environment_binding")
    if isinstance(env_binding, dict):
        path_fields.extend(env_binding.get("lock_digests", []))
    fingerprint = document.get("environment_fingerprint")
    if isinstance(fingerprint, dict):
        path_fields.extend(fingerprint.get("lock_digests", []))
    path_fields.extend(document.get("artifact_digests", []))
    for item in path_fields:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and not _is_canonical_posix_relative_path(path):
            diagnostics.append(ClosureErrorCode.SCHEMA_MALFORMED_PATH.value)
    return diagnostics


def _attempt_type_guard_diagnostics(attempt: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    dict_fields = (
        "candidate_identity",
        "gate_identity",
        "environment_binding",
        "runtime_build_identity",
        "environment_fingerprint",
        "evidence_binding",
        "recorded_result",
        "cleanup_result",
        "supersession",
    )
    for field in dict_fields:
        value = attempt.get(field)
        if value is not None and not isinstance(value, dict):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
    list_fields = (
        "artifact_digests",
        "image_digests",
        "required_check_observations",
        "fault_receipts",
    )
    for field in list_fields:
        value = attempt.get(field)
        if value is not None and not isinstance(value, list):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
    return diagnostics


def _validate_closure_schema_surface(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    try:
        _validator(CLOSURE_SCHEMA_FILE).validate(document)
    except ValidationError as exc:
        diagnostics.append(_schema_error_code(exc))
        return diagnostics

    attempts_raw = document.get("gate_attempts", [])
    if isinstance(attempts_raw, list):
        for attempt in attempts_raw:
            if not isinstance(attempt, dict):
                diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
                continue
            try:
                _validator(GATE_ATTEMPT_SCHEMA_FILE).validate(attempt)
            except ValidationError as exc:
                diagnostics.append(_schema_error_code(exc))
    return diagnostics


def _prevalidate_closure_for_aggregate(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    diagnostics.extend(_validate_closure_schema_surface(document))
    if diagnostics:
        return diagnostics

    diagnostics.extend(_closure_identity_diagnostics(document))

    if not isinstance(document.get("environment_binding"), dict):
        diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
    if not isinstance(document.get("candidate_identity"), dict):
        diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)

    summaries_raw = document.get("gate_summaries", [])
    if isinstance(summaries_raw, list):
        gate_names = [
            item.get("gate_name")
            for item in summaries_raw
            if isinstance(item, dict) and isinstance(item.get("gate_name"), str)
        ]
        if len(gate_names) != len(set(gate_names)):
            diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_GATE.value)
        for summary in summaries_raw:
            if not isinstance(summary, dict):
                diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
                continue
            attempt_ids = summary.get("attempt_ids")
            if attempt_ids is not None and not isinstance(attempt_ids, list):
                diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
            elif isinstance(attempt_ids, list):
                string_ids = [item for item in attempt_ids if isinstance(item, str)]
                if len(string_ids) != len(set(string_ids)):
                    diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_DUPLICATE_ATTEMPT.value)

    attempts_raw = document.get("gate_attempts", [])
    if isinstance(attempts_raw, list):
        for attempt in attempts_raw:
            if not isinstance(attempt, dict):
                diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
                continue
            diagnostics.extend(_attempt_type_guard_diagnostics(attempt))
            diagnostics.extend(_semantic_gate_attempt_checks(attempt))

    return diagnostics


def _digest_list_key(items: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(items, list):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        digest = item.get("digest")
        if isinstance(path, str) and isinstance(digest, str):
            pairs.append((path, digest))
    return tuple(sorted(pairs))


def _image_digest_key(items: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(items, list):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        image_ref = item.get("image_ref")
        digest = item.get("digest")
        if isinstance(image_ref, str) and isinstance(digest, str):
            pairs.append((image_ref, digest))
    return tuple(sorted(pairs))


def _runtime_build_key(document: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    runtime = document.get("runtime_build_identity", {})
    if not isinstance(runtime, dict):
        return ()
    pairs: list[tuple[str, str]] = []
    for key in sorted(runtime):
        value = runtime.get(key)
        if isinstance(value, str):
            pairs.append((key, value))
    return tuple(pairs)


def _environment_fingerprint_key(document: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    fingerprint = document.get("environment_fingerprint", {})
    if not isinstance(fingerprint, dict):
        return ()
    pairs: list[tuple[str, str]] = []
    for key, value in sorted(fingerprint.items()):
        if key == "lock_digests":
            continue
        if isinstance(value, str):
            pairs.append((key, value))
    pairs.extend(_digest_list_key(fingerprint.get("lock_digests", [])))
    return tuple(pairs)


def _duplicate_binding_diagnostics(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    diagnostics.extend(_path_binding_diagnostics(document))
    if _has_duplicate_key(document.get("required_check_observations", []), "check_id"):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_OBSERVATION.value)
    if _has_duplicate_key(document.get("fault_receipts", []), "receipt_id"):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_BINDING.value)
    if _has_duplicate_key(document.get("artifact_digests", []), "path"):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_BINDING.value)
    if _has_duplicate_key(document.get("image_digests", []), "image_ref"):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_BINDING.value)
    env_binding = document.get("environment_binding", {})
    if isinstance(env_binding, dict) and _has_duplicate_key(
        env_binding.get("lock_digests", []), "path"
    ):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_BINDING.value)
    fingerprint = document.get("environment_fingerprint", {})
    if isinstance(fingerprint, dict) and _has_duplicate_key(
        fingerprint.get("lock_digests", []), "path"
    ):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_BINDING.value)
    return diagnostics


def _semantic_identity_diagnostics(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    candidate_revision = document.get("candidate_revision")
    candidate_identity = document.get("candidate_identity", {})
    if isinstance(candidate_identity, dict):
        if candidate_identity.get("revision") != candidate_revision:
            diagnostics.append(ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value)
    gate_name = document.get("gate_name")
    gate_identity = document.get("gate_identity", {})
    if isinstance(gate_name, str) and isinstance(gate_identity, dict):
        if gate_identity.get("gate_name") != gate_name:
            diagnostics.append(ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value)
        expected_activation = _expected_gate_activation(gate_name)
        if gate_identity.get("activation") != expected_activation:
            diagnostics.append(ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value)
    return diagnostics


def _closure_identity_diagnostics(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    candidate_revision = document.get("candidate_revision")
    candidate_identity = document.get("candidate_identity", {})
    if isinstance(candidate_identity, dict):
        if candidate_identity.get("revision") != candidate_revision:
            diagnostics.append(ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value)
    return diagnostics


def _closure_attempt_binding_diagnostics(
    document: dict[str, Any], attempt: dict[str, Any]
) -> list[str]:
    diagnostics: list[str] = []
    if attempt.get("candidate_revision") != document.get("candidate_revision"):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if attempt.get("candidate_identity") != document.get("candidate_identity"):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if _environment_key(attempt.get("environment_binding", {})) != _environment_key(
        document.get("environment_binding", {})
    ):
        diagnostics.append(ClosureErrorCode.CLOSURE_CROSS_ENVIRONMENT.value)
    return diagnostics


def _inter_attempt_binding_diagnostics(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    fields = (
        "runtime_build_identity",
        "environment_fingerprint",
        "artifact_digests",
        "image_digests",
    )
    for field in fields:
        if left.get(field) != right.get(field):
            diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if _runtime_build_key(left) != _runtime_build_key(right):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if _environment_fingerprint_key(left) != _environment_fingerprint_key(right):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if _digest_list_key(left.get("artifact_digests", [])) != _digest_list_key(
        right.get("artifact_digests", [])
    ):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    if _image_digest_key(left.get("image_digests", [])) != _image_digest_key(
        right.get("image_digests", [])
    ):
        diagnostics.append(ClosureErrorCode.CLOSURE_IDENTITY_MISMATCH.value)
    return diagnostics


def validate_gate_attempt_document(document: dict[str, Any]) -> LintResult:
    diagnostics: list[str] = []
    try:
        _validator(GATE_ATTEMPT_SCHEMA_FILE).validate(document)
    except ValidationError as exc:
        diagnostics.append(_schema_error_code(exc))
        return LintResult(False, tuple(sorted(diagnostics)))

    diagnostics.extend(_semantic_gate_attempt_checks(document))
    return LintResult(not diagnostics, tuple(sorted(set(diagnostics))))


def validate_closure_document(document: dict[str, Any]) -> LintResult:
    diagnostics: list[str] = []
    diagnostics.extend(_validate_closure_schema_surface(document))
    if diagnostics:
        return LintResult(False, tuple(sorted(set(diagnostics))))

    attempt_ids = [item.get("attempt_id") for item in document.get("gate_attempts", [])]
    if len(attempt_ids) != len(set(attempt_ids)):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_ATTEMPT.value)

    gate_names = [item.get("gate_name") for item in document.get("gate_summaries", [])]
    if len(gate_names) != len(set(gate_names)):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_GATE.value)

    for attempt in document.get("gate_attempts", []):
        if isinstance(attempt, dict):
            diagnostics.extend(_semantic_gate_attempt_checks(attempt))

    diagnostics.extend(_closure_identity_diagnostics(document))

    agg = aggregate_closure(document)
    diagnostics.extend(agg.diagnostics)
    return LintResult(not diagnostics, tuple(sorted(set(diagnostics))))


def _semantic_gate_attempt_checks(document: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    diagnostics.extend(_semantic_identity_diagnostics(document))
    diagnostics.extend(_duplicate_binding_diagnostics(document))

    status = document.get("status")
    gate_name = document.get("gate_name")
    gate_identity = document.get("gate_identity", {})
    activation = gate_identity.get("activation") if isinstance(gate_identity, dict) else None

    if status in FORBIDDEN_PASS_STATUSES:
        diagnostics.append(ClosureErrorCode.SCHEMA_PASS_LAUNDERING.value)
    if status == "PASS":
        if gate_name in INACTIVE_GATES | EXTERNAL_GATES:
            diagnostics.append(ClosureErrorCode.SCHEMA_INACTIVE_GATE_PASS.value)
        if activation in {"inactive", "external"}:
            diagnostics.append(ClosureErrorCode.SCHEMA_INACTIVE_GATE_PASS.value)

    if status == "BLOCKED":
        block_reason = document.get("block_reason")
        if not isinstance(block_reason, str) or block_reason not in ALLOWED_BLOCK_REASONS:
            diagnostics.append(ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value)
        recorded = document.get("recorded_result", {})
        if isinstance(recorded, dict):
            for item in recorded.get("diagnostics", []):
                if not isinstance(item, str):
                    diagnostics.append(ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value)
                    continue
                if any(marker in item for marker in FORBIDDEN_BLOCKED_MARKERS):
                    diagnostics.append(ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value)
                elif isinstance(block_reason, str) and item != block_reason:
                    diagnostics.append(ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value)
    elif document.get("block_reason") is not None:
        diagnostics.append(ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value)

    evidence_binding = document.get("evidence_binding", {})
    evidence_ids = (
        evidence_binding.get("evidence_ids", []) if isinstance(evidence_binding, dict) else []
    )
    if len(evidence_ids) != len(set(evidence_ids)):
        diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_EVIDENCE.value)

    recorded_result = document.get("recorded_result", {})
    recorded = recorded_result.get("diagnostics", []) if isinstance(recorded_result, dict) else []
    for item in recorded:
        if isinstance(item, str) and any(marker in item for marker in FORBIDDEN_PASS_STATUSES):
            if status == "PASS":
                diagnostics.append(ClosureErrorCode.SCHEMA_PASS_LAUNDERING.value)

    if status == "PASS":
        observations = document.get("required_check_observations", [])
        if not isinstance(observations, list):
            diagnostics.append(ClosureErrorCode.CLOSURE_CHECK_OBSERVATION_MISSING.value)
        elif ClosureErrorCode.SCHEMA_DUPLICATE_OBSERVATION.value not in diagnostics:
            obs_by_id: dict[str, Any] = {}
            for item in observations:
                if isinstance(item, dict):
                    check_id = item.get("check_id")
                    if isinstance(check_id, str):
                        obs_by_id[check_id] = item
            for check_id in WP0_REQUIRED_CHECKS:
                obs = obs_by_id.get(check_id)
                if not isinstance(obs, dict) or obs.get("outcome") != "PASS":
                    diagnostics.append(ClosureErrorCode.CLOSURE_CHECK_OBSERVATION_MISSING.value)
                    break
        cleanup = document.get("cleanup_result", {})
        if not isinstance(cleanup, dict) or cleanup.get("status") != "CLEAN":
            diagnostics.append(ClosureErrorCode.SCHEMA_MISMATCH.value)

    return diagnostics


@dataclass(frozen=True, slots=True)
class AggregationResult:
    ok: bool
    diagnostics: tuple[str, ...]
    closure_status: str


def _environment_key(binding: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(binding, dict):
        return ()
    digests = binding.get("lock_digests", [])
    pairs: list[tuple[str, str]] = []
    for item in digests:
        if isinstance(item, dict):
            path = item.get("path")
            digest = item.get("digest")
            if isinstance(path, str) and isinstance(digest, str):
                pairs.append((path, digest))
    return tuple(sorted(pairs))


def _invalid_aggregate_result(diagnostics: list[str]) -> AggregationResult:
    return AggregationResult(
        ok=False,
        diagnostics=tuple(sorted(set(diagnostics))),
        closure_status="INCOMPLETE",
    )


def _check_observations_pass(attempt: dict[str, Any], required_check_ids: list[str]) -> bool:
    observations = attempt.get("required_check_observations", [])
    if not isinstance(observations, list):
        return False
    if _has_duplicate_key(observations, "check_id"):
        return False
    obs_by_id: dict[str, Any] = {}
    for item in observations:
        if isinstance(item, dict):
            check_id = item.get("check_id")
            if isinstance(check_id, str):
                obs_by_id[check_id] = item
    for check_id in required_check_ids:
        obs = obs_by_id.get(check_id)
        if not isinstance(obs, dict) or obs.get("outcome") != "PASS":
            return False
    return True


def _compute_gate_status(attempt: dict[str, Any], required_check_ids: list[str]) -> str:
    status = attempt.get("status")
    if not isinstance(status, str) or status not in {"PASS", "FAIL", "BLOCKED"}:
        return "FAIL"
    if status != "PASS":
        return status
    if not _check_observations_pass(attempt, required_check_ids):
        return "FAIL"
    cleanup = attempt.get("cleanup_result", {})
    if not isinstance(cleanup, dict) or cleanup.get("status") != "CLEAN":
        return "FAIL"
    return "PASS"


def aggregate_closure(document: Any) -> AggregationResult:
    try:
        return _aggregate_closure_impl(document)
    except Exception:
        return _invalid_aggregate_result([ClosureErrorCode.CLOSURE_INVALID_INPUT.value])


def _aggregate_closure_impl(document: Any) -> AggregationResult:
    diagnostics: list[str] = []
    if not isinstance(document, dict):
        return _invalid_aggregate_result([ClosureErrorCode.CLOSURE_INVALID_INPUT.value])

    diagnostics.extend(_prevalidate_closure_for_aggregate(document))
    if diagnostics:
        return _invalid_aggregate_result(diagnostics)

    attempts_raw = document.get("gate_attempts")
    summaries_raw = document.get("gate_summaries")
    if not isinstance(attempts_raw, list) or not isinstance(summaries_raw, list):
        return _invalid_aggregate_result([ClosureErrorCode.CLOSURE_INVALID_INPUT.value])

    attempts: list[dict[str, Any]] = []
    for attempt in attempts_raw:
        if not isinstance(attempt, dict):
            return _invalid_aggregate_result([ClosureErrorCode.CLOSURE_INVALID_INPUT.value])
        attempts.append(attempt)

    candidate_revision = document.get("candidate_revision")
    environment_binding = document.get("environment_binding", {})
    env_key = _environment_key(environment_binding)

    attempt_by_id: dict[str, dict[str, Any]] = {}
    attempts_by_gate: dict[str, list[str]] = {}
    for attempt in attempts:
        attempt_id = attempt.get("attempt_id")
        if not isinstance(attempt_id, str):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
            continue
        if attempt_id in attempt_by_id:
            diagnostics.append(ClosureErrorCode.CLOSURE_DUPLICATE_ATTEMPT_ID.value)
        attempt_by_id[attempt_id] = attempt

        gate_name = attempt.get("gate_name")
        if isinstance(gate_name, str):
            attempts_by_gate.setdefault(gate_name, []).append(attempt_id)

        if attempt.get("candidate_revision") != candidate_revision:
            diagnostics.append(ClosureErrorCode.CLOSURE_CROSS_CANDIDATE.value)
        attempt_binding = attempt.get("environment_binding", {})
        if not isinstance(attempt_binding, dict):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
        elif _environment_key(attempt_binding) != env_key:
            diagnostics.append(ClosureErrorCode.CLOSURE_CROSS_ENVIRONMENT.value)

        status = attempt.get("status")
        if status == "PASS" and gate_name in EXTERNAL_GATES:
            diagnostics.append(ClosureErrorCode.CLOSURE_EXTERNAL_PASS.value)
        if status == "PASS" and gate_name in INACTIVE_GATES:
            diagnostics.append(ClosureErrorCode.CLOSURE_INACTIVE_PASS.value)

        diagnostics.extend(_closure_attempt_binding_diagnostics(document, attempt))

    if len(attempts) > 1:
        reference_attempt = attempts[0]
        for attempt in attempts[1:]:
            diagnostics.extend(_inter_attempt_binding_diagnostics(reference_attempt, attempt))

    supersession_graph: dict[str, str] = {}
    for attempt in attempts:
        supersession = attempt.get("supersession")
        if not isinstance(supersession, dict):
            continue
        child = attempt.get("attempt_id")
        parent = supersession.get("supersedes_attempt_id")
        if isinstance(child, str) and isinstance(parent, str):
            supersession_graph[child] = parent

    for child, parent in supersession_graph.items():
        if parent not in attempt_by_id:
            diagnostics.append(ClosureErrorCode.CLOSURE_SUPERSESSION_ORPHAN.value)
        if child == parent:
            diagnostics.append(ClosureErrorCode.CLOSURE_SUPERSESSION_CYCLE.value)
        parent_attempt = attempt_by_id.get(parent, {})
        child_attempt = attempt_by_id.get(child, {})
        if parent_attempt.get("gate_name") != child_attempt.get("gate_name"):
            diagnostics.append(ClosureErrorCode.CLOSURE_SUPERSESSION_CROSS_GATE.value)

    parent_children: dict[str, list[str]] = {}
    for child, parent in supersession_graph.items():
        parent_children.setdefault(parent, []).append(child)
    for _parent_id, children in parent_children.items():
        if len(children) > 1:
            diagnostics.append(ClosureErrorCode.CLOSURE_SUPERSESSION_FORK.value)

    visited: set[str] = set()

    def _has_cycle(node: str) -> bool:
        if node in visited:
            return True
        visited.add(node)
        parent = supersession_graph.get(node)
        if parent is None:
            return False
        return _has_cycle(parent)

    for node in supersession_graph:
        visited.clear()
        if _has_cycle(node):
            diagnostics.append(ClosureErrorCode.CLOSURE_SUPERSESSION_CYCLE.value)
            break

    active_requirements = document.get("active_gate_requirements", [])
    if not isinstance(active_requirements, list):
        return _invalid_aggregate_result(
            diagnostics + [ClosureErrorCode.CLOSURE_INVALID_INPUT.value]
        )

    diagnostics.extend(_validate_wp0_active_requirements(active_requirements, attempts=attempts))

    requirements_by_gate: dict[str, dict[str, Any]] = {}
    required_gates: set[str] = set()
    for requirement in active_requirements:
        if not isinstance(requirement, dict):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
            continue
        gate_name = requirement.get("gate_name")
        if requirement.get("activation") == "active" and isinstance(gate_name, str):
            required_gates.add(gate_name)
            requirements_by_gate[gate_name] = requirement
        check_ids = requirement.get("required_check_ids", [])
        if requirement.get("gate_name") == ACTIVE_STATIC_GATE and not check_ids:
            diagnostics.append(ClosureErrorCode.SCHEMA_EMPTY_REQUIRED_PASS.value)

    superseded_ids = set(supersession_graph.values())
    effective_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt.get("attempt_id"), str)
        and attempt["attempt_id"] not in superseded_ids
    ]
    effective_by_gate: dict[str, list[dict[str, Any]]] = {}
    for attempt in effective_attempts:
        gate_name = attempt.get("gate_name")
        if isinstance(gate_name, str):
            effective_by_gate.setdefault(gate_name, []).append(attempt)

    computed_status_by_gate: dict[str, str] = {}
    for gate_name in required_gates:
        gate_attempts = effective_by_gate.get(gate_name, [])
        if len(gate_attempts) != 1:
            computed_status_by_gate[gate_name] = "FAIL"
            diagnostics.append(ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value)
            continue
        requirement = requirements_by_gate.get(gate_name, {})
        required_checks = requirement.get("required_check_ids", [])
        if not isinstance(required_checks, list):
            required_checks = []
        computed_status = _compute_gate_status(gate_attempts[0], required_checks)
        computed_status_by_gate[gate_name] = computed_status
        if computed_status != "PASS":
            diagnostics.append(ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value)
            if gate_attempts[0].get("status") == "PASS" and not _check_observations_pass(
                gate_attempts[0], required_checks
            ):
                diagnostics.append(ClosureErrorCode.CLOSURE_CHECK_OBSERVATION_MISSING.value)

    summaries: dict[str, dict[str, Any]] = {}
    for item in summaries_raw:
        if not isinstance(item, dict):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
            continue
        gate_name = item.get("gate_name")
        if isinstance(gate_name, str):
            if gate_name in summaries:
                diagnostics.append(ClosureErrorCode.SCHEMA_DUPLICATE_GATE.value)
            summaries[gate_name] = item

    extra_summaries = set(summaries) - required_gates
    if extra_summaries:
        diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_EXTRA.value)
    for gate_name in extra_summaries:
        summary = summaries[gate_name]
        if gate_name in INACTIVE_GATES | EXTERNAL_GATES:
            diagnostics.append(ClosureErrorCode.CLOSURE_INACTIVE_SUMMARY.value)
        if summary.get("activation") != "active":
            diagnostics.append(ClosureErrorCode.CLOSURE_INACTIVE_SUMMARY.value)

    for gate_name in required_gates:
        gate_summary = summaries.get(gate_name)
        if gate_summary is None:
            diagnostics.append(ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value)
            continue
        computed_status = computed_status_by_gate.get(gate_name, "FAIL")
        declared_status = gate_summary.get("aggregate_status")
        if declared_status != computed_status:
            diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_MISMATCH.value)

        attempt_ids = gate_summary.get("attempt_ids", [])
        if not isinstance(attempt_ids, list):
            diagnostics.append(ClosureErrorCode.CLOSURE_INVALID_INPUT.value)
            continue
        string_ids = [item for item in attempt_ids if isinstance(item, str)]
        if len(string_ids) != len(set(string_ids)):
            diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_DUPLICATE_ATTEMPT.value)
        expected_ids = sorted(attempts_by_gate.get(gate_name, []))
        if sorted(string_ids) != expected_ids:
            diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_HISTORY_MISMATCH.value)
        for attempt_id in string_ids:
            if attempt_id not in attempt_by_id:
                diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_ORPHAN_ATTEMPT.value)
                continue
            attempt = attempt_by_id[attempt_id]
            if attempt.get("gate_name") != gate_name:
                diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_WRONG_GATE.value)
            activation = gate_summary.get("activation")
            gate_identity = attempt.get("gate_identity")
            gate_activation = (
                gate_identity.get("activation") if isinstance(gate_identity, dict) else None
            )
            if activation != gate_activation:
                diagnostics.append(ClosureErrorCode.CLOSURE_SUMMARY_WRONG_GATE.value)

    computed_closure_status = "INCOMPLETE"
    if not diagnostics and required_gates == {ACTIVE_STATIC_GATE}:
        computed_closure_status = "COMPLETE"
        for gate_name in required_gates:
            if computed_status_by_gate.get(gate_name) != "PASS":
                computed_closure_status = "INCOMPLETE"
                break

    declared_closure_status = document.get("closure_status", "INCOMPLETE")
    if declared_closure_status != computed_closure_status:
        diagnostics.append(ClosureErrorCode.CLOSURE_DECLARED_STATUS_MISMATCH.value)

    if diagnostics:
        computed_closure_status = "INCOMPLETE"

    return AggregationResult(
        ok=not diagnostics,
        diagnostics=tuple(sorted(set(diagnostics))),
        closure_status=computed_closure_status,
    )


def _require_closed_keys(raw: dict[str, Any], allowed: frozenset[str], code: str) -> list[str]:
    unknown = set(raw) - allowed
    if unknown:
        return [f"{code}:{','.join(sorted(unknown))}"]
    return []


def _require_present_keys(raw: dict[str, Any], required: frozenset[str], code: str) -> list[str]:
    missing = required - set(raw)
    if missing:
        return [f"{code}:{','.join(sorted(missing))}"]
    return []


def _resolve_formal_owner(owner: str, repo_root: Path) -> Path | None:
    if owner.startswith("/") or "\\" in owner or ".." in owner.split("/"):
        return None
    if owner.startswith("temporary/") or owner.startswith("docs/"):
        return None
    if owner.startswith("formal/"):
        rel = f"{FORMAL_ROOT_REL}/{owner.removeprefix('formal/')}"
        return repo_root / rel
    return None


def _path_without_symlink_ancestor(repo_root: Path, rel_path: str) -> Path | None:
    repo_resolved = repo_root.resolve()
    current = repo_resolved
    parts = [part for part in rel_path.split("/") if part not in ("", ".")]
    for index, part in enumerate(parts):
        if part == "..":
            return None
        current = current / part
        if not current.exists() and not current.is_symlink():
            if index == len(parts) - 1:
                break
            return None
        try:
            if stat.S_ISLNK(os.lstat(current).st_mode):
                return None
        except OSError:
            return None
    try:
        resolved = current.resolve()
        resolved.relative_to(repo_resolved)
    except OSError, ValueError:
        if current.exists() or current.is_symlink():
            return None
    return current


def _safe_formal_owner_path(owner: str, repo_root: Path) -> Path | None:
    resolved = _resolve_formal_owner(owner, repo_root)
    if resolved is None:
        return None
    formal_root = (repo_root / FORMAL_ROOT_REL).resolve()
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        return None
    safe = _path_without_symlink_ancestor(repo_root, str(rel).replace("\\", "/"))
    if safe is None:
        return None
    try:
        safe.resolve().relative_to(formal_root)
    except OSError, ValueError:
        return None
    return safe


def _formal_evidence_diagnostics(owner: str, repo_root: Path) -> list[str]:
    diagnostics: list[str] = []
    raw = _resolve_formal_owner(owner, repo_root)
    if raw is None:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_INVALID.value)
        return diagnostics
    try:
        rel = str(raw.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_INVALID.value)
        return diagnostics
    safe = _path_without_symlink_ancestor(repo_root, rel)
    if safe is None:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_ESCAPE.value)
        return diagnostics
    formal_root = (repo_root / FORMAL_ROOT_REL).resolve()
    try:
        safe.resolve().relative_to(formal_root)
    except OSError, ValueError:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_INVALID.value)
        return diagnostics
    if not safe.exists() or not safe.is_file():
        diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_MISSING.value)
    return diagnostics


def _read_utf8_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError, OSError:
        return None


def parse_decision_ledger(
    repo_root: Path,
) -> tuple[frozenset[str], frozenset[str], bool, bool]:
    accepted: list[str] = []
    superseded: list[str] = []
    seen: set[str] = set()
    has_duplicates = False
    read_failed = False
    ledger_dir = repo_root / "docs/backend-vnext/refactoring/temporary/phase-2"
    for path in sorted(ledger_dir.glob("decision-ledger-round-*.md")):
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError, OSError:
            read_failed = True
            continue
        sections = re.split(r"(?=^### P2-R\d+-D\d+ —)", text, flags=re.MULTILINE)
        for section in sections:
            header = re.match(r"^### (P2-R\d+-D\d+) —", section)
            if header is None:
                continue
            decision_id = header.group(1)
            if decision_id in seen:
                has_duplicates = True
            seen.add(decision_id)
            status_match = re.search(
                r"^\| Status \| `(ACCEPTED|SUPERSEDED|REJECTED|DEFERRED|OPEN)` \|",
                section,
                flags=re.MULTILINE,
            )
            if status_match is None:
                continue
            status = status_match.group(1)
            if status == "ACCEPTED":
                accepted.append(decision_id)
            elif status == "SUPERSEDED":
                superseded.append(decision_id)
    if len(accepted) != len(set(accepted)) or len(superseded) != len(set(superseded)):
        has_duplicates = True
    return frozenset(accepted), frozenset(superseded), has_duplicates, read_failed


def lint_traceability(repo_root: Path) -> LintResult:
    diagnostics: list[str] = []
    traceability_path = repo_root / TRACEABILITY_REL
    if not traceability_path.is_file():
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
        return LintResult(False, tuple(sorted(diagnostics)))

    try:
        doc = loads_strict_yaml_bytes(traceability_path.read_bytes())
    except StrictYAMLValidationError as exc:
        message = str(exc)
        if "root must be a mapping" in message or "YAML document is empty" in message:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
        else:
            diagnostics.append(ClosureErrorCode.SCHEMA_STRICT_YAML.value)
        return LintResult(False, tuple(sorted(diagnostics)))
    except OSError:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
        return LintResult(False, tuple(sorted(diagnostics)))

    if not isinstance(doc, dict):
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
        return LintResult(False, tuple(sorted(diagnostics)))

    diagnostics.extend(
        _require_present_keys(
            doc, _TRACEABILITY_TOP_KEYS, ClosureErrorCode.TRACEABILITY_BLOCKER_MISSING.value
        )
    )
    diagnostics.extend(
        _require_closed_keys(
            doc, _TRACEABILITY_TOP_KEYS, ClosureErrorCode.TRACEABILITY_UNKNOWN_FIELD.value
        )
    )

    if doc.get("schema_version") != 1:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
    if doc.get("plan_id") != EXPECTED_PLAN_ID:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
    if doc.get("status") != EXPECTED_TRACEABILITY_STATUS:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)

    summary = doc.get("decision_summary", {})
    if isinstance(summary, dict):
        diagnostics.extend(
            _require_closed_keys(
                summary, _SUMMARY_KEYS, ClosureErrorCode.TRACEABILITY_UNKNOWN_FIELD.value
            )
        )
        if summary.get("total") != EXPECTED_DECISION_TOTAL:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SUMMARY_DRIFT.value)
        if summary.get("accepted") != EXPECTED_DECISION_ACCEPTED:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SUMMARY_DRIFT.value)
        if summary.get("superseded") != EXPECTED_DECISION_SUPERSEDED:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SUMMARY_DRIFT.value)
        if summary.get("open") != EXPECTED_DECISION_OPEN:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SUMMARY_DRIFT.value)

    requirements = doc.get("requirements", [])
    if not isinstance(requirements, list):
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
        return LintResult(False, tuple(sorted(set(diagnostics))))

    accepted_decisions: list[str] = []
    requirement_ids: list[str] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
            continue
        diagnostics.extend(
            _require_closed_keys(
                requirement,
                _REQUIREMENT_KEYS,
                ClosureErrorCode.TRACEABILITY_UNKNOWN_FIELD.value,
            )
        )
        req_id = requirement.get("requirement_id")
        if isinstance(req_id, str):
            requirement_ids.append(req_id)
            if not _REQUIREMENT_ID_PATTERN.fullmatch(req_id):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)

        for field in ("formal_owners", "work_packages", "gates", "evidence"):
            values = requirement.get(field)
            if not isinstance(values, list) or not values:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_EMPTY_MAPPING.value)
                continue
            if len(values) != len(set(values)):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_DECISION_DUPLICATE.value)

        for owner in requirement.get("formal_owners", []):
            if not isinstance(owner, str):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_OWNER_INVALID.value)
                continue
            if any(marker in owner for marker in _TEMPORARY_OWNER_MARKERS):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_TEMPORARY_OWNER.value)
            diagnostics.extend(_formal_evidence_diagnostics(owner, repo_root))

        for wp in requirement.get("work_packages", []):
            if wp not in KNOWN_WORK_PACKAGES:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_UNKNOWN_WP.value)

        for gate in requirement.get("gates", []):
            if gate not in KNOWN_GATES:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_UNKNOWN_GATE.value)

        for decision_id in requirement.get("decision_ids", []):
            if isinstance(decision_id, str):
                accepted_decisions.append(decision_id)
                if not _DECISION_ID_PATTERN.fullmatch(decision_id):
                    diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)

        if isinstance(req_id, str):
            expected = EXPECTED_REQUIREMENT_MAPPINGS.get(req_id)
            if expected is None:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_MAPPING_MISMATCH.value)
            else:
                for field in (
                    "decision_ids",
                    "formal_owners",
                    "work_packages",
                    "gates",
                    "evidence",
                ):
                    actual = requirement.get(field, [])
                    if not isinstance(actual, list):
                        diagnostics.append(ClosureErrorCode.TRACEABILITY_MAPPING_MISMATCH.value)
                        continue
                    if tuple(actual) != expected[field]:
                        diagnostics.append(ClosureErrorCode.TRACEABILITY_MAPPING_MISMATCH.value)

    if set(requirement_ids) != set(EXPECTED_REQUIREMENT_MAPPINGS):
        diagnostics.append(ClosureErrorCode.TRACEABILITY_MAPPING_MISMATCH.value)

    if len(requirement_ids) != len(set(requirement_ids)):
        diagnostics.append(ClosureErrorCode.TRACEABILITY_DECISION_DUPLICATE.value)

    accepted_set = set(accepted_decisions)
    if len(accepted_decisions) != len(accepted_set):
        diagnostics.append(ClosureErrorCode.TRACEABILITY_DECISION_DUPLICATE.value)

    superseded_entries = doc.get("superseded_decisions", [])
    superseded_ids: set[str] = set()
    superseded_pairs: list[tuple[str, str]] = []
    if isinstance(superseded_entries, list):
        for entry in superseded_entries:
            if not isinstance(entry, dict):
                continue
            diagnostics.extend(
                _require_closed_keys(
                    entry,
                    _SUPERSEDED_KEYS,
                    ClosureErrorCode.TRACEABILITY_UNKNOWN_FIELD.value,
                )
            )
            decision_id = entry.get("decision_id")
            superseded_by = entry.get("superseded_by")
            if isinstance(decision_id, str) and isinstance(superseded_by, str):
                pair = (decision_id, superseded_by)
                if pair in superseded_pairs:
                    diagnostics.append(ClosureErrorCode.TRACEABILITY_SUPERSEDED_DUPLICATE.value)
                superseded_pairs.append(pair)
            if isinstance(decision_id, str):
                if decision_id in superseded_ids:
                    diagnostics.append(ClosureErrorCode.TRACEABILITY_SUPERSEDED_DUPLICATE.value)
                superseded_ids.add(decision_id)
                if decision_id in accepted_set:
                    diagnostics.append(
                        ClosureErrorCode.TRACEABILITY_SUPERSEDED_IN_REQUIREMENT.value
                    )
                if decision_id == superseded_by:
                    diagnostics.append(ClosureErrorCode.TRACEABILITY_SUPERSEDED_MAPPING.value)
            if isinstance(superseded_by, str) and superseded_by not in accepted_set:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_SUPERSEDED_MAPPING.value)

    if len(superseded_ids) != EXPECTED_DECISION_SUPERSEDED:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SUPERSEDED_MAPPING.value)

    if len(accepted_set) != EXPECTED_DECISION_ACCEPTED:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_DECISION_MISSING.value)

    ledger_accepted, ledger_superseded, ledger_duplicates, ledger_read_failed = (
        parse_decision_ledger(repo_root)
    )
    if ledger_read_failed:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
    if ledger_duplicates:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_LEDGER_DUPLICATE.value)
    if ledger_accepted != accepted_set:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_LEDGER_MISMATCH.value)
    if ledger_superseded != superseded_ids:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_LEDGER_MISMATCH.value)

    blockers = doc.get("blocking_register")
    blocker_ids: list[str] = []
    observed_blockers: dict[str, str] = {}
    if not isinstance(blockers, list) or not blockers:
        diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISSING.value)
    else:
        for blocker in blockers:
            if not isinstance(blocker, dict):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value)
                continue
            diagnostics.extend(
                _require_closed_keys(
                    blocker,
                    _BLOCKER_KEYS,
                    ClosureErrorCode.TRACEABILITY_UNKNOWN_FIELD.value,
                )
            )
            blocker_id = blocker.get("id")
            status = blocker.get("status")
            evidence = blocker.get("evidence")
            if not isinstance(blocker_id, str):
                diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value)
                continue
            blocker_ids.append(blocker_id)
            if status != "closed":
                diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_OPEN.value)
            if not isinstance(evidence, str) or not evidence:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value)
            else:
                observed_blockers[blocker_id] = evidence
                if blocker_id == "F0-B4":
                    diagnostics.extend(_formal_evidence_diagnostics(evidence, repo_root))
        if len(blocker_ids) != len(set(blocker_ids)):
            diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_DUPLICATE.value)
        expected_ids = set(EXPECTED_BLOCKERS)
        observed_ids = set(observed_blockers)
        if observed_ids != expected_ids:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value)
        for blocker_id, expected_evidence in EXPECTED_BLOCKERS.items():
            if observed_blockers.get(blocker_id) != expected_evidence:
                diagnostics.append(ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value)

    for owner in FORMAL_MARKER_OWNERS:
        marker_diags = _formal_evidence_diagnostics(owner, repo_root)
        diagnostics.extend(marker_diags)
        if marker_diags:
            continue
        safe = _safe_formal_owner_path(owner, repo_root)
        if safe is None:
            continue
        text = _read_utf8_text(safe)
        if text is None:
            diagnostics.append(ClosureErrorCode.TRACEABILITY_SCHEMA.value)
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and _FORMAL_UNRESOLVED_RE.search(stripped):
                if "OPEN" in stripped or "blocking" in stripped.lower():
                    diagnostics.append(ClosureErrorCode.TRACEABILITY_FORMAL_UNRESOLVED.value)
                    break

    sanitized = tuple(sorted({sanitize_message(item) for item in diagnostics}))
    return LintResult(ok=not sanitized, diagnostics=sanitized)


def run_validate(repo_root: Path) -> LintResult:
    diagnostics: list[str] = []

    trace = lint_traceability(repo_root)
    diagnostics.extend(trace.diagnostics)

    protection = verify_phase1_protection(repo_root)
    if not protection.ok:
        diagnostics.append(ClosureErrorCode.PHASE1_PROTECTION.value)
        diagnostics.extend(protection.diagnostics)

    sanitized = tuple(sorted({sanitize_message(item) for item in diagnostics}))
    return LintResult(ok=not sanitized, diagnostics=sanitized)


def cli_validate(repo_root: Path) -> int:
    result = run_validate(repo_root)
    payload = {
        "command": "validate",
        "ok": result.ok,
        "diagnostics": list(result.diagnostics),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2 closure and traceability lint")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--repo-root", default=str(_repo_root_from_default()))
    args = parser.parse_args(argv)

    if args.command == "validate":
        return cli_validate(Path(args.repo_root).resolve())

    return 1


if __name__ == "__main__":
    sys.exit(main())
