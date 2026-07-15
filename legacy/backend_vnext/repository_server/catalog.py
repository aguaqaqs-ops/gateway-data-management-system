from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..core.digests import DigestRef, canonical_json_bytes


@dataclass(frozen=True, slots=True)
class RepositoryTableColumn:
    name: str
    ordinal: int
    display_name: str | None = None
    scalar_type: str | None = None
    nullable: bool | None = None
    raw_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(self, "ordinal", _require_int(self.ordinal, "ordinal"))
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
        object.__setattr__(self, "scalar_type", _normalize_optional_text(self.scalar_type))
        object.__setattr__(self, "nullable", _coerce_optional_bool(self.nullable, "nullable"))
        object.__setattr__(self, "raw_type", _normalize_optional_text(self.raw_type))

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ordinal": self.ordinal,
            "display_name": self.display_name,
            "scalar_type": self.scalar_type,
            "nullable": self.nullable,
            "raw_type": self.raw_type,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryTableColumn":
        return cls(
            name=_require_payload_text(payload, "name"),
            ordinal=_require_payload_int(payload, "ordinal"),
            display_name=_optional_payload_text(payload.get("display_name")),
            scalar_type=_optional_payload_text(payload.get("scalar_type")),
            nullable=_optional_payload_bool(payload.get("nullable")),
            raw_type=_optional_payload_text(payload.get("raw_type")),
        )


