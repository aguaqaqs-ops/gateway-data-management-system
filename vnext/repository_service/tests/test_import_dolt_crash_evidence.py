"""Unit tests for Dolt crash evidence helpers."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from support.import_dolt_crash_evidence import (
    records_row_count,
    replay_audit_row_count,
    table_row_count,
)

OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")


@pytest.mark.unit
def test_table_row_count_returns_zero_when_table_missing() -> None:
    provider = MagicMock()
    provider._cli.query_json.return_value = []

    assert table_row_count(provider, "records") == 0
    provider._cli.query_json.assert_called_once()


@pytest.mark.unit
def test_table_row_count_raises_on_query_failure_when_table_exists() -> None:
    provider = MagicMock()
    provider._cli.query_json.side_effect = [
        [{"table_name": "records"}],
        RuntimeError("dolt unavailable"),
    ]

    with pytest.raises(RuntimeError, match="dolt unavailable"):
        table_row_count(provider, "records")


@pytest.mark.unit
def test_records_row_count_delegates_to_table_row_count() -> None:
    provider = MagicMock()
    provider._cli.query_json.side_effect = [
        [{"table_name": "records"}],
        [{"row_count": 2}],
    ]

    assert records_row_count(provider) == 2


@pytest.mark.unit
def test_replay_audit_row_count_uses_import_replay_audit_table() -> None:
    provider = MagicMock()
    provider._cli.query_json.side_effect = [
        [],
    ]

    assert replay_audit_row_count(provider) == 0
    call = provider._cli.query_json.call_args
    assert "import_replay_audit" in call.args[1]


@pytest.mark.unit
@pytest.mark.parametrize("fault_point", list(ImportWorkerFaultPoint))
def test_crash_state_expectation_defined_for_all_fault_points(
    fault_point: ImportWorkerFaultPoint,
) -> None:
    from support.import_dolt_crash_evidence import _CRASH_STATE

    assert fault_point in _CRASH_STATE
