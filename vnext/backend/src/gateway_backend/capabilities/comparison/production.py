"""Operation-bound comparison over canonical Arrow and C's native records."""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass, replace
from typing import Any

import pyarrow as pa
from gateway_compute._native import _encode_canonical_ipc_native
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope, BlankExtension, BlankSummary, ComparisonFacts, ComparisonMode,
    ComparisonPlan, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
    ComparisonRecord, ComparisonRecordKind, DetailedFactsResult, DatasetReplacementResult,
    KeylessPolicy, OrderedExtension, OrderedStatus, OrderedSummary, OrderedTableProcessingMode,
    ReplayGuarantee, SchemaEvolution, TableComparisonTask,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.replacement import compare_dataset_replacement
from gateway_backend.capabilities.comparison.row_encoding import (
    _can_table_early_exit, _ignored_values_changed, _is_columns_added,
    _schema_changes_from_view, _schema_diagnostics, _schema_record, _schema_view,
    _summary_payload, _table_digest_payload, _with_table_digest,
)
from gateway_backend.capabilities.comparison.standard import (
    STANDARD_COMPARISON_ALGORITHM_VERSION, _build_facts, _compare_task,
)
from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_columns
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, SnapshotTable,
)
from gateway_backend.capabilities.table_access import current_kernel_context


_MAX_CODEC_BYTES = 1024**3
_MAX_JCS_ROW_BYTES = 8 * 1024**2
_MAX_RECORDS = 2_000_000
_MAX_RECORD_BYTES = 512 * 1024**2


class _InputCharge:
    def __init__(self, charges: tuple[object, ...]) -> None:
        self._charges = charges

    def close(self) -> None:
        for charge in self._charges:
            close = getattr(charge, "close", None)
            if callable(close):
                close()
        self._charges = ()


@dataclass(slots=True)
class NativeComparison:
    result: DetailedFactsResult | DatasetReplacementResult
    handles: dict[str, Any]
    operation: Any | None

    def close(self) -> None:
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()
        if self.operation is not None:
            self.operation.close()
            self.operation = None


def _stream(table: SnapshotTable) -> tuple[pa.RecordBatchReader, object]:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("native comparison requires an operation context")
    # The codec output is a new backing. Charge its maximum before encoding;
    # shrink only after the canonical IPC file has been built.
    charge = context.memory.reserve(_MAX_CODEC_BYTES)
    try:
        budgets = {
            "max_columns": 2048, "max_input_batches": 4096,
            "max_rows": 10_000_000, "max_descriptor_bytes": 16 * 1024**2,
            "max_input_bytes": _MAX_CODEC_BYTES,
            "max_output_bytes": _MAX_CODEC_BYTES,
            "max_codec_peak_bytes": min(context.memory.available_bytes, 4 * 1024**3),
        }
        if table.reader is not None and callable(getattr(table.reader, "arrow_stream", None)):
            isolated = table.reader.reopen()
            try:
                with closing(isolated.arrow_stream()) as source:
                    raw = _encode_canonical_ipc_native(
                        canonical_columns(table.descriptor), source,
                        context.cancel_probe, budgets, context.deadline_monotonic,
                    )
            finally:
                isolated.close()
        elif table.batch_reader is not None:
            isolated_batch = table.batch_reader.reopen()
            try:
                with closing(pa.RecordBatchReader.from_batches(
                    isolated_batch.schema(), isolated_batch.iter_record_batches(),
                )) as source:
                    raw = _encode_canonical_ipc_native(
                        canonical_columns(table.descriptor), source,
                        context.cancel_probe, budgets, context.deadline_monotonic,
                    )
            finally:
                isolated_batch.close()
        else:
            raise StandardComparisonError("TABLE_READER_UNAVAILABLE")
        charge.shrink_to(len(raw))
        with closing(pa.ipc.open_file(pa.BufferReader(raw))) as file:
            batches = [file.get_batch(index) for index in range(file.num_record_batches)]
            stream = pa.RecordBatchReader.from_batches(file.schema, batches)
        return stream, charge
    except BaseException:
        charge.close()
        raise


