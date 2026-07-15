from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import shutil
from typing import Protocol, runtime_checkable

import polars as pl

from ..artifacts.manifest import ArtifactManifest
from ..capabilities.comparison.models import ProjectionSchema, ProjectionTable
from ..capabilities.comparison.projection import ProjectionRowsReader
from ..capabilities.snapshot_materialization.models import SnapshotTableColumn
from ..contracts.cache import (
    CacheValidationStatus,
    ProjectionSchemaPayload,
    ProjectionTableCacheEntryManifest,
    ProjectionTableCacheKeyPayload,
    ProjectionTableColumnPayload,
)
from ..core.digests import DigestRef, canonical_json_bytes
from ..core.identifiers import canonical_identifier
from ..core.scalar_encoding import normalize_parquet_rows


PROJECTION_TABLE_CACHE_ARTIFACT_KIND = "projection-table-cache"
PROJECTION_TABLE_CACHE_CONTRACT_VERSION = "backend-vnext/projection-table-cache/v1"
PROJECTION_TABLE_CACHE_NAMESPACE = "projection-table"
PROJECTION_TABLE_CACHE_MANIFEST_FILE_NAME = "manifest.json"
PROJECTION_TABLE_CACHE_ROWS_FILE_NAME = "rows.parquet"
PROJECTION_TABLE_CACHE_DEFAULT_TTL_DAYS = 180


@dataclass(frozen=True, slots=True)
class ProjectionTableCacheKey:
    source_raw_content_digest: DigestRef | str
    projection_schema_digest: DigestRef | str
    projection_contract_version: str
    scalar_encoding_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_raw_content_digest",
            DigestRef.parse(str(self.source_raw_content_digest)),
        )
        object.__setattr__(
            self,
            "projection_schema_digest",
            DigestRef.parse(str(self.projection_schema_digest)),
        )
        for field_name in ("projection_contract_version", "scalar_encoding_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

    @classmethod
    def from_projection_table(cls, table: ProjectionTable) -> "ProjectionTableCacheKey":
        if table.source_raw_content_digest is None:
            raise ValueError("projection table must include source_raw_content_digest to build a cache key")
        return cls(
            source_raw_content_digest=table.source_raw_content_digest,
            projection_schema_digest=table.projection_schema.projection_schema_digest,
            projection_contract_version=table.projection_schema.projection_contract_version,
            scalar_encoding_version=table.projection_schema.scalar_encoding_version,
        )

    def payload_for_digest(self) -> dict[str, object]:
        return self.to_contract_payload().to_payload()

    def to_contract_payload(self) -> ProjectionTableCacheKeyPayload:
        return ProjectionTableCacheKeyPayload(
            source_raw_content_digest=self.source_raw_content_digest,
            projection_schema_digest=self.projection_schema_digest,
            projection_contract_version=self.projection_contract_version,
            scalar_encoding_version=self.scalar_encoding_version,
        )

    @property
    def cache_key_digest(self) -> DigestRef:
        return DigestRef.from_payload(self.payload_for_digest())


@dataclass(frozen=True, slots=True)
class ProjectionTableCacheLookup:
    value: ProjectionTable | None
    cache_key_digest: DigestRef | str
    validation_status: CacheValidationStatus | str | None = None
    miss_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cache_key_digest", DigestRef.parse(str(self.cache_key_digest)))
        if self.validation_status is not None:
            object.__setattr__(self, "validation_status", CacheValidationStatus(self.validation_status))
        if self.miss_reason is not None and (
            not isinstance(self.miss_reason, str) or not self.miss_reason.strip()
        ):
            raise ValueError("miss_reason must be a non-empty string or None")

    @property
    def hit(self) -> bool:
        return self.value is not None


@runtime_checkable
class ProjectionTableCache(Protocol):
    @property
    def enabled(self) -> bool: ...

    def lookup(
        self,
        *,
        key: ProjectionTableCacheKey,
        now: datetime | None = None,
    ) -> ProjectionTableCacheLookup: ...

    def write(
        self,
        *,
        key: ProjectionTableCacheKey,
        value: ProjectionTable,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        now: datetime | None = None,
    ) -> ProjectionTable: ...

    def clear(self) -> None: ...


class DisabledProjectionTableCache:
    @property
    def enabled(self) -> bool:
        return False

    def lookup(
        self,
        *,
        key: ProjectionTableCacheKey,
        now: datetime | None = None,
    ) -> ProjectionTableCacheLookup:
        del now
        return ProjectionTableCacheLookup(
            value=None,
            cache_key_digest=key.cache_key_digest,
            miss_reason="DISABLED",
        )

    def write(
        self,
        *,
        key: ProjectionTableCacheKey,
        value: ProjectionTable,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        now: datetime | None = None,
    ) -> ProjectionTable:
        del key, validation_status, now
        return value

    def clear(self) -> None:
        return None


class InMemoryProjectionTableCache:
    def __init__(self) -> None:
        self._entries: dict[ProjectionTableCacheKey, ProjectionTable] = {}
        self._statuses: dict[ProjectionTableCacheKey, CacheValidationStatus] = {}

    @property
    def enabled(self) -> bool:
        return True

    def lookup(
        self,
        *,
        key: ProjectionTableCacheKey,
        now: datetime | None = None,
    ) -> ProjectionTableCacheLookup:
        del now
        value = self._entries.get(key)
        if value is None:
            return ProjectionTableCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="REGISTRY_MISS",
            )
        return ProjectionTableCacheLookup(
            value=value,
            cache_key_digest=key.cache_key_digest,
            validation_status=self._statuses.get(key, CacheValidationStatus.PROVISIONAL),
        )

    def write(
        self,
        *,
        key: ProjectionTableCacheKey,
        value: ProjectionTable,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        now: datetime | None = None,
    ) -> ProjectionTable:
        del now
        self._entries[key] = value
        self._statuses[key] = CacheValidationStatus(validation_status)
        return value

    def clear(self) -> None:
        self._entries.clear()
        self._statuses.clear()


