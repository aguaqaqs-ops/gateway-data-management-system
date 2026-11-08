"""Operation-bound comparison over canonical Arrow and C's native records."""

from __future__ import annotations

import json
from time import perf_counter
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, closing
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import Any, Protocol

import pyarrow as pa
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope, BlankExtension, BlankSummary, ComparisonFacts, ComparisonMode,
    ComparisonPlan, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
    ComparisonRecord, ComparisonRecordKind, DetailedFactsResult, DatasetReplacementResult,
    KeylessPolicy, OrderedExtension, OrderedStatus, OrderedSummary, OrderedTableProcessingMode,
    RecordsDetailPolicy,
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
    STANDARD_COMPARISON_ALGORITHM_VERSION, _build_facts, _compare_task_metadata,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArrowSnapshotTableReader, canonical_comparison_profile, snapshot_arrow_input,
    check_canonical_descriptor_budget, operation_codec_budgets,
    try_declared_type_for_sql_spelling, current_kernel_context, TableAccessError,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, SnapshotTable, normalize_sql_type_spelling,
)


_MAX_JCS_ROW_BYTES = 8 * 1024**2
_MAX_RECORDS = 2_000_000
MAX_NATIVE_RECORD_BYTES = 512 * 1024**2
_CACHE_KEY_PROVISIONAL_BYTES = 16 * 1024**2
_OLD_CODED_ERRORS = frozenset({
    "BLANK_PROVENANCE_INVALID", "BLANK_PROVENANCE_MISSING",
    "CANONICAL_BLANK_PROVENANCE_INVALID", "CANONICAL_GID_INVALID",
    "ORDERED_INTEGER_INVALID", "ORDER_KEY_DUPLICATE", "ORDER_KEY_INVALID",
    "ORDER_KEY_MISSING", "ROW_IDENTITY_DUPLICATE", "ROW_SHAPE_MISMATCH",
    "SCALAR_TYPE_MISMATCH", "SCALAR_TYPE_UNKNOWN", "SCALAR_VALUE_INVALID",
    "SET_VALUE_INVALID", "SOURCE_GID_INVALID", "SOURCE_RESERVED_PSEUDO_GID",
})


class _InputCharge:
    def __init__(self, charges: tuple[object, ...]) -> None:
        self._charges = charges

    def close(self) -> None:
        for charge in self._charges:
            close = getattr(charge, "close", None)
            if callable(close):
                close()
        self._charges = ()


class _Closable(Protocol):
    def close(self) -> None: ...


class _CompositeArrowOwner:
    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def close(self) -> None:
        manager, self._manager = self._manager, None
        if manager is not None:
            manager.__exit__(None, None, None)


def _has_canonical_profile_metadata(schema: pa.Schema) -> bool:
    return ((schema.metadata is not None
             and b"gdds.canonical_mapping_version" in schema.metadata)
            or any(field.metadata is not None
                   and b"gdds.canonical_type" in field.metadata
                   for field in schema))


