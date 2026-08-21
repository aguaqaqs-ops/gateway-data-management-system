"""S5 comparison records artifacts, closure validation and publication.

The comparison kernels keep semantic records in immutable Python contracts.  This module owns the
separate, operation-local Parquet/manifest closure.  Artifact refs and closure metadata are never
part of the comparison or facts-core digests.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from tempfile import SpooledTemporaryFile
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from gateway_shared_kernel import (
    AnomalyScalar,
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
    raw_blob_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    artifact_ref_from_dict,
    artifact_ref_to_dict,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.comparison.contracts import (
    BLANK_RECORDS_SCHEMA_VERSION,
    ORDERED_RECORDS_SCHEMA_VERSION,
    RECORDS_ARTIFACT_CONTRACT_VERSION,
    RECORDS_CLOSURE_CONTRACT_VERSION,
    STANDARD_RECORDS_SCHEMA_VERSION,
    BlankRecord,
    ComparisonFacts,
    ComparisonRecord,
    ComparisonRecordsClosure,
    ComparisonTableFact,
    DetailedFactsResult,
    FailedResult,
    OrderedRecord,
    PairResultStatus,
    RecordsArtifactFamily,
    RecordsArtifactManifest,
    RecordsClosureEntry,
    RecordsDetailPolicy,
    CancelledResult,
)


PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"
MANIFEST_MEDIA_TYPE = "application/json"
_MAX_DEFAULT_RECORDS = 2_000_000
_MAX_DEFAULT_ARTIFACT_BYTES = 512 * 1024 * 1024
_MAX_DEFAULT_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_DEFAULT_CLOSURE_BYTES = 16 * 1024 * 1024
_MAX_DEFAULT_SPOOL_BYTES = 2 * 1024 * 1024 * 1024
_METADATA_PREFIX = b"gateway-vnext.records."


class RecordsPublicationError(ValueError):
    """A records artifact or closure cannot be published or verified."""


class RecordsCancelled(RecordsPublicationError):
    """Publication was cancelled or its deadline was reached."""


@dataclass(frozen=True, slots=True)
class RecordsPublicationPolicy:
    max_records_per_table: int = _MAX_DEFAULT_RECORDS
    max_records_artifact_bytes: int = _MAX_DEFAULT_ARTIFACT_BYTES
    max_manifest_json_bytes: int = _MAX_DEFAULT_MANIFEST_BYTES
    max_closure_json_bytes: int = _MAX_DEFAULT_CLOSURE_BYTES
    max_spool_bytes: int = _MAX_DEFAULT_SPOOL_BYTES

    def __post_init__(self) -> None:
        for name in (
            "max_records_per_table",
            "max_records_artifact_bytes",
            "max_manifest_json_bytes",
            "max_closure_json_bytes",
            "max_spool_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class RecordsPublicationContext:
    """Side-effect-free control hooks for bounded publication."""

    checkpoint: Callable[[], None] = lambda: None
    artifact_id_prefix: str = "comparison"

    def __post_init__(self) -> None:
        if not callable(self.checkpoint):
            raise ValueError("checkpoint must be callable")
        if type(self.artifact_id_prefix) is not str or self.artifact_id_prefix == "":
            raise ValueError("artifact_id_prefix must be non-empty")


def publish_records_closure(
    result: DetailedFactsResult,
    store: ArtifactStorePort,
    *,
    policy: RecordsPublicationPolicy | None = None,
    context: RecordsPublicationContext | None = None,
    detail_policy: RecordsDetailPolicy = RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
) -> DetailedFactsResult | CancelledResult | FailedResult:
    """Publish a complete detailed result behind a fail-closed closure gate."""

    if type(result) is not DetailedFactsResult:
        raise TypeError("result must be DetailedFactsResult")
    if not _is_artifact_store(store):
        raise TypeError("store must implement ArtifactStorePort")
    limits = policy or RecordsPublicationPolicy()
    control = context or RecordsPublicationContext()
    facts = result.facts
    if not isinstance(facts, ComparisonFacts):
        raise TypeError("detailed result must contain ComparisonFacts")
    if facts.records_ref is not None:
        raise ValueError("facts already has a records_ref")
    if type(detail_policy) is not RecordsDetailPolicy:
        raise TypeError("detail_policy must be RecordsDetailPolicy")

    try:
        entries: list[RecordsClosureEntry] = []
        for table in facts.tables:
            control.checkpoint()
            for family, records in _records_by_family(table):
                if not records:
                    continue
                if len(records) > limits.max_records_per_table:
                    raise RecordsPublicationError(
                        f"records limit exceeded for {table.table_name}/{family.value}"
                    )
                entries.append(
                    _publish_family(
                        table,
                        family,
                        records,
                        store,
                        limits,
                        control,
                        detail_policy,
                    )
                )

        control.checkpoint()
        closure_payload = _closure_payload(
            comparison_digest=facts.comparison_digest,
            facts_core_digest=facts.facts_core_digest,
            records=tuple(sorted(entries, key=_entry_sort_key)),
        )
        closure_bytes = canonicalize_json_value(closure_payload)
        if len(closure_bytes) > limits.max_closure_json_bytes:
            raise RecordsPublicationError("closure JSON budget exceeded")
        closure_ref = put_with_built_ref(
            store,
            closure_bytes,
            artifact_id=_artifact_id(control, "closure", raw_blob_digest(closure_bytes)),
            media_type=MANIFEST_MEDIA_TYPE,
        )
        _verify_stored_bytes(store, closure_ref, closure_bytes)
        verified_closure_bytes = _locate(store, closure_ref)
        verified_closure_payload = _load_json_object(verified_closure_bytes, "closure")
        if _entries_from_payload(verified_closure_payload) != tuple(
            sorted(entries, key=_entry_sort_key)
        ):
            raise RecordsPublicationError("stored closure entries changed during publication")
        if (
            _digest_from_payload(verified_closure_payload, "comparison_digest")
            != facts.comparison_digest
            or _digest_from_payload(verified_closure_payload, "facts_core_digest")
            != facts.facts_core_digest
        ):
            raise RecordsPublicationError("stored closure digests changed during publication")
        closure_digest = raw_blob_digest(closure_bytes)
        closure = ComparisonRecordsClosure(
            comparison_digest=facts.comparison_digest,
            facts_core_digest=facts.facts_core_digest,
            records=tuple(sorted(entries, key=_entry_sort_key)),
            closure_manifest_digest=closure_digest,
        )
        final_facts = replace(facts, records_ref=closure_ref)
        return DetailedFactsResult(
            pair_id=result.pair_id,
            status=result.status,
            facts=final_facts,
            records_closure=closure,
            diagnostics=result.diagnostics,
        )
    except RecordsCancelled as exc:
        return CancelledResult(
            pair_id=result.pair_id,
            status=_cancelled_status(),
            diagnostics=(str(exc) or "RECORDS_PUBLICATION_CANCELLED",),
        )
    except Exception as exc:
        return FailedResult(
            pair_id=result.pair_id,
            status=_failed_status(),
            diagnostics=(str(exc) or type(exc).__name__,),
        )


def open_records_closure(
    store: ArtifactStorePort,
    closure_ref: ArtifactRef,
    *,
    policy: RecordsPublicationPolicy | None = None,
) -> ComparisonRecordsClosure:
    """Load and fully validate a closure and every referenced Parquet/manifest artifact."""

    if not _is_artifact_store(store):
        raise TypeError("store must implement ArtifactStorePort")
    if type(closure_ref) is not ArtifactRef:
        raise TypeError("closure_ref must be ArtifactRef")
    if closure_ref.media_type != MANIFEST_MEDIA_TYPE:
        raise RecordsPublicationError("closure ref must identify JSON")
    limits = policy or RecordsPublicationPolicy()
    raw = _locate(store, closure_ref)
    if len(raw) > limits.max_closure_json_bytes:
        raise RecordsPublicationError("closure JSON budget exceeded")
    expected_digest = raw_blob_digest(raw)
    payload = _load_json_object(raw, "closure")
    entries = _entries_from_payload(payload)
    closure = ComparisonRecordsClosure(
        comparison_digest=_digest_from_payload(payload, "comparison_digest"),
        facts_core_digest=_digest_from_payload(payload, "facts_core_digest"),
        records=entries,
        closure_manifest_digest=expected_digest,
    )
    for entry in entries:
        if entry.records_ref.media_type != PARQUET_MEDIA_TYPE:
            raise RecordsPublicationError("records ref must identify Parquet")
        if entry.records_manifest_ref.media_type != MANIFEST_MEDIA_TYPE:
            raise RecordsPublicationError("records manifest ref must identify JSON")
        manifest_raw = _locate(store, entry.records_manifest_ref)
        if raw_blob_digest(manifest_raw) != entry.records_manifest_digest:
            raise RecordsPublicationError("records manifest digest mismatch")
        manifest = _manifest_from_bytes(manifest_raw)
        if (
            manifest.table_name != entry.table_name
            or manifest.family is not entry.family
            or manifest.content_digest != entry.records_content_digest
            or manifest.record_count != entry.record_count
        ):
            raise RecordsPublicationError("records manifest does not match closure entry")
        artifact_raw = _locate(store, entry.records_ref)
        actual_count, actual_content = _validate_parquet_bytes(
            artifact_raw,
            manifest,
            limits,
        )
        if actual_count != entry.record_count or actual_content != entry.records_content_digest:
            raise RecordsPublicationError("records artifact digest or count mismatch")
    return closure


def read_records_artifact(
    store: ArtifactStorePort,
    entry: RecordsClosureEntry,
    *,
    policy: RecordsPublicationPolicy | None = None,
) -> tuple[dict[str, object], ...]:
    """Read one validated artifact as its language-neutral Arrow row representation."""

    if not _is_artifact_store(store):
        raise TypeError("store must implement ArtifactStorePort")
    limits = policy or RecordsPublicationPolicy()
    if entry.records_ref.media_type != PARQUET_MEDIA_TYPE:
        raise RecordsPublicationError("records ref must identify Parquet")
    if entry.records_manifest_ref.media_type != MANIFEST_MEDIA_TYPE:
        raise RecordsPublicationError("records manifest ref must identify JSON")
    manifest_raw = _locate(store, entry.records_manifest_ref)
    if raw_blob_digest(manifest_raw) != entry.records_manifest_digest:
        raise RecordsPublicationError("records manifest digest mismatch")
    manifest = _manifest_from_bytes(manifest_raw)
    if (
        manifest.table_name != entry.table_name
        or manifest.family is not entry.family
        or manifest.content_digest != entry.records_content_digest
        or manifest.record_count != entry.record_count
    ):
        raise RecordsPublicationError("records manifest does not match closure entry")
    return _read_parquet_rows(_locate(store, entry.records_ref), manifest, limits)


def rewrite_closure_refs(
    closure: ComparisonRecordsClosure,
    replacements: Mapping[ArtifactRef, ArtifactRef],
) -> ComparisonRecordsClosure:
    """Rewrite only operation-local refs and produce a new closure digest."""

    if type(closure) is not ComparisonRecordsClosure:
        raise TypeError("closure must be ComparisonRecordsClosure")
    if not isinstance(replacements, Mapping):
        raise TypeError("replacements must be a mapping")
    entries = tuple(
        replace(
            entry,
            records_ref=replacements.get(entry.records_ref, entry.records_ref),
            records_manifest_ref=replacements.get(
                entry.records_manifest_ref, entry.records_manifest_ref
            ),
        )
        for entry in closure.records
    )
    payload = _closure_payload(
        comparison_digest=closure.comparison_digest,
        facts_core_digest=closure.facts_core_digest,
        records=entries,
    )
    return ComparisonRecordsClosure(
        comparison_digest=closure.comparison_digest,
        facts_core_digest=closure.facts_core_digest,
        records=tuple(sorted(entries, key=_entry_sort_key)),
        closure_manifest_digest=raw_blob_digest(canonicalize_json_value(payload)),
    )


@dataclass(frozen=True, slots=True)
class RestoredRecordsClosure:
    """A fully verified closure copied into a new artifact scope."""

    closure_ref: ArtifactRef
    closure: ComparisonRecordsClosure


def restore_records_closure(
    source_store: ArtifactStorePort,
    destination_store: ArtifactStorePort,
    closure_ref: ArtifactRef,
    *,
    policy: RecordsPublicationPolicy | None = None,
    context: RecordsPublicationContext | None = None,
) -> RestoredRecordsClosure:
    """Copy a validated records closure and rewrite its refs into a new artifact scope.

    The source closure and every referenced artifact are verified before they are exposed to the
    caller.  The destination closure is reopened and verified after publication as well.  A
    rewritten closure changes only operation-local artifact refs and its closure digest; semantic
    comparison and records digests remain unchanged.
    """

    if not _is_artifact_store(source_store) or not _is_artifact_store(destination_store):
        raise TypeError("source_store and destination_store must implement ArtifactStorePort")
    limits = policy or RecordsPublicationPolicy()
    control = context or RecordsPublicationContext()
    source = open_records_closure(source_store, closure_ref, policy=limits)
    replacements: dict[ArtifactRef, ArtifactRef] = {}
    for entry in source.records:
        records_raw = _locate(source_store, entry.records_ref)
        records_ref = put_with_built_ref(
            destination_store,
            records_raw,
            artifact_id=_artifact_id(control, "records", entry.records_ref.raw_sha256),
            media_type=entry.records_ref.media_type,
        )
        _verify_stored_bytes(destination_store, records_ref, records_raw)
        replacements[entry.records_ref] = records_ref

        manifest_raw = _locate(source_store, entry.records_manifest_ref)
        manifest_ref = put_with_built_ref(
            destination_store,
            manifest_raw,
            artifact_id=_artifact_id(control, "manifest", entry.records_manifest_digest),
            media_type=entry.records_manifest_ref.media_type,
        )
        _verify_stored_bytes(destination_store, manifest_ref, manifest_raw)
        replacements[entry.records_manifest_ref] = manifest_ref

    rewritten = rewrite_closure_refs(source, replacements)
    closure_bytes = canonicalize_json_value(
        _closure_payload(
            comparison_digest=rewritten.comparison_digest,
            facts_core_digest=rewritten.facts_core_digest,
            records=rewritten.records,
        )
    )
    if len(closure_bytes) > limits.max_closure_json_bytes:
        raise RecordsPublicationError("closure JSON budget exceeded")
    restored_ref = put_with_built_ref(
        destination_store,
        closure_bytes,
        artifact_id=_artifact_id(control, "closure", rewritten.closure_manifest_digest),
        media_type=MANIFEST_MEDIA_TYPE,
    )
    _verify_stored_bytes(destination_store, restored_ref, closure_bytes)
    reopened = open_records_closure(destination_store, restored_ref, policy=limits)
    if reopened != rewritten:
        raise RecordsPublicationError("restored closure changed during publication")
    return RestoredRecordsClosure(closure_ref=restored_ref, closure=reopened)


def _publish_family(
    table: ComparisonTableFact,
    family: RecordsArtifactFamily,
    records: tuple[object, ...],
    store: ArtifactStorePort,
    limits: RecordsPublicationPolicy,
    context: RecordsPublicationContext,
    detail_policy: RecordsDetailPolicy,
) -> RecordsClosureEntry:
    schema_version = _schema_version(family)
    rows = tuple(
        _record_to_row(family, record, detail_policy)
        for record in sorted(records, key=lambda item: _record_sort_key(family, item))
    )
    row_keys = tuple(
        canonicalize_json_value(_json_safe(row))
        for row in rows
    )
    if len(set(row_keys)) != len(row_keys):
        raise RecordsPublicationError("records family contains duplicate logical rows")
    content_digest = _content_digest(family, schema_version, detail_policy, rows)
    parquet_bytes = _write_parquet(
        family,
        rows,
        limits,
        context,
        detail_policy,
    )
    records_ref = put_with_built_ref(
        store,
        parquet_bytes,
        artifact_id=_artifact_id(context, family.value.lower(), content_digest),
        media_type=PARQUET_MEDIA_TYPE,
    )
    _verify_stored_bytes(store, records_ref, parquet_bytes)
    manifest = RecordsArtifactManifest(
        table_name=table.table_name,
        family=family,
        record_format="PARQUET",
        schema_version=schema_version,
        row_diff_detail_policy=detail_policy,
        record_count=len(rows),
        content_digest=content_digest,
    )
    manifest_bytes = canonicalize_json_value(_manifest_payload(manifest))
    if len(manifest_bytes) > limits.max_manifest_json_bytes:
        raise RecordsPublicationError("records manifest JSON budget exceeded")
    manifest_ref = put_with_built_ref(
        store,
        manifest_bytes,
        artifact_id=_artifact_id(context, f"{family.value.lower()}-manifest", raw_blob_digest(manifest_bytes)),
        media_type=MANIFEST_MEDIA_TYPE,
    )
    _verify_stored_bytes(store, manifest_ref, manifest_bytes)
    verified_manifest = _manifest_from_bytes(_locate(store, manifest_ref))
    if verified_manifest != manifest:
        raise RecordsPublicationError("stored records manifest changed during publication")
    actual_count, actual_digest = _validate_parquet_bytes(
        _locate(store, records_ref),
        verified_manifest,
        limits,
    )
    if actual_count != manifest.record_count or actual_digest != manifest.content_digest:
        raise RecordsPublicationError("stored records artifact failed publication validation")
    return RecordsClosureEntry(
        table_name=table.table_name,
        family=family,
        records_ref=records_ref,
        records_manifest_ref=manifest_ref,
        records_manifest_digest=raw_blob_digest(manifest_bytes),
        records_content_digest=content_digest,
        record_count=len(rows),
    )


def _write_parquet(
    family: RecordsArtifactFamily,
    rows: tuple[dict[str, object], ...],
    limits: RecordsPublicationPolicy,
    context: RecordsPublicationContext,
    detail_policy: RecordsDetailPolicy,
) -> bytes:
    context.checkpoint()
    schema_version = _schema_version(family)
    schema = _schema_for(family, schema_version, detail_policy)
    spool = SpooledTemporaryFile(max_size=limits.max_spool_bytes, mode="w+b")
    writer: pq.ParquetWriter | None = None
    try:
        writer = pq.ParquetWriter(spool, schema, compression="zstd", use_dictionary=False)
        for offset in range(0, len(rows), 1024):
            context.checkpoint()
            batch_rows = rows[offset : offset + 1024]
            table = pa.Table.from_pylist(list(batch_rows), schema=schema)
            writer.write_table(table, row_group_size=len(batch_rows))
            spool.seek(0, 2)
            if spool.tell() > limits.max_records_artifact_bytes:
                raise RecordsPublicationError("records artifact budget exceeded")
            if spool.tell() > limits.max_spool_bytes:
                raise RecordsPublicationError("records spool budget exceeded")
        writer.close()
        writer = None
        spool.seek(0, 2)
        size = spool.tell()
        if size > limits.max_records_artifact_bytes or size > limits.max_spool_bytes:
            raise RecordsPublicationError("records artifact or spool budget exceeded")
        spool.seek(0)
        result = spool.read()
        if type(result) is not bytes or len(result) != size:
            raise RecordsPublicationError("records artifact spool read failed")
        context.checkpoint()
        return result
    except (pa.ArrowException, OSError, ValueError) as exc:
        if isinstance(exc, RecordsPublicationError):
            raise
        raise RecordsPublicationError("records Parquet write failed") from exc
    finally:
        if writer is not None:
            writer.close()
        spool.close()


def _validate_parquet_bytes(
    raw: bytes,
    manifest: RecordsArtifactManifest,
    limits: RecordsPublicationPolicy,
) -> tuple[int, DigestRef]:
    if len(raw) > limits.max_records_artifact_bytes:
        raise RecordsPublicationError("records artifact budget exceeded")
    try:
        file = pq.ParquetFile(pa.BufferReader(raw))
        expected_schema = _schema_for(
            manifest.family,
            manifest.schema_version,
            manifest.row_diff_detail_policy,
        )
        actual_schema = file.schema_arrow
        if not _schema_matches(actual_schema, expected_schema):
            raise RecordsPublicationError("records Parquet schema mismatch")
        rows = _read_parquet_rows_from_file(file)
    except (OSError, pa.ArrowException, ValueError) as exc:
        if isinstance(exc, RecordsPublicationError):
            raise
        raise RecordsPublicationError("records Parquet is corrupt") from exc
    if len(rows) != manifest.record_count:
        raise RecordsPublicationError("records Parquet count mismatch")
    digest = _content_digest(
        manifest.family,
        manifest.schema_version,
        manifest.row_diff_detail_policy,
        rows,
    )
    if digest != manifest.content_digest:
        raise RecordsPublicationError("records content digest mismatch")
    return len(rows), digest


def _read_parquet_rows(
    raw: bytes,
    manifest: RecordsArtifactManifest,
    limits: RecordsPublicationPolicy,
) -> tuple[dict[str, object], ...]:
    if len(raw) > limits.max_records_artifact_bytes:
        raise RecordsPublicationError("records artifact budget exceeded")
    try:
        file = pq.ParquetFile(pa.BufferReader(raw))
        if not _schema_matches(
            file.schema_arrow,
            _schema_for(
                manifest.family,
                manifest.schema_version,
                manifest.row_diff_detail_policy,
            ),
        ):
            raise RecordsPublicationError("records Parquet schema mismatch")
        rows = _read_parquet_rows_from_file(file)
    except (OSError, pa.ArrowException, ValueError) as exc:
        if isinstance(exc, RecordsPublicationError):
            raise
        raise RecordsPublicationError("records Parquet is corrupt") from exc
    digest = _content_digest(
        manifest.family,
        manifest.schema_version,
        manifest.row_diff_detail_policy,
        rows,
    )
    if len(rows) != manifest.record_count or digest != manifest.content_digest:
        raise RecordsPublicationError("records content digest or count mismatch")
    return rows


def _read_parquet_rows_from_file(file: pq.ParquetFile) -> tuple[dict[str, object], ...]:
    table = file.read()
    return tuple(cast(tuple[dict[str, object], ...], tuple(table.to_pylist())))


def _schema_matches(actual: pa.Schema, expected: pa.Schema) -> bool:
    if not actual.equals(expected, check_metadata=False):
        return False
    expected_metadata = expected.metadata or {}
    actual_metadata = actual.metadata or {}
    return all(actual_metadata.get(key) == value for key, value in expected_metadata.items())


def _schema_for(
    family: RecordsArtifactFamily,
    schema_version: str | None = None,
    detail_policy: RecordsDetailPolicy | None = None,
) -> pa.Schema:
    scalar = pa.struct(
        [
            pa.field("kind", pa.string(), nullable=False),
            pa.field("text", pa.string(), nullable=True),
            pa.field("raw_bytes", pa.binary(), nullable=True),
            pa.field("boolean", pa.bool_(), nullable=True),
            pa.field("items", pa.list_(pa.string()), nullable=True),
            pa.field("anomaly_json", pa.binary(), nullable=True),
        ]
    )
    values = pa.list_(
        pa.struct(
            [
                pa.field("column_name", pa.string(), nullable=False),
                pa.field("value", scalar, nullable=False),
            ]
        )
    )
    field_changes = pa.list_(
        pa.struct(
            [
                pa.field("column_name", pa.string(), nullable=False),
                pa.field("before_value", scalar, nullable=True),
                pa.field("current_value", scalar, nullable=True),
            ]
        )
    )
    common = [
        pa.field("table_name", pa.string(), nullable=False),
        pa.field("record_kind", pa.string(), nullable=False),
        pa.field("row_identity", pa.binary(32), nullable=True),
        pa.field("changed_columns", pa.list_(pa.string()), nullable=False),
        pa.field("before_values", values, nullable=False),
        pa.field("current_values", values, nullable=False),
        pa.field("diagnostics", pa.list_(pa.string()), nullable=False),
    ]
    if family is RecordsArtifactFamily.STANDARD:
        fields = common[:]
        fields.insert(6, pa.field("field_changes", field_changes, nullable=False))
    elif family is RecordsArtifactFamily.ORDERED:
        fields = [
            common[0],
            common[1],
            pa.field("semantic_kind", pa.string(), nullable=False),
            pa.field("entity_key_kind", pa.string(), nullable=False),
            common[2],
            pa.field("before_position", pa.int64(), nullable=True),
            pa.field("current_position", pa.int64(), nullable=True),
            common[3],
            common[4],
            common[5],
            common[6],
        ]
    else:
        interval = pa.struct(
            [
                pa.field("before_start", pa.int64(), nullable=True),
                pa.field("before_end", pa.int64(), nullable=True),
                pa.field("current_start", pa.int64(), nullable=True),
                pa.field("current_end", pa.int64(), nullable=True),
                pa.field("row_count", pa.int64(), nullable=False),
                pa.field("interval_digest", pa.binary(32), nullable=True),
            ]
        )
        fields = [
            common[0],
            common[1],
            pa.field("semantic_kind", pa.string(), nullable=False),
            pa.field("interval", interval, nullable=False),
            pa.field("before_occupancy", pa.int64(), nullable=False),
            pa.field("current_occupancy", pa.int64(), nullable=False),
            common[6],
        ]
    metadata = {
        _METADATA_PREFIX + b"contract_version": RECORDS_ARTIFACT_CONTRACT_VERSION.encode(),
        _METADATA_PREFIX + b"family": family.value.encode(),
        _METADATA_PREFIX + b"schema_version": (
            (schema_version or _schema_version(family)).encode()
        ),
        _METADATA_PREFIX + b"row_diff_detail_policy": (
            (detail_policy or RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES).value.encode()
        ),
    }
    return pa.schema(fields, metadata=metadata)


def _records_by_family(
    table: ComparisonTableFact,
) -> tuple[tuple[RecordsArtifactFamily, tuple[object, ...]], ...]:
    result: list[tuple[RecordsArtifactFamily, tuple[object, ...]]] = []
    if table.records:
        result.append((RecordsArtifactFamily.STANDARD, tuple(table.records)))
    if table.ordered_extension is not None and table.ordered_extension.records:
        result.append((RecordsArtifactFamily.ORDERED, tuple(table.ordered_extension.records)))
    if table.blank_extension is not None and table.blank_extension.records:
        result.append((RecordsArtifactFamily.BLANK, tuple(table.blank_extension.records)))
    return tuple(result)


def _record_to_row(
    family: RecordsArtifactFamily,
    record: object,
    detail_policy: RecordsDetailPolicy,
) -> dict[str, object]:
    if family is RecordsArtifactFamily.STANDARD:
        if not isinstance(record, ComparisonRecord):
            raise RecordsPublicationError("standard family contains a non-standard record")
        full = detail_policy is RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES
        columns = list(record.changed_columns) if detail_policy is not RecordsDetailPolicy.COUNTS_ONLY else []
        return {
            "table_name": record.table_name,
            "record_kind": record.record_kind.value,
            "row_identity": _digest_bytes(record.row_identity),
            "changed_columns": columns,
            "before_values": _values(record.before_values if full else ()),
            "current_values": _values(record.current_values if full else ()),
            "field_changes": (
                [
                    {
                        "column_name": item.column_name,
                        "before_value": _scalar(item.before_value),
                        "current_value": _scalar(item.current_value),
                    }
                    for item in record.field_changes
                ]
                if full
                else []
            ),
            "diagnostics": list(record.diagnostics),
        }
    if family is RecordsArtifactFamily.ORDERED:
        if not isinstance(record, OrderedRecord):
            raise RecordsPublicationError("ordered family contains a non-ordered record")
        full = detail_policy is RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES
        return {
            "table_name": record.table_name,
            "record_kind": record.record_kind.value,
            "semantic_kind": record.semantic_kind.value,
            "entity_key_kind": record.entity_key_kind.value,
            "row_identity": _digest_bytes(record.row_identity),
            "before_position": record.before_position,
            "current_position": record.current_position,
            "changed_columns": list(record.changed_columns)
            if detail_policy is not RecordsDetailPolicy.COUNTS_ONLY
            else [],
            "before_values": _values(record.before_values if full else ()),
            "current_values": _values(record.current_values if full else ()),
            "diagnostics": list(record.diagnostics),
        }
    if not isinstance(record, BlankRecord):
        raise RecordsPublicationError("blank family contains a non-blank record")
    interval = record.interval
    return {
        "table_name": record.table_name,
        "record_kind": record.record_kind.value,
        "semantic_kind": record.semantic_kind.value,
        "interval": {
            "before_start": interval.before_start,
            "before_end": interval.before_end,
            "current_start": interval.current_start,
            "current_end": interval.current_end,
            "row_count": interval.row_count,
            "interval_digest": _digest_bytes(interval.interval_digest),
        },
        "before_occupancy": record.before_occupancy,
        "current_occupancy": record.current_occupancy,
        "diagnostics": list(record.diagnostics),
    }


def _values(values: tuple[tuple[str, object], ...]) -> list[dict[str, object]]:
    return [{"column_name": name, "value": _scalar(value)} for name, value in values]


def _scalar(value: object) -> dict[str, object]:
    if isinstance(value, NullScalar) or value is None:
        return {
            "kind": "null",
            "text": None,
            "raw_bytes": None,
            "boolean": None,
            "items": None,
            "anomaly_json": None,
        }
    if isinstance(value, BooleanScalar):
        return _scalar_base(value.kind, boolean=value.value)
    if isinstance(value, (SignedIntegerScalar, UnsignedIntegerScalar, DecimalScalar)):
        return _scalar_base(value.kind, text=value.decimal)
    if isinstance(value, (Float32Scalar, Float64Scalar)):
        return _scalar_base(value.kind, text=value.bits_hex)
    if isinstance(value, (StringScalar, DateScalar, DateTimeScalar, TimestampScalar, TimeDurationScalar)):
        return _scalar_base(value.kind, text=value.text)
    if isinstance(value, (BinaryScalar, BitScalar)):
        return _scalar_base(value.kind, raw_bytes=value.raw_bytes)
    if isinstance(value, AnomalyScalar):
        return _scalar_base(
            value.kind,
            anomaly_json=canonicalize_json_value(dict(value.envelope)),
        )
    members = getattr(value, "members", None)
    if type(members) is tuple and all(type(item) is str for item in members):
        return _scalar_base("set", items=list(members))
    raise RecordsPublicationError(f"unsupported typed record value: {type(value).__name__}")


def _scalar_base(kind: str, **values: object) -> dict[str, object]:
    result: dict[str, object] = {
        "kind": kind,
        "text": None,
        "raw_bytes": None,
        "boolean": None,
        "items": None,
        "anomaly_json": None,
    }
    result.update(values)
    return result


def _record_sort_key(family: RecordsArtifactFamily, record: object) -> tuple[object, ...]:
    row = _record_to_row(family, record, RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES)
    return (
        str(row.get("record_kind", "")),
        _bytes_sort(row.get("row_identity")),
        _optional_position(row.get("before_position")),
        _optional_position(row.get("current_position")),
        canonicalize_json_value(_json_safe(row)).decode("utf-8"),
    )


def _content_digest(
    family: RecordsArtifactFamily,
    schema_version: str,
    detail_policy: RecordsDetailPolicy,
    rows: tuple[dict[str, object], ...],
) -> DigestRef:
    payload = {
        "kind": "comparison-records-content",
        "family": family.value,
        "schema_version": schema_version,
        "row_diff_detail_policy": detail_policy.value,
        "rows": [_json_safe(row) for row in rows],
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def _manifest_payload(manifest: RecordsArtifactManifest) -> dict[str, object]:
    return {
        "contract_version": manifest.contract_version,
        "table_name": manifest.table_name,
        "family": manifest.family.value,
        "record_format": manifest.record_format,
        "schema_version": manifest.schema_version,
        "row_diff_detail_policy": manifest.row_diff_detail_policy.value,
        "record_count": manifest.record_count,
        "content_digest": manifest.content_digest.value,
    }


def _manifest_from_bytes(raw: bytes) -> RecordsArtifactManifest:
    payload = _load_json_object(raw, "records manifest")
    try:
        return RecordsArtifactManifest(
            contract_version=_string(payload, "contract_version"),
            table_name=_string(payload, "table_name"),
            family=RecordsArtifactFamily(_string(payload, "family")),
            record_format=_string(payload, "record_format"),
            schema_version=_string(payload, "schema_version"),
            row_diff_detail_policy=RecordsDetailPolicy(
                _string(payload, "row_diff_detail_policy")
            ),
            record_count=_integer(payload, "record_count"),
            content_digest=_digest_from_payload(payload, "content_digest"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RecordsPublicationError("records manifest is invalid") from exc


def _closure_payload(
    *,
    comparison_digest: DigestRef,
    facts_core_digest: DigestRef,
    records: tuple[RecordsClosureEntry, ...],
) -> dict[str, object]:
    return {
        "closure_contract_version": RECORDS_CLOSURE_CONTRACT_VERSION,
        "comparison_digest": comparison_digest.value,
        "facts_core_digest": facts_core_digest.value,
        "records": [
            {
                "table_name": entry.table_name,
                "family": entry.family.value,
                "records_ref": artifact_ref_to_dict(entry.records_ref),
                "records_manifest_ref": artifact_ref_to_dict(entry.records_manifest_ref),
                "records_manifest_digest": entry.records_manifest_digest.value,
                "records_content_digest": entry.records_content_digest.value,
                "record_count": entry.record_count,
            }
            for entry in sorted(records, key=_entry_sort_key)
        ],
    }


def _entries_from_payload(payload: dict[str, object]) -> tuple[RecordsClosureEntry, ...]:
    if _string(payload, "closure_contract_version") != RECORDS_CLOSURE_CONTRACT_VERSION:
        raise RecordsPublicationError("unsupported records closure contract version")
    raw_records = payload.get("records")
    if type(raw_records) is not list:
        raise RecordsPublicationError("closure records must be a list")
    entries: list[RecordsClosureEntry] = []
    try:
        for raw in raw_records:
            if type(raw) is not dict:
                raise ValueError("closure entry must be an object")
            item = cast(dict[str, object], raw)
            entries.append(
                RecordsClosureEntry(
                    table_name=_string(item, "table_name"),
                    family=RecordsArtifactFamily(_string(item, "family")),
                    records_ref=artifact_ref_from_dict(_object(item, "records_ref")),
                    records_manifest_ref=artifact_ref_from_dict(
                        _object(item, "records_manifest_ref")
                    ),
                    records_manifest_digest=_digest_from_payload(
                        item, "records_manifest_digest"
                    ),
                    records_content_digest=_digest_from_payload(item, "records_content_digest"),
                    record_count=_integer(item, "record_count"),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, RecordsPublicationError):
            raise
        raise RecordsPublicationError("closure entry is invalid") from exc
    return tuple(sorted(entries, key=_entry_sort_key))


def _entry_sort_key(entry: RecordsClosureEntry) -> tuple[str, str]:
    return (entry.table_name, entry.family.value)


def _schema_version(family: RecordsArtifactFamily) -> str:
    return {
        RecordsArtifactFamily.STANDARD: STANDARD_RECORDS_SCHEMA_VERSION,
        RecordsArtifactFamily.ORDERED: ORDERED_RECORDS_SCHEMA_VERSION,
        RecordsArtifactFamily.BLANK: BLANK_RECORDS_SCHEMA_VERSION,
    }[family]


def _artifact_id(
    context: RecordsPublicationContext,
    suffix: str,
    digest: DigestRef,
) -> str:
    digest_suffix = digest.value.removeprefix("sha256:")
    return build_artifact_id(
        context.artifact_id_prefix,
        f"{suffix}-{digest_suffix}",
    )


def _verify_stored_bytes(store: ArtifactStorePort, ref: ArtifactRef, expected: bytes) -> None:
    actual = _locate(store, ref)
    if actual != expected:
        raise RecordsPublicationError("stored artifact bytes changed during publication")


def _locate(store: ArtifactStorePort, ref: ArtifactRef) -> bytes:
    try:
        raw = store.locate(ref)
    except Exception as exc:
        raise RecordsPublicationError("artifact store locate failed") from exc
    if type(raw) is not bytes:
        raise RecordsPublicationError("artifact store returned non-bytes")
    return raw


def _is_artifact_store(value: object) -> bool:
    return callable(getattr(value, "put", None)) and callable(getattr(value, "locate", None))


def _load_json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordsPublicationError(f"{label} JSON is corrupt") from exc
    if type(value) is not dict or not all(type(key) is str for key in value):
        raise RecordsPublicationError(f"{label} JSON must be an object")
    typed = cast(dict[str, object], value)
    if canonicalize_json_value(typed) != raw:
        raise RecordsPublicationError(f"{label} JSON is not canonical")
    return typed


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if type(value) is not dict:
        raise ValueError(f"{key} must be an object")
    return cast(dict[str, object], value)


def _string(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str or value == "":
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _digest_from_payload(payload: dict[str, object], key: str) -> DigestRef:
    return DigestRef(_string(payload, key))


def _digest_bytes(value: DigestRef | None) -> bytes | None:
    if value is None:
        return None
    return bytes.fromhex(value.value.removeprefix("sha256:"))


def _bytes_sort(value: object) -> bytes:
    return value if type(value) is bytes else b""


def _optional_position(value: object) -> int:
    return value if type(value) is int else 0


def _json_safe(value: object) -> object:
    if type(value) is bytes:
        return {"bytes_hex": value.hex()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _cancelled_status() -> PairResultStatus:
    return PairResultStatus.CANCELLED


def _failed_status() -> PairResultStatus:
    return PairResultStatus.FAILED
