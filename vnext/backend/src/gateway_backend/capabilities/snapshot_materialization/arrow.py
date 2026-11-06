"""Snapshot values backed by retained Arrow buffers and the single business kernel."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.snapshot_materialization._digest import compare_schema_digest
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.batch import schema_with_batch_metadata
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE, DegradedReason, DiagnosticSeverity,
    MaterializationDiagnostic, MaterializationDiagnosticCode, MaterializationStage,
    SnapshotColumnDescriptor, SnapshotTable, SnapshotTableBatchMetadata,
    SnapshotTableDescriptor, SnapshotTableOrderedMetadata, BlankRowProvenance,
)
from gateway_backend.capabilities.snapshot_materialization.native import materialize_arrow_table
from gateway_backend.capabilities.table_access import (
    ArrowSourceTableReader, current_kernel_context, source_arrow_metadata,
    source_descriptor_from_arrow,
)
from gateway_backend.capabilities.table_access.contracts import SourceTableDescriptor


def operation_business_budgets() -> dict[str, int]:
    context = current_kernel_context()
    if context is None:
        raise ValueError("business Arrow work requires an operation kernel context")
    return {
        "max_columns": 2048, "max_batches": 4096, "max_rows": 10_000_000,
        "max_metadata_bytes": 16 * 1024**2, "max_input_bytes": 1024**3,
        "max_live_bytes": context.memory.available_bytes, "max_output_bytes": 1024**3,
        "max_diagnostic_bytes": 512 * 1024,
    }


def operation_codec_budgets() -> dict[str, int]:
    business = operation_business_budgets()
    return {
        "max_columns": business["max_columns"], "max_input_batches": business["max_batches"],
        "max_rows": business["max_rows"], "max_descriptor_bytes": business["max_metadata_bytes"],
        "max_input_bytes": business["max_input_bytes"], "max_output_bytes": business["max_output_bytes"],
        "max_codec_peak_bytes": business["max_live_bytes"],
    }


class ArrowSnapshotTableReader(BoundSnapshotTableReader):
    def __init__(self, descriptor: SnapshotTableDescriptor, source: ArrowSourceTableReader) -> None:
        super().__init__(descriptor, source)
        self._arrow_source = source

    def arrow_stream(self) -> pa.RecordBatchReader:
        self._require_open()
        return self._arrow_source.arrow_stream()

    def reopen(self) -> ArrowSnapshotTableReader:
        self._require_open()
        return ArrowSnapshotTableReader(self._descriptor, self._arrow_source.reopen())


class ArrowSnapshotTableBatchReader:
    def __init__(self, reader: ArrowSnapshotTableReader, metadata: SnapshotTableBatchMetadata) -> None:
        self._reader = reader
        self._metadata = metadata
        self._closed = False
        isolated = reader.reopen()
        try:
            with isolated.arrow_stream() as stream:
                self._schema = schema_with_batch_metadata(stream.schema, metadata)
        finally:
            isolated.close()

    def descriptor(self) -> SnapshotTableDescriptor:
        return self._reader.descriptor()

    def schema(self) -> pa.Schema:
        if self._closed:
            raise ValueError("batch reader is closed")
        return self._schema

    def metadata(self) -> SnapshotTableBatchMetadata:
        return self._metadata

    def iter_record_batches(self) -> Iterator[pa.RecordBatch]:
        with self._reader.arrow_stream() as stream:
            for batch in stream:
                yield batch.replace_schema_metadata(self._schema.metadata)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._reader.close()

    def reopen(self) -> ArrowSnapshotTableBatchReader:
        return ArrowSnapshotTableBatchReader(self._reader.reopen(), self._metadata)


def snapshot_table_from_arrow(
    descriptor: SnapshotTableDescriptor, table: pa.Table, source: SourceTableDescriptor,
    *, ordered: SnapshotTableOrderedMetadata | None = None,
) -> SnapshotTable:
    context = current_kernel_context()
    if context is None:
        raise ValueError("snapshot Arrow backing requires an operation kernel context")
    reader = ArrowSnapshotTableReader(descriptor, ArrowSourceTableReader(source, table, context))
    try:
        batch = ArrowSnapshotTableBatchReader(reader.reopen(), SnapshotTableBatchMetadata(
            blank_provenance=BlankRowProvenance.NONE if ordered is None else ordered.blank_provenance))
    except BaseException:
        reader.close()
        raise
    return SnapshotTable(descriptor, reader, descriptor.diagnostics, batch_reader=batch, ordered_metadata=ordered)


def materialize_source_arrow(
    reader: ArrowSourceTableReader, *, compare_keys: tuple[str, ...],
    stage: MaterializationStage, table_ruleset_version: int,
) -> tuple[SnapshotTableDescriptor, SnapshotTable | None, tuple[MaterializationDiagnostic, ...]]:
    source = reader.descriptor()
    context = current_kernel_context()
    if context is None:
        raise ValueError("SQL Arrow materialization requires an operation kernel context")
    isolated = reader.reopen()
    try:
        with isolated.arrow_stream() as stream:
            result = materialize_arrow_table(
                source_arrow_metadata(source, stream), effective_compare_key_columns=compare_keys,
                stage=stage, cancel_probe=context.cancel_probe, budgets=operation_business_budgets(),
                deadline_monotonic=context.deadline_monotonic, pool_threads=context.threads,
            )
    finally:
        isolated.close()
    diagnostics = tuple(MaterializationDiagnostic(
        code=MaterializationDiagnosticCode(d["code"]), severity=DiagnosticSeverity(d["severity"]),
        message=d["message"], table=d["table"], column=d["column"],
    ) for d in result["diagnostics"])
    output: dict[str, Any] | None = result["output"]
    descriptor = SnapshotTableDescriptor(
        table_name=source.canonical_name, display_table_name=source.display_name,
        columns=tuple(SnapshotColumnDescriptor(c.canonical_name, c.display_name, c.nullable, c.sql_type) for c in source.columns),
        primary_key_columns=source.primary_key_canonical_names, compare_key_columns=compare_keys,
        row_count=reader.row_count if output is not None else 0, materialization_stage=stage,
        compare_schema_digest=compare_schema_digest(source.canonical_name, tuple(c.canonical_name for c in source.columns), compare_keys),
        table_ruleset_version=table_ruleset_version, row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=1, raw_content_digest=None if output is None or output["raw_content_digest"] is None else DigestRef(output["raw_content_digest"]),
        degraded_reason=DegradedReason.TABLE_FAILED if output is None else DegradedReason.KEYLESS if not compare_keys else
            DegradedReason.DUPLICATE_EFFECTIVE_KEY if output["duplicate_effective_key"] else None,
        diagnostics=diagnostics,
    )
    if output is None:
        return descriptor, None, diagnostics
    metadata = output["tables"][0]
    with metadata["arrow_stream"] as stream:
        arrays = stream.read_all()
    bound = snapshot_table_from_arrow(descriptor, arrays, source_descriptor_from_arrow(metadata),
        ordered=SnapshotTableOrderedMetadata(blank_provenance=BlankRowProvenance.SOURCE_MISSING_STABLE_KEY))
    context.checkpoint()
    return descriptor, bound, diagnostics