def _fresh_view_budget(table: SnapshotTable) -> tuple[int, int]:
    """Bound only a writer-verified fresh comparison view before native M split."""
    reader = table.reader
    if (not isinstance(reader, ArrowSnapshotTableReader)
            or not reader.canonical_comparison_verified):
        return 0, 0
    try:
        schema = reader.arrow_schema
        batch_count = reader.arrow_batch_count_upper
    except TableAccessError:
        # The existing task boundary will emit its reader degradation.
        return 0, 0
    if _has_canonical_profile_metadata(schema):
        return 0, 0
    columns = table.descriptor.columns
    source_bytes = sum(
        256 + len(column.name) + len(column.display_name)
        + len(column.scalar_type or "") for column in columns
    )
    descriptor_upper = 0
    try:
        budgets = operation_codec_budgets()
        context = current_kernel_context()
        assert context is not None
        # This is a static descriptor bound. Actual concurrent M admission is
        # the native split and _stream reserve below, after optional eviction.
        budgets["max_codec_peak_bytes"] = context.memory.limit_bytes
        descriptor_upper = 8 * check_canonical_descriptor_budget(table.descriptor, budgets)
    except MemoryError:
        # A malformed descriptor follows the existing per-table _stream path;
        # this preflight only sizes valid writer-verified input.
        pass
    metadata_upper = max(
        65536 + 64 * source_bytes + 16384 * len(columns), descriptor_upper,
    )
    rows = table.descriptor.row_count
    # A fresh business projection normally has one batch. This upper also
    # covers the union of all column chunk boundaries and our 65k BIT slices.
    batches = batch_count + (rows + 65535) // 65536
    bit_upper = 0
    for column in columns:
        declared = try_declared_type_for_sql_spelling(
            normalize_sql_type_spelling(column.scalar_type or "UNKNOWN")
        )
        if (declared is None or declared.kind.value != "bit"
                or declared.bit_width is None):
            continue
        index = schema.get_field_index(column.name)
        if index < 0 or pa.types.is_fixed_size_binary(schema.field(index).type):
            continue
        width = (declared.bit_width + 7) // 8
        bit_upper += 2 * rows * width + 2 * ((rows + 7) // 8)
        bit_upper += batches * 1024 + 4096
    return metadata_upper, bit_upper


def _task_arrow_inputs(task: TableComparisonTask) -> tuple[SnapshotTable, ...]:
    """Mirror only the existing per-task reader admissions for native M split."""
    before, current = task.before_table, task.current_table
    policy = task.policy
    first, second = task.before_descriptor, task.current_descriptor
    if (before is None or current is None or policy is None
            or first is None or second is None):
        return ()
    try:
        schema = _schema_view(first, second, policy)
        if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
            changes = _schema_changes_from_view(schema, policy)
            return (before, current) if changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED else ()
        if policy.ordered_policy is not None:
            from gateway_backend.capabilities.comparison.ordered import _ordered_schema_diagnostics

            if _ordered_schema_diagnostics(first, second, policy.ordered_policy, schema):
                return ()
            return (current,) if _can_table_early_exit(first, second, policy) else (before, current)
        if _can_table_early_exit(first, second, policy):
            return ()
        if schema.key_invalid or schema.key_changed or not schema.selected:
            return ()
    except (ValueError, StandardComparisonError):
        # The table will follow its existing per-table degraded path.
        return ()
    return before, current


def _cache_key_fits_prepaid_repr(plan: ComparisonPlan, task: TableComparisonTask) -> bool:
    """Conservatively bound repr growth before constructing an optional key."""
    remaining = _CACHE_KEY_PROVISIONAL_BYTES - 8192
    nodes = 0

    def admit(value: object, depth: int = 0) -> bool:
        nonlocal remaining, nodes
        nodes += 1
        remaining -= 4096  # type/field names, delimiters and Python containers
        if remaining < 0 or nodes > 4096 or depth > 24:
            return False
        if isinstance(value, Enum):
            remaining -= 256 * (len(type(value).__qualname__) + len(str(value.value)))
        elif isinstance(value, str | bytes):
            # repr may escape one input character as a ten-character Unicode
            # sequence; 256 bytes covers intermediate repr strings and the
            # charged 8x final key copy at the same time.
            remaining -= 256 * len(value)
        elif value is None or isinstance(value, bool | float):
            pass
        elif isinstance(value, int):
            if value.bit_length() > 512:
                return False
        elif is_dataclass(value) and not isinstance(value, type):
            return all(admit(getattr(value, field.name), depth + 1) for field in fields(value))
        elif isinstance(value, tuple | list):
            return all(admit(item, depth + 1) for item in value)
        elif isinstance(value, Mapping):
            return all(admit(key, depth + 1) and admit(item, depth + 1)
                       for key, item in value.items())
        else:
            return False
        return remaining >= 0

    before_artifact = None if task.before_table is None else task.before_table.artifact
    current_artifact = None if task.current_table is None else task.current_table.artifact
    before_ordered = None if task.before_table is None else task.before_table.ordered_metadata
    current_ordered = None if task.current_table is None else task.current_table.ordered_metadata
    return admit((
        task.table_name, task.before_descriptor, task.current_descriptor,
        before_artifact, current_artifact, before_ordered, current_ordered,
        task.policy, task.artifact_scope, plan.mode, plan.rule_set,
        plan.options, plan.contract_versions,
    ))


def _task_key(plan: ComparisonPlan, task: TableComparisonTask) -> str | None:
    before = task.before_descriptor
    current = task.current_descriptor
    policy = task.policy
    if before is None or current is None or policy is None:
        return None
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        changes = _schema_changes_from_view(_schema_view(before, current, policy), policy)
        if changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED:
            return None
        kind = "nonrecord-shared-multiset"
    elif policy.ordered_policy is not None and _can_table_early_exit(before, current, policy):
        kind = "ordered-current-summary"
    elif _can_table_early_exit(before, current, policy):
        return None
    else:
        schema = _schema_view(before, current, policy)
        if schema.key_invalid or schema.key_changed or not schema.selected:
            return None
        kind = "row-comparison"

    def identity(table: SnapshotTable | None) -> tuple[str, str, str, str]:
        if table is None:
            return ("missing", "", "", "reader-none")
        input_mode = ("reader-none" if table.reader is None else
                      f"reader:{type(table.reader).__module__}.{type(table.reader).__qualname__}")
        if table.artifact is not None:
            return ("verified-canonical-artifact", repr(table.artifact),
                    repr(table.ordered_metadata), input_mode)
        return ("operation-local-reader", str(id(table.reader)),
                repr(table.ordered_metadata), input_mode)

    # Complete schema (including name), direction, both authorities, policy
    # bodies and versions remain in the key. Overly narrow reuse is a safe miss.
    return repr((
        kind, "BEFORE_TO_CURRENT", task.table_name,
        before, current, identity(task.before_table), identity(task.current_table),
        policy, task.artifact_scope, plan.mode, plan.rule_set,
        plan.options, plan.contract_versions,
    ))


class ComparisonTaskSession:
    """Known-use, operation-local native handle retention for adjacent pairs."""

    def __init__(self, plans: tuple[ComparisonPlan, ...]) -> None:
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison dedup requires an operation context")
        # Admit each candidate key before repr() allocates it. Keep the
        # charge only for keys with a known later consumer; one-use entries
        # are discarded after this declaration pass.
        occurrences: list[tuple[str, str, str, Any]] = []
        try:
            for plan in plans:
                if plan.mode is not ComparisonMode.DETAILED:
                    continue
                for task in plan.tasks:
                    try:
                        provisional = context.memory.reserve(_CACHE_KEY_PROVISIONAL_BYTES)
                    except MemoryError:
                        continue
                    try:
                        if not _cache_key_fits_prepaid_repr(plan, task):
                            provisional.close()
                            continue
                        key = _task_key(plan, task)
                        if key is None:
                            provisional.close()
                            continue
                        actual = len(key) * 8 + 512
                        if actual > _CACHE_KEY_PROVISIONAL_BYTES:
                            provisional.close()
                            continue
                        provisional.shrink_to(actual)
                        occurrences.append((plan.pair_id, task.table_name, key, provisional))
                    except MemoryError:
                        provisional.close()
                        continue
                    except BaseException:
                        provisional.close()
                        raise
            counts = Counter(key for _, _, key, _ in occurrences)
            self.remaining_uses = Counter({key: uses for key, uses in counts.items() if uses > 1})
            self.declared_keys = {
                (pair_id, name): key for pair_id, name, key, _ in occurrences
                if key in self.remaining_uses
            }
            self.key_charges: dict[str, Any] = {}
            retained: set[str] = set()
            for _, _, key, charge in occurrences:
                if key not in self.remaining_uses or key in retained:
                    charge.close()
                else:
                    self.key_charges[key] = charge
                    retained.add(key)
        except BaseException:
            for _, _, _, charge in occurrences:
                charge.close()
            raise
        self.cached: dict[str, tuple[ComparisonTableFact, Any | None]] = {}
        self.risk_candidates: dict[tuple[str, str], tuple[tuple[object, ...], ExitStack]] = {}
        self.pending_risk: dict[tuple[str, str], tuple[tuple[object, ...], ExitStack]] = {}
        self.calls = 0
        self.hits = 0
        self.reads = 0
        try:
            self._map_charge = context.memory.reserve(4096 + len(self.remaining_uses) * 512)
        except BaseException:
            for charge in self.key_charges.values():
                charge.close()
            self.key_charges.clear()
            raise
        context.resources.callback(self.close)

    def close(self) -> None:
        for _, handle in self.cached.values():
            if handle is not None:
                handle.close()
        self.cached.clear()
        for _, charges in self.risk_candidates.values():
            charges.close()
        self.risk_candidates.clear()
        self.abort_pending_risk()
        for charge in self.key_charges.values():
            charge.close()
        self.key_charges.clear()
        self.remaining_uses.clear()
        self.declared_keys.clear()
        self._map_charge.close()

    def abort_pending_risk(self) -> None:
        for _, charges in self.pending_risk.values():
            charges.close()
        self.pending_risk.clear()

    def commit_pending_risk(self) -> None:
        self.risk_candidates.update(self.pending_risk)
        self.pending_risk.clear()

    def risk_lookup(self, task_key: str, risk_key: str) -> tuple[object, ...] | None:
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        context.checkpoint()
        item = self.risk_candidates.get((task_key, risk_key))
        return None if item is None else item[0]

    def risk_store(
        self, task_key: str, risk_key: str,
        events: tuple[object, ...], charges: ExitStack,
    ) -> bool:
        if self.remaining_uses.get(task_key, 0) <= 1:
            return False
        self.pending_risk[(task_key, risk_key)] = (events, charges)
        return True

    def risk_evict(self, task_key: str, risk_key: str) -> None:
        item = self.risk_candidates.pop((task_key, risk_key), None)
        if item is not None:
            _, charges = item
            charges.close()

    def risk_evict_for_output(self) -> None:
        """Release only optional Risk candidates before necessary output work."""
        for _, charges in self.risk_candidates.values():
            charges.close()
        self.risk_candidates.clear()
        self.abort_pending_risk()

    def risk_retire_last_uses(self, task_keys: Mapping[str, str]) -> None:
        """Retire replay events after their final table Risk consumer returns."""
        active_keys = frozenset(task_keys.values())
        for cache_key in tuple(self.risk_candidates):
            if (cache_key[0] in active_keys
                    and self.remaining_uses.get(cache_key[0]) == 1):
                _, charges = self.risk_candidates.pop(cache_key)
                charges.close()

    def evict_for(self, plan: ComparisonPlan) -> None:
        # Proactively release optional retention only when the next mixed
        # pair has too little headroom even for facts/core scratch. Otherwise
        # preserve actual adjacent-pair hits; a precise M rejection gets one
        # fresh computation attempt in compare_plan_native below.
        if not self.cached:
            return
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        keys = {self.key_for(plan, task) for task in plan.tasks}
        expected = any((plan.pair_id, task.table_name) in self.declared_keys
                       for task in plan.tasks)
        fresh = (expected and None in keys) or any(
            key is not None and key not in self.cached for key in keys
        )
        if fresh and context.memory.available_bytes < 512 * 1024**2:
            self.close()

    def key_for(self, plan: ComparisonPlan, task: TableComparisonTask) -> str | None:
        declared = self.declared_keys.get((plan.pair_id, task.table_name))
        if declared is None or declared not in self.remaining_uses:
            return None
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        try:
            with context.memory.reserve(_CACHE_KEY_PROVISIONAL_BYTES):
                if not _cache_key_fits_prepaid_repr(plan, task):
                    return None
                actual = _task_key(plan, task)
                return declared if actual == declared else None
        except MemoryError:
            return None

    def lookup(
        self, key: str | None, task: TableComparisonTask,
    ) -> tuple[ComparisonTableFact, Any | None] | None:
        if key is None or key not in self.remaining_uses:
            return None
        item = self.cached.get(key)
        if item is not None:
            context = current_kernel_context()
            if context is None:
                raise RuntimeError("comparison context was lost")
            context.checkpoint()
            # Artifact identity does not prove that a currently bound reader
            # remains open. Check the actual reopen capability before using
            # prior facts; an unavailable reader must take the old per-table
            # degradation path, without consuming the retained result.
            for table in (task.before_table, task.current_table):
                if table is None or table.reader is None:
                    return None
                try:
                    with closing(table.reader.reopen()):
                        context.checkpoint()
                except (InterruptedError, TimeoutError, MemoryError):
                    raise
                except (TableAccessError, ValueError, OSError, pa.ArrowException):
                    context.checkpoint()
                    old = self.cached.pop(key, None)
                    if old is not None and old[1] is not None:
                        old[1].close()
                    return None
            self.hits += 1
        return item


@dataclass(slots=True)
class ComparisonRunMetrics:
    dispatches: int = 0
    native_calls: int = 0
    input_reads: int = 0
    cache_hits: int = 0
    compare_read_build_seconds: float = 0.0
    native_input_read_seconds: float = 0.0
    native_index_compare_seconds: float = 0.0
    native_records_build_seconds: float = 0.0
    ordered_current_summary_seconds: float = 0.0
    records_jcs_seconds: float = 0.0


@dataclass(slots=True)
class NativeComparison:
    result: DetailedFactsResult | DatasetReplacementResult
    handles: dict[str, Any]
    risk_handles: dict[str, Any]
    operation: Any | None
    session: ComparisonTaskSession | None = None
    task_keys: dict[str, str] | None = None
    consumed_keys: dict[str, str] | None = None
    committed: bool = False
    metrics: ComparisonRunMetrics | None = None

    def commit_cache(self) -> None:
        if self.committed:
            return
        self.committed = True
        if self.session is None or self.task_keys is None or self.consumed_keys is None:
            return
        self.session.commit_pending_risk()
        for name, key in self.consumed_keys.items():
            remaining = self.session.remaining_uses[key] - 1
            if remaining > 0:
                self.session.remaining_uses[key] = remaining
            else:
                self.session.remaining_uses.pop(key, None)
            handle = self.handles.get(name)
            if (remaining > 0 and name in self.task_keys
                    and self.session.cached.get(key) is None):
                facts = self.result.facts
                if facts is not None:
                    fact = next(table for table in facts.tables if table.table_name == name)
                    self.session.cached[key] = (fact, handle)
            if remaining <= 0:
                previous = self.session.cached.pop(key, None)
                if (previous is not None and previous[1] is not None
                        and previous[1] is not self.handles.get(name)):
                    previous[1].close()
                charge = self.session.key_charges.pop(key, None)
                if charge is not None:
                    charge.close()
                for identity in tuple(self.session.declared_keys):
                    if self.session.declared_keys[identity] == key:
                        self.session.declared_keys.pop(identity)
                for risk_key in tuple(self.session.risk_candidates):
                    if risk_key[0] == key:
                        _, charges = self.session.risk_candidates.pop(risk_key)
                        charges.close()
        for name, key in self.task_keys.items():
            if key in self.session.cached:
                self.handles.pop(name, None)


    def close(self) -> None:
        if not self.committed and self.session is not None:
            self.session.abort_pending_risk()
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()
        self.risk_handles.clear()
        if self.operation is not None:
            self.operation.close()
            self.operation = None


def _stream(table: SnapshotTable) -> tuple[pa.RecordBatchReader, _Closable]:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("native comparison requires an operation context")
    if table.descriptor.table_name == "composite_signal_point" and not isinstance(
        table.reader, ArrowSnapshotTableReader,
    ):
        # The composition producer still owns a bounded derived row table.
        # Reuse its existing Arrow conversion at this boundary; all ordinary
        # SQL/History tables arrive as retained canonical Arrow already.
        manager = snapshot_arrow_input(table)
        try:
            metadata, _ = manager.__enter__()
            return metadata["arrow_stream"], _CompositeArrowOwner(manager)
        except BaseException:
            manager.__exit__(None, None, None)
            context.checkpoint()
            raise
    if not isinstance(table.reader, ArrowSnapshotTableReader):
        raise StandardComparisonError("canonical comparison requires an Arrow reader")
    isolated = table.reader.reopen()
    original: pa.RecordBatchReader | None = None
    try:
        # reopen() borrows the original Arrow buffers through retain_arrow's
        # unique backing keys. The native handle keeps this charge until its
        # final output consumer closes; no IPC copy or Python row bridge.
        original = isolated.arrow_stream()
        schema = original.schema
        if _has_canonical_profile_metadata(schema):
            # Persisted IPC and any already-profiled input must pass the native
            # validator unchanged, including partial/malformed metadata.
            return original, isolated
        if not isolated.canonical_comparison_verified:
            return original, isolated
        # The fresh canonical writer has already validated this exact backing.
        # Rebind only its comparison view; business/export Arrow stays intact.
        metadata_upper, bit_upper = _fresh_view_budget(table)
        profile_charge = context.memory.reserve(metadata_upper)
        try:
            profile, indices = canonical_comparison_profile(
                table.descriptor, schema, metadata_budget_bytes=metadata_upper,
            )
            for position, source_index in enumerate(indices):
                target = profile.field(position).type
                actual = schema.field(source_index).type
                if actual == target:
                    continue
                if not (pa.types.is_fixed_size_binary(target)
                        and (pa.types.is_binary(actual) or pa.types.is_large_binary(actual))):
                    raise ValueError("canonical comparison view has an unsupported conversion")
            bit_charge = context.memory.reserve(bit_upper) if bit_upper else None
            try:
                def batches() -> Iterator[pa.RecordBatch]:
                    for batch in original:
                        step = 65536 if bit_upper else max(1, batch.num_rows)
                        for start in range(0, max(1, batch.num_rows), step):
                            context.checkpoint()
                            part = batch.slice(start, min(step, batch.num_rows - start))
                            arrays = []
                            for position, source_index in enumerate(indices):
                                array = part.column(source_index)
                                target = profile.field(position).type
                                arrays.append(array if array.type == target else array.cast(target, safe=True))
                            yield pa.RecordBatch.from_arrays(arrays, schema=profile)
                    context.checkpoint()

                view = pa.RecordBatchReader.from_batches(profile, batches())
            except BaseException:
                if bit_charge is not None:
                    bit_charge.close()
                raise
        except BaseException:
            profile_charge.close()
            raise
        return view, _InputCharge(tuple(
            item for item in (original, isolated, bit_charge, profile_charge) if item is not None
        ))
    except BaseException:
        if original is not None:
            original.close()
        isolated.close()
        context.checkpoint()
        raise


def _compare_native(
    operation: object, task: TableComparisonTask, *, kind: str,
    policy: dict[str, object], detail_policy: RecordsDetailPolicy,
    native_budget_bytes: int,
    session: ComparisonTaskSession | None = None,
    metrics: ComparisonRunMetrics,
) -> Any:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("comparison operation context was lost")
    if (task.before_table is None or task.current_table is None
            or task.before_table.reader is None or task.current_table.reader is None):
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
        metrics.native_calls += 1
        metrics.input_reads += 2
        if session is not None:
            session.calls += 1
            session.reads += 2
        try:
            handle = native.compare_records_batches(
                operation, kind=kind, table_name=task.table_name,
                before=before, current=current,
                policy_json=json.dumps(policy, separators=(",", ":")),
                detail_policy=detail_policy.value,
                input_owner_charge=owner, max_records=_MAX_RECORDS,
                max_sort_bytes=native_budget_bytes, max_output_bytes=MAX_NATIVE_RECORD_BYTES,
                max_input_bytes=context.memory.limit_bytes,
            )
            input_seconds, compare_seconds, build_seconds = handle.phase_timings()
            metrics.native_input_read_seconds += input_seconds
            metrics.native_index_compare_seconds += compare_seconds
            metrics.native_records_build_seconds += build_seconds
            return handle
        except BaseException:
            # A Python reader can fail inside the Arrow C Stream before the
            # native watch samples it. Preserve current stop/deadline priority
            # before ordinary table error classification.
            context.checkpoint()
            raise
    finally:
        before.close()
        current.close()


def _scan_keyless_degrade_inputs(
    task: TableComparisonTask, session: ComparisonTaskSession | None,
    metrics: ComparisonRunMetrics,
) -> None:
    # Frozen keyless degradation comes after both readers were consumed.
    # Read Arrow batches without constructing Python row values or a false
    # comparison result, preserving reader/cancel/error precedence.
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("comparison operation context was lost")
    if (task.before_table is None or task.current_table is None
            or task.before_table.reader is None or task.current_table.reader is None):
        raise StandardComparisonError("TABLE_READER_UNAVAILABLE")
    for table in (task.before_table, task.current_table):
        stream, owner = _stream(table)
        try:
            metrics.input_reads += 1
            if session is not None:
                session.reads += 1
            with closing(stream):
                for _ in stream:
                    context.checkpoint()
        finally:
            getattr(owner, "close")()


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
        "mode": ("keyless" if not schema.before_key or
                 (policy.allow_keyless_key_transition and not schema.current_key)
                 else "keyed"),
        "schema_diagnostics": _schema_diagnostics(schema, policy),
    }