def _compare_native(
    operation: object, task: TableComparisonTask, *, kind: str,
    policy: dict[str, object],
) -> Any:
    if task.before_table is None or task.current_table is None:
        raise StandardComparisonError("TABLE_READER_UNAVAILABLE")
    before, before_charge = _stream(task.before_table)
    try:
        current, current_charge = _stream(task.current_table)
    except BaseException:
        before.close()
        before_charge.close()
        raise
    owner = _InputCharge((before_charge, current_charge))
    try:
        return native.compare_records_batches(
            operation, kind=kind, table_name=task.table_name,
            before=before, current=current,
            policy_json=json.dumps(policy, separators=(",", ":")),
            detail_policy="FULL_BEFORE_AFTER_VALUES",
            input_owner_charge=owner, max_records=_MAX_RECORDS,
            max_sort_bytes=2 * 1024**3, max_output_bytes=_MAX_RECORD_BYTES,
            max_input_bytes=2 * _MAX_CODEC_BYTES + 8 * 1024**2,
        )
    finally:
        before.close()
        current.close()


def _standard_policy(task: TableComparisonTask, schema: Any) -> dict[str, object]:
    policy = task.policy
    assert policy is not None
    return {
        "selected_columns": list(schema.selected),
        "effective_key_before": list(schema.before_key),
        "effective_key_current": list(schema.current_key),
        "compare_excluded_columns": list(policy.compare_excluded_columns),
        "incompatible_columns": list(schema.incompatible),
        "emit_add_delete": task.artifact_scope is ArtifactScope.ALL_CHANGES,
        "columns_added": _is_columns_added(schema),
        "mode": "keyed" if schema.before_key else "keyless",
        "schema_diagnostics": _schema_diagnostics(schema, policy),
    }


def _ordered_policy(task: TableComparisonTask, schema: Any) -> dict[str, object]:
    policy = task.policy
    assert policy is not None and policy.ordered_policy is not None
    ordered = policy.ordered_policy
    before = task.before_descriptor
    current = task.current_descriptor
    assert before is not None and current is not None

    def provenance(table: SnapshotTable | None) -> str:
        if table is None or table.ordered_metadata is None:
            raise StandardComparisonError("ORDERED_PROVENANCE_MISSING")
        value = table.ordered_metadata.blank_provenance
        if value is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY:
            return "source"
        if value is BlankRowProvenance.CANONICAL_PSEUDO_GID:
            return "canonical"
        raise StandardComparisonError("ORDERED_PROVENANCE_INVALID")

    changes = _schema_changes_from_view(schema, policy)
    return {
        **_standard_policy(task, schema),
        "table_name": task.table_name,
        "policy_version": ordered.policy_version,
        "policy_digest": None if ordered.policy_digest is None else ordered.policy_digest.value,
        "value_columns": list(ordered.value_columns),
        "digest_value_columns": list(ordered.value_columns),
        "schema_changed": (
            before.business_schema_digest != current.business_schema_digest
            and changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED
        ),
        "raw_content_changed": before.raw_content_digest != current.raw_content_digest,
        "before_blank_provenance": provenance(task.before_table),
        "current_blank_provenance": provenance(task.current_table),
        "schema_changes": {
            "before_only_columns": list(changes.before_only_columns),
            "current_only_columns": list(changes.current_only_columns),
            "selected_columns": list(changes.selected_columns),
            "effective_compare_key_before": list(changes.effective_compare_key_before),
            "effective_compare_key_current": list(changes.effective_compare_key_current),
            "effective_compare_key_changed": changes.effective_compare_key_changed,
            "incompatible_columns": list(changes.incompatible_columns),
            "change_source": None if changes.change_source is None else changes.change_source.value,
        },
    }


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


def _native_fact(task: TableComparisonTask, handle: Any, schema: Any) -> ComparisonTableFact:
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
    status = (ComparisonTableStatus.SCHEMA_CHANGED if diagnostics else
        ComparisonTableStatus.MODIFIED if count else ComparisonTableStatus.UNCHANGED)
    content_changed = False
    if count == 0 and not diagnostics:
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