class FilesystemProjectionTableCache:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return True

    @property
    def root(self) -> Path:
        return self._root

    def lookup(
        self,
        *,
        key: ProjectionTableCacheKey,
        now: datetime | None = None,
    ) -> ProjectionTableCacheLookup:
        del now
        manifest_path = self._manifest_path(key)
        rows_path = self._rows_path(key)
        if not manifest_path.is_file() or not rows_path.is_file():
            return ProjectionTableCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="MISSING_OBJECT",
            )
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest_payload, Mapping):
                raise TypeError("projection table manifest payload must be a mapping")
            manifest = ArtifactManifest.from_payload(manifest_payload)
            if manifest.artifact_kind != PROJECTION_TABLE_CACHE_ARTIFACT_KIND:
                raise ValueError("projection table artifact kind mismatch")
            if manifest.artifact_contract_version != PROJECTION_TABLE_CACHE_CONTRACT_VERSION:
                return ProjectionTableCacheLookup(
                    value=None,
                    cache_key_digest=key.cache_key_digest,
                    miss_reason="VERSION_MISMATCH",
                )
            metadata = manifest.metadata
            cached_key_digest = _required_digest(metadata, "cache_key_digest")
            if cached_key_digest != key.cache_key_digest:
                raise ValueError("cached key digest mismatch")
            entry_manifest = _projection_table_entry_manifest_from_payload(metadata)
            if entry_manifest.rows_content_digest != manifest.content_digest:
                raise ValueError("projection table rows digest mismatch")
            if entry_manifest.rows_content_size_bytes != manifest.content_size_bytes:
                raise ValueError("projection table rows size mismatch")
            projection_table = _projection_table_from_cache(
                manifest=manifest,
                rows_path=rows_path,
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return ProjectionTableCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="MANIFEST_INVALID",
            )
        return ProjectionTableCacheLookup(
            value=projection_table,
            cache_key_digest=key.cache_key_digest,
            validation_status=entry_manifest.validation_status,
        )

    def write(
        self,
        *,
        key: ProjectionTableCacheKey,
        value: ProjectionTable,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        now: datetime | None = None,
    ) -> ProjectionTable:
        del now
        validation_status = CacheValidationStatus(validation_status)
        self._validate_projection_table_matches_key(key, value)
        entry_dir = self._entry_dir(key)
        entry_dir.mkdir(parents=True, exist_ok=True)

        rows_path = self._rows_path(key)
        rows_bytes = _write_rows_parquet(
            rows_path=rows_path,
            rows_reader=value.reader,
        )
        manifest = ArtifactManifest(
            artifact_kind=PROJECTION_TABLE_CACHE_ARTIFACT_KIND,
            artifact_contract_version=PROJECTION_TABLE_CACHE_CONTRACT_VERSION,
            content_digest=DigestRef.from_bytes(rows_bytes),
            content_size_bytes=len(rows_bytes),
            metadata=_projection_table_metadata(
                key=key,
                value=value,
                rows_content_digest=DigestRef.from_bytes(rows_bytes),
                rows_content_size_bytes=len(rows_bytes),
                validation_status=validation_status,
            ),
            diagnostics=value.diagnostics,
        )
        manifest_path = self._manifest_path(key)
        manifest_path.write_bytes(canonical_json_bytes(manifest.to_payload()))
        return value

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
            self._root.mkdir(parents=True, exist_ok=True)

    def cleanup_expired(
        self,
        *,
        max_age_days: int = PROJECTION_TABLE_CACHE_DEFAULT_TTL_DAYS,
        now: datetime | None = None,
    ) -> int:
        if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 0:
            raise ValueError("max_age_days must be a non-negative integer")
        reference_time = now or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("now must be timezone-aware when provided")
        if not self._root.exists():
            return 0
        removed = 0
        for entry_dir in self._root.iterdir():
            if not entry_dir.is_dir():
                continue
            mtime = datetime.fromtimestamp(entry_dir.stat().st_mtime, tz=timezone.utc)
            if reference_time - mtime > timedelta(days=max_age_days):
                shutil.rmtree(entry_dir)
                removed += 1
        return removed

    def _entry_dir(self, key: ProjectionTableCacheKey) -> Path:
        return self._root / key.cache_key_digest.hex_digest

    def _manifest_path(self, key: ProjectionTableCacheKey) -> Path:
        return self._entry_dir(key) / PROJECTION_TABLE_CACHE_MANIFEST_FILE_NAME

    def _rows_path(self, key: ProjectionTableCacheKey) -> Path:
        return self._entry_dir(key) / PROJECTION_TABLE_CACHE_ROWS_FILE_NAME

    def _validate_projection_table_matches_key(
        self,
        key: ProjectionTableCacheKey,
        value: ProjectionTable,
    ) -> None:
        if value.source_raw_content_digest is None:
            raise ValueError("projection table must include source_raw_content_digest")
        if key.source_raw_content_digest != value.source_raw_content_digest:
            raise ValueError("projection table source_raw_content_digest mismatch")
        if key.projection_schema_digest != value.projection_schema.projection_schema_digest:
            raise ValueError("projection table projection_schema_digest mismatch")
        if key.projection_contract_version != value.projection_schema.projection_contract_version:
            raise ValueError("projection table projection_contract_version mismatch")
        if key.scalar_encoding_version != value.projection_schema.scalar_encoding_version:
            raise ValueError("projection table scalar_encoding_version mismatch")
        if not isinstance(value.reader, ProjectionRowsReader):
            raise TypeError("projection table reader must be a ProjectionRowsReader")