def _ordered_policy(
    task: TableComparisonTask, schema: Any, *, unchanged: bool = False,
) -> dict[str, object]:
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
        "before_blank_provenance": (
            provenance(task.current_table) if unchanged else provenance(task.before_table)
        ),
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


def _compare_task_native(
    task: TableComparisonTask, operation: object,
    session: ComparisonTaskSession | None,
    metrics: ComparisonRunMetrics, detail_policy: RecordsDetailPolicy,
    native_budget_bytes: int,
) -> tuple[ComparisonTableFact, Any | None]:
    policy = task.policy
    assert policy is not None
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None or current is None:
        return _compare_task_metadata(task), None
    schema = _schema_view(before, current, policy)
    changes = _schema_changes_from_view(schema, policy)
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        if changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED:
            return _compare_task_metadata(task), None
        probe_policy = _standard_policy(task, schema)
        probe_policy.update(mode="keyless", effective_key_before=[],
                            effective_key_current=[], compare_excluded_columns=[],
                            emit_add_delete=False, columns_added=True,
                            schema_diagnostics=[])
        probe = _compare_native(operation, task, kind="standard", policy=probe_policy,
                                detail_policy=detail_policy,
                                native_budget_bytes=native_budget_bytes,
                                session=session, metrics=metrics)
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
            if task.current_table is None or task.current_table.reader is None:
                return _degraded_fact(task, before, current, changes,
                                      ("TABLE_READER_UNAVAILABLE",)), None
            return _ordered_unchanged_native(task, operation, schema, session, metrics), None
        handle = _compare_native(operation, task, kind="ordered",
                                 policy=_ordered_policy(task, schema), detail_policy=detail_policy,
                                 native_budget_bytes=native_budget_bytes,
                                 session=session,
                                 metrics=metrics)
        return _native_fact(task, handle, schema), handle
    if _can_table_early_exit(before, current, policy):
        return _compare_task_metadata(task), None
    if schema.key_invalid or schema.key_changed or not schema.selected:
        return _compare_task_metadata(task), None
    is_keyless = not schema.before_key or (
        policy.allow_keyless_key_transition and not schema.current_key
    )
    if is_keyless and policy.keyless_policy is KeylessPolicy.DEGRADE_NO_COMPARE_KEY:
        _scan_keyless_degrade_inputs(task, session, metrics)
        diagnostics = tuple(_schema_diagnostics(schema, policy)) + ("DEGRADE_NO_COMPARE_KEY",)
        return ComparisonTableFact(
            table_name=task.table_name, status=ComparisonTableStatus.DEGRADED,
            before_descriptor=before, current_descriptor=current,
            schema_changes=changes, row_count_before=before.row_count,
            row_count_current=current.row_count, diagnostics=diagnostics,
            records=(_schema_record(task.table_name, diagnostics, schema.selected),),
        ), None
    handle = _compare_native(operation, task, kind="standard",
                             policy=_standard_policy(task, schema), detail_policy=detail_policy,
                             native_budget_bytes=native_budget_bytes,
                             session=session,
                             metrics=metrics)
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


