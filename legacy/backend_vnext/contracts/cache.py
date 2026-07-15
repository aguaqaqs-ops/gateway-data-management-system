from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from ..artifacts import ArtifactRef
from ..core.digests import DigestRef
from ..core.identifiers import canonical_identifier


class CacheValidationStatus(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    CONTENT_VERIFIED = "CONTENT_VERIFIED"
    COMMIT_VALIDATED = "COMMIT_VALIDATED"


class CacheLookupPolicy(StrEnum):
    READ_ANY = "READ_ANY"
    READ_COMMIT_VALIDATED_ONLY = "READ_COMMIT_VALIDATED_ONLY"


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _required_non_negative_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = _payload_value(value)
    return normalized


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Mapping):
        return _mapping_payload(value)
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _string_tuple(values: Sequence[str] | object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{field_name} must be a sequence of strings")
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise TypeError(f"{field_name} must contain non-empty strings")
        normalized.append(canonical_identifier(item))
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheKeyPayload:
    before_snapshot_digest: DigestRef | str
    current_snapshot_digest: DigestRef | str
    comparison_contract_version: str
    projection_contract_version: str
    scalar_encoding_version: str
    table_ruleset_digest: DigestRef | str
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    comparison_options: Mapping[str, object] = field(default_factory=dict)
    table_aliases: tuple[Mapping[str, object], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "before_snapshot_digest", DigestRef.parse(str(self.before_snapshot_digest)))
        object.__setattr__(self, "current_snapshot_digest", DigestRef.parse(str(self.current_snapshot_digest)))
        object.__setattr__(self, "table_ruleset_digest", DigestRef.parse(str(self.table_ruleset_digest)))
        for field_name in (
            "comparison_contract_version",
            "projection_contract_version",
            "scalar_encoding_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "requested_tables",
            _string_tuple(self.requested_tables, field_name="requested_tables"),
        )
        if not isinstance(self.comparison_options, Mapping):
            raise TypeError("comparison_options must be a mapping")
        object.__setattr__(self, "comparison_options", _mapping_payload(self.comparison_options))
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        normalized_aliases: list[Mapping[str, object]] = []
        for alias in self.table_aliases:
            if not isinstance(alias, Mapping):
                raise TypeError("table_aliases must contain mappings")
            normalized_aliases.append(_mapping_payload(alias))
        object.__setattr__(
            self,
            "table_aliases",
            tuple(sorted(normalized_aliases, key=lambda item: repr(item))),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "before_snapshot_digest": self.before_snapshot_digest.to_payload(),
            "current_snapshot_digest": self.current_snapshot_digest.to_payload(),
            "comparison_contract_version": self.comparison_contract_version,
            "projection_contract_version": self.projection_contract_version,
            "scalar_encoding_version": self.scalar_encoding_version,
            "table_ruleset_digest": self.table_ruleset_digest.to_payload(),
            "requested_tables": list(self.requested_tables),
            "comparison_options": self.comparison_options,
            "table_aliases": [dict(alias) for alias in self.table_aliases],
        }


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheEntryPayload:
    comparison_digest: DigestRef | str
    facts_core_digest: DigestRef | str
    records_artifact_count: int
    records_table_names: tuple[str, ...] = field(default_factory=tuple)
    validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_digest", DigestRef.parse(str(self.comparison_digest)))
        object.__setattr__(self, "facts_core_digest", DigestRef.parse(str(self.facts_core_digest)))
        object.__setattr__(
            self,
            "records_artifact_count",
            _required_non_negative_int(self.records_artifact_count, field_name="records_artifact_count"),
        )
        object.__setattr__(
            self,
            "records_table_names",
            _string_tuple(self.records_table_names, field_name="records_table_names"),
        )
        object.__setattr__(self, "validation_status", CacheValidationStatus(self.validation_status))

    def to_payload(self) -> dict[str, object]:
        return {
            "comparison_digest": self.comparison_digest.to_payload(),
            "facts_core_digest": self.facts_core_digest.to_payload(),
            "records_artifact_count": self.records_artifact_count,
            "records_table_names": list(self.records_table_names),
            "validation_status": self.validation_status.value,
        }


@dataclass(frozen=True, slots=True)
class ProjectionTableCacheKeyPayload:
    source_raw_content_digest: DigestRef | str
    projection_schema_digest: DigestRef | str
    projection_contract_version: str
    scalar_encoding_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_raw_content_digest", DigestRef.parse(str(self.source_raw_content_digest)))
        object.__setattr__(self, "projection_schema_digest", DigestRef.parse(str(self.projection_schema_digest)))
        object.__setattr__(
            self,
            "projection_contract_version",
            _required_text(self.projection_contract_version, field_name="projection_contract_version"),
        )
        object.__setattr__(
            self,
            "scalar_encoding_version",
            _required_text(self.scalar_encoding_version, field_name="scalar_encoding_version"),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_raw_content_digest": self.source_raw_content_digest.to_payload(),
            "projection_schema_digest": self.projection_schema_digest.to_payload(),
            "projection_contract_version": self.projection_contract_version,
            "scalar_encoding_version": self.scalar_encoding_version,
        }


@dataclass(frozen=True, slots=True)
class ProjectionSchemaPayload:
    table_name: str
    selected_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
    before_only_columns: tuple[str, ...] = field(default_factory=tuple)
    current_only_columns: tuple[str, ...] = field(default_factory=tuple)
    effective_compare_key: tuple[str, ...] = field(default_factory=tuple)
    projection_schema_digest: DigestRef | str | None = None
    table_ruleset_version: str = ""
    projection_contract_version: str = ""
    scalar_encoding_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if not self.table_name:
            raise ValueError("table_name must resolve to a non-empty identifier")
        for field_name in (
            "selected_columns",
            "ignored_columns",
            "before_only_columns",
            "current_only_columns",
            "effective_compare_key",
        ):
            object.__setattr__(
                self,
                field_name,
                _string_tuple(getattr(self, field_name), field_name=field_name),
            )
        if self.projection_schema_digest is not None:
            object.__setattr__(self, "projection_schema_digest", DigestRef.parse(str(self.projection_schema_digest)))
        for field_name in (
            "table_ruleset_version",
            "projection_contract_version",
            "scalar_encoding_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name=field_name),
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "selected_columns": list(self.selected_columns),
            "ignored_columns": list(self.ignored_columns),
            "before_only_columns": list(self.before_only_columns),
            "current_only_columns": list(self.current_only_columns),
            "effective_compare_key": list(self.effective_compare_key),
            "projection_schema_digest": (
                self.projection_schema_digest.to_payload()
                if self.projection_schema_digest is not None
                else None
            ),
            "table_ruleset_version": self.table_ruleset_version,
            "projection_contract_version": self.projection_contract_version,
            "scalar_encoding_version": self.scalar_encoding_version,
        }


@dataclass(frozen=True, slots=True)
class ProjectionTableColumnPayload:
    name: str
    display_name: str | None = None
    scalar_type: str | None = None
    nullable: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonical_identifier(self.name))
        if not self.name:
            raise ValueError("name must resolve to a non-empty identifier")
        object.__setattr__(self, "display_name", _optional_text(self.display_name, field_name="display_name"))
        object.__setattr__(self, "scalar_type", _optional_text(self.scalar_type, field_name="scalar_type"))
        if self.nullable is not None and not isinstance(self.nullable, bool):
            raise TypeError("nullable must be a bool or None")

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "scalar_type": self.scalar_type,
            "nullable": self.nullable,
        }