def _projection_table_from_cache(
    *,
    manifest: ArtifactManifest,
    rows_path: Path,
) -> ProjectionTable:
    metadata = manifest.metadata
    projection_schema = _projection_schema_from_payload(_required_mapping(metadata, "projection_schema"))
    row_count = _required_int(metadata, "row_count")
    columns = tuple(
        _snapshot_table_column_from_payload(column_payload)
        for column_payload in _required_sequence(metadata, "selected_columns")
    )
    if tuple(column.name for column in columns) != tuple(projection_schema.selected_columns):
        raise ValueError("projection table selected columns mismatch")
    rows_bytes = rows_path.read_bytes()
    if DigestRef.from_bytes(rows_bytes) != manifest.content_digest:
        raise ValueError("projection table content digest mismatch")
    if len(rows_bytes) != manifest.content_size_bytes:
        raise ValueError("projection table content size mismatch")
    rows_frame = pl.read_parquet(rows_path)
    rows = _frame_to_rows(rows_frame, columns)
    if len(rows) != row_count:
        raise ValueError("projection table row count mismatch")
    reader = ProjectionRowsReader(
        projection_schema=projection_schema,
        columns=columns,
        rows=rows,
    )
    manifest_digest = DigestRef.from_payload(manifest.to_payload())
    source_snapshot_digest = _required_digest(metadata, "source_snapshot_digest")
    source_raw_content_digest = _required_digest(metadata, "source_raw_content_digest")
    source_table_name = canonical_identifier(_required_text(metadata, "source_table_name"))
    if source_table_name != projection_schema.table_name:
        raise ValueError("projection table source table mismatch")
    projection_logical_digest = _optional_digest(metadata.get("projection_logical_digest"))
    artifact_ref = manifest.to_ref(manifest_digest)
    return ProjectionTable(
        source_snapshot_digest=source_snapshot_digest,
        source_raw_content_digest=source_raw_content_digest,
        source_table_name=source_table_name,
        projection_schema=projection_schema,
        row_count=row_count,
        projection_logical_digest=projection_logical_digest,
        reader=reader,
        artifact_ref=artifact_ref,
    )