def _ordered_unchanged_native(
    task: TableComparisonTask, operation: object, schema: Any,
    session: ComparisonTaskSession | None,
    metrics: ComparisonRunMetrics,
) -> ComparisonTableFact:
    # The unchanged fast path must read only the current side and never run LIS.
    policy = _ordered_policy(task, schema, unchanged=True)
    table = task.current_table
    before = task.before_descriptor
    current = task.current_descriptor
    assert table is not None and before is not None and current is not None and task.policy is not None
    ordered_policy = task.policy.ordered_policy
    assert ordered_policy is not None
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("comparison operation context was lost")
    stream, charge = _stream(table)
    try:
        metrics.native_calls += 1
        metrics.input_reads += 1
        if session is not None:
            session.calls += 1
            session.reads += 1
        summary_started = perf_counter()
        before_digest, current_digest, before_occupancy, current_occupancy, _ = native.summarize_unchanged_ordered(
            operation, current=stream, policy_json=json.dumps(policy),
            input_owner_charge=charge,
            max_input_bytes=context.memory.limit_bytes,
        )
        metrics.ordered_current_summary_seconds += perf_counter() - summary_started
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
            policy_digest=ordered_policy.policy_digest,
        ),
        blank_extension=BlankExtension(
            status=OrderedStatus.UNCHANGED, blank_summary=BlankSummary(),
            before_occupancy_digest=DigestRef(before_occupancy),
            current_occupancy_digest=DigestRef(current_occupancy),
            replay_guarantee=ReplayGuarantee.EXACT,
        ),
    )