@dataclass(frozen=True, slots=True)
class ProjectionTableCacheEntryManifest:
    cache_key_digest: DigestRef | str
    source_snapshot_digest: DigestRef | str
    source_raw_content_digest: DigestRef | str
    source_table_name: str
    projection_schema: ProjectionSchemaPayload
    row_count: int
    selected_columns: tuple[ProjectionTableColumnPayload, ...]
    rows_content_digest: DigestRef | str
    rows_content_size_bytes: int
    projection_logical_digest: DigestRef | str | None = None
    validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL
    rows_artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "cache_key_digest",
            "source_snapshot_digest",
            "source_raw_content_digest",
            "rows_content_digest",
        ):
            object.__setattr__(self, field_name, DigestRef.parse(str(getattr(self, field_name))))
        object.__setattr__(self, "source_table_name", canonical_identifier(self.source_table_name))
        if not self.source_table_name:
            raise ValueError("source_table_name must resolve to a non-empty identifier")
        if not isinstance(self.projection_schema, ProjectionSchemaPayload):
            raise TypeError("projection_schema must be a ProjectionSchemaPayload")
        object.__setattr__(self, "row_count", _required_non_negative_int(self.row_count, field_name="row_count"))
        object.__setattr__(
            self,
            "rows_content_size_bytes",
            _required_non_negative_int(self.rows_content_size_bytes, field_name="rows_content_size_bytes"),
        )
        if not isinstance(self.selected_columns, tuple):
            object.__setattr__(self, "selected_columns", tuple(self.selected_columns))
        normalized_columns: list[ProjectionTableColumnPayload] = []
        for column in self.selected_columns:
            if not isinstance(column, ProjectionTableColumnPayload):
                raise TypeError("selected_columns must contain ProjectionTableColumnPayload values")
            normalized_columns.append(column)
        object.__setattr__(self, "selected_columns", tuple(normalized_columns))
        if self.projection_logical_digest is not None:
            object.__setattr__(self, "projection_logical_digest", DigestRef.parse(str(self.projection_logical_digest)))
        object.__setattr__(self, "validation_status", CacheValidationStatus(self.validation_status))
        if self.rows_artifact_ref is not None and not isinstance(self.rows_artifact_ref, ArtifactRef):
            raise TypeError("rows_artifact_ref must be an ArtifactRef or None")

    def to_payload(self) -> dict[str, object]:
        return {
            "cache_key_digest": self.cache_key_digest.to_payload(),
            "source_snapshot_digest": self.source_snapshot_digest.to_payload(),
            "source_raw_content_digest": self.source_raw_content_digest.to_payload(),
            "source_table_name": self.source_table_name,
            "projection_schema": self.projection_schema.to_payload(),
            "row_count": self.row_count,
            "projection_logical_digest": (
                self.projection_logical_digest.to_payload()
                if self.projection_logical_digest is not None
                else None
            ),
            "selected_columns": [column.to_payload() for column in self.selected_columns],
            "rows_content_digest": self.rows_content_digest.to_payload(),
            "rows_content_size_bytes": self.rows_content_size_bytes,
            "validation_status": self.validation_status.value,
            "rows_artifact_ref": (
                self.rows_artifact_ref.to_payload()
                if self.rows_artifact_ref is not None
                else None
            ),
        }
