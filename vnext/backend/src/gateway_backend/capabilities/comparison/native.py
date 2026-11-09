"""Owned Arrow entry points for comparison records.

The artifact store supplies decoded Parquet batches. Rust owns schema and
logical-content validation; raw artifact identity stays with the store.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, cast
from gateway_shared_kernel import DigestRef

import pyarrow as pa
from gateway_compute._native import (
    _begin_comparison_operation_native,
    _compare_records_native,
    _restore_comparison_table_native,
    _comparison_format_versions_native,
    _facts_core_digest_native,
    _summarize_unchanged_ordered_native,
    _validate_records_batches_native,
)

from gateway_backend.capabilities.snapshot_materialization import current_kernel_context

from gateway_backend.capabilities.comparison.contracts import (
    BlankExtension, BlankSummary, ComparisonTableFact, ComparisonTableStatus,
    OrderedExtension, OrderedStatus, OrderedSummary, OrderedTableProcessingMode,
    ReplayGuarantee, SchemaEvolution, TableComparisonTask,
)
from gateway_backend.capabilities.comparison.row_encoding import (
    _schema_changes_from_view, _schema_diagnostics, _ignored_values_changed,
)


class CancelProbe(Protocol):
    def is_set(self) -> bool: ...


class ComparisonOperation(Protocol):
    """The coarse native phase owner returned by the PyO3 boundary."""

    def seal(self) -> int: ...
    def require_operation(self, operation_identity: int) -> None: ...
    def close(self) -> None: ...


class ComparisonRecordsHandle(Protocol):
    """One sealed-table candidate and its bounded Arrow outputs."""

    def phase_timings(self) -> tuple[float, float, float]: ...
    def require_operation(self, operation_identity: int) -> None: ...
    def metadata_json(self) -> str: ...
    def prepare_risk_batches(self) -> None: ...
    def prepare_cache_views(self, max_row_bytes: int) -> None: ...
    def discard_cache_views(self) -> None: ...
    def cache_metadata_json(self) -> str: ...
    def cache_family_names(self) -> list[str]: ...
    def facts_batches(self, family: str) -> pa.RecordBatchReader: ...
    def neutral_record_batches(self, family: str) -> pa.RecordBatchReader: ...
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


def restore_table_cache(
    operation: ComparisonOperation, *, table_name: str, kind: str, metadata_json: str,
    detail_policy: str, family_names: list[str], facts: list[pa.RecordBatchReader],
    artifacts: list[pa.RecordBatchReader], risk: pa.RecordBatchReader,
    input_owner_charge: object, max_records: int, max_row_bytes: int, max_input_bytes: int,
) -> ComparisonRecordsHandle:
    """Restore complete neutral Arrow views under the caller's active M phase."""
    context = current_kernel_context()
    handle: ComparisonRecordsHandle | None = None
    try:
        if context is None:
            raise RuntimeError("comparison restore requires an operation scope")
        context.require_active()
        operation.require_operation(id(context.memory))
        handle = cast(ComparisonRecordsHandle, _restore_comparison_table_native(
            operation, id(context.memory), table_name, kind, metadata_json, detail_policy, family_names, facts,
            artifacts, risk, max_records, max_row_bytes, max_input_bytes, input_owner_charge,
        ))
        context.checkpoint()
        return handle
    except BaseException:
        if handle is not None:
            handle.close()
        close = getattr(input_owner_charge, "close", None)
        if callable(close):
            close()
        raise


def comparison_format_versions() -> tuple[str, int, str]:
    """Existing Rust ordered algorithm and canonical mapping constants."""
    return cast(tuple[str, int, str], _comparison_format_versions_native())


def _optional_digest(value: object) -> DigestRef | None:
    return None if value is None else DigestRef(str(value))


