"""Operation-bound comparison over canonical Arrow and C's native records."""

from __future__ import annotations

import json
from time import perf_counter
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import ExitStack, closing
from dataclasses import dataclass, field as dataclass_field, replace
from typing import Any, Protocol

import pyarrow as pa
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.computation_cache import (
    CacheOperationOwner, ComputationCacheKey, ComputationCacheKind, ComputationCachePort,
    ComputationCacheLease,
)
from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.persistence import (
    decode_persistent_comparison, encode_persistent_comparison,
)
from gateway_backend.capabilities.comparison.contracts import (
    BlankExtension, BlankSummary, ComparisonFacts, ComparisonMode,
    ComparisonPlan, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
    ComparisonRecord, ComparisonRecordKind, DetailedFactsResult, DatasetReplacementResult,
    KeylessPolicy, OrderedExtension, OrderedStatus, OrderedSummary,
    RecordsDetailPolicy,
    ReplayGuarantee, SchemaEvolution, TableComparisonTask,
)
from gateway_backend.capabilities.comparison.cache_codec import ComparisonCacheCodec, ComparisonCachePayload
from gateway_backend.capabilities.comparison.task_input import TableTaskIdentity
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.replacement import compare_dataset_replacement
from gateway_backend.capabilities.comparison.task_input import (
    TableTaskInputV1, build_table_task_input, build_table_task_identity,
)
from gateway_backend.capabilities.comparison.row_encoding import (
    _can_table_early_exit, _ignored_values_changed,
    _schema_changes_from_view, _schema_diagnostics, _schema_record, _schema_view,
    _summary_payload, _table_digest_payload, _with_table_digest,
)
from gateway_backend.capabilities.comparison.standard import (
    STANDARD_COMPARISON_ALGORITHM_VERSION, _build_facts, _compare_task_metadata,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArrowSnapshotTableReader, canonical_comparison_input, snapshot_arrow_input,
    fresh_canonical_view_budget, current_kernel_context, TableAccessError, KernelExecutionContext,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTable,
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


def _task_key(plan: ComparisonPlan, task: TableComparisonTask, repository_id: str | None = None) -> str | None:
    from gateway_backend.capabilities.comparison.task_input import (
        TableTaskIdentity, build_table_task_identity,
    )
    repository = repository_id or (plan.current.snapshot.source_context.repository_id
                  or plan.before.snapshot.source_context.repository_id or "operation-local")
    identity = build_table_task_identity(
        plan, task, repository_id=repository, artifact_scope=task.artifact_scope.value,
    )
    return identity.task_digest.value if isinstance(identity, TableTaskIdentity) else None


class ComparisonTaskSession:
    """Known-use, operation-local native handle retention for adjacent pairs."""

    def __init__(self, plans: tuple[ComparisonPlan, ...], *,
                 persistent_cache: ComputationCachePort | None = None,
                 persistent_owner: CacheOperationOwner | None = None,
                 repository_id: str | None = None, risk_persistence: Any = None) -> None:
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison dedup requires an operation context")
        self.persistent_cache = persistent_cache
        self.persistent_owner = persistent_owner
        self.repository_id = repository_id
        self.risk_persistence = risk_persistence
        self.optional_comparison_evictor: Callable[[], None] | None = None
        self.persistent_identities: dict[tuple[str, str], TableTaskIdentity] = {}
        self.persistent_identity_charges: dict[tuple[str, str], Any] = {}
        self.persistent_ready: dict[str, tuple[ComparisonTableFact, Any | None]] = {}
        self.persistent_payloads: dict[str, ComparisonCachePayload] = {}
        self.persistent_leases: dict[str, ComputationCacheLease] = {}
        self.persistent_checked: set[str] = set()
        self.persistent_used: set[str] = set()
        self.persistent_lookup_counts: Counter[str] = Counter()
        self.persistent_restore_counts: Counter[str] = Counter()
        self.persistent_validation_counts: Counter[str] = Counter()
        self.persistent_digest_counts: Counter[str] = Counter()
        self.persistent_lookup_seconds: dict[str, float] = {}
        self.persistent_restore_seconds: dict[str, float] = {}
        # Admit each candidate key before its canonical projection allocates. Keep the
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
                        key = _task_key(plan, task, self.repository_id)
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
            self.persistent_remaining = counts.copy()
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
        self.close_persistent()
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

    @property
    def persistent_retention(self) -> bool:
        return self.persistent_cache is not None and self.persistent_owner is not None and self.repository_id is not None

    def close_persistent(self) -> None:
        for _, handle in self.persistent_ready.values():
            if handle is not None:
                handle.close()
        self.persistent_ready.clear()
        for payload in self.persistent_payloads.values():
            payload.close()
        self.persistent_payloads.clear()
        self.persistent_leases.clear()
        for charge in self.persistent_identity_charges.values():
            charge.close()
        self.persistent_identity_charges.clear()
        self.persistent_identities.clear()
        if self.risk_persistence is not None:
            self.risk_persistence.close()

    def prepare_persistent(self, plan: ComparisonPlan) -> None:
        """Validate optional hits before History decides which exact rows to read.

        Each restored table has a bounded native phase that seals before the
        next lookup or the miss compute phase reserves its available M share.
        """
        if not self.persistent_retention or plan.mode is not ComparisonMode.DETAILED:
            return
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        assert self.persistent_cache is not None and self.persistent_owner is not None
        assert self.repository_id is not None
        for task in plan.tasks:
            context.checkpoint()
            identity_key = (plan.pair_id, task.table_name)
            identity = self.persistent_identities.get(identity_key)
            if identity is None:
                try:
                    charge = context.memory.reserve(_CACHE_KEY_PROVISIONAL_BYTES)
                except MemoryError:
                    continue
                try:
                    candidate = build_table_task_identity(plan, task, repository_id=self.repository_id,
                        artifact_scope=task.artifact_scope.value)
                    if not isinstance(candidate, TableTaskIdentity):
                        charge.close()
                        continue
                    identity = candidate
                    retained = 4096 + 8 * (len(identity.task_input.semantic_jcs) + len(identity.task_input.native_policy_jcs))
                    if retained > _CACHE_KEY_PROVISIONAL_BYTES:
                        charge.close()
                        continue
                    charge.shrink_to(retained)
                    self.persistent_identities[identity_key] = identity
                    self.persistent_identity_charges[identity_key] = charge
                except MemoryError:
                    charge.close()
                    continue
                except BaseException:
                    charge.close()
                    raise
            key = identity.task_digest.value
            if key in self.persistent_checked:
                continue
            self.persistent_checked.add(key)
            lookup_started = perf_counter()
            self.persistent_lookup_counts[plan.pair_id] += 1
            lease = self.persistent_cache.lookup_and_pin(
                ComputationCacheKey(identity.repository_id, ComputationCacheKind.COMPARISON, identity.task_digest),
                owner=self.persistent_owner, checkpoint=context.checkpoint, reserve=context.memory.reserve)
            self.persistent_lookup_seconds[plan.pair_id] = self.persistent_lookup_seconds.get(plan.pair_id, 0.0) + perf_counter() - lookup_started
            if lease is None:
                continue
            restore_started = perf_counter()
            payload = None
            operation = None
            handle = None
            try:
                payload = decode_persistent_comparison(lease, identity, context)
                budget = context.memory.available_bytes // 2
                if budget <= 0:
                    raise MemoryError("optional comparison restore has no headroom")
                operation = native.begin_records_operation(native_budget_bytes=budget,
                    cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
                fact, handle = ComparisonCacheCodec.restore(payload, identity, task, operation, context)
                if handle is not None:
                    metadata_json = json.dumps(_table_digest_payload(fact), separators=(",", ":"))
                    fact = replace(fact, table_fact_digest=DigestRef(
                        handle.table_fact_digest(metadata_json, _MAX_JCS_ROW_BYTES)))
                    self.persistent_digest_counts[plan.pair_id] += 1
                operation.seal()
                self.persistent_ready[key] = (fact, handle)
                self.persistent_payloads[key] = payload
                self.persistent_leases[key] = lease
                self.persistent_restore_counts[plan.pair_id] += 1
                if handle is not None:
                    self.persistent_validation_counts[plan.pair_id] += 1
            except (InterruptedError, TimeoutError):
                if handle is not None:
                    handle.close()
                if payload is not None:
                    payload.close()
                lease.close()
                raise
            except MemoryError:
                if handle is not None:
                    handle.close()
                if payload is not None:
                    payload.close()
                lease.close()
                context.checkpoint()
            except (ValueError, TypeError, KeyError, RecursionError, OSError, pa.ArrowException):
                if handle is not None:
                    handle.close()
                # The payload owns this read lease. Discard the exact version
                # while it is still open, then release its decoded resources.
                try:
                    lease.discard()
                finally:
                    if payload is not None:
                        payload.close()
                    lease.close()
                context.checkpoint()
            except BaseException:
                if handle is not None:
                    handle.close()
                if payload is not None:
                    payload.close()
                lease.close()
                raise
            finally:
                self.persistent_restore_seconds[plan.pair_id] = self.persistent_restore_seconds.get(plan.pair_id, 0.0) + perf_counter() - restore_started
                if operation is not None:
                    operation.close()

    def persistent_lookup(self, plan: ComparisonPlan, task: TableComparisonTask) -> tuple[ComparisonTableFact, Any | None] | None:
        identity = self.persistent_identities.get((plan.pair_id, task.table_name))
        if identity is None:
            return None
        item = self.persistent_ready.get(identity.task_digest.value)
        if item is None:
            return None
        fact, handle = item
        return replace(fact, table_name=task.table_name,
            before_descriptor=task.before_descriptor, current_descriptor=task.current_descriptor), handle

    def retire_persistent(self, comparison: NativeComparison) -> None:
        """Release payloads after their real last pair Arrow consumer closes."""
        for identity in comparison.cache_identities.values():
            key = identity.task_digest.value
            if key not in self.persistent_remaining:
                # A key that could not be admitted during declaration has no
                # proven final consumer count; the assembly owner closes it.
                continue
            self.persistent_remaining[key] -= 1
            if self.persistent_remaining[key] > 0:
                continue
            item = self.persistent_ready.pop(key, None)
            if item is not None and item[1] is not None:
                item[1].close()
            payload = self.persistent_payloads.pop(key, None)
            if payload is not None:
                payload.close()
            self.persistent_leases.pop(key, None)
            for risk_key in tuple(self.risk_candidates):
                if risk_key[0] == key:
                    _, charges = self.risk_candidates.pop(risk_key)
                    charges.close()

    def commit_persistent(self, comparison: NativeComparison) -> None:
        if not self.persistent_retention:
            return
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        assert self.persistent_cache is not None and self.persistent_owner is not None
        for name, identity in comparison.cache_identities.items():
            key = identity.task_digest.value
            lease = self.persistent_leases.get(key)
            if lease is not None:
                lease.mark_used()
                self.persistent_used.add(key)
                continue
            try:
                payload = comparison.encode_cache_candidate(name, identity, context)
            except (MemoryError, ValueError):
                handle = comparison.handles.get(name)
                if handle is not None:
                    handle.discard_cache_views()
                if comparison.operation is not None:
                    comparison.operation.seal()
                context.checkpoint()
                continue
            try:
                entry, blobs = encode_persistent_comparison(payload)
                self.persistent_cache.store(entry, blobs, owner=self.persistent_owner,
                    checkpoint=context.checkpoint, reserve=context.memory.reserve)
            except (MemoryError, ValueError):
                context.checkpoint()
            finally:
                payload.close()
                handle = comparison.handles.get(name)
                if handle is not None:
                    handle.discard_cache_views()
                if comparison.operation is not None:
                    comparison.operation.seal()
        if self.risk_persistence is not None:
            self.risk_persistence.commit(self.pending_risk)

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
        if item is not None:
            return item[0]
        return None if self.risk_persistence is None else self.risk_persistence.lookup(risk_key)

    def risk_store(
        self, task_key: str, risk_key: str,
        events: tuple[object, ...], charges: ExitStack,
    ) -> bool:
        if self.remaining_uses.get(task_key, 0) <= 1 and not self.persistent_retention:
            return False
        self.pending_risk[(task_key, risk_key)] = (events, charges)
        return True

    def risk_evict(self, task_key: str, risk_key: str) -> None:
        item = self.risk_candidates.pop((task_key, risk_key), None)
        if item is not None:
            _, charges = item
            charges.close()

    def risk_evict_for_output(self) -> None:
        """Release optional candidate views before necessary output work."""
        if self.optional_comparison_evictor is not None:
            self.optional_comparison_evictor()
        for _, charges in self.risk_candidates.values():
            charges.close()
        self.risk_candidates.clear()
        self.abort_pending_risk()
        if self.risk_persistence is not None:
            self.risk_persistence.close()

    def risk_retire_last_uses(self, task_keys: Mapping[str, str]) -> None:
        """Retire replay events after their final table Risk consumer returns."""
        active_keys = frozenset(task_keys.values())
        for cache_key in tuple(self.risk_candidates):
            if (cache_key[0] in active_keys
                    and self.remaining_uses.get(cache_key[0]) == 1):
                _, charges = self.risk_candidates.pop(cache_key)
                charges.close()

    def evict_local(self) -> None:
        """Drop optional adjacent-pair retention without invalidating admitted hits."""
        retained = tuple(handle for _, handle in self.persistent_ready.values())
        for _, handle in self.cached.values():
            if handle is not None and not any(handle is value for value in retained):
                handle.close()
        self.cached.clear()
        for charge in self.key_charges.values():
            charge.close()
        self.key_charges.clear()
        self.remaining_uses.clear()
        self.declared_keys.clear()
        self.risk_evict_for_output()

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
            self.evict_local()

    def key_for(self, plan: ComparisonPlan, task: TableComparisonTask) -> str | None:
        declared = self.declared_keys.get((plan.pair_id, task.table_name))
        if declared is None or declared not in self.remaining_uses:
            return None
        context = current_kernel_context()
        if context is None:
            raise RuntimeError("comparison context was lost")
        try:
            with context.memory.reserve(_CACHE_KEY_PROVISIONAL_BYTES):
                actual = _task_key(plan, task, self.repository_id)
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
            fact, handle = item
            return replace(fact, table_name=task.table_name,
                before_descriptor=task.before_descriptor, current_descriptor=task.current_descriptor), handle
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
    cache_restores: int = 0
    cache_records_validations: int = 0
    persistent_cache_lookups: int = 0
    cache_lookup_seconds: float = 0.0
    cache_restore_seconds: float = 0.0
    ordered_single_side_calls: int = 0
    digest_rebinds: int = 0


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
    cache_identities: dict[str, TableTaskIdentity] = dataclass_field(default_factory=dict)

    def encode_cache_candidate(
        self, table_name: str, identity: TableTaskIdentity, context: KernelExecutionContext,
    ) -> ComparisonCachePayload:
        """Export this completed table through the single neutral codec owner.

        The caller publishes required pair output first and owns optional
        retention failures and the returned payload's closing lifetime.
        """
        context.require_active()
        facts = self.result.facts
        if facts is None:
            raise ValueError("cache candidate requires completed comparison facts")
        fact = next((item for item in facts.tables if item.table_name == table_name), None)
        if fact is None:
            raise ValueError("cache candidate table is absent from this comparison")
        return ComparisonCacheCodec.encode(self.handles.get(table_name), identity, fact, context)

    def discard_optional_views(self) -> None:
        # A restored handle's backing remains necessary until its real Arrow
        # consumers close. Only cold retention views are optional here.
        retained = (() if self.session is None else tuple(
            item[1] for item in self.session.persistent_ready.values()))
        for handle in self.handles.values():
            if not any(handle is value for value in retained):
                handle.discard_cache_views()
        if self.operation is not None:
            self.operation.seal()

    def commit_cache(self) -> None:
        if self.committed:
            return
        if self.session is not None:
            self.session.commit_persistent(self)
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
        if self.session is not None:
            self.session.optional_comparison_evictor = None
        if not self.committed and self.session is not None:
            self.session.abort_pending_risk()
        persistent_handles = (() if self.session is None else tuple(
            handle for _, handle in self.session.persistent_ready.values() if handle is not None))
        for handle in self.handles.values():
            if not any(handle is retained for retained in persistent_handles):
                handle.close()
        self.handles.clear()
        self.risk_handles.clear()
        if self.committed and self.session is not None:
            self.session.retire_persistent(self)
            self.cache_identities.clear()
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
    return canonical_comparison_input(table)


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






def _compare_task_native(
    task: TableComparisonTask, operation: object,
    session: ComparisonTaskSession | None,
    metrics: ComparisonRunMetrics, detail_policy: RecordsDetailPolicy,
    native_budget_bytes: int, plan: ComparisonPlan,
) -> tuple[ComparisonTableFact, Any | None]:
    policy = task.policy
    assert policy is not None
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None or current is None:
        return _compare_task_metadata(task), None
    schema = _schema_view(before, current, policy)
    changes = _schema_changes_from_view(schema, policy)
    def native_input() -> TableTaskInputV1:
        return build_table_task_input(plan, task, include_identity=False)
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        if changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED:
            return _compare_task_metadata(task), None
        probe_policy = json.loads(native_input().native_policy())
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
            return _ordered_unchanged_native(task, operation, schema, session, metrics, native_input()), None
        handle = _compare_native(operation, task, kind="ordered",
                                 policy=json.loads(native_input().native_policy()), detail_policy=detail_policy,
                                 native_budget_bytes=native_budget_bytes,
                                 session=session,
                                 metrics=metrics)
        return native.table_fact(task, handle, schema), handle
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
                             policy=json.loads(native_input().native_policy()), detail_policy=detail_policy,
                             native_budget_bytes=native_budget_bytes,
                             session=session,
                             metrics=metrics)
    return native.table_fact(task, handle, schema), handle


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
    metrics: ComparisonRunMetrics, task_input: TableTaskInputV1,
) -> ComparisonTableFact:
    # The unchanged fast path must read only the current side and never run LIS.
    policy = json.loads(task_input.native_policy())
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
        metrics.ordered_single_side_calls += 1
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
    retain_cache_candidates: bool = False,
) -> NativeComparison:
    metrics = ComparisonRunMetrics()
    try:
        return _compare_plan_native_once(plan, session=session, metrics=metrics, retain_cache_candidates=retain_cache_candidates)
    except MemoryError:
        # Optional retained keys/handles may have consumed the room needed
        # by a real compare. Drop them, then try that same immutable plan once
        # with no reuse. A second M rejection is the business resource limit.
        if session is None or (not session.key_charges and not session.cached):
            raise
        retry_session = None
        if session.persistent_retention:
            session.evict_local()
            retry_session = session
        else:
            session.close()
        context = current_kernel_context()
        if context is not None:
            context.checkpoint()
        return _compare_plan_native_once(plan, session=retry_session, metrics=metrics, retain_cache_candidates=retain_cache_candidates)


def _compare_plan_native_once(
    plan: ComparisonPlan, *, session: ComparisonTaskSession | None = None,
    metrics: ComparisonRunMetrics, retain_cache_candidates: bool = False,
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
        session.prepare_persistent(plan)
        metrics.cache_restores = session.persistent_restore_counts[plan.pair_id]
        metrics.cache_records_validations = session.persistent_validation_counts[plan.pair_id]
        metrics.digest_rebinds = session.persistent_digest_counts[plan.pair_id]
        metrics.persistent_cache_lookups = session.persistent_lookup_counts[plan.pair_id]
        metrics.cache_lookup_seconds = session.persistent_lookup_seconds.get(plan.pair_id, 0.0)
        metrics.cache_restore_seconds = session.persistent_restore_seconds.get(plan.pair_id, 0.0)
        retain_cache_candidates = retain_cache_candidates or session.persistent_retention
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
            sum(fresh_canonical_view_budget(table))
            for task in plan.tasks
            if session is None or session.persistent_lookup(plan, task) is None
            for table in _task_arrow_inputs(task)
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
            persistent = None if session is None else session.persistent_lookup(plan, task)
            cached = persistent if persistent is not None else (None if session is None else session.lookup(key, task))
            try:
                if cached is None:
                    fact, handle = _compare_task_native(
                        task, operation, session, metrics, detail_policy, native_budget,
                        plan,
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
            if session is not None and (plan.pair_id, task.table_name) in session.persistent_identities:
                identity = session.persistent_identities[(plan.pair_id, task.table_name)]
                task_keys[task.table_name] = identity.task_digest.value
            tables.append(fact)
        metrics.compare_read_build_seconds += perf_counter() - started
        records_jcs_started = perf_counter()
        metadata = []
        table_handles: list[object | None] = []
        with context.memory.reserve(metadata_upper):
            for fact in tables:
                handle = handles.get(fact.table_name)
                if handle is None:
                    metrics.digest_rebinds += 1
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
                    metrics.digest_rebinds += 1
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
        if retain_cache_candidates:
            for handle in handles.values():
                if handle.is_sealed():
                    continue
                try:
                    handle.prepare_cache_views(_MAX_JCS_ROW_BYTES)
                except MemoryError:
                    handle.discard_cache_views()
        operation.seal()
        context.checkpoint()
        context.resources.enter_context(metadata_charge)
        return NativeComparison(result, handles, risk_handles, operation,
                                session=session, task_keys=task_keys,
                                consumed_keys=consumed_keys, metrics=metrics,
                                cache_identities={} if session is None else {
                                    task.table_name: session.persistent_identities[(plan.pair_id, task.table_name)]
                                    for task in plan.tasks
                                    if (plan.pair_id, task.table_name) in session.persistent_identities
                                })
    except BaseException:
        persistent_handles = (() if session is None else tuple(
            item[1] for item in session.persistent_ready.values()))
        for handle in handles.values():
            if not any(handle is retained for retained in persistent_handles):
                handle.close()
        operation.close()
        metadata_charge.close()
        raise


def comparison_row_demands(plan: ComparisonPlan, session: ComparisonTaskSession | None = None) -> tuple[SnapshotTable, ...]:
    """Actual remaining readers; no parallel copy of Comparison equality rules."""
    if session is not None:
        session.prepare_persistent(plan)
    return tuple(table for task in plan.tasks
        if session is None or session.persistent_lookup(plan, task) is None
        for table in _task_arrow_inputs(task))