def _compare_task_native(task: TableComparisonTask, operation: object) -> tuple[ComparisonTableFact, Any | None]:
    policy = task.policy
    assert policy is not None
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None or current is None:
        return _compare_task(task), None
    schema = _schema_view(before, current, policy)
    changes = _schema_changes_from_view(schema, policy)
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        if changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED:
            return _compare_task(task), None
        probe_policy = _standard_policy(task, schema)
        probe_policy.update(mode="keyless", effective_key_before=[],
                            effective_key_current=[], compare_excluded_columns=[],
                            emit_add_delete=False, columns_added=True,
                            schema_diagnostics=[])
        probe = _compare_native(operation, task, kind="standard", policy=probe_policy)
        try:
            metadata = json.loads(probe.metadata_json())
        finally:
            probe.close()
        # The role exposes only content_changed. Rust's suppressed counts are
        # private to the shared-column multiset and never become public facts.
        old = _compare_task_metadata_nonrecord(task, changes)
        return replace(old, content_changed=bool(
            metadata["row_added_count"] or metadata["row_deleted_count"])), None
    if policy.ordered_policy is not None:
        from gateway_backend.capabilities.comparison.ordered import (
            _ordered_schema_diagnostics, _degraded_fact,
        )
        diagnostics = _ordered_schema_diagnostics(before, current, policy.ordered_policy, schema)
        if diagnostics:
            return _degraded_fact(task, before, current, changes, diagnostics), None
        if _can_table_early_exit(before, current, policy):
            return _ordered_unchanged_native(task, operation, schema), None
        handle = _compare_native(operation, task, kind="ordered", policy=_ordered_policy(task, schema))
        return _native_fact(task, handle, schema), handle
    if _can_table_early_exit(before, current, policy):
        return _compare_task(task), None
    if schema.key_invalid or schema.key_changed or not schema.selected:
        return _compare_task(task), None
    if not schema.before_key and policy.keyless_policy is KeylessPolicy.DEGRADE_NO_COMPARE_KEY:
        diagnostics = tuple(_schema_diagnostics(schema, policy)) + ("DEGRADE_NO_COMPARE_KEY",)
        return ComparisonTableFact(
            table_name=task.table_name, status=ComparisonTableStatus.DEGRADED,
            before_descriptor=before, current_descriptor=current,
            schema_changes=changes, row_count_before=before.row_count,
            row_count_current=current.row_count, diagnostics=diagnostics,
            records=(_schema_record(task.table_name, diagnostics, schema.selected),),
        ), None
    handle = _compare_native(operation, task, kind="standard", policy=_standard_policy(task, schema))
    return _native_fact(task, handle, schema), handle


def _compare_task_metadata_nonrecord(task: TableComparisonTask, changes: ComparisonSchemaChanges) -> ComparisonTableFact:
    before = task.before_descriptor
    current = task.current_descriptor
    assert before is not None and current is not None
    return ComparisonTableFact(
        table_name=task.table_name, status=ComparisonTableStatus.UNCHANGED,
        before_descriptor=before, current_descriptor=current, schema_changes=changes,
        row_count_before=before.row_count, row_count_current=current.row_count,
    )


def _ordered_unchanged_native(task: TableComparisonTask, operation: object, schema: Any) -> ComparisonTableFact:
    # The unchanged fast path must read only the current side and never run LIS.
    policy = _ordered_policy(task, schema)
    table = task.current_table
    before = task.before_descriptor
    current = task.current_descriptor
    assert table is not None and before is not None and current is not None and task.policy is not None
    stream, charge = _stream(table)
    try:
        before_digest, current_digest, before_occupancy, current_occupancy, _ = native.summarize_unchanged_ordered(
            operation, current=stream, policy_json=json.dumps(policy),
            input_owner_charge=charge, max_input_bytes=_MAX_CODEC_BYTES + 4 * 1024**2,
        )
    finally:
        stream.close()
    return ComparisonTableFact(
        table_name=task.table_name, status=ComparisonTableStatus.UNCHANGED,
        before_descriptor=before, current_descriptor=current,
        schema_changes=_schema_changes_from_view(schema, task.policy),
        row_count_before=before.row_count, row_count_current=current.row_count,
        content_changed=_ignored_values_changed(before, current, task.policy),
        ordered_extension=OrderedExtension(
            status=OrderedStatus.UNCHANGED, ordered_summary=OrderedSummary(),
            before_ordered_digest=DigestRef(before_digest), current_ordered_digest=DigestRef(current_digest),
            replay_guarantee=ReplayGuarantee.EXACT,
            policy_digest=task.policy.ordered_policy.policy_digest,
        ),
        blank_extension=BlankExtension(
            status=OrderedStatus.UNCHANGED, blank_summary=BlankSummary(),
            before_occupancy_digest=DigestRef(before_occupancy),
            current_occupancy_digest=DigestRef(current_occupancy),
            replay_guarantee=ReplayGuarantee.EXACT,
        ),
    )


