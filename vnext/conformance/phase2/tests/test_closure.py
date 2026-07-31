"""WP0-R3 closure, schema and Phase 1 protection tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from closure import (
    ClosureErrorCode,
    aggregate_closure,
    cli_validate,
    loads_document_json,
    loads_document_yaml_bytes,
    lint_traceability,
    parse_decision_ledger,
    run_validate,
    validate_closure_document,
    validate_gate_attempt_document,
)
from gateway_conformance.strict_yaml import StrictYAMLValidationError, loads_strict_yaml_bytes
from phase1_protection import (
    IDENTITY_ARTIFACT_REL,
    IDENTITY_BASENAME,
    PHASE1_EXIT_SOURCE,
    SIGNOFF_REL,
    Phase1ProtectionCode,
    verify_phase1_protection,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFORMANCE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = CONFORMANCE_ROOT / "phase2" / "schemas"

_MODULE_CLONE: Path | None = None

_LOCK_DIGESTS = [
    {
        "path": "vnext/conformance/uv.lock",
        "digest": "sha256:36091eadcfd8fde94983d4d843f095494f493ce75da02049415b574c468575d4",
    },
    {
        "path": "vnext/rust/Cargo.lock",
        "digest": "sha256:95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544",
    },
]

_WP0_CHECK_OBSERVATIONS = [
    {
        "check_id": check_id,
        "outcome": "PASS",
        "diagnostics": [f"check:{check_id}:exit=0"],
    }
    for check_id in (
        "static.ruff",
        "static.mypy",
        "static.pytest",
        "static.lock.conformance",
        "static.closure",
    )
]

_BINDING_FIELDS: dict[str, Any] = {
    "runtime_build_identity": {
        "python_version": "Python 3.14.6",
        "uv_version": "uv 0.11.28",
        "rustc_version": "rustc 1.97.0",
    },
    "environment_fingerprint": {
        "host_python_version": "Python 3.14.6",
        "host_uv_version": "uv 0.11.28",
        "lock_digests": list(_LOCK_DIGESTS),
    },
    "artifact_digests": [
        {
            "path": "vnext/conformance/dist/gateway_conformance-0.0.0-py3-none-any.whl",
            "digest": "sha256:" + "a" * 64,
        }
    ],
    "image_digests": [],
    "required_check_observations": list(_WP0_CHECK_OBSERVATIONS),
    "fault_receipts": [],
    "cleanup_result": {"status": "CLEAN", "diagnostics": []},
}


def _minimal_gate_attempt(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "gate_attempt_schema_version": 1,
        "attempt_id": "attempt-static-1",
        "gate_name": "P2-PR-STATIC",
        "status": "PASS",
        "candidate_revision": "a" * 40,
        "candidate_identity": {"revision": "a" * 40, "worktree_status": "clean"},
        "gate_identity": {
            "gate_name": "P2-PR-STATIC",
            "activation": "active",
            "gate_schema_version": 1,
        },
        "environment_binding": {"lock_digests": list(_LOCK_DIGESTS)},
        "evidence_binding": {"evidence_ids": ["static-pass"]},
        "recorded_result": {"diagnostics": ["check:static.ruff:exit=0"]},
        **_BINDING_FIELDS,
    }
    doc.update(overrides)
    return doc


def _minimal_closure(**overrides: Any) -> dict[str, Any]:
    attempt = _minimal_gate_attempt()
    doc: dict[str, Any] = {
        "closure_schema_version": 1,
        "candidate_revision": attempt["candidate_revision"],
        "candidate_identity": attempt["candidate_identity"],
        "environment_binding": attempt["environment_binding"],
        "gate_attempts": [attempt],
        "gate_summaries": [
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "PASS",
                "attempt_ids": ["attempt-static-1"],
            }
        ],
        "active_gate_requirements": [
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "required_check_ids": [
                    "static.ruff",
                    "static.mypy",
                    "static.pytest",
                    "static.lock.conformance",
                    "static.closure",
                ],
            }
        ],
        "closure_status": "COMPLETE",
    }
    doc.update(overrides)
    return doc


# Schema tests 1-11


def test_schema_valid_minimal_gate_attempt() -> None:
    assert validate_gate_attempt_document(_minimal_gate_attempt()).ok


def test_schema_valid_minimal_closure() -> None:
    assert validate_closure_document(_minimal_closure()).ok


def test_schema_unknown_field_gate_attempt() -> None:
    doc = _minimal_gate_attempt(extra_field=True)
    assert not validate_gate_attempt_document(doc).ok


def test_schema_missing_required_field() -> None:
    doc = _minimal_gate_attempt()
    del doc["attempt_id"]
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_MISSING_REQUIRED.value in result.diagnostics


def test_schema_wrong_schema_version() -> None:
    doc = _minimal_gate_attempt(gate_attempt_schema_version=2)
    assert not validate_gate_attempt_document(doc).ok


def test_schema_malformed_revision() -> None:
    doc = _minimal_gate_attempt(candidate_revision="abc")
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_MALFORMED_REVISION.value in result.diagnostics


def test_schema_malformed_digest() -> None:
    doc = _minimal_gate_attempt(
        environment_binding={
            "lock_digests": [{"path": "vnext/conformance/uv.lock", "digest": "bad"}]
        }
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_MALFORMED_DIGEST.value in result.diagnostics


def test_schema_malformed_attempt_id() -> None:
    doc = _minimal_gate_attempt(attempt_id="INVALID")
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_MALFORMED_ATTEMPT_ID.value in result.diagnostics


def test_schema_unknown_gate() -> None:
    doc = _minimal_gate_attempt(gate_name="P2-UNKNOWN")
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_UNKNOWN_GATE.value in result.diagnostics


def test_schema_unknown_status() -> None:
    doc = _minimal_gate_attempt(status="DELEGATED")
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_UNKNOWN_STATUS.value in result.diagnostics


def test_schema_unknown_activation() -> None:
    doc = _minimal_gate_attempt(
        gate_identity={"gate_name": "P2-PR-STATIC", "activation": "bogus", "gate_schema_version": 1}
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_UNKNOWN_ACTIVATION.value in result.diagnostics


def test_schema_duplicate_attempt_in_closure() -> None:
    attempt = _minimal_gate_attempt()
    doc = _minimal_closure(gate_attempts=[attempt, deepcopy(attempt)])
    result = validate_closure_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_DUPLICATE_ATTEMPT.value in result.diagnostics


def test_schema_duplicate_gate_summary() -> None:
    doc = _minimal_closure()
    summaries = doc["gate_summaries"]
    doc["gate_summaries"] = summaries + [deepcopy(summaries[0])]
    result = validate_closure_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_DUPLICATE_GATE.value in result.diagnostics


def test_schema_duplicate_evidence_ids() -> None:
    doc = _minimal_gate_attempt(evidence_binding={"evidence_ids": ["dup", "dup"]})
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_DUPLICATE_EVIDENCE.value in result.diagnostics


def test_schema_fail_laundered_as_pass() -> None:
    doc = _minimal_gate_attempt(
        status="PASS",
        recorded_result={"diagnostics": ["status:DELEGATED"]},
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_PASS_LAUNDERING.value in result.diagnostics


def test_schema_inactive_gate_pass() -> None:
    doc = _minimal_gate_attempt(
        gate_name="P2-PR-CONTRACT",
        gate_identity={
            "gate_name": "P2-PR-CONTRACT",
            "activation": "inactive",
            "gate_schema_version": 1,
        },
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_INACTIVE_GATE_PASS.value in result.diagnostics


def test_schema_empty_required_checks_cannot_pass() -> None:
    doc = _minimal_closure(
        active_gate_requirements=[
            {"gate_name": "P2-PR-STATIC", "activation": "active", "required_check_ids": []}
        ]
    )
    result = validate_closure_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_EMPTY_REQUIRED_PASS.value in result.diagnostics


@pytest.mark.parametrize(
    "document",
    [
        "{not-json",
        '{"nan": .nan}',
        "key: !!python/object:os.system []\n",
        "key: &a 1\nother: *a\n",
        "key: 1\nkey: 2\n",
        "first\n---\nsecond\n",
        b"\xff\xfe",
    ],
)
def test_schema_strict_document_failures(document: str | bytes) -> None:
    if isinstance(document, bytes):
        with pytest.raises((ValueError, StrictYAMLValidationError, UnicodeDecodeError)):
            loads_document_yaml_bytes(document)
        return
    if document.startswith("{"):
        with pytest.raises(ValueError):
            loads_document_json(document)
        return
    with pytest.raises((ValueError, StrictYAMLValidationError)):
        loads_strict_yaml_bytes(document.encode("utf-8"))


# Attempt/closure tests 12-24


def test_frozen_gate_attempt_dataclass_mutation_fails() -> None:
    from closure import LintResult

    original = LintResult(ok=True, diagnostics=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        original.ok = False  # type: ignore[misc]


def test_input_reordering_stable_diagnostics() -> None:
    doc = _minimal_closure()
    doc["gate_attempts"] = list(reversed(doc["gate_attempts"]))
    first = validate_closure_document(doc)
    second = validate_closure_document(doc)
    assert first.diagnostics == second.diagnostics


def test_aggregate_valid_same_candidate_attempts() -> None:
    result = aggregate_closure(_minimal_closure())
    assert result.ok
    assert result.closure_status == "COMPLETE"


def test_aggregate_cross_candidate_rejected() -> None:
    attempt = _minimal_gate_attempt()
    other = _minimal_gate_attempt(
        attempt_id="attempt-static-2",
        candidate_revision="b" * 40,
    )
    doc = _minimal_closure(gate_attempts=[attempt, other])
    result = aggregate_closure(doc)
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_CROSS_CANDIDATE.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value in result.diagnostics
    )


def test_aggregate_cross_environment_rejected() -> None:
    attempt = _minimal_gate_attempt()
    other = _minimal_gate_attempt(
        attempt_id="attempt-static-2",
        environment_binding={
            "lock_digests": [{"path": "vnext/conformance/uv.lock", "digest": "sha256:" + "b" * 64}]
        },
    )
    doc = _minimal_closure(gate_attempts=[attempt, other])
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_CROSS_ENVIRONMENT.value in result.diagnostics


def test_aggregate_missing_required_gate_rejected() -> None:
    doc = _minimal_closure(
        gate_attempts=[_minimal_gate_attempt(status="FAIL")],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "FAIL",
                "attempt_ids": ["attempt-static-1"],
            }
        ],
        closure_status="INCOMPLETE",
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value in result.diagnostics


def test_aggregate_duplicate_attempt_id_rejected() -> None:
    attempt = _minimal_gate_attempt()
    doc = _minimal_closure(gate_attempts=[attempt, deepcopy(attempt)])
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_DUPLICATE_ATTEMPT_ID.value in result.diagnostics


def test_aggregate_supersession_orphan_rejected() -> None:
    doc = _minimal_closure()
    attempts = doc["gate_attempts"]
    attempts[0]["supersession"] = {
        "supersedes_attempt_id": "missing-parent",
        "reason": "retry",
    }
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUPERSESSION_ORPHAN.value in result.diagnostics


def test_aggregate_supersession_cycle_rejected() -> None:
    first = _minimal_gate_attempt(attempt_id="attempt-a")
    second = _minimal_gate_attempt(
        attempt_id="attempt-b",
        status="FAIL",
        supersession={"supersedes_attempt_id": "attempt-a", "reason": "retry"},
    )
    first["supersession"] = {"supersedes_attempt_id": "attempt-b", "reason": "retry"}
    doc = _minimal_closure(
        gate_attempts=[first, second],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "FAIL",
                "attempt_ids": ["attempt-a", "attempt-b"],
            }
        ],
        closure_status="INCOMPLETE",
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUPERSESSION_CYCLE.value in result.diagnostics


def test_retry_supersession_pass_is_allowed() -> None:
    failed = _minimal_gate_attempt(attempt_id="attempt-fail", status="FAIL")
    passed = _minimal_gate_attempt(
        attempt_id="attempt-pass",
        status="PASS",
        supersession={"supersedes_attempt_id": "attempt-fail", "reason": "retry"},
    )
    doc = _minimal_closure(
        gate_attempts=[failed, passed],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "PASS",
                "attempt_ids": ["attempt-fail", "attempt-pass"],
            }
        ],
    )
    result = aggregate_closure(doc)
    assert result.ok
    assert result.closure_status == "COMPLETE"


def test_assertion_failure_is_fail_not_blocked() -> None:
    doc = _minimal_gate_attempt(
        status="FAIL", recorded_result={"diagnostics": ["assertion_failed"]}
    )
    result = validate_gate_attempt_document(doc)
    assert result.ok
    assert doc["status"] == "FAIL"


def test_blocked_only_for_external_unavailable() -> None:
    doc = _minimal_gate_attempt(
        status="BLOCKED",
        block_reason="uv_unavailable",
        recorded_result={"diagnostics": ["uv_unavailable"]},
    )
    assert validate_gate_attempt_document(doc).ok


def test_blocked_assertion_failed_rejected() -> None:
    doc = _minimal_gate_attempt(
        status="BLOCKED",
        block_reason="uv_unavailable",
        recorded_result={"diagnostics": ["assertion_failed"]},
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_INVALID_BLOCKED_STATUS.value in result.diagnostics


def test_inactive_contract_recovery_container_no_pass() -> None:
    for gate_name in ("P2-PR-CONTRACT", "P2-PR-RECOVERY", "P2-PHASE-EXIT-CONTAINER"):
        doc = _minimal_gate_attempt(
            gate_name=gate_name,
            status="PASS",
            gate_identity={
                "gate_name": gate_name,
                "activation": "inactive",
                "gate_schema_version": 1,
            },
        )
        result = validate_gate_attempt_document(doc)
        assert not result.ok


def test_external_gates_not_locally_passed() -> None:
    for gate_name in ("PR-CORRECTNESS", "PR-NATIVE"):
        doc = _minimal_gate_attempt(
            gate_name=gate_name,
            status="PASS",
            gate_identity={
                "gate_name": gate_name,
                "activation": "external",
                "gate_schema_version": 1,
            },
        )
        result = validate_gate_attempt_document(doc)
        assert not result.ok
        closure_doc = _minimal_closure(
            gate_attempts=[doc],
            gate_summaries=[
                {
                    "gate_name": gate_name,
                    "activation": "external",
                    "aggregate_status": "PASS",
                    "attempt_ids": [doc["attempt_id"]],
                }
            ],
        )
        agg = aggregate_closure(closure_doc)
        assert (
            ClosureErrorCode.CLOSURE_EXTERNAL_PASS.value in agg.diagnostics
            or ClosureErrorCode.SCHEMA_INACTIVE_GATE_PASS.value in agg.diagnostics
        )


# Traceability tests 25-36


def test_traceability_current_formal_positive() -> None:
    assert lint_traceability(REPO_ROOT).ok


def test_traceability_accepted_decision_missing(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    )
    copy = tmp_path / "trace.yaml"
    copy.write_text(trace.read_text(encoding="utf-8"), encoding="utf-8")
    text = copy.read_text(encoding="utf-8")
    text = text.replace("P2-R0-D02\n", "")
    copy.write_text(text, encoding="utf-8")
    fake_root = tmp_path
    (fake_root / "docs/backend-vnext/refactoring/formal/plans").mkdir(parents=True)
    (fake_root / "docs/backend-vnext/refactoring/temporary/phase-2").mkdir(parents=True)
    for ledger in (REPO_ROOT / "docs/backend-vnext/refactoring/temporary/phase-2").glob(
        "decision-ledger-round-*.md"
    ):
        target = fake_root / ledger.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ledger.read_text(encoding="utf-8"), encoding="utf-8")
    (fake_root / "docs/backend-vnext/refactoring/formal").mkdir(parents=True, exist_ok=True)
    for owner in REPO_ROOT.glob("docs/backend-vnext/refactoring/formal/**/*.md"):
        target = fake_root / owner.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(owner.read_text(encoding="utf-8"), encoding="utf-8")
    (
        fake_root
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).write_text(
        copy.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = lint_traceability(fake_root)
    assert not result.ok


def test_traceability_superseded_in_requirements(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        "      - P2-R0-D06\n",
        "      - P2-R0-D06\n      - P2-R0-D01\n",
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_SUPERSEDED_IN_REQUIREMENT.value in result.diagnostics


def test_traceability_summary_count_drift(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace("  total: 148", "  total: 149")
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_SUMMARY_DRIFT.value in result.diagnostics


def test_traceability_duplicate_requirement(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = (
        trace
        + "\n  - requirement_id: P2-REQ-GOVERNANCE\n    description: dup\n    decision_ids: [P2-R0-D02]\n    formal_owners: [formal/plans/phase-2-implementation-design-and-delivery-plan.md]\n    work_packages: [F0]\n    gates: [P2-PR-STATIC]\n    evidence: [formal-closure-manifest]\n"
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok


def test_traceability_blocker_open(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace("    status: closed", "    status: open", 1)
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_BLOCKER_OPEN.value in result.diagnostics


def test_traceability_unknown_gate(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace("P2-PR-STATIC", "P2-UNKNOWN-GATE", 1)
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_UNKNOWN_GATE.value in result.diagnostics


def test_traceability_unknown_wp(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace("work_packages: [F0, WP0", "work_packages: [F0, WP99", 1)
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_UNKNOWN_WP.value in result.diagnostics


def test_traceability_empty_owner_mapping(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        """    evidence:
      - formal-closure-manifest
      - architecture-import-boundary
      - current-versioned-independence
      - exact-candidate-signoff""",
        "    evidence: []",
        1,
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_EMPTY_MAPPING.value in result.diagnostics


def test_traceability_owner_missing(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        "formal/architecture/architecture-and-refactoring-plan.md",
        "formal/architecture/missing-owner.md",
        1,
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_OWNER_MISSING.value in result.diagnostics


def test_traceability_owner_absolute_path(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        "formal/architecture/architecture-and-refactoring-plan.md",
        "/etc/passwd",
        1,
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_OWNER_INVALID.value in result.diagnostics


def test_traceability_temporary_owner_forbidden(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        "formal/architecture/architecture-and-refactoring-plan.md",
        "temporary/phase-2/decision-ledger-round-8-to-11.md",
        1,
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert ClosureErrorCode.TRACEABILITY_TEMPORARY_OWNER.value in result.diagnostics


def test_traceability_output_order_stable() -> None:
    first = lint_traceability(REPO_ROOT)
    second = lint_traceability(REPO_ROOT)
    assert first.diagnostics == second.diagnostics


def _copy_traceability_fixture(tmp_path: Path, trace_text: str) -> Path:
    fake_root = tmp_path / "repo"
    for ledger in (REPO_ROOT / "docs/backend-vnext/refactoring/temporary/phase-2").glob(
        "decision-ledger-round-*.md"
    ):
        target = fake_root / ledger.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ledger.read_text(encoding="utf-8"), encoding="utf-8")
    for owner in REPO_ROOT.glob("docs/backend-vnext/refactoring/formal/**/*.md"):
        target = fake_root / owner.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(owner.read_text(encoding="utf-8"), encoding="utf-8")
    trace_path = (
        fake_root
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    )
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(trace_text, encoding="utf-8")
    return fake_root


# Phase 1 protection tests 37-49


def test_phase1_protection_current_repo_positive() -> None:
    assert verify_phase1_protection(REPO_ROOT).ok


def _copy_identity_artifacts_to_clone(dest: Path) -> None:
    artifact_src = REPO_ROOT / IDENTITY_ARTIFACT_REL
    if not artifact_src.is_file():
        return
    artifact_dest = dest / IDENTITY_ARTIFACT_REL
    artifact_dest.parent.mkdir(parents=True, exist_ok=True)
    artifact_dest.write_bytes(artifact_src.read_bytes())
    latest_src = artifact_src.parent / "phase-exit-container-identity-latest.json"
    if latest_src.is_symlink():
        latest_dest = dest / latest_src.relative_to(REPO_ROOT)
        if latest_dest.exists() or latest_dest.is_symlink():
            latest_dest.unlink()
        latest_dest.symlink_to(str(latest_src.readlink()))


def _copy_candidate_phase2_into_clone(dest: Path) -> None:
    candidates = (
        "vnext/conformance/phase2/closure.py",
        "vnext/conformance/phase2/phase1_protection.py",
        "vnext/conformance/phase2/schemas/gate-attempt-v1.json",
        "vnext/conformance/phase2/schemas/closure-v1.json",
    )
    for rel in candidates:
        src = REPO_ROOT / rel
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _clone_repo_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    if dest.exists():
        shutil.rmtree(dest)
    proc = subprocess.run(
        ["git", "clone", "--shared", str(REPO_ROOT), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(f"git clone failed: {proc.stderr}")
    _copy_identity_artifacts_to_clone(dest)
    _copy_candidate_phase2_into_clone(dest)
    return dest


def test_phase1_identity_artifact_content_modified(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    artifact = repo / IDENTITY_ARTIFACT_REL
    artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.IDENTITY_DIGEST_MISMATCH.value in result.diagnostics


def test_phase1_identity_filename_digest_mismatch(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    artifact = repo / IDENTITY_ARTIFACT_REL
    wrong = artifact.with_name("phase-exit-container-identity-wrong.json")
    wrong.write_bytes(artifact.read_bytes())
    artifact.unlink()
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.IDENTITY_ARTIFACT_MISSING.value in result.diagnostics


def test_phase1_signoff_source_revision_modified(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    signoff = repo / "docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md"
    signoff.write_text(
        signoff.read_text(encoding="utf-8").replace(PHASE1_EXIT_SOURCE, "f" * 40), encoding="utf-8"
    )
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.SIGNOFF_SOURCE_REVISION.value in result.diagnostics


def test_phase1_artifact_source_revision_current_head(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    artifact = repo / IDENTITY_ARTIFACT_REL
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    doc["source_revision"] = head
    doc["expected_head"] = head
    artifact.write_text(json.dumps(doc), encoding="utf-8")
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.IDENTITY_SOURCE_REVISION.value in result.diagnostics


def test_phase1_frozen_gate_script_modified(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    script = repo / "vnext/scripts/phase_exit_container_gate.sh"
    script.write_text(script.read_text(encoding="utf-8") + "\n# mutated\n", encoding="utf-8")
    result = verify_phase1_protection(repo)
    assert any(
        Phase1ProtectionCode.PROTECTED_FILE_MODIFIED.value in item for item in result.diagnostics
    )


def test_phase1_protected_file_deleted(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    (repo / "vnext/deploy/phase-1-image-pins.env").unlink()
    result = verify_phase1_protection(repo)
    assert any(
        Phase1ProtectionCode.PROTECTED_FILE_MISSING.value in item for item in result.diagnostics
    )


def test_phase1_protected_symlink_replacement(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    pins = repo / "vnext/deploy/phase-1-image-pins.env"
    pins.unlink()
    pins.symlink_to("/etc/passwd")
    result = verify_phase1_protection(repo)
    assert any("symlink_replacement" in item for item in result.diagnostics)


def test_phase1_alternate_identity_ambiguity(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    alt = (
        repo
        / "docs/backend-vnext/refactoring/temporary/phase-1/artifacts/phase-exit-container-identity-ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff.json"
    )
    alt.write_text("{}", encoding="utf-8")
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value in result.diagnostics


def test_phase1_phase2_new_files_do_not_false_positive(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    new_file = repo / "vnext/conformance/phase2/new-phase2-only.txt"
    new_file.write_text("phase2", encoding="utf-8")
    assert verify_phase1_protection(repo).ok


def test_phase1_current_head_not_exit_source_still_passes() -> None:
    head = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head != PHASE1_EXIT_SOURCE
    assert verify_phase1_protection(REPO_ROOT).ok


def test_phase1_does_not_require_current_locks_match_artifact() -> None:
    artifact_path = REPO_ROOT / IDENTITY_ARTIFACT_REL
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    embedded = next(
        item
        for item in artifact["lockfiles"]
        if item["path"].endswith("repository_service/uv.lock")
    )
    current = (REPO_ROOT / "vnext/repository_service/uv.lock").read_bytes()
    current_digest = hashlib.sha256(current).hexdigest()
    assert embedded["sha256"] != current_digest
    assert verify_phase1_protection(REPO_ROOT).ok


def test_phase1_non_git_path_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "not-git"
    repo.mkdir()
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.NON_GIT_REPO.value in result.diagnostics


def test_phase1_missing_baseline_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "empty-git"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    result = verify_phase1_protection(repo)
    assert Phase1ProtectionCode.BASELINE_MISSING.value in result.diagnostics


# Static/CLI tests 50-54 (55-56 in test_router.py)


def test_cli_validate_positive() -> None:
    assert cli_validate(REPO_ROOT) == 0


def test_cli_validate_negative(tmp_path: Path) -> None:
    repo = tmp_path / "not-git"
    repo.mkdir()
    assert cli_validate(repo) == 1


def test_cli_output_stable_json_no_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_validate(REPO_ROOT)
    captured = capsys.readouterr()
    assert code == 0
    assert "Traceback" not in captured.out
    payload = json.loads(captured.out)
    assert payload["command"] == "validate"
    assert "/root/" not in captured.out


def test_run_validate_matches_cli() -> None:
    assert run_validate(REPO_ROOT).ok


def test_decision_ledger_parse_counts() -> None:
    accepted, superseded, has_duplicates, read_failed = parse_decision_ledger(REPO_ROOT)
    assert len(accepted) == 141
    assert len(superseded) == 7
    assert not has_duplicates
    assert not read_failed


_CLOSURE_REQUIRED_FIELDS = (
    "closure_schema_version",
    "candidate_revision",
    "candidate_identity",
    "environment_binding",
    "gate_attempts",
    "gate_summaries",
    "active_gate_requirements",
    "closure_status",
)

_GATE_ATTEMPT_REQUIRED_FIELDS = (
    "gate_attempt_schema_version",
    "attempt_id",
    "gate_name",
    "status",
    "candidate_revision",
    "candidate_identity",
    "gate_identity",
    "environment_binding",
    "runtime_build_identity",
    "environment_fingerprint",
    "artifact_digests",
    "image_digests",
    "required_check_observations",
    "fault_receipts",
    "cleanup_result",
    "evidence_binding",
    "recorded_result",
)


@pytest.mark.parametrize("field", _CLOSURE_REQUIRED_FIELDS)
def test_aggregate_rejects_missing_closure_required_field(field: str) -> None:
    doc = _minimal_closure()
    del doc[field]
    result = aggregate_closure(doc)
    assert not result.ok
    assert result.closure_status == "INCOMPLETE"


@pytest.mark.parametrize("field", _GATE_ATTEMPT_REQUIRED_FIELDS)
def test_aggregate_rejects_missing_attempt_required_field(field: str) -> None:
    doc = _minimal_closure()
    del doc["gate_attempts"][0][field]
    result = aggregate_closure(doc)
    assert not result.ok
    assert result.closure_status == "INCOMPLETE"


def test_aggregate_rejects_pass_with_empty_artifact_digests() -> None:
    attempt = _minimal_gate_attempt(artifact_digests=[])
    doc = _minimal_closure(gate_attempts=[attempt])
    result = aggregate_closure(doc)
    assert not result.ok
    assert result.closure_status == "INCOMPLETE"


@pytest.mark.parametrize("field", _CLOSURE_REQUIRED_FIELDS)
def test_validate_and_aggregate_both_reject_missing_closure_field(field: str) -> None:
    doc = _minimal_closure()
    del doc[field]
    assert not aggregate_closure(doc).ok
    assert not validate_closure_document(doc).ok


def test_lint_traceability_rejects_non_utf8_decision_ledger(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    ledger_dir = repo / "docs/backend-vnext/refactoring/temporary/phase-2"
    ledger_files = sorted(ledger_dir.glob("decision-ledger-round-*.md"))
    assert ledger_files
    ledger_path = ledger_files[0]
    ledger_path.write_bytes(ledger_path.read_bytes() + b"\xff")
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_SCHEMA.value in result.diagnostics


_FORMAL_MARKER_RELS = (
    "docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md",
    "docs/backend-vnext/refactoring/formal/plans/phase-2-f0-validation-report.md",
)


@pytest.mark.parametrize("marker_rel", _FORMAL_MARKER_RELS)
def test_lint_traceability_rejects_non_utf8_formal_marker(tmp_path: Path, marker_rel: str) -> None:
    repo = _clone_repo_fixture(tmp_path)
    marker_path = repo / marker_rel
    assert marker_path.is_file()
    marker_path.write_bytes(marker_path.read_bytes() + b"\xff")
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_SCHEMA.value in result.diagnostics


@pytest.mark.parametrize("marker_rel", _FORMAL_MARKER_RELS)
def test_lint_traceability_rejects_formal_marker_read_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, marker_rel: str
) -> None:
    repo = _clone_repo_fixture(tmp_path)
    target = repo / marker_rel
    assert target.is_file()
    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self: Path) -> bytes:
        if self.resolve() == target.resolve():
            raise OSError("simulated read failure")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_SCHEMA.value in result.diagnostics


@pytest.mark.parametrize("marker_rel", _FORMAL_MARKER_RELS)
def test_lint_traceability_rejects_missing_formal_marker(tmp_path: Path, marker_rel: str) -> None:
    repo = _clone_repo_fixture(tmp_path)
    marker_path = repo / marker_rel
    assert marker_path.is_file()
    marker_path.unlink()
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_MISSING.value in result.diagnostics


F0_REPORT_REL = "docs/backend-vnext/refactoring/formal/plans/phase-2-f0-validation-report.md"
IMPLEMENTATION_PLAN_REL = (
    "docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md"
)


def test_lint_traceability_rejects_f0_report_symlink_outside_absolute(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    f0 = repo / F0_REPORT_REL
    outside = tmp_path / "outside-f0.md"
    outside.write_text(f0.read_text(encoding="utf-8"), encoding="utf-8")
    f0.unlink()
    f0.symlink_to(outside)
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_ESCAPE.value in result.diagnostics


def test_lint_traceability_rejects_f0_report_symlink_outside_relative(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    f0 = repo / F0_REPORT_REL
    outside = tmp_path / "outside-f0.md"
    outside.write_text(f0.read_text(encoding="utf-8"), encoding="utf-8")
    f0.unlink()
    f0.symlink_to(Path(os.path.relpath(outside, f0.parent)))
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_ESCAPE.value in result.diagnostics


def test_lint_traceability_rejects_f0_report_symlink_inside_formal(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    f0 = repo / F0_REPORT_REL
    other = repo / IMPLEMENTATION_PLAN_REL
    f0.unlink()
    f0.symlink_to(other)
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_ESCAPE.value in result.diagnostics


def test_lint_traceability_rejects_f0_report_ancestor_symlink(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    plans = repo / "docs/backend-vnext/refactoring/formal/plans"
    plans_backup = repo / "docs/backend-vnext/refactoring/formal/plans_real"
    plans.rename(plans_backup)
    outside = tmp_path / "outside_plans"
    outside.mkdir()
    for item in plans_backup.iterdir():
        shutil.move(str(item), str(outside / item.name))
    plans_backup.rmdir()
    plans.symlink_to(outside, target_is_directory=True)
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_ESCAPE.value in result.diagnostics


def test_lint_traceability_rejects_f0_report_directory(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    f0 = repo / F0_REPORT_REL
    f0.unlink()
    f0.mkdir()
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_MISSING.value in result.diagnostics


def test_lint_traceability_rejects_f0_b4_evidence_file_deleted(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    (repo / F0_REPORT_REL).unlink()
    result = lint_traceability(repo)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_OWNER_MISSING.value in result.diagnostics


@pytest.mark.parametrize(
    ("old_evidence", "new_evidence", "expected_code"),
    [
        (
            "evidence: formal/plans/phase-2-f0-validation-report.md",
            "evidence: formal/../temporary/phase-2/decision-ledger-round-1.md",
            ClosureErrorCode.TRACEABILITY_OWNER_INVALID,
        ),
        (
            "evidence: formal/plans/phase-2-f0-validation-report.md",
            r"evidence: formal\plans\phase-2-f0-validation-report.md",
            ClosureErrorCode.TRACEABILITY_OWNER_INVALID,
        ),
        (
            "evidence: formal/plans/phase-2-f0-validation-report.md",
            "evidence: /formal/plans/phase-2-f0-validation-report.md",
            ClosureErrorCode.TRACEABILITY_OWNER_INVALID,
        ),
    ],
)
def test_lint_traceability_rejects_f0_b4_evidence_bad_path(
    tmp_path: Path,
    old_evidence: str,
    new_evidence: str,
    expected_code: ClosureErrorCode,
) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(old_evidence, new_evidence, 1)
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok
    assert expected_code.value in result.diagnostics


def test_phase1_identity_artifact_read_oserror_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _clone_repo_fixture(tmp_path)
    artifact = repo / IDENTITY_ARTIFACT_REL
    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self: Path) -> bytes:
        if self.resolve() == artifact.resolve():
            raise OSError("simulated read failure")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert Phase1ProtectionCode.UNREADABLE_MATERIAL.value in result.diagnostics


def test_phase1_signoff_read_oserror_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _clone_repo_fixture(tmp_path)
    signoff = repo / SIGNOFF_REL
    original_read_text = Path.read_text

    def _patched_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if self.resolve() == signoff.resolve():
            raise OSError("simulated read failure")
        return original_read_text(self, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "read_text", _patched_read_text)
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert Phase1ProtectionCode.UNREADABLE_MATERIAL.value in result.diagnostics


def test_schema_files_exist() -> None:
    assert (SCHEMA_DIR / "gate-attempt-v1.json").is_file()
    assert (SCHEMA_DIR / "closure-v1.json").is_file()


# Audit finding reproducers and additional negative coverage


def test_aggregate_fail_attempt_cannot_be_laundered_via_summary() -> None:
    attempt = _minimal_gate_attempt(status="FAIL")
    doc = _minimal_closure(
        gate_attempts=[attempt],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "PASS",
                "attempt_ids": ["attempt-static-1"],
            }
        ],
        closure_status="COMPLETE",
    )
    result = validate_closure_document(doc)
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_SUMMARY_MISMATCH.value in result.diagnostics
        or ClosureErrorCode.CLOSURE_DECLARED_STATUS_MISMATCH.value in result.diagnostics
    )


def test_aggregate_blocked_attempt_rejects_complete_closure() -> None:
    attempt = _minimal_gate_attempt(
        status="BLOCKED",
        block_reason="uv_unavailable",
        recorded_result={"diagnostics": ["uv_unavailable"]},
    )
    doc = _minimal_closure(
        gate_attempts=[attempt],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "BLOCKED",
                "attempt_ids": ["attempt-static-1"],
            }
        ],
        closure_status="INCOMPLETE",
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value in result.diagnostics


def test_aggregate_summary_orphan_attempt_rejected() -> None:
    doc = _minimal_closure()
    doc["gate_summaries"][0]["attempt_ids"] = ["missing-attempt"]
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUMMARY_ORPHAN_ATTEMPT.value in result.diagnostics


def test_aggregate_summary_wrong_gate_rejected() -> None:
    other = _minimal_gate_attempt(
        attempt_id="attempt-contract",
        gate_name="P2-PR-CONTRACT",
        gate_identity={
            "gate_name": "P2-PR-CONTRACT",
            "activation": "inactive",
            "gate_schema_version": 1,
        },
        status="FAIL",
    )
    doc = _minimal_closure(
        gate_attempts=[_minimal_gate_attempt(), other],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "PASS",
                "attempt_ids": ["attempt-static-1", "attempt-contract"],
            }
        ],
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUMMARY_WRONG_GATE.value in result.diagnostics


def test_aggregate_invalid_input_no_traceback() -> None:
    result = aggregate_closure({"gate_attempts": [None]})
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_INVALID_INPUT.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_MISSING_REQUIRED.value in result.diagnostics
    )

    result = aggregate_closure([])
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_INVALID_INPUT.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_MISSING_REQUIRED.value in result.diagnostics
    )


def test_traceability_missing_blocking_register(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    start = trace.index("blocking_register:")
    mutated = trace[:start].rstrip() + "\n"
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_BLOCKER_MISSING.value in result.diagnostics


def test_traceability_empty_blocking_register(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    start = trace.index("blocking_register:")
    mutated = trace[:start] + "blocking_register: []\n"
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_BLOCKER_MISSING.value in result.diagnostics


def test_traceability_unknown_blocker_id(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace + "\n  - id: F0-B99\n    status: closed\n    evidence: bogus\n"
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_BLOCKER_MISMATCH.value in result.diagnostics


@pytest.mark.parametrize(
    "field",
    [
        "runtime_build_identity",
        "environment_fingerprint",
        "artifact_digests",
        "required_check_observations",
        "cleanup_result",
    ],
)
def test_schema_pass_missing_binding_field_rejected(field: str) -> None:
    doc = _minimal_gate_attempt()
    del doc[field]
    result = validate_gate_attempt_document(doc)
    assert not result.ok


def test_schema_pass_empty_artifact_digests_rejected() -> None:
    doc = _minimal_gate_attempt(artifact_digests=[])
    result = validate_gate_attempt_document(doc)
    assert not result.ok


def test_schema_pass_missing_check_observation_rejected() -> None:
    observations = [item for item in _WP0_CHECK_OBSERVATIONS if item["check_id"] != "static.ruff"]
    doc = _minimal_gate_attempt(required_check_observations=observations)
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_CHECK_OBSERVATION_MISSING.value in result.diagnostics


def test_phase1_git_ls_tree_failure_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import phase1_protection as protection_module

    repo = _clone_repo_fixture(tmp_path)
    original_git_run = protection_module._git_run

    def _fail_ls_tree(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
        if args and args[0] == "ls-tree":
            return subprocess.CompletedProcess(args, 128, b"", b"fatal")
        return original_git_run(repo_root, *args)

    monkeypatch.setattr(protection_module, "_git_run", _fail_ls_tree)
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert Phase1ProtectionCode.GIT_COMMAND_FAILED.value in result.diagnostics


def test_phase1_index_only_mode_change_detected(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    pins = repo / "vnext/deploy/phase-1-image-pins.env"
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--chmod=+x", str(pins)],
        check=True,
        capture_output=True,
    )
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert any(
        Phase1ProtectionCode.INDEX_MODE_MISMATCH.value in item for item in result.diagnostics
    )


def test_phase1_extra_identity_symlink_detected(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    alt = (
        repo
        / "docs/backend-vnext/refactoring/temporary/phase-1/artifacts/phase-exit-container-identity-deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef.json"
    )
    alt.symlink_to(IDENTITY_BASENAME)
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value in result.diagnostics


def test_aggregate_empty_requirements_cannot_complete() -> None:
    result = aggregate_closure(
        {
            "gate_attempts": [],
            "gate_summaries": [],
            "active_gate_requirements": [],
            "closure_status": "COMPLETE",
        }
    )
    assert not result.ok
    assert result.closure_status == "INCOMPLETE"
    assert (
        ClosureErrorCode.CLOSURE_MISSING_REQUIRED.value in result.diagnostics
        or ClosureErrorCode.CLOSURE_INVALID_INPUT.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_MISSING_REQUIRED.value in result.diagnostics
    )


def test_aggregate_inactive_summary_rejected() -> None:
    doc = _minimal_closure()
    doc["gate_summaries"].append(
        {
            "gate_name": "P2-PR-CONTRACT",
            "activation": "inactive",
            "aggregate_status": "PASS",
            "attempt_ids": ["attempt-static-1"],
        }
    )
    result = validate_closure_document(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUMMARY_EXTRA.value in result.diagnostics


@pytest.mark.parametrize(
    "gate_name,activation",
    [
        ("P2-PR-CONTRACT", "inactive"),
        ("P2-PR-RECOVERY", "inactive"),
        ("P2-PHASE-EXIT-CONTAINER", "inactive"),
        ("PR-CORRECTNESS", "external"),
        ("PR-NATIVE", "external"),
    ],
)
def test_aggregate_extra_inactive_or_external_summary_rejected(
    gate_name: str, activation: str
) -> None:
    doc = _minimal_closure()
    doc["gate_summaries"].append(
        {
            "gate_name": gate_name,
            "activation": activation,
            "aggregate_status": "FAIL",
            "attempt_ids": [],
        }
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_SUMMARY_EXTRA.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_MALFORMED_ATTEMPT_ID.value in result.diagnostics
    )


def test_schema_identity_mismatch_rejected() -> None:
    doc = _minimal_gate_attempt()
    doc["candidate_identity"] = {
        "revision": "b" * 40,
        "worktree_status": "clean",
    }
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value in result.diagnostics


def test_schema_gate_identity_mismatch_rejected() -> None:
    doc = _minimal_gate_attempt(
        gate_identity={
            "gate_name": "P2-PR-CONTRACT",
            "activation": "inactive",
            "gate_schema_version": 1,
        }
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_IDENTITY_MISMATCH.value in result.diagnostics


def test_schema_duplicate_observation_order_independent() -> None:
    observations = [
        {
            "check_id": "static.ruff",
            "outcome": "FAIL",
            "diagnostics": ["check:static.ruff:exit=1"],
        },
        {
            "check_id": "static.ruff",
            "outcome": "PASS",
            "diagnostics": ["check:static.ruff:exit=0"],
        },
        *_WP0_CHECK_OBSERVATIONS[1:],
    ]
    doc_fail_first = _minimal_gate_attempt(required_check_observations=observations)
    doc_pass_first = _minimal_gate_attempt(
        required_check_observations=list(reversed(observations[:2])) + observations[2:]
    )
    first = validate_gate_attempt_document(doc_fail_first)
    second = validate_gate_attempt_document(doc_pass_first)
    assert not first.ok
    assert not second.ok
    assert first.diagnostics == second.diagnostics
    assert ClosureErrorCode.SCHEMA_DUPLICATE_OBSERVATION.value in first.diagnostics


def test_traceability_mapping_mutation_rejected(tmp_path: Path) -> None:
    trace = (
        REPO_ROOT
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    ).read_text(encoding="utf-8")
    mutated = trace.replace(
        "formal/architecture/architecture-and-refactoring-plan.md",
        "formal/architecture/missing-owner.md",
        1,
    )
    fake_root = _copy_traceability_fixture(tmp_path, mutated)
    result = lint_traceability(fake_root)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_MAPPING_MISMATCH.value in result.diagnostics


def test_traceability_non_object_root_no_traceback(tmp_path: Path) -> None:
    fake_root = tmp_path / "repo"
    trace_path = (
        fake_root
        / "docs/backend-vnext/refactoring/formal/plans/phase-2-requirement-traceability.yaml"
    )
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text("- not-a-mapping\n", encoding="utf-8")
    result = lint_traceability(fake_root)
    assert not result.ok
    assert ClosureErrorCode.TRACEABILITY_SCHEMA.value in result.diagnostics


def test_phase1_conformance_source_index_mutation_detected(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    target = repo / "vnext/conformance/src/gateway_conformance/errors.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# mutated\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", str(target)],
        check=True,
        capture_output=True,
    )
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert any(
        Phase1ProtectionCode.INDEX_MODE_MISMATCH.value in item
        or Phase1ProtectionCode.PROTECTED_FILE_MODIFIED.value in item
        for item in result.diagnostics
    )


def test_supersession_fork_rejected() -> None:
    first = _minimal_gate_attempt(attempt_id="attempt-a", status="FAIL")
    second = _minimal_gate_attempt(
        attempt_id="attempt-b",
        status="PASS",
        supersession={"supersedes_attempt_id": "attempt-a", "reason": "retry"},
    )
    third = _minimal_gate_attempt(
        attempt_id="attempt-c",
        status="PASS",
        supersession={"supersedes_attempt_id": "attempt-a", "reason": "retry"},
    )
    doc = _minimal_closure(
        gate_attempts=[first, second, third],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "FAIL",
                "attempt_ids": ["attempt-a", "attempt-b", "attempt-c"],
            }
        ],
        closure_status="INCOMPLETE",
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUPERSESSION_FORK.value in result.diagnostics


def test_clone_fixture_uses_tmp_path(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    assert repo.is_dir()
    assert str(repo).startswith(str(tmp_path))


def test_aggregate_identity_mismatch_fail_closed() -> None:
    doc = _minimal_closure()
    doc["candidate_identity"] = {"revision": "b" * 40, "worktree_status": "clean"}
    result = aggregate_closure(doc)
    assert not result.ok
    assert result.closure_status == "INCOMPLETE"


def test_aggregate_duplicate_gate_summaries_fail_closed() -> None:
    doc = _minimal_closure()
    doc["gate_summaries"] = doc["gate_summaries"] + [deepcopy(doc["gate_summaries"][0])]
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_DUPLICATE_GATE.value in result.diagnostics


def test_aggregate_summary_duplicate_attempt_ids_fail_closed() -> None:
    doc = _minimal_closure()
    doc["gate_summaries"][0]["attempt_ids"] = ["attempt-static-1", "attempt-static-1"]
    result = aggregate_closure(doc)
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_SUMMARY_DUPLICATE_ATTEMPT.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_DUPLICATE_ATTEMPT.value in result.diagnostics
    )


def test_aggregate_invalid_nested_types_no_traceback() -> None:
    doc = _minimal_closure()
    doc["gate_attempts"][0]["environment_binding"] = []
    result = aggregate_closure(doc)
    assert not result.ok
    assert (
        ClosureErrorCode.CLOSURE_INVALID_INPUT.value in result.diagnostics
        or ClosureErrorCode.SCHEMA_MISMATCH.value in result.diagnostics
    )

    doc2 = _minimal_closure()
    doc2["gate_attempts"][0]["gate_identity"] = []
    result2 = aggregate_closure(doc2)
    assert not result2.ok
    assert (
        ClosureErrorCode.CLOSURE_INVALID_INPUT.value in result2.diagnostics
        or ClosureErrorCode.SCHEMA_MISMATCH.value in result2.diagnostics
    )


def test_aggregate_summary_omits_superseded_history() -> None:
    failed = _minimal_gate_attempt(attempt_id="attempt-fail", status="FAIL")
    passed = _minimal_gate_attempt(
        attempt_id="attempt-pass",
        status="PASS",
        supersession={"supersedes_attempt_id": "attempt-fail", "reason": "retry"},
    )
    doc = _minimal_closure(
        gate_attempts=[failed, passed],
        gate_summaries=[
            {
                "gate_name": "P2-PR-STATIC",
                "activation": "active",
                "aggregate_status": "PASS",
                "attempt_ids": ["attempt-pass"],
            }
        ],
    )
    result = aggregate_closure(doc)
    assert not result.ok
    assert ClosureErrorCode.CLOSURE_SUMMARY_HISTORY_MISMATCH.value in result.diagnostics


def test_schema_malformed_binding_path_rejected() -> None:
    doc = _minimal_gate_attempt(
        environment_binding={"lock_digests": [{"path": "..", "digest": _LOCK_DIGESTS[0]["digest"]}]}
    )
    result = validate_gate_attempt_document(doc)
    assert not result.ok
    assert ClosureErrorCode.SCHEMA_MALFORMED_PATH.value in result.diagnostics


def test_schema_oversized_attempt_id_rejected() -> None:
    doc = _minimal_gate_attempt(attempt_id="a" * 100_000)
    result = validate_gate_attempt_document(doc)
    assert not result.ok


def test_phase1_ancestor_symlink_escape_detected(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    deploy = repo / "vnext/deploy"
    external = tmp_path / "external-deploy"
    shutil.copytree(deploy, external)
    shutil.rmtree(deploy)
    deploy.symlink_to(external, target_is_directory=True)
    result = verify_phase1_protection(repo)
    assert not result.ok
    assert any(
        Phase1ProtectionCode.PATH_ESCAPE.value in item
        or Phase1ProtectionCode.PROTECTED_SYMLINK_REPLACEMENT.value in item
        for item in result.diagnostics
    )


def test_phase1_non_utf8_untracked_path_no_traceback(tmp_path: Path) -> None:
    repo = _clone_repo_fixture(tmp_path)
    bad_name = b"vnext/conformance/\xff-invalid-name.txt"
    bad_path = repo / bad_name.decode("utf-8", "surrogateescape")
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("x", encoding="utf-8")
    result = verify_phase1_protection(repo)
    assert isinstance(result.diagnostics, tuple)
