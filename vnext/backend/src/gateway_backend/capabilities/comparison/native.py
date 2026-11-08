"""Owned Arrow entry points for comparison records.

The artifact store supplies decoded Parquet batches. Rust owns schema and
logical-content validation; raw artifact identity stays with the store.
"""

from __future__ import annotations

from typing import Protocol, cast

import pyarrow as pa
from gateway_compute._native import (
    _begin_comparison_operation_native,
    _compare_records_native,
    _facts_core_digest_native,
    _summarize_unchanged_ordered_native,
    _validate_records_batches_native,
)

from gateway_backend.capabilities.table_access import current_kernel_context


class CancelProbe(Protocol):
    def is_set(self) -> bool: ...


class ComparisonOperation(Protocol):
    """The coarse native phase owner returned by the PyO3 boundary."""

    def seal(self) -> int: ...
    def close(self) -> None: ...


class ComparisonRecordsHandle(Protocol):
    """One sealed-table candidate and its bounded Arrow outputs."""

    def phase_timings(self) -> tuple[float, float, float]: ...
    def metadata_json(self) -> str: ...
    def prepare_risk_batches(self) -> None: ...
    def table_fact_digest(self, metadata_json: str, max_jcs_row_bytes: int) -> str: ...
    def family_summary(self, family: str) -> tuple[int, str]: ...
    def record_batches(self, family: str) -> pa.RecordBatchReader: ...
    def risk_record_batches(self) -> pa.RecordBatchReader: ...
    def is_sealed(self) -> bool: ...
    def close(self) -> None: ...


class _NeverCancel:
    def is_set(self) -> bool:
        return False


def begin_records_operation(
    *,
    native_budget_bytes: int,
    cancel_probe: CancelProbe,
    deadline_monotonic: float | None,
) -> ComparisonOperation:
    """Use the caller's existing operation budget and initialized pool.

    D owns the operation scope and picks the native reservation. The native
    owner closes it only after all exported Arrow buffers release their charge.
    """
    operation = current_kernel_context()
    if operation is None:
        raise RuntimeError("comparison records require an operation scope")
    reservation = operation.memory.reserve(native_budget_bytes)
    try:
        return cast(ComparisonOperation, _begin_comparison_operation_native(
            native_budget_bytes, reservation, cancel_probe, deadline_monotonic,
            id(operation.memory),
        ))
    except BaseException:
        reservation.close()
        raise


def compare_records_batches(
    operation: object,
    *,
    kind: str,
    table_name: str,
    before: pa.RecordBatchReader,
    current: pa.RecordBatchReader,
    policy_json: str,
    detail_policy: str,
    input_owner_charge: object,
    max_records: int,
    max_sort_bytes: int,
    max_output_bytes: int,
    max_input_bytes: int,
) -> ComparisonRecordsHandle:
    """One coarse Arrow comparison with an explicit unique input owner."""
    try:
        return cast(ComparisonRecordsHandle, _compare_records_native(
            operation, kind, table_name, before, current, policy_json,
            detail_policy, max_records, max_sort_bytes, max_output_bytes, max_input_bytes,
            input_owner_charge,
        ))
    except BaseException:
        close = getattr(input_owner_charge, "close", None)
        if callable(close):
            close()
        raise


def facts_core_digest(
    operation: object,
    handles: list[object],
    metadata_jsons: list[str],
    *,
    algorithm_version: str,
    summary_json: str,
    max_jcs_row_bytes: int,
) -> str:
    return cast(str, _facts_core_digest_native(
        operation, handles, metadata_jsons, algorithm_version, summary_json, max_jcs_row_bytes
    ))


def summarize_unchanged_ordered(
    operation: object,
    *,
    current: pa.RecordBatchReader,
    policy_json: str,
    input_owner_charge: object,
    max_input_bytes: int,
) -> tuple[str, str, str, str, int]:
    try:
        return cast(tuple[str, str, str, str, int], _summarize_unchanged_ordered_native(
            operation, current, policy_json, max_input_bytes, input_owner_charge
        ))
    except BaseException:
        close = getattr(input_owner_charge, "close", None)
        if callable(close):
            close()
        raise


def validate_records_batches(
    reader: pa.RecordBatchReader,
    *,
    max_records: int,
    max_batch_bytes: int,
    cancel_probe: CancelProbe | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[str, str, str, int, str]:
    return cast(tuple[str, str, str, int, str], _validate_records_batches_native(
        reader,
        max_records,
        max_batch_bytes,
        cancel_probe or _NeverCancel(),
        deadline_monotonic,
    ))