def compare_plan_native(
    plan: ComparisonPlan, *, session: ComparisonTaskSession | None = None,
) -> NativeComparison:
    metrics = ComparisonRunMetrics()
    try:
        return _compare_plan_native_once(plan, session=session, metrics=metrics)
    except MemoryError:
        # Optional retained keys/handles may have consumed the room needed
        # by a real compare. Drop them, then try that same immutable plan once
        # with no reuse. A second M rejection is the business resource limit.
        if session is None or (not session.key_charges and not session.cached):
            raise
        session.close()
        context = current_kernel_context()
        if context is not None:
            context.checkpoint()
        return _compare_plan_native_once(plan, session=None, metrics=metrics)


def _compare_plan_native_once(
    plan: ComparisonPlan, *, session: ComparisonTaskSession | None = None,
    metrics: ComparisonRunMetrics,
) -> NativeComparison:
    started = perf_counter()
    if plan.mode is ComparisonMode.DATASET_REPLACEMENT:
        replaced = compare_dataset_replacement(plan)
        if not isinstance(replaced, DatasetReplacementResult):
            raise StandardComparisonError("replacement comparison failed")
        return NativeComparison(replaced, {}, {}, None, session=session, metrics=metrics)
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("native comparison requires an operation context")
    detail_policy_value = dict(plan.options).get(
        "row_diff_detail_policy", RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES.value,
    )
    if not isinstance(detail_policy_value, str):
        raise ValueError("row_diff_detail_policy is invalid")
    detail_policy = RecordsDetailPolicy(detail_policy_value)
    context.checkpoint()
    if session is not None:
        session.evict_for(plan)
    # Small Python descriptors/facts and their JSON copies survive native
    # sealing and, in FULL, the next pair. Bound them before any table work.
    metadata_upper = 16 * 1024**2 + len(plan.tasks) * 1024**2
    for task in plan.tasks:
        for descriptor in (task.before_descriptor, task.current_descriptor):
            if descriptor is not None:
                metadata_upper += len(descriptor.columns) * 16 * 1024
                metadata_upper += sum(
                    (len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 64
                    for column in descriptor.columns
                )
                metadata_upper += sum(
                    len(diagnostic.message) * 64 + 4096 for diagnostic in descriptor.diagnostics
                )
    context.memory.record_stage_admission("comparison-metadata", metadata_upper)
    metadata_charge = context.memory.reserve(metadata_upper)
    # The writer and Risk run after seal, when the unused native phase is
    # returned. Leave only the Python facts/core scratch needed concurrently;
    # a fixed future-writer holdback would reject small cached replays.
    try:
        available = context.memory.available_bytes
        necessary_view_total = sum(
            sum(_fresh_view_budget(table))
            for task in plan.tasks for table in _task_arrow_inputs(task)
        )
        concurrent_scratch = max(
            min(available // 2, max(metadata_upper + 16 * 1024**2, 512 * 1024**2)),
            necessary_view_total + 16 * 1024**2,
        )
        native_budget = available - concurrent_scratch
        if native_budget <= 0:
            raise MemoryError("comparison native phase exceeds operation budget")
        context.memory.record_stage_admission("comparison-native", native_budget)
        operation = native.begin_records_operation(
            native_budget_bytes=native_budget,
            cancel_probe=context.cancel_probe,
            deadline_monotonic=context.deadline_monotonic,
        )
    except BaseException:
        metadata_charge.close()
        raise
    handles: dict[str, Any] = {}
    risk_handles: dict[str, Any] = {}
    task_keys: dict[str, str] = {}
    consumed_keys: dict[str, str] = {}
    cached_names: set[str] = set()
    try:
        tables = []
        for task in plan.tasks:
            context.checkpoint()
            metrics.dispatches += 1
            key = session.key_for(plan, task) if session is not None else None
            cached = None if session is None else session.lookup(key, task)
            try:
                if cached is None:
                    fact, handle = _compare_task_native(
                        task, operation, session, metrics, detail_policy, native_budget,
                    )
                else:
                    fact, handle = cached
                    cached_names.add(task.table_name)
                    metrics.cache_hits += 1
            except (InterruptedError, TimeoutError, MemoryError):
                raise
            except (StandardComparisonError, TableAccessError, ValueError, OSError, pa.ArrowException) as exc:
                context.checkpoint()
                # Ordinary malformed table data retains the existing per-table
                # degraded result. Native adapter panic/runtime failures escape.
                coded = str(exc) if isinstance(exc, ValueError) else ""
                if coded == "DUPLICATE_EFFECTIVE_KEY":
                    diagnostic = f"DUPLICATE_EFFECTIVE_KEY:{task.table_name}"
                elif isinstance(exc, StandardComparisonError) or coded in _OLD_CODED_ERRORS:
                    diagnostic = str(exc)
                else:
                    diagnostic = type(exc).__name__
                schema_changes = ComparisonSchemaChanges()
                if (task.before_descriptor is not None and task.current_descriptor is not None
                        and task.policy is not None):
                    try:
                        schema_changes = _schema_changes_from_view(_schema_view(
                            task.before_descriptor, task.current_descriptor, task.policy,
                        ), task.policy)
                    except ValueError:
                        pass
                if (task.policy is not None and task.policy.ordered_policy is not None
                        and (isinstance(exc, StandardComparisonError)
                             or coded in _OLD_CODED_ERRORS)):
                    from gateway_backend.capabilities.comparison.ordered import _degraded_fact
                    fact = _degraded_fact(
                        task, task.before_descriptor, task.current_descriptor,
                        schema_changes, (diagnostic,),
                    )
                else:
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
                if cached is None and (fact.row_modified_count or
                    fact.row_added_count > fact.suppressed_added_count or
                    fact.row_deleted_count > fact.suppressed_deleted_count):
                    handle.prepare_risk_batches()
                if (fact.row_modified_count or
                    fact.row_added_count > fact.suppressed_added_count or
                    fact.row_deleted_count > fact.suppressed_deleted_count):
                    risk_handles[task.table_name] = handle
            if key is not None and session is not None and key in session.remaining_uses:
                consumed_keys[task.table_name] = key
                if fact.status is not ComparisonTableStatus.DEGRADED:
                    task_keys[task.table_name] = key
            tables.append(fact)
        metrics.compare_read_build_seconds += perf_counter() - started
        records_jcs_started = perf_counter()
        metadata = []
        table_handles: list[object | None] = []
        with context.memory.reserve(metadata_upper):
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
                if handle is not None and fact.table_name not in cached_names:
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
        metrics.records_jcs_seconds += perf_counter() - records_jcs_started
        result = DetailedFactsResult(plan.pair_id, facts.summary.status, facts=facts, diagnostics=facts.diagnostics)
        operation.seal()
        context.checkpoint()
        context.resources.enter_context(metadata_charge)
        return NativeComparison(result, handles, risk_handles, operation,
                                session=session, task_keys=task_keys,
                                consumed_keys=consumed_keys, metrics=metrics)
    except BaseException:
        for handle in handles.values():
            handle.close()
        operation.close()
        metadata_charge.close()
        raise
