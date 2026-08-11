"""Contract-owned Versioned fixture consumer for public HTTP end-to-end proof."""

# mypy: disable-error-code=import-untyped

from __future__ import annotations

import argparse
import asyncio
import compression.zstd
import hashlib
import io
import json
import os
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID

import pyarrow as pa
import pyarrow.ipc as pa_ipc

from gateway_repository_client import RepositoryClient
from gateway_repository_client.arrow_stream import ArrowIpcByteStream
from gateway_repository_contracts import (
    CommitIdString,
    CreateRepositoryResponse,
    GetVersionedCatalogResponse,
    IdempotencyKeyString,
    MainRefLiteral,
    OperationStatus,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    RepositoryArtifactRef,
    ResolveVersionedRefResponse,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
    UnknownTypePolicy,
    UploadArtifactResponse,
    VerificationPolicy,
    VersionedImportResult,
    VersionedOperation,
    VersionedTableNameString,
)
from gateway_repository_contracts.types import MediaTypeString, Sha256String

_ENV_BASE_URL = "GATEWAY_REPOSITORY_BASE_URL"
_ENV_BEARER_TOKEN = "GATEWAY_REPOSITORY_BEARER_TOKEN"
_ENV_FIXTURE_ROOT = "GATEWAY_VERSIONED_FIXTURE_ROOT"
_PACKAGE_NAME = "package.tar.zst"
_EXPECTED_NAME = "expected.json"
_MANIFEST_ENTRY_NAME = "manifest.json"
_REPLAY_SQL_ENTRY_NAME = "replay.sql"
_ARROW_IPC_STREAM_EOS = b"\xff\xff\xff\xff\x00\x00\x00\x00"
_SUMMARY_ALLOWED_KEYS = frozenset({"status", "repository_id", "c0", "c1", "c2", "main_commit"})

FIXTURE_PACKAGE_FACTS: dict[str, tuple[int, str]] = {
    "c1": (428, "83e6e96e643ee8ea4520aaaba65f2c31dbfaed1f798757d54dbee7303a142547"),
    "c2": (490, "ecf9958a757b39ebf0b1baac4f7ad68994d076e0e3ed3abb199c304485393d1a"),
}


class VersionedFixtureConsumerClient(Protocol):
    async def create_repository(
        self,
        *,
        idempotency_key: IdempotencyKeyString,
    ) -> CreateRepositoryResponse: ...

    async def upload_artifact(
        self,
        *,
        repository_id: UUID,
        idempotency_key: IdempotencyKeyString,
        media_type: MediaTypeString,
        raw_sha256: Sha256String,
        body: bytes | bytearray,
    ) -> UploadArtifactResponse: ...

    async def submit_versioned_import(
        self,
        *,
        idempotency_key: IdempotencyKeyString,
        request: SubmitVersionedImportRequest,
    ) -> SubmitVersionedImportResponse: ...

    async def wait_operation(
        self,
        *,
        repository_id: UUID,
        operation_id: UUID,
        deadline_seconds: float | None = None,
    ) -> VersionedOperation: ...

    async def resolve_versioned_ref(
        self,
        *,
        repository_id: UUID,
        ref_name: MainRefLiteral = "main",
    ) -> ResolveVersionedRefResponse: ...

    async def get_versioned_catalog(
        self,
        *,
        repository_id: UUID,
        commit_id: CommitIdString,
    ) -> GetVersionedCatalogResponse: ...

    def stream_versioned_table_rows(
        self,
        *,
        repository_id: UUID,
        commit_id: CommitIdString,
        table_name: VersionedTableNameString,
        unknown_type_policy: UnknownTypePolicy = UnknownTypePolicy.REJECT,
    ) -> ArrowIpcByteStream: ...


def _make_fixture_consumer_client(
    *,
    base_url: str,
    bearer_token: str,
) -> VersionedFixtureConsumerClient:
    return cast(
        VersionedFixtureConsumerClient,
        RepositoryClient(base_url=base_url, bearer_token=bearer_token),
    )


