"""Operation runtime public identity contract tests."""

from __future__ import annotations

import dataclasses
import importlib

import pytest

import gateway_backend.operations as operations
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationStatus,
    StepStatus,
)

pytestmark = pytest.mark.unit

EXPECTED_OPERATION_STATUSES = (
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "SUPERSEDED",
    "MANUAL_RECOVERY_REQUIRED",
)

EXPECTED_STEP_STATUSES = (
    "PENDING",
    "RUNNING",
    "RETRY_WAIT",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "MANUAL_RECOVERY_REQUIRED",
)

S1A_PUBLIC_EXPORTS = frozenset(
    {
        "OPERATION_RUNTIME_CONTRACT_VERSION",
        "JobStepKey",
        "OperationStatus",
        "StepStatus",
    }
)


def test_operations_package_importable() -> None:
    importlib.import_module("gateway_backend.operations")
    importlib.import_module("gateway_backend.operations.contracts")


def test_contract_version_exact() -> None:
    assert OPERATION_RUNTIME_CONTRACT_VERSION == "backend-vnext/operation-runtime/v1"


def test_operation_status_values_exact() -> None:
    assert tuple(status.value for status in OperationStatus) == EXPECTED_OPERATION_STATUSES


def test_step_status_values_exact() -> None:
    assert tuple(status.value for status in StepStatus) == EXPECTED_STEP_STATUSES


def test_job_step_key_registry_identity() -> None:
    first = JobStepKey(job_kind="import.package", step_name="validate")
    second = JobStepKey(job_kind="import.package", step_name="validate")
    different = JobStepKey(job_kind="import.package", step_name="publish")

    assert dataclasses.is_dataclass(first)
    assert first.__slots__ == ("job_kind", "step_name")
    assert (first.job_kind, first.step_name) == ("import.package", "validate")
    assert first == second
    assert first != different
    assert hash(first) == hash(second)
    assert {first: "handler"}[second] == "handler"


def test_public_exports_match_s1a_subset() -> None:
    assert frozenset(operations.__all__) == S1A_PUBLIC_EXPORTS
    for symbol in S1A_PUBLIC_EXPORTS:
        assert hasattr(operations, symbol)


def test_no_operation_kind_in_public_surface() -> None:
    assert not hasattr(operations, "operation_kind")
    assert "operation_kind" not in dir(operations)
