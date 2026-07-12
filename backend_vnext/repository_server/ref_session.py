from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .catalog import RepositoryTableCatalog
from .dolt_backend import RepositoryBackend, RepositoryResolvedRef
from .table_cache import RepositoryServerTableCache, RepositoryServerTableCacheKey
from .table_export import RepositoryTableExportArtifact
from .table_reader import RepositoryTableReader


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    repository_id: str
    repository_ref: str


@dataclass(frozen=True, slots=True)
class RepositoryRefTimeoutPolicy:
    open_ref_timeout_ms: int | None = None
    operation_timeout_ms: int | None = None
    catalog_timeout_ms: int | None = None
    table_reader_open_timeout_ms: int | None = None
    table_read_idle_timeout_ms: int | None = None


@runtime_checkable
class RepositoryTableAccessProvider(Protocol):
    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None = None,
    ) -> "RepositoryRefSession": ...


class LocalRepositoryTableAccessProvider:
    def __init__(
        self,
        *,
        backend: RepositoryBackend,
        cache: RepositoryServerTableCache | None = None,
    ) -> None:
        self._backend = backend
        self._cache = cache

    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None = None,
    ) -> "RepositoryRefSession":
        if not isinstance(repository_ref, RepositoryRef):
            raise TypeError("repository_ref must be a RepositoryRef")
        _validate_timeout_policy(timeout_policy)
        resolved_ref = self._backend.resolve_ref(
            repository_ref.repository_id,
            repository_ref.repository_ref,
            timeout_policy,
        )
        return RepositoryRefSession(
            provider=self,
            backend=self._backend,
            cache=self._cache,
            repository_ref=repository_ref,
            resolved_ref=resolved_ref,
            timeout_policy=timeout_policy,
        )


class RepositoryRefSession:
    def __init__(
        self,
        *,
        provider: LocalRepositoryTableAccessProvider,
        backend: RepositoryBackend,
        cache: RepositoryServerTableCache | None,
        repository_ref: RepositoryRef,
        resolved_ref: RepositoryResolvedRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> None:
        self._provider = provider
        self._backend = backend
        self._cache = cache
        self._repository_ref = repository_ref
        self._resolved_ref = resolved_ref
        self._timeout_policy = timeout_policy
        self._catalog: RepositoryTableCatalog | None = None
        self._closed = False

    @property
    def repository_id(self) -> str:
        return self._repository_ref.repository_id

    @property
    def repository_ref(self) -> str:
        return self._repository_ref.repository_ref

    @property
    def resolved_commit_hash(self) -> str:
        return self._resolved_ref.resolved_commit_hash

    @property
    def dolt_version(self) -> str | None:
        return self._resolved_ref.dolt_version

    @property
    def repository_server_contract_version(self) -> str:
        return self._resolved_ref.repository_server_contract_version

    def get_catalog(self) -> RepositoryTableCatalog:
        self._ensure_open()
        if self._catalog is not None:
            return self._catalog
        cache_key = RepositoryServerTableCacheKey.for_catalog(
            repository_id=self.repository_id,
            resolved_commit_hash=self.resolved_commit_hash,
            repository_server_contract_version=self.repository_server_contract_version,
            dolt_version=self.dolt_version,
        )
        if self._cache is not None:
            cached_catalog = self._cache.get_catalog(cache_key)
            if cached_catalog is not None:
                self._catalog = cached_catalog
                return cached_catalog
        catalog = self._backend.load_catalog(self._resolved_ref)
        if self._cache is not None:
            catalog = self._cache.put_catalog(cache_key, catalog)
        self._catalog = catalog
        return catalog

    def open_table_reader(self, table_name: str) -> RepositoryTableReader:
        self._ensure_open()
        catalog = self.get_catalog()
        table = catalog.table(table_name)
        reader = self._backend.open_table_reader(
            self._resolved_ref,
            table.table_name,
            catalog=catalog,
        )
        if reader.catalog_table.table_name != table.table_name:
            raise ValueError("table reader catalog mismatch")
        return reader

    def export_table_artifact(
        self,
        table_name: str,
        export_format: str,
    ) -> RepositoryTableExportArtifact:
        self._ensure_open()
        catalog = self.get_catalog()
        table = catalog.table(table_name)
        cache_key = RepositoryServerTableCacheKey.for_export(
            repository_id=self.repository_id,
            resolved_commit_hash=self.resolved_commit_hash,
            repository_server_contract_version=self.repository_server_contract_version,
            table_name=table.table_name,
            table_root_hash=table.table_root_hash or None,
            export_format=export_format,
            dolt_version=self.dolt_version,
        )
        if self._cache is not None:
            cached_artifact = self._cache.get_export_artifact(cache_key)
            if cached_artifact is not None:
                return cached_artifact
        artifact = self._backend.export_table_artifact(
            self._resolved_ref,
            table.table_name,
            export_format,
            catalog=catalog,
        )
        if self._cache is not None:
            artifact = self._cache.put_export_artifact(cache_key, artifact)
        return artifact

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if hasattr(self._backend, "close_session"):
            self._backend.close_session(self._resolved_ref)

    def __enter__(self) -> "RepositoryRefSession":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("session is closed")


def _validate_timeout_policy(
    timeout_policy: RepositoryRefTimeoutPolicy | None,
) -> None:
    if timeout_policy is None:
        return
    if not isinstance(timeout_policy, RepositoryRefTimeoutPolicy):
        raise TypeError("timeout_policy must be a RepositoryRefTimeoutPolicy or None")
    for field_name in (
        "open_ref_timeout_ms",
        "operation_timeout_ms",
        "catalog_timeout_ms",
        "table_reader_open_timeout_ms",
        "table_read_idle_timeout_ms",
    ):
        value = getattr(timeout_policy, field_name)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{field_name} must be an integer or None")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