def _projection_table_metadata(
    *,
    key: ProjectionTableCacheKey,
    value: ProjectionTable,
    rows_content_digest: DigestRef | str,
    rows_content_size_bytes: int,
    validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
) -> dict[str, object]:
    reader = value.reader
    if not isinstance(reader, ProjectionRowsReader):
        raise TypeError("projection table reader must be a ProjectionRowsReader")
    return ProjectionTableCacheEntryManifest(
        cache_key_digest=key.cache_key_digest,
        source_snapshot_digest=value.source_snapshot_digest,
        source_raw_content_digest=value.source_raw_content_digest,
        source_table_name=value.source_table_name,
        projection_schema=_projection_schema_contract_payload(value.projection_schema),
        row_count=value.row_count,
        projection_logical_digest=value.projection_logical_digest,
        selected_columns=tuple(
            _snapshot_table_column_contract_payload(column)
            for column in reader.columns
        ),
        rows_content_digest=rows_content_digest,
        rows_content_size_bytes=rows_content_size_bytes,
        validation_status=validation_status,
    ).to_payload()


def _projection_schema_payload(schema: ProjectionSchema) -> dict[str, object]:
    return _projection_schema_contract_payload(schema).to_payload()


def _projection_schema_contract_payload(schema: ProjectionSchema) -> ProjectionSchemaPayload:
    return ProjectionSchemaPayload(
        table_name=schema.table_name,
        selected_columns=schema.selected_columns,
        ignored_columns=schema.ignored_columns,
        before_only_columns=schema.before_only_columns,
        current_only_columns=schema.current_only_columns,
        effective_compare_key=schema.effective_compare_key,
        projection_schema_digest=schema.projection_schema_digest,
        table_ruleset_version=schema.table_ruleset_version,
        projection_contract_version=schema.projection_contract_version,
        scalar_encoding_version=schema.scalar_encoding_version,
    )


def _projection_schema_from_payload(payload: Mapping[str, object]) -> ProjectionSchema:
    return ProjectionSchema(
        table_name=_required_text(payload, "table_name"),
        selected_columns=_string_tuple(payload.get("selected_columns")),
        ignored_columns=_string_tuple(payload.get("ignored_columns")),
        before_only_columns=_string_tuple(payload.get("before_only_columns")),
        current_only_columns=_string_tuple(payload.get("current_only_columns")),
        effective_compare_key=_string_tuple(payload.get("effective_compare_key")),
        projection_schema_digest=_optional_digest(payload.get("projection_schema_digest")),
        table_ruleset_version=_required_text(payload, "table_ruleset_version"),
        projection_contract_version=_required_text(payload, "projection_contract_version"),
        scalar_encoding_version=_required_text(payload, "scalar_encoding_version"),
    )


def _snapshot_table_column_payload(column: SnapshotTableColumn) -> dict[str, object]:
    return _snapshot_table_column_contract_payload(column).to_payload()


def _snapshot_table_column_contract_payload(column: SnapshotTableColumn) -> ProjectionTableColumnPayload:
    return ProjectionTableColumnPayload(
        name=column.name,
        display_name=column.display_name,
        scalar_type=column.scalar_type,
        nullable=column.nullable,
    )


def _projection_table_entry_manifest_from_payload(
    payload: Mapping[str, object],
) -> ProjectionTableCacheEntryManifest:
    return ProjectionTableCacheEntryManifest(
        cache_key_digest=_required_digest(payload, "cache_key_digest"),
        source_snapshot_digest=_required_digest(payload, "source_snapshot_digest"),
        source_raw_content_digest=_required_digest(payload, "source_raw_content_digest"),
        source_table_name=_required_text(payload, "source_table_name"),
        projection_schema=_projection_schema_contract_from_payload(
            _required_mapping(payload, "projection_schema")
        ),
        row_count=_required_int(payload, "row_count"),
        projection_logical_digest=_optional_digest(payload.get("projection_logical_digest")),
        selected_columns=tuple(
            _snapshot_table_column_contract_from_payload(column_payload)
            for column_payload in _required_sequence(payload, "selected_columns")
        ),
        rows_content_digest=_required_digest(payload, "rows_content_digest"),
        rows_content_size_bytes=_required_int(payload, "rows_content_size_bytes"),
        validation_status=payload.get("validation_status") or CacheValidationStatus.PROVISIONAL,
    )


