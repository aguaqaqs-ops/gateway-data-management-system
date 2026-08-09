"""Unit tests for Dolt crash evidence helpers."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from gateway_repository_service.versioned_import.ports import (
    MarkerInspectionUnique,
    MarkerInspectionZero,
)
from support.import_dolt_crash_evidence import (
    REPLAY_AUDIT_TABLE,
    assert_marker_inspection,
    assert_replay_audit_table_absent,
    records_row_count,
    table_exists,
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
def test_assert_replay_audit_table_absent_passes_when_table_missing() -> None:
    provider = MagicMock()
    provider._cli.query_json.return_value = []

    assert_replay_audit_table_absent(provider)


@pytest.mark.unit
def test_assert_replay_audit_table_absent_fails_when_table_exists() -> None:
    provider = MagicMock()
    provider._cli.query_json.return_value = [{"table_name": REPLAY_AUDIT_TABLE}]

    with pytest.raises(AssertionError, match=f"{REPLAY_AUDIT_TABLE} must not exist"):
        assert_replay_audit_table_absent(provider)


@pytest.mark.unit
def test_assert_marker_inspection_zero() -> None:
    provider = MagicMock()
    provider.inspect_marker.return_value = MarkerInspectionZero()

    assert assert_marker_inspection(provider, "marker-1", kind="zero") is None


@pytest.mark.unit
def test_assert_marker_inspection_unique_with_refs() -> None:
    provider = MagicMock()
    provider.inspect_marker.return_value = MarkerInspectionUnique(
        candidate="candidate-1",
        parent="parent-1",
        refs=("private-ref", "main"),
    )

    candidate = assert_marker_inspection(
        provider,
        "marker-1",
        kind="unique",
        parent="parent-1",
        refs_contain=("private-ref", "main"),
    )
    assert candidate == "candidate-1"


@pytest.mark.unit
def test_assert_marker_inspection_unique_refs_mismatch_raises() -> None:
    provider = MagicMock()
    provider.inspect_marker.return_value = MarkerInspectionUnique(
        candidate="candidate-1",
        parent="parent-1",
        refs=("private-ref",),
    )

    with pytest.raises(AssertionError, match="missing required ref"):
        assert_marker_inspection(
            provider,
            "marker-1",
            kind="unique",
            refs_contain="main",
        )


@pytest.mark.unit
@pytest.mark.parametrize("fault_point", list(ImportWorkerFaultPoint))
def test_crash_state_expectation_defined_for_all_fault_points(
    fault_point: ImportWorkerFaultPoint,
) -> None:
    from support.import_dolt_crash_evidence import _CRASH_STATE

    assert fault_point in _CRASH_STATE


@pytest.mark.unit
def test_table_exists_uses_information_schema() -> None:
    provider = MagicMock()
    provider._cli.query_json.return_value = [{"table_name": "records"}]

    assert table_exists(provider, "records") is True
    assert "information_schema" in provider._cli.query_json.call_args.args[1]
