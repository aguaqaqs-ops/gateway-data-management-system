"""Protocol and runner result semantic tests."""

from __future__ import annotations

from typing import Any, cast

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.digest import compute_run_evidence_content_digest
from gateway_conformance.protocol.validate import (
    validate_harness_plan,
    validate_runner_result_semantics,
    validate_run_evidence_bundle,
)


def _base_plan() -> dict[str, object]:
    return {
        "harness_protocol_version": 1,
        "execution_key": {
            "scenario_id": "data.test-capability.minimal",
            "profile": "reference",
            "provider_id": None,
            "fixture_content_digest": "sha256:" + "0" * 64,
        },
        "run_id": "run-1",
        "subject": {"kind": "capability", "name": "test-capability"},
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "test-capability",
                "contract_id": "gateway-vnext.test-contract",
                "semantic_version": "1.0.0",
            }
        ],
        "logical_time_start": "2026-01-01T00:00:00Z",
        "deterministic_seed": "seed",
        "verified_assets": [],
        "stimulus": {
            "contract_binding_id": "subject",
            "payload": {"storage": "inline", "value": {}},
        },
        "observation_requests": [
            {
                "expectation_id": "result",
                "kind": "structured",
                "contract_binding": {
                    "owner": "test-capability",
                    "contract_id": "gateway-vnext.test-contract",
                    "semantic_version": "1.0.0",
                },
                "payload_descriptor": {
                    "media_type": "application/json",
                    "schema_id": "gateway-vnext.test-result.v1",
                    "schema_version": 1,
                    "canonical_encoding_version": 1,
                    "comparison_mode": "exact-canonical",
                },
            }
        ],
    }


def test_harness_plan_rejects_golden_leakage() -> None:
    plan = _base_plan()
    plan["golden_path"] = "expected/result.golden.json"
    with pytest.raises(ConformanceValidationError, match="golden_path"):
        validate_harness_plan(plan)


def test_runner_result_unsupported_with_match_rejected() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "UNSUPPORTED",
        "comparison_outcome": "MATCH",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": None,
                "outcome": "NOT_RUN",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ConformanceValidationError, match="NOT_RUN"):
        validate_runner_result_semantics(result)


def test_runner_result_valid_passed_shape() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "PASSED",
        "comparison_outcome": "MATCH",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": "sha256:" + "0" * 64,
                "outcome": "MATCH",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    validate_runner_result_semantics(result)


def test_provider_matrix_requires_provider_id() -> None:
    plan = cast(dict[str, Any], dict(_base_plan()))
    plan["execution_key"] = {
        "scenario_id": "data.test-capability.minimal",
        "profile": "provider-matrix",
        "provider_id": None,
        "fixture_content_digest": "sha256:" + "0" * 64,
    }
    with pytest.raises(ConformanceValidationError):
        validate_harness_plan(plan)


def test_reference_profile_rejects_non_null_provider_id() -> None:
    plan = cast(dict[str, Any], dict(_base_plan()))
    execution_key = cast(dict[str, Any], dict(plan["execution_key"]))
    execution_key["provider_id"] = "python"
    plan["execution_key"] = execution_key
    with pytest.raises(ConformanceValidationError):
        validate_harness_plan(plan)


def test_structured_observation_rejects_artifact_comparator() -> None:
    plan = cast(dict[str, Any], dict(_base_plan()))
    cast(list[dict[str, Any]], plan["observation_requests"])[0]["payload_descriptor"][
        "comparison_mode"
    ] = "artifact-closure"
    with pytest.raises(ConformanceValidationError, match="comparison_mode"):
        validate_harness_plan(plan)


def test_runner_result_passed_with_leaked_cleanup_rejected() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "PASSED",
        "comparison_outcome": "MATCH",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": "sha256:" + "0" * 64,
                "outcome": "MATCH",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "LEAKED", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ConformanceValidationError):
        validate_runner_result_semantics(result)


def test_runner_result_passed_with_all_not_run_rejected() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "PASSED",
        "comparison_outcome": "MATCH",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": None,
                "outcome": "NOT_RUN",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ConformanceValidationError, match="all expectations MATCH"):
        validate_runner_result_semantics(result)


def _expectation(expectation_id: str, outcome: str) -> dict[str, Any]:
    actual = None if outcome == "NOT_RUN" else "sha256:" + ("0" if outcome == "MATCH" else "1") * 64
    return {
        "expectation_id": expectation_id,
        "expected_content_digest": "sha256:" + "0" * 64,
        "actual_content_digest": actual,
        "outcome": outcome,
    }


def _result(
    *,
    status: str,
    comparison: str,
    cleanup: str,
    outcomes: list[str],
) -> dict[str, Any]:
    return {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": status,
        "comparison_outcome": comparison,
        "expectations": [
            _expectation(chr(ord("a") + index), outcome) for index, outcome in enumerate(outcomes)
        ],
        "evidence_ref": None,
        "cleanup": {"status": cleanup, "diagnostics": []},
        "diagnostics": [],
    }


