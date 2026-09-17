"""Unit tests for operator recovery typed error classification."""

from __future__ import annotations

import pytest

from gateway_backend.application.submission.operator_recovery_mapping import (
    classify_operator_recovery_stale_write,
)
from gateway_backend.operations.store import StaleWrite

pytestmark = pytest.mark.unit


def test_generic_stale_write_maps_to_step_version_conflict() -> None:
    code, message = classify_operator_recovery_stale_write(
        StaleWrite("write precondition no longer matches")
    )
    assert code == "STEP_VERSION_CONFLICT"
    assert message == "step optimistic version is stale"


def test_operation_stale_write_maps_to_operation_version_conflict() -> None:
    code, message = classify_operator_recovery_stale_write(
        StaleWrite("operation CAS lost its precondition")
    )
    assert code == "OPERATION_VERSION_CONFLICT"
    assert message == "operation optimistic version is stale"


def test_step_stale_write_maps_to_step_version_conflict() -> None:
    code, message = classify_operator_recovery_stale_write(
        StaleWrite("step CAS lost its precondition")
    )
    assert code == "STEP_VERSION_CONFLICT"
    assert message == "step optimistic version is stale"