@dataclass(frozen=True, slots=True)
class ExpectedColumn:
    name: str
    sql_type: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class ExpectedTableCatalog:
    columns: tuple[ExpectedColumn, ...]
    primary_key: tuple[str, ...]
    row_count: int


@dataclass(frozen=True, slots=True)
class ExpectedTableRows:
    primary_key: tuple[str, ...]
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ExpectedFacts:
    catalog: dict[str, ExpectedTableCatalog]
    rows: dict[str, ExpectedTableRows]


@dataclass(frozen=True, slots=True)
class DecodedArrowTable:
    schema: pa.Schema
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class FixtureBundle:
    label: str
    package_path: Path
    package_bytes: bytes
    expected: ExpectedFacts


@dataclass(frozen=True, slots=True)
class ManifestFacts:
    canonicalization_manifest_digest: str
    table_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class ConsumerSummary:
    status: str
    repository_id: UUID
    c0: str
    c1: str
    c2: str
    main_commit: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "repository_id": str(self.repository_id),
                "c0": self.c0,
                "c1": self.c1,
                "c2": self.c2,
                "main_commit": self.main_commit,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def _require_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _require_list(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _parse_expected_column(raw: object, *, field: str) -> ExpectedColumn:
    mapping = _require_mapping(raw, field=field)
    extra = set(mapping) - {"name", "sql_type", "nullable"}
    if extra:
        raise ValueError(f"{field} has unexpected keys: {sorted(extra)}")
    name = mapping.get("name")
    sql_type = mapping.get("sql_type")
    nullable = mapping.get("nullable")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{field}.name must be a non-empty string")
    if not isinstance(sql_type, str) or not sql_type:
        raise ValueError(f"{field}.sql_type must be a non-empty string")
    if not isinstance(nullable, bool):
        raise ValueError(f"{field}.nullable must be a boolean")
    return ExpectedColumn(name=name, sql_type=sql_type, nullable=nullable)


def _assert_unique_primary_key_columns(primary_key: tuple[str, ...], *, field: str) -> None:
    if len(primary_key) != len(set(primary_key)):
        raise ValueError(f"{field}.primary_key must not contain duplicate column names")


def _assert_unique_record_primary_keys(
    records: tuple[dict[str, Any], ...],
    primary_key: tuple[str, ...],
    *,
    field: str,
) -> None:
    seen_keys: set[tuple[Any, ...]] = set()
    for record in records:
        key = row_primary_key_tuple(record, primary_key)
        if key in seen_keys:
            raise ValueError(f"{field}.records must not contain duplicate primary keys")
        seen_keys.add(key)


def _parse_expected_table_catalog(raw: object, *, field: str) -> ExpectedTableCatalog:
    mapping = _require_mapping(raw, field=field)
    extra = set(mapping) - {"columns", "primary_key", "row_count"}
    if extra:
        raise ValueError(f"{field} has unexpected keys: {sorted(extra)}")
    columns_raw = _require_list(mapping.get("columns"), field=f"{field}.columns")
    primary_key_raw = _require_list(mapping.get("primary_key"), field=f"{field}.primary_key")
    row_count = mapping.get("row_count")
    if type(row_count) is not int or row_count < 0:
        raise ValueError(f"{field}.row_count must be a non-negative integer")
    columns = tuple(
        _parse_expected_column(item, field=f"{field}.columns[{index}]")
        for index, item in enumerate(columns_raw)
    )
    column_names = [column.name for column in columns]
    if len(column_names) != len(set(column_names)):
        raise ValueError(f"{field}.columns must not contain duplicate names")
    primary_key = tuple(
        str(item) for item in primary_key_raw if isinstance(item, str) and item
    )
    if len(primary_key) != len(primary_key_raw):
        raise ValueError(f"{field}.primary_key must contain non-empty strings")
    if not primary_key:
        raise ValueError(f"{field}.primary_key must not be empty")
    _assert_unique_primary_key_columns(primary_key, field=field)
    return ExpectedTableCatalog(columns=columns, primary_key=primary_key, row_count=row_count)


def _parse_expected_table_rows(raw: object, *, field: str) -> ExpectedTableRows:
    mapping = _require_mapping(raw, field=field)
    extra = set(mapping) - {"primary_key", "records"}
    if extra:
        raise ValueError(f"{field} has unexpected keys: {sorted(extra)}")
    primary_key_raw = _require_list(mapping.get("primary_key"), field=f"{field}.primary_key")
    records_raw = _require_list(mapping.get("records"), field=f"{field}.records")
    primary_key = tuple(
        str(item) for item in primary_key_raw if isinstance(item, str) and item
    )
    if len(primary_key) != len(primary_key_raw):
        raise ValueError(f"{field}.primary_key must contain non-empty strings")
    if not primary_key:
        raise ValueError(f"{field}.primary_key must not be empty")
    _assert_unique_primary_key_columns(primary_key, field=field)
    records: list[dict[str, Any]] = []
    for index, item in enumerate(records_raw):
        record = _require_mapping(item, field=f"{field}.records[{index}]")
        records.append(dict(record))
    records_tuple = tuple(records)
    _assert_unique_record_primary_keys(records_tuple, primary_key, field=field)
    return ExpectedTableRows(primary_key=primary_key, records=records_tuple)


def parse_expected_facts(payload: object) -> ExpectedFacts:
    root = _require_mapping(payload, field="expected")
    extra = set(root) - {"catalog", "rows"}
    if extra:
        raise ValueError(f"expected has unexpected keys: {sorted(extra)}")
    catalog_root = _require_mapping(root.get("catalog"), field="catalog")
    catalog_extra = set(catalog_root) - {"tables"}
    if catalog_extra:
        raise ValueError(f"catalog has unexpected keys: {sorted(catalog_extra)}")
    catalog_tables = _require_mapping(catalog_root.get("tables"), field="catalog.tables")
    rows_root = _require_mapping(root.get("rows"), field="rows")
    catalog = {
        str(name): _parse_expected_table_catalog(value, field=f"catalog.tables.{name}")
        for name, value in catalog_tables.items()
    }
    rows = {
        str(name): _parse_expected_table_rows(value, field=f"rows.{name}")
        for name, value in rows_root.items()
    }
    if set(catalog) != set(rows):
        raise ValueError("catalog.tables and rows must describe the same table set")
    for table_name, catalog_table in catalog.items():
        row_table = rows[table_name]
        column_names = {column.name for column in catalog_table.columns}
        undeclared_pk = [name for name in catalog_table.primary_key if name not in column_names]
        if undeclared_pk:
            raise ValueError(
                f"catalog.primary_key references undeclared columns for {table_name!r}: "
                f"{undeclared_pk!r}"
            )
        if catalog_table.primary_key != row_table.primary_key:
            raise ValueError(
                f"catalog.primary_key and rows.primary_key must match for {table_name!r}: "
                f"{catalog_table.primary_key!r} != {row_table.primary_key!r}"
            )
        if catalog_table.row_count != len(row_table.records):
            raise ValueError(
                f"catalog.row_count and rows.records length must match for {table_name!r}: "
                f"{catalog_table.row_count} != {len(row_table.records)}"
            )
        column_names = {column.name for column in catalog_table.columns}
        for index, record in enumerate(row_table.records):
            record_keys = set(record)
            if record_keys != column_names:
                extra_keys = sorted(record_keys - column_names)
                missing_keys = sorted(column_names - record_keys)
                raise ValueError(
                    f"rows.{table_name}.records[{index}] keys must match column names exactly: "
                    f"extra={extra_keys!r} missing={missing_keys!r}"
                )
    return ExpectedFacts(catalog=catalog, rows=rows)


def load_expected_facts(path: Path) -> ExpectedFacts:
    text = path.read_text(encoding="utf-8")

    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            seen.add(key)
            payload[key] = value
        return payload

    payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    return parse_expected_facts(payload)


def load_fixture_bundle(fixture_root: Path, label: str) -> FixtureBundle:
    bundle_dir = fixture_root / label
    package_path = bundle_dir / _PACKAGE_NAME
    expected_path = bundle_dir / _EXPECTED_NAME
    if not package_path.is_file():
        raise FileNotFoundError(f"missing fixture package: {package_path}")
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing expected facts: {expected_path}")
    package_bytes = package_path.read_bytes()
    if not package_bytes:
        raise ValueError(f"fixture package is empty: {package_path}")
    return FixtureBundle(
        label=label,
        package_path=package_path,
        package_bytes=package_bytes,
        expected=load_expected_facts(expected_path),
    )


def package_digest(package_bytes: bytes) -> tuple[int, str]:
    return len(package_bytes), hashlib.sha256(package_bytes).hexdigest()


def read_package_manifest_digest(package_bytes: bytes) -> str:
    tar_bytes = compression.zstd.decompress(package_bytes)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        manifest_file = archive.extractfile(_MANIFEST_ENTRY_NAME)
        if manifest_file is None:
            raise ValueError("package is missing manifest.json")
        manifest = json.loads(manifest_file.read().decode("utf-8"))
    digest = manifest.get("canonicalization_manifest_digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError("manifest canonicalization_manifest_digest must be a non-empty string")
    return digest


def validate_fixture_package_bytes(
    label: str,
    package_bytes: bytes,
    expected: ExpectedFacts,
) -> ManifestFacts:
    if label not in FIXTURE_PACKAGE_FACTS:
        raise ValueError(f"unknown fixture label: {label!r}")
    expected_size, expected_sha = FIXTURE_PACKAGE_FACTS[label]
    size_bytes, raw_sha256 = package_digest(package_bytes)
    if size_bytes != expected_size or raw_sha256 != expected_sha:
        raise ValueError(
            f"fixture package bytes mismatch for {label}: "
            f"size={size_bytes} sha={raw_sha256} expected_size={expected_size} "
            f"expected_sha={expected_sha}"
        )
    tar_bytes = compression.zstd.decompress(package_bytes)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        file_members = [member for member in archive.getmembers() if member.isfile()]
        entry_names = {member.name for member in file_members}
        if entry_names != {_MANIFEST_ENTRY_NAME, _REPLAY_SQL_ENTRY_NAME}:
            raise ValueError(
                f"fixture package must contain only {_MANIFEST_ENTRY_NAME!r} and "
                f"{_REPLAY_SQL_ENTRY_NAME!r}: actual={sorted(entry_names)}"
            )
        for member in file_members:
            if not member.isreg():
                raise ValueError(f"fixture package entry must be a regular file: {member.name!r}")
        manifest_file = archive.extractfile(_MANIFEST_ENTRY_NAME)
        replay_file = archive.extractfile(_REPLAY_SQL_ENTRY_NAME)
        if manifest_file is None or replay_file is None:
            raise ValueError("fixture package is missing required tar entries")
        manifest = json.loads(manifest_file.read().decode("utf-8"))
        replay_sql = replay_file.read().decode("utf-8")
    tables_raw = manifest.get("tables")
    if not isinstance(tables_raw, list):
        raise ValueError("manifest.tables must be an array")
    manifest_table_names = {str(table["name"]) for table in tables_raw if isinstance(table, dict)}
    if manifest_table_names != set(expected.catalog):
        raise ValueError(
            f"manifest tables must match expected catalog tables for {label}: "
            f"manifest={sorted(manifest_table_names)} expected={sorted(expected.catalog)}"
        )
    if label == "c2" and "INSERT INTO fixture_items" not in replay_sql:
        raise ValueError("c2 replay.sql must contain an INSERT into fixture_items")
    digest = read_package_manifest_digest(package_bytes)
    return ManifestFacts(
        canonicalization_manifest_digest=digest,
        table_names=frozenset(manifest_table_names),
    )


def assert_upload_artifact_ref(
    ref: RepositoryArtifactRef,
    *,
    size_bytes: int,
    raw_sha256: str,
    media_type: str,
) -> None:
    if ref.size_bytes != size_bytes:
        raise AssertionError(
            f"upload artifact size_bytes mismatch: actual={ref.size_bytes} expected={size_bytes}"
        )
    if ref.raw_sha256 != raw_sha256:
        raise AssertionError(
            f"upload artifact raw_sha256 mismatch: actual={ref.raw_sha256!r} expected={raw_sha256!r}"
        )
    if ref.media_type != media_type:
        raise AssertionError(
            f"upload artifact media_type mismatch: actual={ref.media_type!r} expected={media_type!r}"
        )


def row_primary_key_tuple(row: dict[str, Any], primary_key: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[column] for column in primary_key)


def canonical_row_set(
    records: tuple[dict[str, Any], ...],
    *,
    primary_key: tuple[str, ...],
) -> frozenset[tuple[Any, ...]]:
    return frozenset(row_primary_key_tuple(record, primary_key) for record in records)


def _arrow_type_for_sql_type(sql_type: str) -> pa.DataType:
    upper = sql_type.upper()
    if upper == "BIGINT":
        return pa.int64()
    if upper in {"INT", "INTEGER"}:
        return pa.int32()
    if upper.startswith("VARCHAR") or upper.startswith("CHAR"):
        return pa.string()
    raise ValueError(f"unsupported fixture sql_type for Arrow schema: {sql_type!r}")


def expected_arrow_schema(columns: tuple[ExpectedColumn, ...]) -> pa.Schema:
    fields = [
        pa.field(
            column.name,
            _arrow_type_for_sql_type(column.sql_type),
            nullable=column.nullable,
            metadata=None,
        )
        for column in columns
    ]
    return pa.schema(fields)


def _normalize_field_metadata(metadata: dict[bytes, bytes] | None) -> dict[bytes, bytes]:
    if metadata is None:
        return {}
    return dict(metadata)


def assert_arrow_schema_matches(actual_schema: pa.Schema, expected_columns: tuple[ExpectedColumn, ...]) -> None:
    expected_schema = expected_arrow_schema(expected_columns)
    if len(actual_schema) != len(expected_schema):
        raise AssertionError(
            f"arrow schema field count mismatch: actual={len(actual_schema)} expected={len(expected_schema)}"
        )
    for actual_field, expected_field in zip(actual_schema, expected_schema, strict=True):
        if actual_field.name != expected_field.name:
            raise AssertionError(
                f"arrow schema field name mismatch: actual={actual_field.name!r} "
                f"expected={expected_field.name!r}"
            )
        if not actual_field.type.equals(expected_field.type):
            raise AssertionError(
                f"arrow schema field type mismatch for {actual_field.name!r}: "
                f"actual={actual_field.type!r} expected={expected_field.type!r}"
            )
        if actual_field.nullable != expected_field.nullable:
            raise AssertionError(
                f"arrow schema nullable mismatch for {actual_field.name!r}: "
                f"actual={actual_field.nullable!r} expected={expected_field.nullable!r}"
            )
        actual_metadata = _normalize_field_metadata(actual_field.metadata)
        expected_metadata = _normalize_field_metadata(expected_field.metadata)
        if actual_metadata != expected_metadata:
            raise AssertionError(
                f"arrow schema metadata mismatch for {actual_field.name!r}: "
                f"actual={actual_metadata!r} expected={expected_metadata!r}"
            )
    actual_schema_metadata = _normalize_field_metadata(actual_schema.metadata)
    expected_schema_metadata = _normalize_field_metadata(expected_schema.metadata)
    if actual_schema_metadata != expected_schema_metadata:
        raise AssertionError(
            "arrow schema-level metadata mismatch: "
            f"actual={actual_schema_metadata!r} expected={expected_schema_metadata!r}"
        )


def decode_arrow_stream(body: bytes) -> DecodedArrowTable:
    if not body.endswith(_ARROW_IPC_STREAM_EOS):
        raise ValueError("Arrow IPC stream is missing EOS trailer")
    buffer_reader = pa.BufferReader(body)
    reader = pa_ipc.open_stream(buffer_reader)
    schema = reader.schema
    rows: list[dict[str, Any]] = []
    for batch in reader:
        table = pa.Table.from_batches([batch], schema=schema)
        column_names = table.column_names
        for row_index in range(table.num_rows):
            rows.append({name: table.column(name)[row_index].as_py() for name in column_names})
    if buffer_reader.tell() != len(body):
        raise ValueError("Arrow IPC stream has unconsumed trailing bytes")
    return DecodedArrowTable(schema=schema, rows=tuple(rows))


def _catalog_table_map(response: GetVersionedCatalogResponse) -> dict[str, Any]:
    return {table.name: table for table in response.catalog.tables}


def assert_catalog_matches(
    response: GetVersionedCatalogResponse,
    expected: ExpectedFacts,
    *,
    commit_id: str,
) -> None:
    if response.catalog.commit_id != commit_id:
        raise AssertionError(
            f"catalog commit_id mismatch: actual={response.catalog.commit_id!r} "
            f"expected={commit_id!r}"
        )
    tables = response.catalog.tables
    if len(tables) != len({table.name for table in tables}):
        raise AssertionError("catalog contains duplicate table names")
    actual_tables = _catalog_table_map(response)
    if set(actual_tables) != set(expected.catalog):
        raise AssertionError(
            f"catalog table set mismatch: actual={sorted(actual_tables)} "
            f"expected={sorted(expected.catalog)}"
        )
    for table_name, expected_table in expected.catalog.items():
        actual_table = actual_tables[table_name]
        if actual_table.row_count != expected_table.row_count:
            raise AssertionError(
                f"catalog row_count mismatch for {table_name}: "
                f"actual={actual_table.row_count} expected={expected_table.row_count}"
            )
        if tuple(actual_table.primary_key) != expected_table.primary_key:
            raise AssertionError(
                f"catalog primary_key mismatch for {table_name}: "
                f"actual={actual_table.primary_key} expected={expected_table.primary_key}"
            )
        if len(actual_table.columns) != len(expected_table.columns):
            raise AssertionError(
                f"catalog column count mismatch for {table_name}: "
                f"actual={len(actual_table.columns)} expected={len(expected_table.columns)}"
            )
        for actual_column, expected_column in zip(
            actual_table.columns,
            expected_table.columns,
            strict=True,
        ):
            if (
                actual_column.name != expected_column.name
                or actual_column.sql_type != expected_column.sql_type
                or actual_column.nullable != expected_column.nullable
            ):
                raise AssertionError(
                    f"catalog column mismatch for {table_name}.{expected_column.name}: "
                    f"actual=({actual_column.name!r}, {actual_column.sql_type!r}, "
                    f"{actual_column.nullable!r}) "
                    f"expected=({expected_column.name!r}, {expected_column.sql_type!r}, "
                    f"{expected_column.nullable!r})"
                )


def assert_rows_match(
    actual_records: list[dict[str, Any]],
    expected_table: ExpectedTableRows,
    *,
    table_name: str,
) -> None:
    if len(actual_records) != len(expected_table.records):
        raise AssertionError(
            f"row count mismatch for {table_name}: "
            f"actual={len(actual_records)} expected={len(expected_table.records)}"
        )
    actual_keys = canonical_row_set(
        tuple(actual_records),
        primary_key=expected_table.primary_key,
    )
    expected_keys = canonical_row_set(
        expected_table.records,
        primary_key=expected_table.primary_key,
    )
    if len(actual_keys) != len(actual_records):
        raise AssertionError(f"duplicate primary keys in actual rows for {table_name}")
    if len(expected_keys) != len(expected_table.records):
        raise AssertionError(f"duplicate primary keys in expected rows for {table_name}")
    if actual_keys != expected_keys:
        raise AssertionError(
            f"row primary-key set mismatch for {table_name}: "
            f"actual={sorted(actual_keys)} expected={sorted(expected_keys)}"
        )
    expected_by_key = {
        row_primary_key_tuple(record, expected_table.primary_key): record
        for record in expected_table.records
    }
    for record in actual_records:
        key = row_primary_key_tuple(record, expected_table.primary_key)
        expected_record = expected_by_key[key]
        if record != expected_record:
            raise AssertionError(
                f"row value mismatch for {table_name} key={key}: "
                f"actual={record!r} expected={expected_record!r}"
            )


async def _read_commit_facts(
    client: VersionedFixtureConsumerClient,
    *,
    repository_id: UUID,
    commit_id: str,
    expected: ExpectedFacts,
) -> None:
    catalog_response = await client.get_versioned_catalog(
        repository_id=repository_id,
        commit_id=commit_id,
    )
    assert_catalog_matches(catalog_response, expected, commit_id=commit_id)
    for table_name, expected_rows in expected.rows.items():
        stream = client.stream_versioned_table_rows(
            repository_id=repository_id,
            commit_id=commit_id,
            table_name=table_name,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        async with stream:
            body = b"".join([chunk async for chunk in stream.aiter_bytes()])
        decoded = decode_arrow_stream(body)
        catalog_table = expected.catalog[table_name]
        assert_arrow_schema_matches(decoded.schema, catalog_table.columns)
        assert_rows_match(list(decoded.rows), expected_rows, table_name=table_name)


def assert_import_result_identity(
    result: VersionedImportResult,
    *,
    expected_commit_id: str,
    artifact_id: UUID,
    manifest_digest: str,
    completed_verification_policy: VerificationPolicy = VerificationPolicy.STRUCTURAL,
    unknown_type_policy: UnknownTypePolicy = UnknownTypePolicy.REJECT,
) -> None:
    if result.expected_commit_id != expected_commit_id:
        raise AssertionError(
            "import result expected_commit_id mismatch: "
            f"actual={result.expected_commit_id!r} expected={expected_commit_id!r}"
        )
    if result.target_ref != "main":
        raise AssertionError(
            f"import result target_ref mismatch: actual={result.target_ref!r} expected='main'"
        )
    if result.artifact_id != artifact_id:
        raise AssertionError(
            f"import result artifact_id mismatch: actual={result.artifact_id} expected={artifact_id}"
        )
    if result.canonicalization_manifest_digest != manifest_digest:
        raise AssertionError(
            "import result canonicalization_manifest_digest mismatch: "
            f"actual={result.canonicalization_manifest_digest!r} expected={manifest_digest!r}"
        )
    if result.completed_verification_policy != completed_verification_policy:
        raise AssertionError(
            "import result completed_verification_policy mismatch: "
            f"actual={result.completed_verification_policy!r} "
            f"expected={completed_verification_policy!r}"
        )
    if result.unknown_type_policy != unknown_type_policy:
        raise AssertionError(
            "import result unknown_type_policy mismatch: "
            f"actual={result.unknown_type_policy!r} expected={unknown_type_policy!r}"
        )


async def _import_fixture(
    client: VersionedFixtureConsumerClient,
    *,
    repository_id: UUID,
    bundle: FixtureBundle,
    expected_commit_id: str,
    idempotency_prefix: str,
) -> str:
    size_bytes, raw_sha256 = package_digest(bundle.package_bytes)
    manifest_digest = read_package_manifest_digest(bundle.package_bytes)
    upload_response = await client.upload_artifact(
        repository_id=repository_id,
        idempotency_key=f"{idempotency_prefix}-upload",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=raw_sha256,
        body=bundle.package_bytes,
    )
    assert_upload_artifact_ref(
        upload_response.artifact_ref,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
    )
    submit_response = await client.submit_versioned_import(
        idempotency_key=f"{idempotency_prefix}-submit",
        request=SubmitVersionedImportRequest(
            repository_id=repository_id,
            artifact_ref=upload_response.artifact_ref,
            target_ref="main",
            expected_commit_id=expected_commit_id,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    operation = await client.wait_operation(
        repository_id=repository_id,
        operation_id=submit_response.operation_id,
        deadline_seconds=120.0,
    )
    if operation.status != OperationStatus.SUCCEEDED or operation.result is None:
        raise RuntimeError(
            f"import {bundle.label} did not succeed: status={operation.status} error={operation.error}"
        )
    if operation.operation_id != submit_response.operation_id:
        raise AssertionError(
            "operation operation_id mismatch: "
            f"actual={operation.operation_id} expected={submit_response.operation_id}"
        )
    assert_import_result_identity(
        operation.result,
        expected_commit_id=expected_commit_id,
        artifact_id=upload_response.artifact_ref.artifact_id,
        manifest_digest=manifest_digest,
    )
    return str(operation.result.commit_id)


async def run_consumer(
    *,
    base_url: str,
    bearer_token: str,
    fixture_root: Path,
) -> ConsumerSummary:
    c1_bundle = load_fixture_bundle(fixture_root, "c1")
    c2_bundle = load_fixture_bundle(fixture_root, "c2")
    client = _make_fixture_consumer_client(base_url=base_url, bearer_token=bearer_token)
    create_response = await client.create_repository(idempotency_key="fixture-consumer-create")
    repository_id = create_response.repository_id
    c0 = create_response.initial_commit_id
    c1 = await _import_fixture(
        client,
        repository_id=repository_id,
        bundle=c1_bundle,
        expected_commit_id=c0,
        idempotency_prefix="fixture-c1",
    )
    c2 = await _import_fixture(
        client,
        repository_id=repository_id,
        bundle=c2_bundle,
        expected_commit_id=c1,
        idempotency_prefix="fixture-c2",
    )
    resolve_response = await client.resolve_versioned_ref(repository_id=repository_id)
    if resolve_response.commit_id != c2:
        raise AssertionError(
            f"main did not resolve to C2: main={resolve_response.commit_id!r} c2={c2!r}"
        )
    await _read_commit_facts(
        client,
        repository_id=repository_id,
        commit_id=c1,
        expected=c1_bundle.expected,
    )
    await _read_commit_facts(
        client,
        repository_id=repository_id,
        commit_id=c2,
        expected=c2_bundle.expected,
    )
    return ConsumerSummary(
        status="ok",
        repository_id=repository_id,
        c0=c0,
        c1=c1,
        c2=c2,
        main_commit=resolve_response.commit_id,
    )


def _resolve_config_from_env() -> tuple[str, str, Path]:
    base_url = os.environ.get(_ENV_BASE_URL, "").strip()
    bearer_token = os.environ.get(_ENV_BEARER_TOKEN, "").strip()
    fixture_root_raw = os.environ.get(_ENV_FIXTURE_ROOT, "").strip()
    if not base_url:
        raise ValueError(f"missing {_ENV_BASE_URL}")
    if not bearer_token:
        raise ValueError(f"missing {_ENV_BEARER_TOKEN}")
    if not fixture_root_raw:
        raise ValueError(f"missing {_ENV_FIXTURE_ROOT}")
    return base_url, bearer_token, Path(fixture_root_raw)


def _sanitize_error_message(message: str, bearer_token: str) -> str:
    if not bearer_token:
        return message
    return message.replace(bearer_token, "<redacted>")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Versioned fixture consumer.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--fixture-root", default=None)
    args = parser.parse_args(argv)

    base_url = (args.base_url or os.environ.get(_ENV_BASE_URL, "")).strip()
    bearer_token = os.environ.get(_ENV_BEARER_TOKEN, "").strip()
    fixture_root_raw = (args.fixture_root or os.environ.get(_ENV_FIXTURE_ROOT, "")).strip()
    if not base_url or not bearer_token or not fixture_root_raw:
        base_url, bearer_token, fixture_root = _resolve_config_from_env()
        fixture_root_raw = str(fixture_root)
    fixture_root = Path(fixture_root_raw)
    if not fixture_root.is_dir():
        raise FileNotFoundError(f"fixture root does not exist: {fixture_root}")

    summary = asyncio.run(
        run_consumer(
            base_url=base_url,
            bearer_token=bearer_token,
            fixture_root=fixture_root,
        )
    )
    sys.stdout.write(summary.to_json())
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    bearer_token = os.environ.get(_ENV_BEARER_TOKEN, "").strip()
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(_sanitize_error_message(str(exc), bearer_token), file=sys.stderr)
        raise SystemExit(1) from exc
