"""Harness protocol and runner result semantic validation."""

from __future__ import annotations

from typing import Any

from jsonschema.exceptions import ValidationError

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import FORBIDDEN_PROTOCOL_FIELDS
from gateway_conformance.schemas import (
    validate_harness_protocol,
    validate_runner_result,
    validate_run_evidence,
)
from gateway_conformance.protocol.digest import compute_run_evidence_content_digest
from gateway_conformance.scenario.identity import assert_sorted_unique_bytes


def _assert_no_forbidden_fields(payload: dict[str, Any], *, label: str) -> None:
    for key in payload:
        if key in FORBIDDEN_PROTOCOL_FIELDS:
            raise ConformanceValidationError(f"{label} must not expose {key}")
        value = payload[key]
        if isinstance(value, dict):
            _assert_no_forbidden_fields(value, label=f"{label}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    _assert_no_forbidden_fields(item, label=f"{label}.{key}[{index}]")


def _assert_observation_kind_matches_descriptor(item: dict[str, Any]) -> None:
    kind = str(item["kind"])
    mode = str(item["payload_descriptor"]["comparison_mode"])
    expected = {
        "structured": "exact-canonical",
        "recovery": "recovery-checkpoints",
        "artifact": "artifact-closure",
    }.get(kind)
    if expected != mode:
        raise ConformanceValidationError("observation kind and comparison_mode mismatch")


def validate_harness_plan(plan: dict[str, Any]) -> None:
    try:
        validate_harness_protocol(plan)
    except ValidationError as exc:
        raise ConformanceValidationError(exc.message) from exc
    _assert_no_forbidden_fields(plan, label="harness protocol")
    observation_requests = plan["observation_requests"]
    ids = [str(item["expectation_id"]) for item in observation_requests]
    assert_sorted_unique_bytes(ids, label="observation_requests")
    for item in observation_requests:
        for forbidden in ("expected_content_digest", "golden_path", "path", "payload"):
            if forbidden in item:
                raise ConformanceValidationError(f"observation request must not expose {forbidden}")
        _assert_observation_kind_matches_descriptor(item)


def validate_runner_result_semantics(result: dict[str, Any]) -> None:
    try:
        validate_runner_result(result)
    except ValidationError as exc:
        raise ConformanceValidationError(exc.message) from exc
    status = str(result["status"])
    comparison = str(result["comparison_outcome"])
    cleanup = str(result["cleanup"]["status"])
    expectations = result["expectations"]
    exp_ids = [str(item["expectation_id"]) for item in expectations]
    assert_sorted_unique_bytes(exp_ids, label="expectations")
    outcomes = [str(item["outcome"]) for item in expectations]

    if status == "PASSED":
        if comparison != "MATCH":
            raise ConformanceValidationError("PASSED requires comparison_outcome MATCH")
        if cleanup != "CLEAN":
            raise ConformanceValidationError("PASSED requires cleanup status CLEAN")
        if any(item != "MATCH" for item in outcomes):
            raise ConformanceValidationError("PASSED requires all expectations MATCH")
    elif status == "ASSERTION_FAILED":
        if comparison != "MISMATCH":
            raise ConformanceValidationError(
                "ASSERTION_FAILED requires comparison_outcome MISMATCH"
            )
        if cleanup != "CLEAN":
            raise ConformanceValidationError("ASSERTION_FAILED requires cleanup status CLEAN")
        if "NOT_RUN" in outcomes:
            raise ConformanceValidationError("ASSERTION_FAILED forbids NOT_RUN expectations")
        if any(item not in {"MATCH", "MISMATCH"} for item in outcomes):
            raise ConformanceValidationError(
                "ASSERTION_FAILED expectations must be MATCH or MISMATCH"
            )
        if outcomes.count("MISMATCH") == 0:
            raise ConformanceValidationError(
                "ASSERTION_FAILED requires at least one MISMATCH expectation"
            )
    elif status == "UNSUPPORTED":
        if comparison != "NOT_RUN":
            raise ConformanceValidationError("UNSUPPORTED requires comparison_outcome NOT_RUN")
        if cleanup != "CLEAN":
            raise ConformanceValidationError("UNSUPPORTED requires cleanup status CLEAN")
        if any(item != "NOT_RUN" for item in outcomes):
            raise ConformanceValidationError("UNSUPPORTED requires all expectations NOT_RUN")
    elif status == "HARNESS_ERROR":
        if comparison not in {"NOT_RUN", "MATCH", "MISMATCH"}:
            raise ConformanceValidationError("HARNESS_ERROR has invalid comparison_outcome")
        if "MISMATCH" in outcomes:
            expected_comparison = "MISMATCH"
        elif "MATCH" in outcomes:
            expected_comparison = "MATCH"
        else:
            expected_comparison = "NOT_RUN"
        if comparison != expected_comparison:
            raise ConformanceValidationError(
                "HARNESS_ERROR comparison_outcome must aggregate expectation outcomes"
            )
    else:
        raise ConformanceValidationError(f"unsupported runner status: {status}")

    for item in expectations:
        outcome = str(item["outcome"])
        expected = item["expected_content_digest"]
        actual = item["actual_content_digest"]
        if outcome == "NOT_RUN" and actual is not None:
            raise ConformanceValidationError(
                "NOT_RUN expectation requires null actual_content_digest"
            )
        if outcome in {"MATCH", "MISMATCH"} and actual is None:
            raise ConformanceValidationError(
                f"{outcome} expectation requires actual_content_digest"
            )
        if outcome == "MATCH" and actual != expected:
            raise ConformanceValidationError(
                "MATCH expectation requires actual_content_digest equal to expected"
            )
        if outcome == "MISMATCH" and actual == expected:
            raise ConformanceValidationError(
                "MISMATCH expectation requires actual_content_digest unequal to expected"
            )


def _assert_evidence_observation_shape(observation: dict[str, Any]) -> None:
    if observation.get("canonical_encoding_version") != 1:
        raise ConformanceValidationError("evidence observation requires canonical_encoding_version")
    if "payload" not in observation:
        raise ConformanceValidationError("evidence observation requires payload or ref")


def _assert_checkpoint_outcome_digest(checkpoint: dict[str, Any]) -> None:
    outcome = str(checkpoint["outcome"])
    digest = checkpoint.get("content_digest")
    if outcome in {"MATCH", "MISMATCH"} and digest is None:
        raise ConformanceValidationError(f"{outcome} checkpoint requires non-null content_digest")
    if outcome == "NOT_RUN" and digest is not None:
        raise ConformanceValidationError("NOT_RUN checkpoint requires null content_digest")


def validate_run_evidence_bundle(evidence: dict[str, Any]) -> None:
    validate_run_evidence(evidence)
    for observation in evidence["observations"]:
        _assert_evidence_observation_shape(observation)
    for checkpoint in evidence.get("checkpoint_results", []):
        _assert_checkpoint_outcome_digest(checkpoint)
    computed = compute_run_evidence_content_digest(evidence)
    if str(evidence["content_digest"]) != computed:
        raise ConformanceValidationError("run evidence content_digest mismatch")