def _ordered_extension(data: dict[str, Any]) -> OrderedExtension:
    summary = data["summary"]
    return OrderedExtension(
        status=OrderedStatus(data["status"]),
        ordered_summary=OrderedSummary(
            row_added_count=summary["row_added_count"],
            row_deleted_count=summary["row_deleted_count"],
            row_modified_count=summary["row_modified_count"],
            row_moved_count=summary["row_moved_count"],
            position_changed_count=summary["position_changed_count"],
            degraded_count=summary["degraded_count"],
        ),
        before_ordered_digest=_optional_digest(data["before_ordered_digest"]),
        current_ordered_digest=_optional_digest(data["current_ordered_digest"]),
        replay_guarantee=ReplayGuarantee(data["replay_guarantee"]),
        table_processing_mode=(None if data["table_processing_mode"] is None else
            OrderedTableProcessingMode(data["table_processing_mode"])),
        diagnostics=tuple(data["diagnostics"]),
        contract_version=data["contract_version"],
        policy_digest=_optional_digest(data["policy_digest"]),
    )


def _blank_extension(data: dict[str, Any]) -> BlankExtension:
    summary = data["summary"]
    return BlankExtension(
        status=OrderedStatus(data["status"]),
        blank_summary=BlankSummary(
            interval_inserted_count=summary["interval_inserted_count"],
            interval_deleted_count=summary["interval_deleted_count"],
            blank_changed_count=summary["blank_changed_count"],
            degraded_count=summary["degraded_count"],
        ),
        before_occupancy_digest=_optional_digest(data["before_occupancy_digest"]),
        current_occupancy_digest=_optional_digest(data["current_occupancy_digest"]),
        replay_guarantee=ReplayGuarantee(data["replay_guarantee"]),
        diagnostics=tuple(data["diagnostics"]),
        contract_version=data["contract_version"],
    )


def table_fact(task: TableComparisonTask, handle: Any, schema: Any) -> ComparisonTableFact:
    before = task.before_descriptor
    current = task.current_descriptor
    policy = task.policy
    assert before is not None and current is not None and policy is not None
    data: dict[str, Any] = json.loads(handle.metadata_json())
    changes = _schema_changes_from_view(schema, policy)
    if policy.ordered_policy is not None:
        return ComparisonTableFact(
            table_name=task.table_name, status=ComparisonTableStatus(data["status"]),
            before_descriptor=before, current_descriptor=current,
            schema_changes=changes, row_count_before=before.row_count,
            row_count_current=current.row_count,
            row_added_count=data["row_added_count"], row_deleted_count=data["row_deleted_count"],
            row_modified_count=data["row_modified_count"],
            suppressed_added_count=data["suppressed_added_count"],
            suppressed_deleted_count=data["suppressed_deleted_count"],
            diagnostics=tuple(data["diagnostics"]), content_changed=data["content_changed"],
            ordered_extension=_ordered_extension(data["ordered_extension"]),
            blank_extension=_blank_extension(data["blank_extension"]),
        )
    diagnostics = tuple(_schema_diagnostics(schema, policy))
    count = data["record_count"]
    changed_rows = bool(data["row_added_count"] or data["row_deleted_count"])
    is_keyless = not schema.before_key or (
        policy.allow_keyless_key_transition and not schema.current_key
    )
    status = (ComparisonTableStatus.SCHEMA_CHANGED if diagnostics else
        ComparisonTableStatus.MODIFIED if (count or (is_keyless and changed_rows))
        else ComparisonTableStatus.UNCHANGED)
    content_changed = False
    if (count == 0 and not diagnostics and
            (not is_keyless or not changed_rows)):
        content_changed = (data["ignored_shared_content_changed"] if
            changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED else
            _ignored_values_changed(before, current, policy))
    return ComparisonTableFact(
        table_name=task.table_name, status=status,
        before_descriptor=before, current_descriptor=current,
        schema_changes=changes, row_count_before=before.row_count,
        row_count_current=current.row_count,
        row_added_count=data["row_added_count"], row_deleted_count=data["row_deleted_count"],
        row_modified_count=data["row_modified_count"],
        suppressed_added_count=data["suppressed_added_count"],
        suppressed_deleted_count=data["suppressed_deleted_count"],
        diagnostics=diagnostics, content_changed=content_changed,
    )
