from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ..core.digests import DigestRef
from ..core.diagnostics import DiagnosticRecord
from ..core.row_digests import stable_rows_digest
from ..core.scalar_encoding import normalize_snapshot_rows
from .catalog import RepositoryTableCatalogTable
from .ref_session import RepositoryRefSession


class RepositoryNativeDiffTableStatus(StrEnum):
    TABLE_UNCHANGED = "TABLE_UNCHANGED"
    TABLE_CHANGED = "TABLE_CHANGED"
    TABLE_ADDED = "TABLE_ADDED"
    TABLE_DELETED = "TABLE_DELETED"
    TABLE_UNSUPPORTED = "TABLE_UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class RepositoryNativeDiffRequest:
    include_rows: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.include_rows, bool):
            raise TypeError("include_rows must be a bool")


@dataclass(frozen=True, slots=True)
class RepositoryNativeDiffResult:
    repository_id: str
    table_name: str
    before_resolved_commit_hash: str
    current_resolved_commit_hash: str
    status: RepositoryNativeDiffTableStatus
    before_table: RepositoryTableCatalogTable | None = None
    current_table: RepositoryTableCatalogTable | None = None
    before_table_root_hash: str | None = None
    current_table_root_hash: str | None = None
    before_schema_digest: DigestRef | None = None
    current_schema_digest: DigestRef | None = None
    before_row_count: int | None = None
    current_row_count: int | None = None
    row_count_delta: int | None = None
    before_row_digest: DigestRef | None = None
    current_row_digest: DigestRef | None = None
    before_rows: tuple[tuple[object | None, ...], ...] | None = None
    current_rows: tuple[tuple[object | None, ...], ...] | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.repository_id, str) or not self.repository_id.strip():
            raise ValueError("repository_id must be a non-empty string")
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if not isinstance(self.before_resolved_commit_hash, str) or not self.before_resolved_commit_hash.strip():
            raise ValueError("before_resolved_commit_hash must be a non-empty string")
        if not isinstance(self.current_resolved_commit_hash, str) or not self.current_resolved_commit_hash.strip():
            raise ValueError("current_resolved_commit_hash must be a non-empty string")
        if not isinstance(self.status, RepositoryNativeDiffTableStatus):
            raise TypeError("status must be a RepositoryNativeDiffTableStatus")
        if self.before_table is not None and not isinstance(self.before_table, RepositoryTableCatalogTable):
            raise TypeError("before_table must be a RepositoryTableCatalogTable or None")
        if self.current_table is not None and not isinstance(self.current_table, RepositoryTableCatalogTable):
            raise TypeError("current_table must be a RepositoryTableCatalogTable or None")
        for field_name in (
            "before_table_root_hash",
            "current_table_root_hash",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in (
            "before_schema_digest",
            "current_schema_digest",
            "before_row_digest",
            "current_row_digest",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, DigestRef):
                raise TypeError(f"{field_name} must be a DigestRef or None")
        for field_name in (
            "before_row_count",
            "current_row_count",
            "row_count_delta",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                raise TypeError(f"{field_name} must be an integer or None")
        if self.before_rows is not None and not isinstance(self.before_rows, tuple):
            object.__setattr__(self, "before_rows", tuple(tuple(row) for row in self.before_rows))
        if self.current_rows is not None and not isinstance(self.current_rows, tuple):
            object.__setattr__(self, "current_rows", tuple(tuple(row) for row in self.current_rows))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")


@runtime_checkable
class RepositoryNativeDiffAccess(Protocol):
    def diff_table(
        self,
        before_session: RepositoryRefSession,
        current_session: RepositoryRefSession,
        table_name: str,
        request: RepositoryNativeDiffRequest | None = None,
    ) -> RepositoryNativeDiffResult: ...


@dataclass(slots=True)
class SessionPairRepositoryNativeDiffAccess:
    def diff_table(
        self,
        before_session: RepositoryRefSession,
        current_session: RepositoryRefSession,
        table_name: str,
        request: RepositoryNativeDiffRequest | None = None,
    ) -> RepositoryNativeDiffResult:
        if not isinstance(before_session, RepositoryRefSession):
            raise TypeError("before_session must be a RepositoryRefSession")
        if not isinstance(current_session, RepositoryRefSession):
            raise TypeError("current_session must be a RepositoryRefSession")
        if before_session.repository_id != current_session.repository_id:
            raise ValueError("repository_id must match for native diff access")
        if before_session.repository_server_contract_version != current_session.repository_server_contract_version:
            raise ValueError("repository_server_contract_version must match for native diff access")
        normalized_table_name = _require_text(table_name, "table_name")
        effective_request = request or RepositoryNativeDiffRequest()
        if not isinstance(effective_request, RepositoryNativeDiffRequest):
            raise TypeError("request must be a RepositoryNativeDiffRequest or None")

        before_catalog = before_session.get_catalog()
        current_catalog = current_session.get_catalog()
        before_table = before_catalog.tables.get(normalized_table_name)
        current_table = current_catalog.tables.get(normalized_table_name)

        if before_table is None and current_table is None:
            raise KeyError(normalized_table_name)

        before_rows, before_row_digest = _load_table_rows(
            before_session,
            normalized_table_name,
            include_rows=effective_request.include_rows,
            table=before_table,
        )
        current_rows, current_row_digest = _load_table_rows(
            current_session,
            normalized_table_name,
            include_rows=effective_request.include_rows,
            table=current_table,
        )
        before_schema_digest = _table_schema_digest(before_table) if before_table is not None else None
        current_schema_digest = _table_schema_digest(current_table) if current_table is not None else None
        before_row_count = before_table.row_count if before_table is not None else None
        current_row_count = current_table.row_count if current_table is not None else None
        row_count_delta = (
            None
            if before_row_count is None or current_row_count is None
            else current_row_count - before_row_count
        )

        if before_table is None:
            status = RepositoryNativeDiffTableStatus.TABLE_ADDED
        elif current_table is None:
            status = RepositoryNativeDiffTableStatus.TABLE_DELETED
        elif before_schema_digest != current_schema_digest or before_row_digest != current_row_digest:
            status = RepositoryNativeDiffTableStatus.TABLE_CHANGED
        else:
            status = RepositoryNativeDiffTableStatus.TABLE_UNCHANGED

        return RepositoryNativeDiffResult(
            repository_id=before_session.repository_id,
            table_name=normalized_table_name,
            before_resolved_commit_hash=before_session.resolved_commit_hash,
            current_resolved_commit_hash=current_session.resolved_commit_hash,
            status=status,
            before_table=before_table,
            current_table=current_table,
            before_table_root_hash=before_table.table_root_hash if before_table is not None else None,
            current_table_root_hash=current_table.table_root_hash if current_table is not None else None,
            before_schema_digest=before_schema_digest,
            current_schema_digest=current_schema_digest,
            before_row_count=before_row_count,
            current_row_count=current_row_count,
            row_count_delta=row_count_delta,
            before_row_digest=before_row_digest,
            current_row_digest=current_row_digest,
            before_rows=before_rows,
            current_rows=current_rows,
        )


def _load_table_rows(
    session: RepositoryRefSession,
    table_name: str,
    *,
    include_rows: bool,
    table: RepositoryTableCatalogTable | None,
) -> tuple[tuple[tuple[object | None, ...], ...] | None, DigestRef | None]:
    if table is None:
        return None, None
    reader = session.open_table_reader(table_name)
    try:
        rows = normalize_snapshot_rows(
            tuple(tuple(row) for row in reader.stream_rows()),
            table.columns,
        )
    finally:
        reader.close()
    row_digest = stable_rows_digest(rows, tuple(column.name for column in table.columns))
    if not include_rows:
        return None, row_digest
    return rows, row_digest


def _table_schema_digest(table: RepositoryTableCatalogTable) -> DigestRef:
    return DigestRef.from_payload(
        {
            "table_name": table.table_name,
            "display_table_name": table.display_table_name,
            "columns": [column.to_payload() for column in table.columns],
            "primary_key_columns": list(table.primary_key_columns),
            "repository_table_version": table.repository_table_version,
            "schema_facts_digest": (
                table.schema_facts_digest.to_payload()
                if table.schema_facts_digest is not None
                else None
            ),
        }
    )


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized
