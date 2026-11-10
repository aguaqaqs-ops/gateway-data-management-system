"""Committed canonical cache recovery through a bounded exact-commit source.

Frozen, uncommitted Attempt files deliberately have no source-recovery entry here.
Their owner opens the exact ref directly and treats absence as a stable failure.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager, ExitStack
from dataclasses import replace
from typing import ContextManager, Protocol

import pyarrow as pa
from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.artifacts.canonical_table_store import CanonicalTableIndexPort, CanonicalTableKey
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.store import ManifestVerificationError, ArtifactBufferStorePort
from gateway_backend.capabilities.snapshot_materialization import (
    ArtifactReadHandle, ArrowSnapshotTableReader,
    CanonicalTableStore,
    check_canonical_descriptor_budget,
    canonical_columns,
    canonical_source_descriptor,
    canonical_table_key,
    canonical_repository_stream,
    current_kernel_context, snapshot_table_from_arrow,
    operation_codec_budgets, operation_business_budgets,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableCatalog, RepositoryProviderError, MaterializationDiagnosticCode,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
    normalize_sql_type_spelling,
    SnapshotTable, CanonicalTableIdentity, SnapshotTableOrderedMetadata, BlankRowProvenance,

)
from gateway_backend.capabilities.storage_projection import project_arrow_table, compute_schema_digest
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView, OrderedPolicy
from gateway_backend.capabilities.table_access import kernel_control_scope
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext, NeverCancel


class CanonicalTableTransaction(Protocol):
    @property
    def canonical_tables(self) -> CanonicalTableIndexPort: ...


class CanonicalArrowSession(Protocol):
    def pinned_commit_hash(self) -> str: ...
    def get_catalog(self) -> RepositoryTableCatalog: ...
    def open_arrow_table_reader(
        self, table_name: str, *, max_input_bytes: int, max_rows: int,
        max_columns: int, max_batches: int,
    ) -> ContextManager[pa.RecordBatchReader]: ...
    def close(self) -> None: ...


class CanonicalArrowProvider(Protocol):
    def open_ref(
        self, repository_ref: RepositoryRef, timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> CanonicalArrowSession: ...


class CanonicalCommittedTableAccess:
    def __init__(
        self, *, store: CanonicalTableStore,
        unit_of_work_factory: Callable[[], ContextManager[CanonicalTableTransaction]],
        repository_provider_factory: Callable[[str, str], CanonicalArrowProvider],
        budgets: dict[str, int],
    ) -> None:
        self._store = store
        self._uow = unit_of_work_factory
        self._providers = repository_provider_factory
        self._budgets = dict(budgets)

    @property
    def repository_id(self) -> str:
        return self._store.repository_id

    @contextmanager
    def open_committed(
        self, *, commit_id: str, bound_descriptor: SnapshotTableDescriptor, storage_view: StorageRuleView,
        invocation: ParserInvocationContext | None = None, timeout_policy: RepositoryRefTimeoutPolicy | None = None,
    ) -> Iterator[ArtifactReadHandle]:
        caller = invocation or ParserInvocationContext(NeverCancel())
        with kernel_control_scope(caller.cancel_requested, caller.deadline_monotonic):
            with self._open_committed(commit_id=commit_id, bound_descriptor=bound_descriptor,
                storage_view=storage_view, timeout_policy=timeout_policy) as handle:
                yield handle

    @contextmanager
    def _open_committed(
        self, *, commit_id: str, bound_descriptor: SnapshotTableDescriptor, storage_view: StorageRuleView,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> Iterator[ArtifactReadHandle]:
        context = current_kernel_context()
        if context is None:
            raise ValueError("committed canonical access requires an operation kernel context")
        context.checkpoint()
        budgets = {**self._budgets, "max_live_bytes": min(self._budgets["max_live_bytes"], context.memory.available_bytes)}
        if not commit_id or commit_id in ("main", "HEAD") or commit_id.startswith("refs/"):
            raise ValueError("canonical recovery requires an exact immutable commit")
        check_canonical_descriptor_budget(bound_descriptor, {
            "max_columns": self._budgets["max_columns"],
            "max_descriptor_bytes": self._budgets["max_metadata_bytes"],
            "max_codec_peak_bytes": self._budgets["max_live_bytes"],
        })
        repository_id = self._store.repository_id
        key = canonical_table_key(repository_id, bound_descriptor)
        with self._uow() as uow:
            ref = uow.canonical_tables.lookup(key)
            if ref is not None:
                uow.canonical_tables.bind_commit(repository_id=repository_id, commit_id=commit_id, refs=(ref,))
        handle = None
        if ref is not None:
            try:
                handle = self._store.open(ref, bound_descriptor)
            except (InterruptedError, TimeoutError, MemoryError):
                raise
            except (ManifestVerificationError, ValueError, OSError, pa.ArrowException):
                context.checkpoint()
                handle = None
        if handle is None:
            session = self._providers(repository_id, commit_id).open_ref(RepositoryRef(repository_id, commit_id), timeout_policy)
            try:
                context.checkpoint()
                catalog = session.get_catalog()
                context.checkpoint()
                if session.pinned_commit_hash() != commit_id or catalog.resolved_commit_hash != commit_id or catalog.repository_id != repository_id:
                    raise ValueError("canonical recovery source is not the exact bound commit")
                table = next((item for item in catalog.tables if canonicalize_identifier(item.table_name) == bound_descriptor.table_name), None)
                if table is None:
                    raise ValueError("canonical recovery table is missing from exact commit")
                # Bound catalog metadata before copying or normalizing strings.
                metadata_bytes = 4096 + (len(table.table_name) + len(table.display_table_name or "")) * 32
                metadata_bytes += sum((len(c.name) + len(c.display_name or "") + len(c.scalar_type or "") + len(c.raw_type or "")) * 32 + 4096 for c in table.columns)
                metadata_bytes += sum(len(name) * 32 + 128 for name in table.primary_key_columns)
                if max(len(table.columns), len(table.primary_key_columns)) > self._budgets["max_columns"] or metadata_bytes > self._budgets["max_metadata_bytes"] or metadata_bytes * 8 > self._budgets["max_live_bytes"]:
                    raise MemoryError("canonical recovery catalog metadata exceeds budget")
                context.memory.retain_metadata(table, metadata_bytes * 8)
                actual = replace(bound_descriptor, columns=tuple(SnapshotColumnDescriptor(
                    name=canonicalize_identifier(column.name), display_name=column.display_name or column.name,
                    nullable=True if column.nullable is None else column.nullable,
                    scalar_type=normalize_sql_type_spelling(column.scalar_type or column.raw_type or "UNKNOWN"),
                ) for column in table.columns), primary_key_columns=tuple(canonicalize_identifier(name) for name in table.primary_key_columns))
                if actual.business_schema_digest != bound_descriptor.business_schema_digest or (table.row_count is not None and table.row_count != bound_descriptor.row_count):
                    raise ValueError("canonical recovery catalog differs from bound business schema/count")
                with ExitStack() as retained, session.open_arrow_table_reader(
                    table.table_name, max_input_bytes=self._budgets["max_input_bytes"],
                    max_rows=self._budgets["max_rows"], max_columns=self._budgets["max_columns"],
                    max_batches=self._budgets["max_batches"],
                ) as source:
                    with canonical_repository_stream(source, bound_descriptor, budgets=budgets) as converted:
                        input_arrays = converted.read_all()
                        context.checkpoint()
                        if input_arrays.num_rows != bound_descriptor.row_count:
                            raise RepositoryProviderError(MaterializationDiagnosticCode.REPOSITORY_ROW_COUNT_MISMATCH,
                                "Repository catalog row count differs from streamed row count", table=bound_descriptor.table_name)
                        # DDL-primary-key bindings resolve their canonical key from
                        # this exact commit's bound catalog, as the existing owner.
                        resolved_view = storage_view
                        if storage_view.canonical_key_policy.value in ("DDL_PRIMARY_KEY", "DDL_PRIMARY_KEY_OR_KEYLESS"):
                            resolved_view = replace(storage_view, canonical_key_columns=bound_descriptor.primary_key_columns)
                        input_stream = input_arrays.to_reader()
                        try:
                            result = project_arrow_table({
                                "canonical_name": bound_descriptor.table_name,
                                "display_name": bound_descriptor.display_table_name,
                                "columns": canonical_columns(bound_descriptor),
                                "primary_key": list(bound_descriptor.primary_key_columns), "reader_ready": True,
                                "arrow_stream": input_stream,
                            }, bound_descriptor, resolved_view, canonicalized_input=True,
                                cancel_probe=context.cancel_probe, budgets=budgets,
                                deadline_monotonic=context.deadline_monotonic, pool_threads=context.threads)
                        finally:
                            input_stream.close()
                        del input_stream, input_arrays
                        output = result["output"]
                        if output is None or output["raw_content_digest"] != key.table_digest.value:
                            raise ValueError("canonical recovery business digest mismatch")
                        with output["tables"][0]["arrow_stream"] as output_reader:
                            arrays = output_reader.read_all()
                        retained.enter_context(context.memory.retain_arrow(arrays))
                    projected = arrays.to_reader()
                    def protect_before_write(key: CanonicalTableKey, ref: ArtifactRef) -> None:
                        context.checkpoint()
                        with self._uow() as uow:
                            uow.canonical_tables.register(key, ref)
                            uow.canonical_tables.bind_commit(repository_id=repository_id, commit_id=commit_id, refs=(ref,))
                    try:
                        ref = self._store.put(projected, bound_descriptor, before_write=protect_before_write, restore_exact_commit=True)
                    finally:
                        projected.close()
                    del arrays, result, output, projected
                handle = self._store.open(ref, bound_descriptor)
            finally:
                session.close()
        assert handle is not None
        with handle:
            context.checkpoint()
            yield handle

    def lookup(self, key: CanonicalTableKey) -> ArtifactRef | None:
        if key.repository_id != self._store.repository_id:
            raise ValueError("canonical cache lookup scope differs from caller")
        with self._uow() as uow:
            return uow.canonical_tables.lookup(key)

    def register(self, key: CanonicalTableKey, ref: ArtifactRef) -> None:
        if key.repository_id != self._store.repository_id:
            raise ValueError("canonical cache registration scope differs from caller")
        with self._uow() as uow:
            uow.canonical_tables.register(key, ref)

    def describe_table(
        self, *, commit_id: str, descriptor: SnapshotTableDescriptor, identity: CanonicalTableIdentity, storage_view: StorageRuleView,
        context: ParserInvocationContext, timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> SnapshotTable:
        with kernel_control_scope(context.cancel_requested, context.deadline_monotonic) as active:
            active.checkpoint()
            if not commit_id or commit_id in ("main", "HEAD") or commit_id.startswith("refs/"):
                raise ValueError("canonical description requires an exact immutable commit")
            metadata_size = check_canonical_descriptor_budget(descriptor, {
                "max_columns": self._budgets["max_columns"],
                "max_descriptor_bytes": self._budgets["max_metadata_bytes"],
                "max_codec_peak_bytes": min(self._budgets["max_live_bytes"], active.memory.available_bytes),
            })
            with active.memory.reserve(metadata_size * 8):
                schema_digest = compute_schema_digest(columns=[{"name": column.name,
                    "sql_type": normalize_sql_type_spelling(column.scalar_type or "UNKNOWN"), "nullable": column.nullable}
                    for column in descriptor.columns], primary_key=descriptor.primary_key_columns)
                if (identity.canonical_table != descriptor.table_name or identity.row_count != descriptor.row_count
                        or identity.raw_content_digest != descriptor.raw_content_digest
                        or identity.canonical_schema_digest != schema_digest):
                    raise RepositoryProviderError(MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                        "canonical manifest schema/content binding differs from the exact catalog", table=descriptor.table_name)
            active.memory.retain_metadata(descriptor, metadata_size * 8)
            active.checkpoint()
            return SnapshotTable(descriptor=descriptor, reader=None, diagnostics=descriptor.diagnostics,
                ordered_metadata=SnapshotTableOrderedMetadata(BlankRowProvenance.CANONICAL_PSEUDO_GID)
                if storage_view.ordered_policy is OrderedPolicy.GID_NO_V1 else None)

    def load_table(
        self, *, commit_id: str, descriptor: SnapshotTableDescriptor, identity: CanonicalTableIdentity, storage_view: StorageRuleView,
        context: ParserInvocationContext, timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> SnapshotTable:
        described = self.describe_table(commit_id=commit_id, descriptor=descriptor, identity=identity,
            storage_view=storage_view, context=context, timeout_policy=timeout_policy)
        with kernel_control_scope(context.cancel_requested, context.deadline_monotonic) as active:
            manager = self._open_committed(commit_id=commit_id, bound_descriptor=descriptor,
                storage_view=storage_view, timeout_policy=timeout_policy)
            handle = manager.__enter__()
            try:
                with handle.borrow_stream() as stream:
                    arrays = stream.read_all()
                source = canonical_source_descriptor(descriptor)
                def close_handle() -> None:
                    manager.__exit__(None, None, None)
                table = snapshot_table_from_arrow(descriptor, arrays, source, execution_context=active, close=close_handle,
                    ordered=described.ordered_metadata)
                assert isinstance(table.reader, ArrowSnapshotTableReader)
                table.reader.mark_canonical_committed_read_verified()
                return table
            except BaseException:
                manager.__exit__(None, None, None)
                raise


def build_committed_table_access(
    *, store: ArtifactBufferStorePort,
    unit_of_work_factory: Callable[[], ContextManager[CanonicalTableTransaction]],
    repository_provider_factory: Callable[[str, str], CanonicalArrowProvider],
    repository_id: str,
) -> CanonicalCommittedTableAccess:
    """Compose the one C recovery owner for an operation's known repository."""
    return CanonicalCommittedTableAccess(
        store=CanonicalTableStore(store, repository_id=repository_id, budgets=operation_codec_budgets()),
        unit_of_work_factory=unit_of_work_factory, repository_provider_factory=repository_provider_factory,
        budgets=operation_business_budgets(),
    )