@pytest.mark.parametrize(
    ("status", "comparison", "cleanup", "outcomes", "ok"),
    [
        ("PASSED", "MATCH", "CLEAN", ["MATCH"], True),
        ("PASSED", "MATCH", "CLEAN", ["MATCH", "MATCH"], True),
        ("PASSED", "MATCH", "CLEAN", ["MATCH", "NOT_RUN"], False),
        ("PASSED", "MATCH", "CLEAN", ["MATCH", "MISMATCH"], False),
        ("PASSED", "MATCH", "LEAKED", ["MATCH"], False),
        ("PASSED", "MISMATCH", "CLEAN", ["MATCH"], False),
        ("ASSERTION_FAILED", "MISMATCH", "CLEAN", ["MISMATCH"], True),
        ("ASSERTION_FAILED", "MISMATCH", "CLEAN", ["MATCH", "MISMATCH"], True),
        ("ASSERTION_FAILED", "MISMATCH", "CLEAN", ["MISMATCH", "NOT_RUN"], False),
        ("ASSERTION_FAILED", "MISMATCH", "CLEAN", ["MATCH", "MATCH"], False),
        ("ASSERTION_FAILED", "MISMATCH", "LEAKED", ["MISMATCH"], False),
        ("UNSUPPORTED", "NOT_RUN", "CLEAN", ["NOT_RUN"], True),
        ("UNSUPPORTED", "NOT_RUN", "CLEAN", ["NOT_RUN", "NOT_RUN"], True),
        ("UNSUPPORTED", "NOT_RUN", "LEAKED", ["NOT_RUN"], False),
        ("UNSUPPORTED", "NOT_RUN", "CLEAN", ["MATCH"], False),
        ("UNSUPPORTED", "MATCH", "CLEAN", ["NOT_RUN"], False),
        ("HARNESS_ERROR", "MATCH", "LEAKED", ["MATCH"], True),
        ("HARNESS_ERROR", "MISMATCH", "LEAKED", ["MATCH", "MISMATCH"], True),
        ("HARNESS_ERROR", "NOT_RUN", "CLEAN", ["NOT_RUN"], True),
        ("HARNESS_ERROR", "MATCH", "CLEAN", ["NOT_RUN"], False),
        ("HARNESS_ERROR", "NOT_RUN", "CLEAN", ["MATCH"], False),
    ],
)
def test_runner_result_precedence_truth_table(
    status: str,
    comparison: str,
    cleanup: str,
    outcomes: list[str],
    ok: bool,
) -> None:
    result = _result(status=status, comparison=comparison, cleanup=cleanup, outcomes=outcomes)
    if ok:
        validate_runner_result_semantics(result)
    else:
        with pytest.raises(ConformanceValidationError):
            validate_runner_result_semantics(result)


def test_match_with_unequal_digests_rejected() -> None:
    result = _result(status="PASSED", comparison="MATCH", cleanup="CLEAN", outcomes=["MATCH"])
    result["expectations"][0]["actual_content_digest"] = "sha256:" + "1" * 64
    with pytest.raises(ConformanceValidationError, match="equal to expected"):
        validate_runner_result_semantics(result)


def test_mismatch_with_equal_digests_rejected() -> None:
    result = _result(
        status="ASSERTION_FAILED",
        comparison="MISMATCH",
        cleanup="CLEAN",
        outcomes=["MISMATCH"],
    )
    result["expectations"][0]["actual_content_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ConformanceValidationError, match="unequal to expected"):
        validate_runner_result_semantics(result)


def test_unsupported_with_match_expectation_rejected() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "UNSUPPORTED",
        "comparison_outcome": "NOT_RUN",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": "sha256:" + "0" * 64,
                "outcome": "MATCH",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ConformanceValidationError, match="all expectations NOT_RUN"):
        validate_runner_result_semantics(result)


def _minimal_evidence() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "run_evidence_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-1",
        "environment_versions": [{"component": "gateway-conformance", "version": "0.1.0"}],
        "fault_receipt": None,
        "observations": [],
        "checkpoint_results": [],
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
        "content_digest": "sha256:" + "0" * 64,
    }
    evidence["content_digest"] = compute_run_evidence_content_digest(evidence)
    return evidence


def test_run_evidence_valid_digest_accepted() -> None:
    validate_run_evidence_bundle(_minimal_evidence())


def test_run_evidence_tampered_content_digest_rejected() -> None:
    evidence = _minimal_evidence()
    evidence["content_digest"] = "sha256:" + "f" * 64
    with pytest.raises(ConformanceValidationError, match="content_digest mismatch"):
        validate_run_evidence_bundle(evidence)


@pytest.mark.parametrize(
    ("outcome", "digest"),
    [
        ("MATCH", None),
        ("MISMATCH", None),
        ("NOT_RUN", "sha256:" + "0" * 64),
    ],
)
def test_run_evidence_checkpoint_outcome_digest_mismatch_rejected(
    outcome: str, digest: str | None
) -> None:
    evidence = _minimal_evidence()
    evidence["checkpoint_results"] = [
        {"checkpoint": "after_failure", "outcome": outcome, "content_digest": digest}
    ]
    evidence["content_digest"] = compute_run_evidence_content_digest(evidence)
    with pytest.raises(ConformanceValidationError, match="checkpoint"):
        validate_run_evidence_bundle(evidence)


@pytest.mark.parametrize(
    ("outcome", "digest"),
    [
        ("MATCH", "sha256:" + "0" * 64),
        ("MISMATCH", "sha256:" + "1" * 64),
        ("NOT_RUN", None),
    ],
)
def test_run_evidence_checkpoint_outcome_digest_consistent_accepted(
    outcome: str, digest: str | None
) -> None:
    evidence = _minimal_evidence()
    evidence["checkpoint_results"] = [
        {"checkpoint": "after_recovery", "outcome": outcome, "content_digest": digest}
    ]
    evidence["content_digest"] = compute_run_evidence_content_digest(evidence)
    validate_run_evidence_bundle(evidence)
