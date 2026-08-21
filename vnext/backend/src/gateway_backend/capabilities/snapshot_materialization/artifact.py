"""Immutable SnapshotTableArtifact publish, open, and validation."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    ManifestVerificationError,
    artifact_ref_from_dict,
    artifact_ref_to_dict,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.snapshot_materialization._digest import (
    raw_content_digest_of,
    row_content_hash,
)
from gateway_backend.capabilities.snapshot_materialization._parquet import (
    encoding_columns_from_table,
    export_schema_payload,
    iter_decoded_rows,
    read_parquet_table,
    source_descriptor_for,
    write_parquet_rows,
)
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.batch import (
    ParquetSnapshotTableBatchReader,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ARTIFACT_COMPRESSION_ZSTD,
    MANIFEST_MEDIA_TYPE,
    PARQUET_MEDIA_TYPE,
    ROW_FORMAT_PARQUET,
    ROW_MATERIALIZATION_PROFILE,
    SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
    DegradedReason,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    SnapshotColumnDescriptor,
    BlankRowProvenance,
    SnapshotTableBatchMetadata,
    SnapshotTable,
    SnapshotTableArtifact,
    SnapshotTableArtifactManifest,
    SnapshotTableDescriptor,
    SnapshotTableOrderedMetadata,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    ParserInvocationContext,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
    TableAccessError,
)

_ARTIFACT_CONTENT_KIND = "artifact-content"
_ROW_LAYOUT_KIND = "row-layout"


class ArtifactPublishError(Exception):
    def __init__(
        self,
        code: MaterializationDiagnosticCode,
        message: str,
        *,
        table: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.table = table


class ParquetBytesReader:
    def __init__(
        self,
        source: SourceTableDescriptor,
        parquet_bytes: bytes,
        rows: tuple[SourceRow, ...],
    ) -> None:
        self._source = source
        self._parquet_bytes = parquet_bytes
        self._rows = rows
        self._closed = False
        self._consumed = False

    def descriptor(self) -> SourceTableDescriptor:
        self._require_open()
        return self._source

    def iter_rows(self) -> Iterator[SourceRow]:
        self._require_open()
        if self._consumed:
            raise ValueError("table reader is single-consumer and non-rewind")
        self._consumed = True
        yield from self._rows

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> ParquetBytesReader:
        return ParquetBytesReader(self._source, self._parquet_bytes, self._rows)

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")


def publish_snapshot_table_artifact(
    table: SnapshotTable,
    *,
    snapshot_digest: DigestRef,
    store: ArtifactStorePort,
    context: ParserInvocationContext,
) -> SnapshotTableArtifact:
    if type(table) is not SnapshotTable:
        raise ValueError("table must be SnapshotTable")
    if table.descriptor.degraded_reason is DegradedReason.TABLE_FAILED:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_PUBLISH_FAILED,
            "failed table must not publish an artifact",
            table=table.descriptor.table_name,
        )
    if table.reader is None:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
            "ready table has no reader to publish",
            table=table.descriptor.table_name,
        )
    _checkpoint(context, table.descriptor.table_name)
    source_columns = _source_columns(table)
    rows = _consume_rows(table.reader, context, table.descriptor.table_name)
    try:
        parquet_bytes = write_parquet_rows(
            source_columns,
            rows,
            SnapshotTableBatchMetadata(
                blank_provenance=(
                    BlankRowProvenance.NONE
                    if table.ordered_metadata is None
                    else table.ordered_metadata.blank_provenance
                )
            ),
        )
    except ValueError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_PUBLISH_FAILED,
            str(exc) or "parquet encode failed",
            table=table.descriptor.table_name,
        ) from exc
    _checkpoint(context, table.descriptor.table_name)
    try:
        row_ref = put_with_built_ref(
            store,
            parquet_bytes,
            artifact_id=_opaque_id("sta-rows"),
            media_type=PARQUET_MEDIA_TYPE,
        )
    except ManifestVerificationError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_PUBLISH_FAILED,
            str(exc) or "parquet store write failed",
            table=table.descriptor.table_name,
        ) from exc
    try:
        stored_parquet = store.locate(row_ref)
        _validate_parquet_against_descriptor(
            stored_parquet,
            table.descriptor,
            source_columns,
            table.descriptor.table_name,
        )
    except ArtifactPublishError:
        raise
    except (ManifestVerificationError, ValueError) as exc:
        raise ArtifactPublishError(
            _map_open_error(exc),
            str(exc) or "published parquet failed validation",
            table=table.descriptor.table_name,
        ) from exc
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    artifact_digest = artifact_content_digest_of(
        row_file_refs=(row_ref,),
        descriptor=table.descriptor,
    )
    layout = row_layout_digest_of(table.descriptor, source_columns)
    manifest = SnapshotTableArtifactManifest(
        artifact_contract_version=SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
        snapshot_digest=snapshot_digest,
        table_name=table.descriptor.table_name,
        descriptor=table.descriptor,
        row_file_refs=(row_ref,),
        row_format=ROW_FORMAT_PARQUET,
        compression=ARTIFACT_COMPRESSION_ZSTD,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        artifact_content_digest=artifact_digest,
        created_at=created_at,
        diagnostics=table.descriptor.diagnostics,
        ordered_metadata=table.ordered_metadata,
    )
    manifest_bytes = canonicalize_json_value(manifest_to_payload(manifest))
    try:
        manifest_ref = put_with_built_ref(
            store,
            manifest_bytes,
            artifact_id=_opaque_id("sta-manifest"),
            media_type=MANIFEST_MEDIA_TYPE,
        )
        stored_manifest = store.locate(manifest_ref)
        if stored_manifest != manifest_bytes:
            raise ArtifactPublishError(
                MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
                "stored manifest bytes do not match the published payload",
                table=table.descriptor.table_name,
            )
    except ArtifactPublishError:
        raise
    except ManifestVerificationError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_PUBLISH_FAILED,
            str(exc) or "manifest store write failed",
            table=table.descriptor.table_name,
        ) from exc
    return SnapshotTableArtifact(
        manifest_ref=manifest_ref,
        manifest=manifest,
        row_layout_digest=layout,
    )


def open_snapshot_table_artifact(
    store: ArtifactStorePort,
    manifest_ref: ArtifactRef,
) -> SnapshotTable:
    try:
        raw_manifest = store.locate(manifest_ref)
    except ManifestVerificationError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT,
            str(exc) or "manifest artifact is missing or corrupt",
        ) from exc
    try:
        manifest = manifest_from_bytes(raw_manifest)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT,
            str(exc) or "manifest JSON is corrupt",
        ) from exc
    if len(manifest.row_file_refs) != 1:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT,
            "v1 artifact requires exactly one row file",
            table=manifest.table_name,
        )
    row_ref = manifest.row_file_refs[0]
    try:
        parquet_bytes = store.locate(row_ref)
    except ManifestVerificationError as exc:
        raise ArtifactPublishError(
            _map_open_error(exc),
            str(exc) or "row file is missing or corrupt",
            table=manifest.table_name,
        ) from exc
    source_columns = _validate_parquet_against_descriptor(
        parquet_bytes,
        manifest.descriptor,
        None,
        manifest.table_name,
    )
    expected = artifact_content_digest_of(
        row_file_refs=manifest.row_file_refs,
        descriptor=manifest.descriptor,
    )
    if expected != manifest.artifact_content_digest:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
            "artifact_content_digest does not match physical files",
            table=manifest.table_name,
        )
    layout = row_layout_digest_of(manifest.descriptor, source_columns)
    artifact = SnapshotTableArtifact(
        manifest_ref=manifest_ref,
        manifest=manifest,
        row_layout_digest=layout,
    )
    source = source_descriptor_for(
        manifest.descriptor.table_name,
        manifest.descriptor.display_table_name,
        source_columns,
        manifest.descriptor.primary_key_columns,
    )
    table = read_parquet_table(parquet_bytes)
    rows = iter_decoded_rows(table, source_columns)
    reader = BoundSnapshotTableReader(
        manifest.descriptor,
        ParquetBytesReader(source, parquet_bytes, rows),
    )
    return SnapshotTable(
        descriptor=manifest.descriptor,
        reader=reader,
        diagnostics=manifest.descriptor.diagnostics,
        artifact=artifact,
            batch_reader=ParquetSnapshotTableBatchReader(
                manifest.descriptor,
                parquet_bytes,
                metadata=SnapshotTableBatchMetadata(
                    blank_provenance=(
                        BlankRowProvenance.NONE
                        if manifest.ordered_metadata is None
                        else manifest.ordered_metadata.blank_provenance
                    )
                ),
            ),
            ordered_metadata=manifest.ordered_metadata,
    )


def validate_snapshot_table_artifact(
    store: ArtifactStorePort,
    artifact: SnapshotTableArtifact,
) -> None:
    opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
    if opened.descriptor != artifact.manifest.descriptor:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            "opened descriptor does not match the artifact",
            table=artifact.manifest.table_name,
        )
    if opened.artifact is None:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT,
            "opened table did not carry an artifact",
            table=artifact.manifest.table_name,
        )
    if opened.artifact.manifest.artifact_content_digest != (
        artifact.manifest.artifact_content_digest
    ):
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
            "opened artifact digest does not match",
            table=artifact.manifest.table_name,
        )


def publish_ready_tables(
    tables: tuple[SnapshotTable, ...],
    *,
    snapshot_digest: DigestRef,
    store: ArtifactStorePort,
    context: ParserInvocationContext,
) -> tuple[SnapshotTable, ...]:
    published: list[SnapshotTable] = []
    for table in tables:
        if table.descriptor.degraded_reason is DegradedReason.TABLE_FAILED or table.reader is None:
            published.append(table)
            continue
        artifact = publish_snapshot_table_artifact(
            table,
            snapshot_digest=snapshot_digest,
            store=store,
            context=context,
        )
        opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
        published.append(
            SnapshotTable(
                descriptor=table.descriptor,
                reader=opened.reader,
                diagnostics=table.diagnostics,
                artifact=artifact,
                batch_reader=opened.batch_reader,
                ordered_metadata=table.ordered_metadata,
            )
        )
    return tuple(published)


def require_artifact_store(store: object | None) -> ArtifactStorePort:
    if store is None:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_STORE_REQUIRED,
            "ARTIFACTS_REQUIRED requires an artifact_store",
        )
    put = getattr(store, "put", None)
    locate = getattr(store, "locate", None)
    if not callable(put) or not callable(locate):
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_STORE_REQUIRED,
            "artifact_store must implement ArtifactStorePort",
        )
    return store  # type: ignore[return-value]


def artifact_error_diagnostic(exc: ArtifactPublishError) -> MaterializationDiagnostic:
    return MaterializationDiagnostic(
        code=exc.code,
        severity=DiagnosticSeverity.ERROR,
        message=exc.message,
        table=exc.table,
    )


def artifact_content_digest_of(
    *,
    row_file_refs: tuple[ArtifactRef, ...],
    descriptor: SnapshotTableDescriptor,
) -> DigestRef:
    payload: dict[str, Any] = {
        "kind": _ARTIFACT_CONTENT_KIND,
        "artifact_contract_version": SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
        "row_format": ROW_FORMAT_PARQUET,
        "row_files": [
            {
                "raw_sha256": ref.raw_sha256.value,
                "size_bytes": ref.size_bytes,
                "media_type": ref.media_type,
            }
            for ref in row_file_refs
        ],
        "raw_content_digest": _digest_value(descriptor.raw_content_digest),
        "compare_schema_digest": descriptor.compare_schema_digest.value,
        "row_count": descriptor.row_count,
        "columns": [
            {
                "name": column.name,
                "nullable": column.nullable,
                "scalar_type": column.scalar_type,
            }
            for column in sorted(descriptor.columns, key=lambda item: item.name)
        ],
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def row_layout_digest_of(
    descriptor: SnapshotTableDescriptor,
    source_columns: tuple[SourceColumnDescriptor, ...],
) -> DigestRef:
    payload = {
        "kind": _ROW_LAYOUT_KIND,
        "raw_content_digest": _digest_value(descriptor.raw_content_digest),
        "export_schema": export_schema_payload(source_columns),
        "scalar_encoding_version": descriptor.scalar_encoding_version,
        "artifact_contract_version": SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def manifest_to_payload(manifest: SnapshotTableArtifactManifest) -> dict[str, Any]:
    return {
        "artifact_contract_version": manifest.artifact_contract_version,
        "snapshot_digest": manifest.snapshot_digest.value,
        "table_name": manifest.table_name,
        "descriptor": _descriptor_payload(manifest.descriptor),
        "row_file_refs": [artifact_ref_to_dict(ref) for ref in manifest.row_file_refs],
        "row_format": manifest.row_format,
        "compression": manifest.compression,
        "row_materialization_profile": manifest.row_materialization_profile,
        "artifact_content_digest": manifest.artifact_content_digest.value,
        "created_at": manifest.created_at,
        "diagnostics": [_diagnostic_payload(item) for item in manifest.diagnostics],
        "ordered_metadata": _ordered_metadata_payload(manifest.ordered_metadata),
    }


def manifest_from_bytes(raw: bytes) -> SnapshotTableArtifactManifest:
    payload = json.loads(raw.decode("utf-8"))
    if type(payload) is not dict:
        raise ValueError("manifest must be a JSON object")
    refs_payload = payload["row_file_refs"]
    if type(refs_payload) is not list:
        raise ValueError("row_file_refs must be a list")
    refs = tuple(artifact_ref_from_dict(_as_object(item)) for item in refs_payload)
    return SnapshotTableArtifactManifest(
        artifact_contract_version=int(payload["artifact_contract_version"]),
        snapshot_digest=DigestRef(str(payload["snapshot_digest"])),
        table_name=str(payload["table_name"]),
        descriptor=_descriptor_from_payload(_as_object(payload["descriptor"])),
        row_file_refs=refs,
        row_format=str(payload["row_format"]),
        compression=str(payload["compression"]),
        row_materialization_profile=str(payload["row_materialization_profile"]),
        artifact_content_digest=DigestRef(str(payload["artifact_content_digest"])),
        created_at=str(payload["created_at"]),
        diagnostics=_diagnostics_from_payload(payload.get("diagnostics")),
        ordered_metadata=_ordered_metadata_from_payload(payload.get("ordered_metadata")),
    )


def _ordered_metadata_payload(metadata: SnapshotTableOrderedMetadata | None) -> dict[str, str] | None:
    if metadata is None:
        return None
    return {"blank_provenance": metadata.blank_provenance.value}


def _ordered_metadata_from_payload(payload: object) -> SnapshotTableOrderedMetadata | None:
    if payload is None:
        return None
    if type(payload) is not dict:
        raise ValueError("ordered_metadata must be an object or null")
    value = payload.get("blank_provenance")
    if type(value) is not str:
        raise ValueError("ordered_metadata.blank_provenance must be a string")
    return SnapshotTableOrderedMetadata(blank_provenance=BlankRowProvenance(value))


def _source_columns(table: SnapshotTable) -> tuple[SourceColumnDescriptor, ...]:
    reader = table.reader
    if isinstance(reader, BoundSnapshotTableReader):
        return reader.source_descriptor().columns
    raise ArtifactPublishError(
        MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
        "artifact publish requires a bound snapshot table reader",
        table=table.descriptor.table_name,
    )


def _consume_rows(
    reader: Any,
    context: ParserInvocationContext,
    table_name: str,
) -> tuple[SourceRow, ...]:
    isolated = reader.reopen()
    collected: list[SourceRow] = []
    try:
        for row in isolated.iter_rows():
            _checkpoint(context, table_name)
            collected.append(row)
    finally:
        isolated.close()
    return tuple(collected)


def _validate_parquet_against_descriptor(
    parquet_bytes: bytes,
    descriptor: SnapshotTableDescriptor,
    expected_columns: tuple[SourceColumnDescriptor, ...] | None,
    table_name: str,
) -> tuple[SourceColumnDescriptor, ...]:
    try:
        table = read_parquet_table(parquet_bytes)
    except ValueError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_TRUNCATED,
            str(exc) or "parquet rows are truncated",
            table=table_name,
        ) from exc
    try:
        columns = encoding_columns_from_table(table)
        rows = iter_decoded_rows(table, columns)
    except ValueError as exc:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            str(exc) or "parquet schema does not match encoding metadata",
            table=table_name,
        ) from exc
    if expected_columns is not None and columns != expected_columns:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            "parquet encoding columns do not match the source descriptor",
            table=table_name,
        )
    names = tuple(column.canonical_name for column in columns)
    expected_names = tuple(column.name for column in descriptor.columns)
    if names != expected_names:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            "parquet columns do not match the snapshot descriptor",
            table=table_name,
        )
    if len(rows) != descriptor.row_count:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            "parquet row_count does not match the snapshot descriptor",
            table=table_name,
        )
    if descriptor.raw_content_digest is not None:
        recomputed = raw_content_digest_of(
            tuple(row_content_hash(columns, row) for row in rows)
        )
        if recomputed != descriptor.raw_content_digest:
            raise ArtifactPublishError(
                MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
                "parquet rows do not match raw_content_digest",
                table=table_name,
            )
    return columns


def _descriptor_payload(descriptor: SnapshotTableDescriptor) -> dict[str, Any]:
    return {
        "table_name": descriptor.table_name,
        "display_table_name": descriptor.display_table_name,
        "columns": [
            {
                "name": column.name,
                "display_name": column.display_name,
                "nullable": column.nullable,
                "scalar_type": column.scalar_type,
            }
            for column in descriptor.columns
        ],
        "primary_key_columns": list(descriptor.primary_key_columns),
        "compare_key_columns": list(descriptor.compare_key_columns),
        "row_count": descriptor.row_count,
        "materialization_stage": descriptor.materialization_stage.value,
        "compare_schema_digest": descriptor.compare_schema_digest.value,
        "table_ruleset_version": descriptor.table_ruleset_version,
        "row_materialization_profile": descriptor.row_materialization_profile,
        "scalar_encoding_version": descriptor.scalar_encoding_version,
        "fast_row_digest": _digest_value(descriptor.fast_row_digest),
        "raw_content_digest": _digest_value(descriptor.raw_content_digest),
        "business_content_digest": None,
        "degraded_reason": (
            None if descriptor.degraded_reason is None else descriptor.degraded_reason.value
        ),
        "diagnostics": [_diagnostic_payload(item) for item in descriptor.diagnostics],
    }


def _descriptor_from_payload(payload: dict[str, Any]) -> SnapshotTableDescriptor:
    from gateway_backend.capabilities.snapshot_materialization.contracts import (
        MaterializationStage,
    )

    columns_payload = payload["columns"]
    if type(columns_payload) is not list:
        raise ValueError("descriptor columns must be a list")
    columns = tuple(
        SnapshotColumnDescriptor(
            name=str(item["name"]),
            display_name=str(item["display_name"]),
            nullable=bool(item["nullable"]),
            scalar_type=None if item.get("scalar_type") is None else str(item["scalar_type"]),
        )
        for item in columns_payload
    )
    degraded = payload.get("degraded_reason")
    return SnapshotTableDescriptor(
        table_name=str(payload["table_name"]),
        display_table_name=str(payload["display_table_name"]),
        columns=columns,
        primary_key_columns=tuple(str(name) for name in payload["primary_key_columns"]),
        compare_key_columns=tuple(str(name) for name in payload["compare_key_columns"]),
        row_count=int(payload["row_count"]),
        materialization_stage=MaterializationStage(str(payload["materialization_stage"])),
        compare_schema_digest=DigestRef(str(payload["compare_schema_digest"])),
        table_ruleset_version=int(payload["table_ruleset_version"]),
        row_materialization_profile=str(payload["row_materialization_profile"]),
        scalar_encoding_version=int(payload["scalar_encoding_version"]),
        fast_row_digest=_optional_digest(payload.get("fast_row_digest")),
        raw_content_digest=_optional_digest(payload.get("raw_content_digest")),
        degraded_reason=None if degraded is None else DegradedReason(str(degraded)),
        diagnostics=_diagnostics_from_payload(payload.get("diagnostics")),
    )


def _diagnostic_payload(item: MaterializationDiagnostic) -> dict[str, object]:
    return {
        "code": item.code.value,
        "severity": item.severity.value,
        "message": item.message,
        "table": item.table,
        "column": item.column,
    }


def _diagnostics_from_payload(payload: object) -> tuple[MaterializationDiagnostic, ...]:
    if payload is None:
        return ()
    if type(payload) is not list:
        raise ValueError("diagnostics must be a list")
    items: list[MaterializationDiagnostic] = []
    for item in payload:
        obj = _as_object(item)
        items.append(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode(str(obj["code"])),
                severity=DiagnosticSeverity(str(obj["severity"])),
                message=str(obj["message"]),
                table=None if obj.get("table") is None else str(obj["table"]),
                column=None if obj.get("column") is None else str(obj["column"]),
            )
        )
    return tuple(items)


def _as_object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("JSON object expected")
    return value


def _digest_value(digest: DigestRef | None) -> str | None:
    if digest is None:
        return None
    return digest.value


def _optional_digest(value: object) -> DigestRef | None:
    if value is None:
        return None
    return DigestRef(str(value))


def _opaque_id(namespace: str) -> str:
    return build_artifact_id(namespace, secrets.token_hex(8))


def _checkpoint(context: ParserInvocationContext, table: str) -> None:
    if context.cancel_requested.is_set():
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED,
            "materialization cancelled",
            table=table,
        )
    deadline = context.deadline_monotonic
    if deadline is not None and time.monotonic() >= deadline:
        raise ArtifactPublishError(
            MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT,
            "materialization deadline exceeded",
            table=table,
        )


def _map_open_error(exc: BaseException) -> MaterializationDiagnosticCode:
    message = str(exc)
    lowered = message.casefold()
    if "unknown" in lowered or "missing" in lowered:
        return MaterializationDiagnosticCode.ARTIFACT_TRUNCATED
    if "mismatch" in lowered or "sha256" in lowered or "digest" in lowered or "size" in lowered:
        return MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH
    return MaterializationDiagnosticCode.ARTIFACT_MANIFEST_CORRUPT