def compare_plan_native(plan: ComparisonPlan) -> NativeComparison:
    if plan.mode is ComparisonMode.DATASET_REPLACEMENT:
        replaced = compare_dataset_replacement(plan)
        if not isinstance(replaced, DatasetReplacementResult):
            raise StandardComparisonError("replacement comparison failed")
        return NativeComparison(replaced, {}, None)
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("native comparison requires an operation context")
    context.checkpoint()
    # Leave an independent writer/risk reservation after native seal. The
    # native owner shrinks this phase to actual retained allocations at seal.
    native_budget = context.memory.available_bytes - 2 * 1024**3
    if native_budget < 64 * 1024**2:
        raise MemoryError("comparison native phase exceeds operation budget")
    context.memory.record_stage_admission("comparison-native", native_budget)
    operation = native.begin_records_operation(
        native_budget_bytes=native_budget,
        cancel_probe=context.cancel_probe,
        deadline_monotonic=context.deadline_monotonic,
    )
    handles: dict[str, Any] = {}
    try:
        tables = []
        for task in plan.tasks:
            context.checkpoint()
            try:
                fact, handle = _compare_task_native(task, operation)
            except (InterruptedError, TimeoutError, MemoryError):
                raise
            except (StandardComparisonError, ValueError) as exc:
                # Ordinary malformed table data retains the existing per-table
                # degraded result. Native adapter panic/runtime failures escape.
                diagnostic = str(exc) if isinstance(exc, StandardComparisonError) else type(exc).__name__
                schema_changes = ComparisonSchemaChanges()
                if (task.before_descriptor is not None and task.current_descriptor is not None
                        and task.policy is not None):
                    try:
                        schema_changes = _schema_changes_from_view(_schema_view(
                            task.before_descriptor, task.current_descriptor, task.policy,
                        ), task.policy)
                    except ValueError:
                        pass
                fact = ComparisonTableFact(
                    table_name=task.table_name, status=ComparisonTableStatus.DEGRADED,
                    before_descriptor=task.before_descriptor,
                    current_descriptor=task.current_descriptor,
                    schema_changes=schema_changes,
                    row_count_before=None if task.before_descriptor is None else task.before_descriptor.row_count,
                    row_count_current=None if task.current_descriptor is None else task.current_descriptor.row_count,
                    diagnostics=(diagnostic,),
                    records=(ComparisonRecord(
                        table_name=task.table_name,
                        record_kind=ComparisonRecordKind.TABLE_DEGRADED,
                        diagnostics=(diagnostic,),
                    ),),
                )
                handle = None
            if handle is not None:
                handles[task.table_name] = handle
                handle.prepare_risk_batches()
            tables.append(fact)
        metadata = []
        table_handles: list[object | None] = []
        with context.memory.reserve(8192 + len(tables) * 65536):
            for fact in tables:
                handle = handles.get(fact.table_name)
                if handle is None:
                    fact = _with_table_digest(fact)
                payload = _table_digest_payload(fact)
                if handle is not None:
                    payload["records"] = []
                    if isinstance(payload["ordered_extension"], dict):
                        payload["ordered_extension"]["records"] = []
                    if isinstance(payload["blank_extension"], dict):
                        payload["blank_extension"]["records"] = []
                raw = json.dumps(payload, separators=(",", ":"))
                if handle is not None:
                    fact = replace(fact, table_fact_digest=DigestRef(
                        handle.table_fact_digest(raw, _MAX_JCS_ROW_BYTES)))
                metadata.append(raw)
                table_handles.append(handle)
                tables[len(metadata) - 1] = fact
            from gateway_backend.capabilities.comparison.standard import _summary
            summary_json = json.dumps(_summary_payload(_summary(tuple(tables))), separators=(",", ":"))
            core = DigestRef(native.facts_core_digest(
                operation, table_handles, metadata,
                algorithm_version=STANDARD_COMPARISON_ALGORITHM_VERSION,
                summary_json=summary_json, max_jcs_row_bytes=_MAX_JCS_ROW_BYTES,
            ))
            facts: ComparisonFacts = _build_facts(plan, tuple(tables), core_digest=core)
        result = DetailedFactsResult(plan.pair_id, facts.summary.status, facts=facts, diagnostics=facts.diagnostics)
        operation.seal()
        context.checkpoint()
        return NativeComparison(result, handles, operation)
    except BaseException:
        for handle in handles.values():
            handle.close()
        operation.close()
        raise