def _projection_schema_contract_from_payload(
    payload: Mapping[str, object],
) -> ProjectionSchemaPayload:
    return ProjectionSchemaPayload(
        table_name=_required_text(payload, "table_name"),
        selected_columns=_string_tuple(payload.get("selected_columns")),
        ignored_columns=_string_tuple(payload.get("ignored_columns")),
        before_only_columns=_string_tuple(payload.get("before_only_columns")),
        current_only_columns=_string_tuple(payload.get("current_only_columns")),
        effective_compare_key=_string_tuple(payload.get("effective_compare_key")),
        projection_schema_digest=_optional_digest(payload.get("projection_schema_digest")),
        table_ruleset_version=_required_text(payload, "table_ruleset_version"),
        projection_contract_version=_required_text(payload, "projection_contract_version"),
        scalar_encoding_version=_required_text(payload, "scalar_encoding_version"),
    )


def _snapshot_table_column_contract_from_payload(
    payload: Mapping[str, object],
) -> ProjectionTableColumnPayload:
    return ProjectionTableColumnPayload(
        name=_required_text(payload, "name"),
        display_name=_optional_text(payload.get("display_name")),
        scalar_type=_optional_text(payload.get("scalar_type")),
        nullable=_optional_bool(payload.get("nullable")),
    )


def _snapshot_table_column_from_payload(payload: Mapping[str, object]) -> SnapshotTableColumn:
    return SnapshotTableColumn(
        name=_required_text(payload, "name"),
        display_name=_optional_text(payload.get("display_name")),
        scalar_type=_optional_text(payload.get("scalar_type")),
        nullable=_optional_bool(payload.get("nullable")),
    )


def _write_rows_parquet(
    *,
    rows_path: Path,
    rows_reader: object,
) -> bytes:
    if not isinstance(rows_reader, ProjectionRowsReader):
        raise TypeError("rows_reader must be a ProjectionRowsReader")
    rows = normalize_parquet_rows(rows_reader.rows, rows_reader.columns)
    columns = tuple(rows_reader.columns)
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        row_payloads = [
            {
                column.name: row[index]
                for index, column in enumerate(columns)
            }
            for row in rows
        ]
        frame = pl.from_dicts(row_payloads, infer_schema_length=None, strict=False).select(
            [column.name for column in columns]
        )
    else:
        frame = pl.DataFrame(schema={column.name: pl.Null for column in columns})
    tmp_path = rows_path.with_name(f"{rows_path.name}.tmp")
    frame.write_parquet(tmp_path)
    tmp_path.replace(rows_path)
    return rows_path.read_bytes()


def _frame_to_rows(
    frame: pl.DataFrame,
    columns: Sequence[SnapshotTableColumn],
) -> tuple[tuple[object, ...], ...]:
    column_names = [column.name for column in columns]
    if frame.width != len(column_names):
        raise ValueError("projection rows parquet column count mismatch")
    selected_frame = frame.select(column_names)
    rows = normalize_parquet_rows(tuple(tuple(row) for row in selected_frame.rows()), columns)
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("projection rows parquet row width mismatch")
    return rows


def _required_mapping(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return value


def _required_sequence(
    payload: Mapping[str, object],
    key: str,
) -> Sequence[Mapping[str, object]]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{key} must be a sequence")
    result: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(f"{key} must contain mapping values")
        result.append(item)
    return tuple(result)


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value.strip()


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional text fields must be strings or None")
    normalized = value.strip()
    return normalized or None


def _optional_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError("nullable fields must be bool or None")
    return value


def _optional_digest(value: object | None) -> DigestRef | None:
    if value is None:
        return None
    return DigestRef.parse(str(value))


def _required_digest(
    payload: Mapping[str, object],
    key: str,
) -> DigestRef:
    value = payload[key]
    return DigestRef.parse(str(value))


def _string_tuple(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("tuple fields must be sequences of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TypeError("tuple fields must contain non-empty strings")
        normalized.append(canonical_identifier(item))
    return tuple(normalized)


__all__ = [
    "PROJECTION_TABLE_CACHE_ARTIFACT_KIND",
    "PROJECTION_TABLE_CACHE_CONTRACT_VERSION",
    "PROJECTION_TABLE_CACHE_DEFAULT_TTL_DAYS",
    "PROJECTION_TABLE_CACHE_MANIFEST_FILE_NAME",
    "PROJECTION_TABLE_CACHE_NAMESPACE",
    "PROJECTION_TABLE_CACHE_ROWS_FILE_NAME",
    "DisabledProjectionTableCache",
    "FilesystemProjectionTableCache",
    "InMemoryProjectionTableCache",
    "ProjectionTableCache",
    "ProjectionTableCacheKey",
    "ProjectionTableCacheLookup",
]
