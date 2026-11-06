"""Committed canonical cache recovery through a bounded exact-commit source.

Frozen, uncommitted Attempt files deliberately have no source-recovery entry here.
Their owner opens the exact ref directly and treats absence as a stable failure.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import ContextManager, Protocol

import pyarrow as pa
from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.artifacts.canonical_table_store import CanonicalTableIndexPort, CanonicalTableKey
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.capabilities.snapshot_materialization.canonical_store import (
    ArtifactReadHandle,
    CanonicalTableStore,
    _check_descriptor_budget,
    canonical_columns,
    canonical_table_key,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableCatalog,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
    normalize_sql_type_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.repository_arrow import canonical_repository_stream
from gateway_backend.capabilities.storage_projection.native import project_arrow_table
from gateway_backend.capabilities.table_access.contracts import NeverCancel
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView


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

    @contextmanager
    def open_committed(
        self, *, commit_id: str, bound_descriptor: SnapshotTableDescriptor, storage_view: StorageRuleView,
    ) -> Iterator[ArtifactReadHandle]:
        if not commit_id or commit_id in ("main", "HEAD") or commit_id.startswith("refs/"):
            raise ValueError("canonical recovery requires an exact immutable commit")
        _check_descriptor_budget(bound_descriptor, {
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
            except (ManifestVerificationError, ValueError, OSError, pa.ArrowException):
                handle = None
        if handle is None:
            session = self._providers(repository_id, commit_id).open_ref(RepositoryRef(repository_id, commit_id), None)
            try:
                catalog = session.get_catalog()
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
                actual = replace(bound_descriptor, columns=tuple(SnapshotColumnDescriptor(
                    name=canonicalize_identifier(column.name), display_name=column.display_name or column.name,
                    nullable=True if column.nullable is None else column.nullable,
                    scalar_type=normalize_sql_type_spelling(column.scalar_type or column.raw_type or "UNKNOWN"),
                ) for column in table.columns), primary_key_columns=tuple(canonicalize_identifier(name) for name in table.primary_key_columns))
                if actual.business_schema_digest != bound_descriptor.business_schema_digest or table.row_count != bound_descriptor.row_count:
                    raise ValueError("canonical recovery catalog differs from bound business schema/count")
                with session.open_arrow_table_reader(
                    table.table_name, max_input_bytes=self._budgets["max_input_bytes"],
                    max_rows=self._budgets["max_rows"], max_columns=self._budgets["max_columns"],
                    max_batches=self._budgets["max_batches"],
                ) as source:
                    converted = canonical_repository_stream(source, bound_descriptor, budgets=self._budgets)
                    try:
                        result = project_arrow_table({
                            "canonical_name": bound_descriptor.table_name,
                            "display_name": bound_descriptor.display_table_name,
                            "columns": canonical_columns(bound_descriptor),
                            "primary_key": list(bound_descriptor.primary_key_columns), "reader_ready": True,
                            "arrow_stream": converted,
                        }, bound_descriptor, storage_view, canonicalized_input=True,
                            cancel_probe=NeverCancel(), budgets=self._budgets, deadline_monotonic=None, pool_threads=1)
                    finally:
                        converted.close()
                    output = result["output"]
                    if output is None or output["raw_content_digest"] != key.table_digest.value:
                        raise ValueError("canonical recovery business digest mismatch")
                    projected = output["tables"][0]["arrow_stream"]
                    def protect_before_write(key: CanonicalTableKey, ref: ArtifactRef) -> None:
                        with self._uow() as uow:
                            uow.canonical_tables.register(key, ref)
                            uow.canonical_tables.bind_commit(repository_id=repository_id, commit_id=commit_id, refs=(ref,))
                    try:
                        ref = self._store.put(projected, bound_descriptor, before_write=protect_before_write)
                    finally:
                        projected.close()
                handle = self._store.open(ref, bound_descriptor)
            finally:
                session.close()
        assert handle is not None
        with handle:
            yield handle
