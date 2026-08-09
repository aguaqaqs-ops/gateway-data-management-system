"""Private application service for commit-pinned reads."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import CompiledTablePlan, TableCatalog, compile_table_plan
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.versioned_read.errors import (
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    RepositoryNotVisibleError,
    TableNotFoundError,
)
from gateway_repository_service.versioned_read.ports import CancellationCallback, VersionedReadProvider

MAIN_REF = "main"
_UNAVAILABLE_MESSAGE = "versioned read provider is unavailable"


class VersionedReadApplication:
    """Commit-pinned read orchestration without HTTP or import semantics."""

    def __init__(
        self,
        mutation_store: MutationStore,
        layout: DurableLayout,
        provider_factory: Callable[[UUID], VersionedReadProvider],
    ) -> None:
        self._mutation_store = mutation_store
        self._layout = layout
        self._provider_factory = provider_factory

    def _require_visible(self, repository_id: UUID) -> VersionedReadProvider:
        try:
            if not is_repository_visible(self._mutation_store, self._layout, repository_id):
                raise RepositoryNotVisibleError("repository is not visible")
            return self._provider_factory(repository_id)
        except RepositoryNotVisibleError:
            raise
        except (sqlite3.Error, OSError):
            raise ProviderUnavailableError(_UNAVAILABLE_MESSAGE) from None

    def resolve_main(self, repository_id: UUID) -> str:
        provider = self._require_visible(repository_id)
        try:
            return provider.read_ref(MAIN_REF)
        except MainRefNotFoundError:
            raise

    def get_catalog(self, repository_id: UUID, commit_id: str) -> tuple[TableCatalog, ...]:
        provider = self._require_visible(repository_id)
        return provider.catalog_at(commit_id)

    def open_table_rows(
        self,
        repository_id: UUID,
        commit_id: str,
        exact_table_name: str,
        policy: UnknownTypePolicy,
        cancellation: CancellationCallback | None = None,
    ) -> tuple[CompiledTablePlan, Iterator[pa.RecordBatch]]:
        provider = self._require_visible(repository_id)
        if not provider.commit_exists(commit_id):
            raise CommitNotFoundError("versioned read commit was not found")
        catalog = provider.catalog_at(commit_id, existence_verified=True)
        matched = next((table for table in catalog if table.name == exact_table_name), None)
        if matched is None:
            raise TableNotFoundError("versioned read table was not found")
        plan = compile_table_plan(matched, policy)
        rows = provider.stream_table_at(
            commit_id,
            matched,
            policy,
            table_plan=plan,
            cancellation=cancellation,
            existence_verified=True,
        )
        return plan, rows