@dataclass(frozen=True, slots=True)
class RepositoryTableCatalogTable:
    table_name: str
    display_table_name: str | None = None
    columns: tuple[RepositoryTableColumn, ...] = field(default_factory=tuple)
    primary_key_columns: tuple[str, ...] = field(default_factory=tuple)
    row_count: int | None = None
    repository_table_version: str | None = None
    table_root_hash: str | None = None
    schema_facts_digest: DigestRef | str | None = None
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", _require_text(self.table_name, "table_name"))
        object.__setattr__(
            self,
            "display_table_name",
            _normalize_optional_text(self.display_table_name),
        )
        normalized_columns = tuple(_coerce_column(column) for column in self.columns)
        if not normalized_columns:
            raise ValueError("columns must be non-empty")
        column_names = [column.name for column in normalized_columns]
        if len(set(column_names)) != len(column_names):
            raise ValueError("column names must be unique")
        object.__setattr__(self, "columns", normalized_columns)
        normalized_primary_key_columns = tuple(
            _require_text(column_name, "primary_key_columns item")
            for column_name in self.primary_key_columns
        )
        for column_name in normalized_primary_key_columns:
            if column_name not in column_names:
                raise ValueError("primary_key_columns must reference declared columns")
        object.__setattr__(
            self,
            "primary_key_columns",
            normalized_primary_key_columns,
        )
        object.__setattr__(self, "row_count", _coerce_optional_int(self.row_count, "row_count"))
        object.__setattr__(
            self,
            "repository_table_version",
            _normalize_optional_text(self.repository_table_version),
        )
        object.__setattr__(self, "table_root_hash", _normalize_optional_text(self.table_root_hash))
        object.__setattr__(
            self,
            "schema_facts_digest",
            _coerce_optional_digest_ref(self.schema_facts_digest, "schema_facts_digest"),
        )
        object.__setattr__(self, "diagnostics", tuple(_require_text(item, "diagnostics item") for item in self.diagnostics))

    @property
    def column_order(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> RepositoryTableColumn:
        normalized_name = _require_text(name, "name")
        for column in self.columns:
            if column.name == normalized_name:
                return column
        raise KeyError(normalized_name)

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "display_table_name": self.display_table_name,
            "columns": [column.to_payload() for column in self.columns],
            "primary_key_columns": list(self.primary_key_columns),
            "row_count": self.row_count,
            "repository_table_version": self.repository_table_version,
            "table_root_hash": self.table_root_hash,
            "schema_facts_digest": (
                self.schema_facts_digest.to_payload()
                if self.schema_facts_digest is not None
                else None
            ),
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "RepositoryTableCatalogTable":
        columns_payload = payload.get("columns")
        if not isinstance(columns_payload, Sequence):
            raise TypeError("columns must be a sequence")
        return cls(
            table_name=_require_payload_text(payload, "table_name"),
            display_table_name=_optional_payload_text(payload.get("display_table_name")),
            columns=tuple(
                RepositoryTableColumn.from_payload(_require_mapping(item, "columns item"))
                for item in columns_payload
            ),
            primary_key_columns=tuple(
                _require_text(item, "primary_key_columns item")
                for item in _require_sequence(payload.get("primary_key_columns"), "primary_key_columns")
            ),
            row_count=_optional_payload_int(payload.get("row_count")),
            repository_table_version=_optional_payload_text(payload.get("repository_table_version")),
            table_root_hash=_optional_payload_text(payload.get("table_root_hash")),
            schema_facts_digest=_coerce_optional_digest_ref(
                payload.get("schema_facts_digest"),
                "schema_facts_digest",
            ),
            diagnostics=tuple(
                _require_text(item, "diagnostics item")
                for item in _require_sequence(payload.get("diagnostics"), "diagnostics")
            ),
        )


@dataclass(frozen=True, slots=True)
class RepositoryTableCatalog:
    repository_id: str
    repository_ref: str
    resolved_commit_hash: str
    repository_server_contract_version: str
    tables: Mapping[str, RepositoryTableCatalogTable] = field(default_factory=dict)
    dolt_version: str | None = None
    catalog_digest: DigestRef | str | None = None
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _require_text(self.repository_id, "repository_id"))
        object.__setattr__(self, "repository_ref", _require_text(self.repository_ref, "repository_ref"))
        object.__setattr__(
            self,
            "resolved_commit_hash",
            _require_text(self.resolved_commit_hash, "resolved_commit_hash"),
        )
        object.__setattr__(
            self,
            "repository_server_contract_version",
            _require_text(
                self.repository_server_contract_version,
                "repository_server_contract_version",
            ),
        )
        object.__setattr__(self, "dolt_version", _normalize_optional_text(self.dolt_version))
        normalized_tables: dict[str, RepositoryTableCatalogTable] = {}
        for table_name, table in self.tables.items():
            normalized_table = _coerce_table(table)
            if _require_text(table_name, "tables key") != normalized_table.table_name:
                raise ValueError("table mapping key must match table.table_name")
            if table_name in normalized_tables:
                raise ValueError("table names must be unique")
            normalized_tables[normalized_table.table_name] = normalized_table
        object.__setattr__(self, "tables", normalized_tables)
        object.__setattr__(
            self,
            "catalog_digest",
            _coerce_optional_digest_ref(self.catalog_digest, "catalog_digest"),
        )
        object.__setattr__(self, "diagnostics", tuple(_require_text(item, "diagnostics item") for item in self.diagnostics))

    @property
    def table_count(self) -> int:
        return len(self.tables)

    def table_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.tables))

    def table(self, table_name: str) -> RepositoryTableCatalogTable:
        normalized_table_name = _require_text(table_name, "table_name")
        try:
            return self.tables[normalized_table_name]
        except KeyError as exc:
            raise KeyError(normalized_table_name) from exc

    def to_payload(self) -> dict[str, object]:
        return {
            "repository_id": self.repository_id,
            "repository_ref": self.repository_ref,
            "resolved_commit_hash": self.resolved_commit_hash,
            "repository_server_contract_version": self.repository_server_contract_version,
            "dolt_version": self.dolt_version,
            "catalog_digest": (
                self.catalog_digest.to_payload() if self.catalog_digest is not None else None
            ),
            "tables": [
                self.tables[table_name].to_payload() for table_name in self.table_names()
            ],
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryTableCatalog":
        tables_payload = payload.get("tables")
        if not isinstance(tables_payload, Sequence):
            raise TypeError("tables must be a sequence")
        tables = tuple(
            RepositoryTableCatalogTable.from_payload(_require_mapping(item, "tables item"))
            for item in tables_payload
        )
        return cls(
            repository_id=_require_payload_text(payload, "repository_id"),
            repository_ref=_require_payload_text(payload, "repository_ref"),
            resolved_commit_hash=_require_payload_text(payload, "resolved_commit_hash"),
            repository_server_contract_version=_require_payload_text(
                payload,
                "repository_server_contract_version",
            ),
            tables={table.table_name: table for table in tables},
            dolt_version=_optional_payload_text(payload.get("dolt_version")),
            catalog_digest=_coerce_optional_digest_ref(payload.get("catalog_digest"), "catalog_digest"),
            diagnostics=tuple(
                _require_text(item, "diagnostics item")
                for item in _require_sequence(payload.get("diagnostics"), "diagnostics")
            ),
        )


def catalog_digest(catalog: RepositoryTableCatalog) -> DigestRef:
    return DigestRef.from_payload(canonical_json_bytes(catalog.to_payload()))


def _coerce_column(column: object) -> RepositoryTableColumn:
    if isinstance(column, RepositoryTableColumn):
        return column
    if isinstance(column, Mapping):
        return RepositoryTableColumn.from_payload(column)
    raise TypeError("columns must contain RepositoryTableColumn values")


def _coerce_table(table: object) -> RepositoryTableCatalogTable:
    if isinstance(table, RepositoryTableCatalogTable):
        return table
    if isinstance(table, Mapping):
        return RepositoryTableCatalogTable.from_payload(table)
    raise TypeError("tables must contain RepositoryTableCatalogTable values")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _normalize_optional_text(value: object | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("optional text fields must be strings or None")
    return value.strip()


def _require_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _coerce_optional_int(value: object | None, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _optional_payload_int(value: object | None) -> int | None:
    if value is None:
        return None
    return _require_int(value, "value")


def _coerce_optional_bool(value: object | None, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool or None")
    return value


def _optional_payload_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError("value must be a bool or None")
    return value


def _coerce_optional_digest_ref(
    value: object | None,
    field_name: str,
) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return DigestRef.parse(normalized)
    raise TypeError(f"{field_name} must be a DigestRef, string, or None")


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _require_sequence(value: object | None, field_name: str) -> Sequence[object]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{field_name} must be a sequence, not text")
    if not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _require_payload_text(payload: Mapping[str, object], field_name: str) -> str:
    return _require_text(payload[field_name], field_name)


def _require_payload_int(payload: Mapping[str, object], field_name: str) -> int:
    return _require_int(payload[field_name], field_name)


def _optional_payload_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("value must be a string or None")
    return value.strip()
