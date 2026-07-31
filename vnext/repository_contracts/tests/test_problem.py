"""Enum and problem contract tests."""

from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from gateway_repository_contracts._json import encode_jcs_bytes
from gateway_repository_contracts.enums import (
    EFFECT_CLASSIFICATIONS,
    FAILURE_CATEGORIES,
    RECOVERY_ACTIONS,
    STREAM_FRAME_FAMILIES,
    EffectClassification,
    FailureCategory,
    RecoveryAction,
    parse_failure_category,
)
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from types import MappingProxyType

from gateway_repository_contracts.problem import (
    PROBLEM_SCHEMA_VERSION,
    FailureDescriptor,
    RepositoryProblemDetails,
)
from gateway_repository_contracts.wire import load_schema_resource

EXPECTED_FAILURE_CATEGORIES = {
    "INVALID_REQUEST",
    "FORBIDDEN",
    "NOT_FOUND",
    "STATE_CONFLICT",
    "DEPENDENCY_FAILURE",
    "INTEGRITY_FAILURE",
    "INTERNAL_FAILURE",
}
EXPECTED_RECOVERY_ACTIONS = {
    "RETRY_COMMAND",
    "RETRY_SAME_OPERATION",
    "RECONCILE_SAME_OPERATION",
    "NEW_USER_INPUT",
    "OPERATOR_INTERVENTION",
    "NO_RETRY",
}
EXPECTED_EFFECTS = {"NOT_APPLIED", "UNKNOWN", "APPLIED", "NONE"}
EXPECTED_STREAM_FAMILIES = {
    "STREAM_HEADER",
    "ARROW_BATCH",
    "CHECKPOINT",
    "STREAM_END",
    "STREAM_ERROR",
}


def test_enum_sets_match_formal_authority() -> None:
    assert {item.value for item in FAILURE_CATEGORIES} == EXPECTED_FAILURE_CATEGORIES
    assert {item.value for item in RECOVERY_ACTIONS} == EXPECTED_RECOVERY_ACTIONS
    assert {item.value for item in EFFECT_CLASSIFICATIONS} == EXPECTED_EFFECTS
    assert {item.value for item in STREAM_FRAME_FAMILIES} == EXPECTED_STREAM_FAMILIES


def test_unknown_enum_values_fail_closed() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_failure_category("UNKNOWN_ENUM")
    assert exc.value.code is RepositoryContractErrorCode.ENUM_UNKNOWN


def _sample_failure(*, code: str = "REPOSITORY_NOT_READY") -> FailureDescriptor:
    return FailureDescriptor(
        code=code,
        category=FailureCategory.INVALID_REQUEST,
        phase="ACCEPT",
        recovery=RecoveryAction.RETRY_COMMAND,
        effect=EffectClassification.NOT_APPLIED,
        message="request rejected",
        details={"reason": "not-ready"},
        diagnostic_refs=("diag-1", "diag-2"),
    )


def test_unknown_stable_code_is_preserved() -> None:
    failure = _sample_failure(code="FUTURE_OWNER_CODE")
    wire = failure.to_wire_dict()
    parsed = FailureDescriptor.from_wire_dict(wire)
    assert parsed.code == "FUTURE_OWNER_CODE"


def test_forward_compatible_decode_ignores_unknown_additive_fields_by_default() -> None:
    payload = _sample_failure().to_wire_dict()
    payload["future_field"] = "ignored"
    parsed = FailureDescriptor.from_wire_dict(payload)
    assert parsed.code == "REPOSITORY_NOT_READY"
    assert "future_field" not in parsed.to_wire_dict()


def test_forward_compatible_decode_ignores_unknown_additive_fields() -> None:
    payload = _sample_failure().to_wire_dict()
    payload["future_field"] = "ignored"
    parsed = FailureDescriptor.from_wire_dict(payload, ignore_unknown_fields=True)
    assert parsed.code == "REPOSITORY_NOT_READY"
    assert "future_field" not in parsed.to_wire_dict()


def test_strict_schema_rejects_unknown_fields() -> None:
    schema = load_schema_resource("problem-v1.schema.json")
    validator = Draft202012Validator(schema)
    payload = {
        "type": "about:blank",
        "title": "Rejected",
        "status": 400,
        "detail": "bad",
        "instance": "/v1/repositories/x",
        "request_id": "req-1",
        "wire_schema_version": PROBLEM_SCHEMA_VERSION,
        "failure": _sample_failure().to_wire_dict(),
        "future_field": "not allowed",
    }
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_unknown_recovery_or_effect_fail_closed_on_decode() -> None:
    payload = _sample_failure().to_wire_dict()
    payload["recovery"] = "AUTO_RETRY"
    with pytest.raises(RepositoryContractError):
        FailureDescriptor.from_wire_dict(payload)


def test_status_and_message_do_not_change_recovery_or_effect() -> None:
    failure = _sample_failure()
    problem = RepositoryProblemDetails(
        type="about:blank",
        title="Human title",
        status=500,
        detail="human detail",
        instance="/v1/repositories/x",
        failure=failure,
        request_id="req-1",
        wire_schema_version=PROBLEM_SCHEMA_VERSION,
    )
    parsed = RepositoryProblemDetails.from_wire_dict(problem.to_wire_dict())
    assert parsed.failure.recovery is RecoveryAction.RETRY_COMMAND
    assert parsed.failure.effect is EffectClassification.NOT_APPLIED


def test_details_are_defensively_immutable() -> None:
    failure = _sample_failure()
    details = failure.details
    assert isinstance(details, MappingProxyType)
    with pytest.raises(TypeError):
        details["reason"] = "mutated"  # type: ignore[index]


def test_problem_encode_is_deterministic() -> None:
    problem = RepositoryProblemDetails(
        type="about:blank",
        title="Rejected",
        status=400,
        detail="bad request",
        instance="/v1/repositories/x",
        failure=_sample_failure(),
        request_id="req-1",
        wire_schema_version=PROBLEM_SCHEMA_VERSION,
    )
    first = encode_jcs_bytes(problem.to_wire_dict())
    second = encode_jcs_bytes(copy.deepcopy(problem.to_wire_dict()))
    assert first == second


def test_nested_forbidden_fields_rejected_on_to_wire() -> None:
    failure = FailureDescriptor(
        code="REPOSITORY_NOT_READY",
        category=FailureCategory.INVALID_REQUEST,
        phase="ACCEPT",
        recovery=RecoveryAction.RETRY_COMMAND,
        effect=EffectClassification.NOT_APPLIED,
        message="request rejected",
        details={"nested": {"server_path": "/tmp"}},
    )
    with pytest.raises(RepositoryContractError):
        failure.to_wire_dict()


def test_nested_forbidden_fields_rejected_on_from_wire() -> None:
    payload = _sample_failure().to_wire_dict()
    details = payload["details"]
    assert isinstance(details, dict)
    details["secret"] = "x"
    with pytest.raises(RepositoryContractError):
        FailureDescriptor.from_wire_dict(payload)


def test_direct_constructor_rejects_empty_code() -> None:
    with pytest.raises(RepositoryContractError):
        FailureDescriptor(
            code="",
            category=FailureCategory.INVALID_REQUEST,
            phase="ACCEPT",
            recovery=RecoveryAction.RETRY_COMMAND,
            effect=EffectClassification.NOT_APPLIED,
            message="request rejected",
            details={},
        )


def test_diagnostic_refs_external_mutation_does_not_affect_frozen_object() -> None:
    refs = ["diag-1", "diag-2"]
    failure = FailureDescriptor(
        code="REPOSITORY_NOT_READY",
        category=FailureCategory.INVALID_REQUEST,
        phase="ACCEPT",
        recovery=RecoveryAction.RETRY_COMMAND,
        effect=EffectClassification.NOT_APPLIED,
        message="request rejected",
        details={},
        diagnostic_refs=tuple(refs),
    )
    refs.append("diag-3")
    assert failure.diagnostic_refs == ("diag-1", "diag-2")


def test_problem_serialization_excludes_forbidden_fields() -> None:
    payload = {
        "type": "about:blank",
        "title": "Rejected",
        "status": 400,
        "detail": "bad",
        "instance": "/v1/repositories/x",
        "request_id": "req-1",
        "wire_schema_version": PROBLEM_SCHEMA_VERSION,
        "failure": _sample_failure().to_wire_dict(),
        "stack": "must-not-appear",
    }
    with pytest.raises(RepositoryContractError):
        RepositoryProblemDetails.assert_no_forbidden_fields(payload)


def test_failure_descriptor_missing_required_field_raises_stable_error() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        FailureDescriptor.from_wire_dict({"code": "X"})
    assert exc.value.code is RepositoryContractErrorCode.WIRE_INVALID_VALUE


def test_problem_details_missing_required_field_raises_stable_error() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        RepositoryProblemDetails.from_wire_dict({"type": "about:blank"})
    assert exc.value.code is RepositoryContractErrorCode.WIRE_INVALID_VALUE
