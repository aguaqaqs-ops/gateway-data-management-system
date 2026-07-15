from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Protocol

from ..core.digests import DigestRef, canonical_json_bytes
from .catalog import RepositoryTableCatalog, RepositoryTableCatalogTable
from .table_export import RepositoryTableExportArtifact
from .table_reader import TupleRepositoryTableReader


@dataclass(frozen=True, slots=True)
class RepositoryResolvedRef:
    repository_id: str
    repository_ref: str
    resolved_commit_hash: str
    repository_server_contract_version: str
    dolt_version: str | None = None


class RepositoryBackend(Protocol):
    def resolve_ref(
        self,
        repository_id: str,
        repository_ref: str,
        timeout_policy: object | None = None,
    ) -> RepositoryResolvedRef: ...

    def load_catalog(self, resolved_ref: RepositoryResolvedRef) -> RepositoryTableCatalog: ...

    def open_table_reader(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> TupleRepositoryTableReader: ...

    def export_table_artifact(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        export_format: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> RepositoryTableExportArtifact: ...

    def close_session(self, resolved_ref: RepositoryResolvedRef) -> None: ...


@dataclass(slots=True)
class InMemoryRepositoryBackend:
    catalog: RepositoryTableCatalog
    rows_by_table: Mapping[str, Sequence[Sequence[object | None]]]
    artifact_root: Path | None = None
    resolve_ref_calls: int = 0
    load_catalog_calls: int = 0
    open_table_reader_calls: int = 0
    export_table_artifact_calls: int = 0
    close_session_calls: int = 0
    last_timeout_policy: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, RepositoryTableCatalog):
            raise TypeError("catalog must be a RepositoryTableCatalog")
        if not isinstance(self.rows_by_table, Mapping):
            raise TypeError("rows_by_table must be a mapping")
        normalized_rows: dict[str, tuple[tuple[object | None, ...], ...]] = {}
        for table_name, rows in self.rows_by_table.items():
            normalized_table_name = _require_text(table_name, "rows_by_table key")
            table = self.catalog.table(normalized_table_name)
            normalized_rows[normalized_table_name] = _normalize_rows(rows, table)
        self.rows_by_table = normalized_rows
        if self.artifact_root is not None:
            self.artifact_root = Path(self.artifact_root)
            self.artifact_root.mkdir(parents=True, exist_ok=True)

    def resolve_ref(
        self,
        repository_id: str,
        repository_ref: str,
        timeout_policy: object | None = None,
    ) -> RepositoryResolvedRef:
        self.resolve_ref_calls += 1
        self.last_timeout_policy = timeout_policy
        if repository_id != self.catalog.repository_id:
            raise ValueError("repository_id mismatch")
        return RepositoryResolvedRef(
            repository_id=repository_id,
            repository_ref=repository_ref,
            resolved_commit_hash=self.catalog.resolved_commit_hash,
            repository_server_contract_version=self.catalog.repository_server_contract_version,
            dolt_version=self.catalog.dolt_version or None,
        )

    def load_catalog(self, resolved_ref: RepositoryResolvedRef) -> RepositoryTableCatalog:
        self.load_catalog_calls += 1
        self._require_resolved_ref(resolved_ref)
        return self.catalog

    def open_table_reader(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> TupleRepositoryTableReader:
        self.open_table_reader_calls += 1
        self._require_resolved_ref(resolved_ref)
        effective_catalog = catalog or self.catalog
        table = effective_catalog.table(table_name)
        rows = self.rows_by_table[table.table_name]
        return TupleRepositoryTableReader(catalog_table=table, rows=rows)

    def export_table_artifact(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        export_format: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> RepositoryTableExportArtifact:
        self.export_table_artifact_calls += 1
        self._require_resolved_ref(resolved_ref)
        effective_catalog = catalog or self.catalog
        table = effective_catalog.table(table_name)
        rows = self.rows_by_table[table.table_name]
        payload = {
            "repository_id": resolved_ref.repository_id,
            "repository_ref": resolved_ref.repository_ref,
            "resolved_commit_hash": resolved_ref.resolved_commit_hash,
            "table_name": table.table_name,
            "export_format": export_format.strip().upper(),
            "table": table.to_payload(),
            "rows": rows,
        }
        artifact_bytes = canonical_json_bytes(payload)
        artifact_path = self._artifact_path(table.table_name, export_format)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        return RepositoryTableExportArtifact(
            repository_id=resolved_ref.repository_id,
            repository_ref=resolved_ref.repository_ref,
            resolved_commit_hash=resolved_ref.resolved_commit_hash,
            table_name=table.table_name,
            export_format=export_format,
            path=artifact_path,
            content_digest=DigestRef.from_bytes(artifact_bytes),
            content_size_bytes=len(artifact_bytes),
            table_root_hash=table.table_root_hash or None,
        )

    def close_session(self, resolved_ref: RepositoryResolvedRef) -> None:
        self.close_session_calls += 1
        self._require_resolved_ref(resolved_ref)

    def _artifact_path(self, table_name: str, export_format: str) -> Path:
        root = self.artifact_root or Path(tempfile.gettempdir()) / "backend_vnext_repo_server"
        return root / f"{table_name}.{export_format.strip().lower()}.json"

    def _require_resolved_ref(self, resolved_ref: RepositoryResolvedRef) -> None:
        if resolved_ref.repository_id != self.catalog.repository_id:
            raise ValueError("repository_id mismatch")
        if resolved_ref.resolved_commit_hash != self.catalog.resolved_commit_hash:
            raise ValueError("resolved_commit_hash mismatch")


def _normalize_rows(
    rows: Sequence[Sequence[object | None]],
    table: RepositoryTableCatalogTable,
) -> tuple[tuple[object | None, ...], ...]:
    normalized_rows: list[tuple[object | None, ...]] = []
    column_count = len(table.columns)
    for row in rows:
        if isinstance(row, (str, bytes, bytearray)):
            raise TypeError("rows must be sequences of row values, not text")
        if not isinstance(row, Sequence):
            raise TypeError("rows must be sequences of row values")
        row_tuple = tuple(row)
        if len(row_tuple) != column_count:
            raise ValueError("row length must match table column count")
        normalized_rows.append(row_tuple)
    return tuple(normalized_rows)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized
