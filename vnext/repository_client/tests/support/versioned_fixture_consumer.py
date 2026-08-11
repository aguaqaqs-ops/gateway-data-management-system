"""Contract-owned Versioned fixture consumer for public HTTP end-to-end proof."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]

from gateway_repository_client import RepositoryClient
from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    OperationStatus,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    SubmitVersionedImportRequest,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)

_ENV_BASE_URL = "GATEWAY_REPOSITORY_BASE_URL"
_ENV_BEARER_TOKEN = "GATEWAY_REPOSITORY_BEARER_TOKEN"
_ENV_FIXTURE_ROOT = "GATEWAY_VERSIONED_FIXTURE_ROOT"
_PACKAGE_NAME = "package.tar.zst"
_EXPECTED_NAME = "expected.json"


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
class FixtureBundle:
    label: str
    package_path: Path
    package_bytes: bytes
    expected: ExpectedFacts


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
    primary_key = tuple(
        str(item) for item in primary_key_raw if isinstance(item, str) and item
    )
    if len(primary_key) != len(primary_key_raw):
        raise ValueError(f"{field}.primary_key must contain non-empty strings")
    if not primary_key:
        raise ValueError(f"{field}.primary_key must not be empty")
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
    records: list[dict[str, Any]] = []
    for index, item in enumerate(records_raw):
        if not isinstance(item, dict):
            raise ValueError(f"{field}.records[{index}] must be an object")
        records.append(dict(item))
    return ExpectedTableRows(primary_key=primary_key, records=tuple(records))


def parse_expected_facts(payload: object) -> ExpectedFacts:
    root = _require_mapping(payload, field="expected")
    extra = set(root) - {"catalog", "rows"}
    if extra:
        raise ValueError(f"expected has unexpected keys: {sorted(extra)}")
    catalog_root = _require_mapping(root.get("catalog"), field="catalog")
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
    return ExpectedFacts(catalog=catalog, rows=rows)


def load_expected_facts(path: Path) -> ExpectedFacts:
    payload = json.loads(path.read_text(encoding="utf-8"))
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


def row_primary_key_tuple(row: dict[str, Any], primary_key: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[column] for column in primary_key)


def canonical_row_set(
    records: tuple[dict[str, Any], ...],
    *,
    primary_key: tuple[str, ...],
) -> frozenset[tuple[Any, ...]]:
    return frozenset(row_primary_key_tuple(record, primary_key) for record in records)


def decode_arrow_stream(body: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = pa_ipc.open_stream(body)
    for batch in reader:
        table = pa.Table.from_batches([batch])
        column_names = table.column_names
        for row_index in range(table.num_rows):
            rows.append({name: table.column(name)[row_index].as_py() for name in column_names})
    return rows


def _catalog_table_map(response: GetVersionedCatalogResponse) -> dict[str, Any]:
    return {table.name: table for table in response.catalog.tables}


def assert_catalog_matches(
    response: GetVersionedCatalogResponse,
    expected: ExpectedFacts,
) -> None:
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
    client: RepositoryClient,
    *,
    repository_id: UUID,
    commit_id: str,
    expected: ExpectedFacts,
) -> None:
    catalog_response = await client.get_versioned_catalog(
        repository_id=repository_id,
        commit_id=commit_id,
    )
    assert_catalog_matches(catalog_response, expected)
    for table_name, expected_rows in expected.rows.items():
        stream = client.stream_versioned_table_rows(
            repository_id=repository_id,
            commit_id=commit_id,
            table_name=table_name,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        async with stream:
            body = b"".join([chunk async for chunk in stream.aiter_bytes()])
        actual_records = decode_arrow_stream(body)
        assert_rows_match(actual_records, expected_rows, table_name=table_name)


def assert_import_result_identity(
    result: VersionedImportResult,
    *,
    expected_commit_id: str,
    artifact_id: UUID,
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


async def _import_fixture(
    client: RepositoryClient,
    *,
    repository_id: UUID,
    bundle: FixtureBundle,
    expected_commit_id: str,
    idempotency_prefix: str,
) -> str:
    size_bytes, raw_sha256 = package_digest(bundle.package_bytes)
    upload_response = await client.upload_artifact(
        repository_id=repository_id,
        idempotency_key=f"{idempotency_prefix}-upload",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=raw_sha256,
        body=bundle.package_bytes,
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
    assert_import_result_identity(
        operation.result,
        expected_commit_id=expected_commit_id,
        artifact_id=upload_response.artifact_ref.artifact_id,
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
    client = RepositoryClient(base_url=base_url, bearer_token=bearer_token)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Versioned fixture consumer.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--bearer-token", default=None)
    parser.add_argument("--fixture-root", default=None)
    args = parser.parse_args(argv)

    base_url = (args.base_url or os.environ.get(_ENV_BASE_URL, "")).strip()
    bearer_token = (args.bearer_token or os.environ.get(_ENV_BEARER_TOKEN, "")).strip()
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
    print(summary.to_json())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
