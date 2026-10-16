"""Private application service for commit-pinned reads."""

from __future__ import annotations

import sqlite3
from collections import OrderedDict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from sys import getsizeof
from threading import Lock
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    CompiledTablePlan,
    TableCatalog,
    compile_table_plan,
)
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.versioned_read.errors import (
    ProviderUnavailableError,
    RepositoryNotVisibleError,
    TableNotFoundError,
)
from gateway_repository_service.versioned_read.ports import CancellationCallback, VersionedReadProvider

MAIN_REF = "main"
_UNAVAILABLE_MESSAGE = "versioned read provider is unavailable"
_VERSIONED_CATALOG_CACHE_ENTRIES = 8
_VERSIONED_CATALOG_CACHE_BYTES = 16 * 1024 * 1024
_VERSIONED_CATALOG_CACHE_ENTRY_OVERHEAD_BYTES = 512


@dataclass(frozen=True)
class _CatalogCacheEntry:
    catalog: tuple[TableCatalog, ...]
    size_bytes: int


class _VersionedCatalogCache:
    """Bounded process-local cache for immutable commit catalog metadata."""

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[UUID, str], _CatalogCacheEntry] = OrderedDict()
        self._size_bytes = 0
        self._lock = Lock()

    def get_or_load(
        self,
        key: tuple[UUID, str],
        loader: Callable[[], tuple[TableCatalog, ...]],
    ) -> tuple[TableCatalog, ...]:
        cached = self._get(key)
        if cached is not None:
            return cached

        catalog = loader()
        size_bytes = _catalog_cache_size(key, catalog)
        if size_bytes > _VERSIONED_CATALOG_CACHE_BYTES:
            return catalog

        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                self._entries.move_to_end(key)
                return existing.catalog
            while self._entries and (
                len(self._entries) >= _VERSIONED_CATALOG_CACHE_ENTRIES
                or self._size_bytes + size_bytes > _VERSIONED_CATALOG_CACHE_BYTES
            ):
                _evicted_key, evicted = self._entries.popitem(last=False)
                self._size_bytes -= evicted.size_bytes
            self._entries[key] = _CatalogCacheEntry(catalog, size_bytes)
            self._size_bytes += size_bytes
        return catalog

    def _get(self, key: tuple[UUID, str]) -> tuple[TableCatalog, ...] | None:
        with self._lock:
            cached = self._entries.get(key)
            if cached is None:
                return None
            self._entries.move_to_end(key)
            return cached.catalog


def _catalog_cache_size(
    key: tuple[UUID, str],
    catalog: tuple[TableCatalog, ...],
) -> int:
    size = getsizeof(key) + getsizeof(key[0]) + getsizeof(key[1])
    pending: list[object] = [catalog]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        size += getsizeof(value)
        if type(value) is tuple:
            pending.extend(value)
        elif type(value) is TableCatalog:
            fields = vars(value)
            size += getsizeof(fields)
            pending.extend(fields.values())
        elif type(value) is ColumnCatalog:
            fields = vars(value)
            size += getsizeof(fields)
            pending.extend(fields.values())
    return size + _VERSIONED_CATALOG_CACHE_ENTRY_OVERHEAD_BYTES


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
        self._catalog_cache = _VersionedCatalogCache()

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
        return provider.read_ref(MAIN_REF)

    def get_catalog(self, repository_id: UUID, commit_id: str) -> tuple[TableCatalog, ...]:
        provider = self._require_visible(repository_id)
        return self._catalog_for_commit(provider, repository_id, commit_id)

    def open_table_rows(
        self,
        repository_id: UUID,
        commit_id: str,
        exact_table_name: str,
        policy: UnknownTypePolicy,
        cancellation: CancellationCallback | None = None,
        stream_owner: object | None = None,
    ) -> tuple[CompiledTablePlan, Iterator[pa.RecordBatch]]:
        provider = self._require_visible(repository_id)
        catalog = self._catalog_for_commit(provider, repository_id, commit_id)
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
            stream_owner=stream_owner,
        )
        return plan, rows

    def _catalog_for_commit(
        self,
        provider: VersionedReadProvider,
        repository_id: UUID,
        commit_id: str,
    ) -> tuple[TableCatalog, ...]:
        return self._catalog_cache.get_or_load(
            (repository_id, commit_id),
            lambda: provider.catalog_at(commit_id),
        )
