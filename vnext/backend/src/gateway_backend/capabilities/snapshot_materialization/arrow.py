"""Snapshot values backed by retained Arrow buffers and the single business kernel."""

from __future__ import annotations

from collections.abc import Iterator, Callable
from contextlib import contextmanager, ExitStack
import json
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.snapshot_materialization._digest import compare_schema_digest
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.batch import schema_with_batch_metadata
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE, DegradedReason, DiagnosticSeverity,
    MaterializationDiagnostic, MaterializationDiagnosticCode, MaterializationStage,
    SnapshotColumnDescriptor, SnapshotTable, SnapshotTableBatchMetadata, SnapshotMaterializationResult,
    SnapshotTableDescriptor, SnapshotTableOrderedMetadata, BlankRowProvenance,
)
from gateway_backend.capabilities.composite_signal.contracts import SpecialDeviceCatalog
from gateway_backend.capabilities.snapshot_materialization.native import (
    materialize_arrow_table, filter_arrow_catalog, catalog_from_arrow_result,
)
from gateway_backend.capabilities.table_access import (
    ArrowSourceTableReader, current_kernel_context, source_arrow_metadata,
    source_descriptor_from_arrow,
)
from gateway_backend.capabilities.table_access.contracts import SourceTableDescriptor, ParserInvocationContext
from gateway_backend.capabilities.table_access import KernelExecutionContext, merge_kernel_control


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
    def __init__(
        self, descriptor: SnapshotTableDescriptor, source: ArrowSourceTableReader,
        *, canonical_comparison_verified: bool = False,
    ) -> None:
        super().__init__(descriptor, source)
        self._arrow_source = source
        self._canonical_comparison_verified = canonical_comparison_verified
        self._canonical_artifact_read_verified = False
        self._canonical_committed_read_verified = False

    @property
    def canonical_comparison_verified(self) -> bool:
        return self._canonical_comparison_verified

    def mark_canonical_comparison_verified(self) -> None:
        """Only the successful fresh canonical IPC writer calls this."""
        self._require_open()
        self._canonical_comparison_verified = True

    @property
    def canonical_artifact_read_verified(self) -> bool:
        return self._canonical_artifact_read_verified

    def mark_canonical_artifact_read_verified(self) -> None:
        """Only a successful canonical IPC artifact reader calls this."""
        self._require_open()
        self._canonical_artifact_read_verified = True

    @property
    def canonical_committed_read_verified(self) -> bool:
        return self._canonical_committed_read_verified

    def mark_canonical_committed_read_verified(self) -> None:
        """Only exact-commit committed canonical access calls this after verification."""
        self._require_open()
        self._canonical_committed_read_verified = True

    @property
    def execution_context(self) -> KernelExecutionContext:
        return self._arrow_source.execution_context

    @property
    def logical_size_bytes(self) -> int:
        self._require_open()
        return self._arrow_source.logical_size_bytes

    @property
    def arrow_schema(self) -> pa.Schema:
        self._require_open()
        return self._arrow_source.arrow_schema

    @property
    def arrow_batch_count_upper(self) -> int:
        self._require_open()
        return self._arrow_source.arrow_batch_count_upper

    def arrow_stream(self) -> pa.RecordBatchReader:
        self._require_open()
        return self._arrow_source.arrow_stream()

    def reopen(self) -> ArrowSnapshotTableReader:
        self._require_open()
        reopened = ArrowSnapshotTableReader(
            self._descriptor, self._arrow_source.reopen(),
            canonical_comparison_verified=self._canonical_comparison_verified,
        )
        reopened._canonical_artifact_read_verified = self._canonical_artifact_read_verified
        reopened._canonical_committed_read_verified = self._canonical_committed_read_verified
        return reopened


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
    *, ordered: SnapshotTableOrderedMetadata | None = None, execution_context: KernelExecutionContext | None = None,
    close: Callable[[], None] | None = None,
) -> SnapshotTable:
    context = execution_context or current_kernel_context()
    if context is None:
        raise ValueError("snapshot Arrow backing requires an operation kernel context")
    reader = ArrowSnapshotTableReader(descriptor, ArrowSourceTableReader(source, table, context, close=close))
    batch_source = reader.reopen()
    try:
        batch = ArrowSnapshotTableBatchReader(batch_source, SnapshotTableBatchMetadata(
            blank_provenance=BlankRowProvenance.NONE if ordered is None else ordered.blank_provenance))
    except BaseException:
        batch_source.close()
        reader.close()
        raise
    return SnapshotTable(descriptor, reader, descriptor.diagnostics, batch_reader=batch, ordered_metadata=ordered)


def materialize_source_arrow(
    reader: ArrowSourceTableReader, *, compare_keys: tuple[str, ...],
    stage: MaterializationStage, table_ruleset_version: int, invocation: ParserInvocationContext,
) -> tuple[SnapshotTableDescriptor, SnapshotTable | None, tuple[MaterializationDiagnostic, ...]]:
    source = reader.descriptor()
    context = current_kernel_context()
    if context is None:
        raise ValueError("SQL Arrow materialization requires an operation kernel context")
    context = merge_kernel_control(context, reader.execution_context.cancel_probe, reader.execution_context.deadline_monotonic)
    context = merge_kernel_control(context, invocation.cancel_requested, invocation.deadline_monotonic)
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
        ordered=SnapshotTableOrderedMetadata(blank_provenance=BlankRowProvenance.SOURCE_MISSING_STABLE_KEY), execution_context=context)
    context.checkpoint()
    return descriptor, bound, diagnostics


def _derived_arrow_value(cell: object) -> object:
    from gateway_shared_kernel import NullScalar, StringScalar, SignedIntegerScalar, UnsignedIntegerScalar

    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, StringScalar):
        return cell.text
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar)):
        return int(cell.decimal)
    raise ValueError("derived composite column has an unsupported cell")


@contextmanager
def snapshot_arrow_input(table: SnapshotTable) -> Iterator[tuple[dict[str, Any], KernelExecutionContext]]:
    """Borrow SQL/canonical Arrow directly; composite rows are the bounded exception."""
    context = current_kernel_context()
    if context is None or table.reader is None:
        raise ValueError("Arrow input requires an operation context and ready reader")
    isolated = table.reader.reopen()
    retained = None
    try:
        if isinstance(isolated, ArrowSnapshotTableReader):
            with isolated.arrow_stream() as stream:
                yield source_arrow_metadata(isolated.source_descriptor(), stream), isolated.execution_context
            return
        if table.descriptor.table_name != "composite_signal_point" or not isinstance(isolated, BoundSnapshotTableReader):
            raise ValueError("ordinary canonical tables must use the Arrow production reader")
        source = isolated.source_descriptor()
        # Only the established Python composite result crosses this boundary.
        # Check payload/object/Arrow conversion before building any column lists.
        upper = 8192 + len(source.columns) * 4096
        for row in isolated.iter_rows():
            context.checkpoint()
            upper += 1024 + len(row) * 256
            for cell in row:
                text = getattr(cell, "text", None)
                if text is not None:
                    upper += len(text) * 8
        isolated.close()
        isolated = table.reader.reopen()
        with context.memory.reserve(upper):
            columns: list[list[object]] = [[] for _ in source.columns]
            for row in isolated.iter_rows():
                context.checkpoint()
                for index, cell in enumerate(row):
                    columns[index].append(_derived_arrow_value(cell))
            fields = []
            arrays = []
            for index, column in enumerate(source.columns):
                kind = None if column.declared_type is None else column.declared_type.kind.value
                physical = pa.int64() if kind == "signed-integer" else pa.uint64() if kind == "unsigned-integer" else pa.string()
                declared = column.declared_type
                canonical_type = {
                    "declared_type": None if declared is None else {
                        "kind": declared.kind.value, "bits": declared.bits,
                        "precision": declared.precision, "scale": declared.scale,
                        "bit_width": declared.bit_width,
                    },
                    "labels": None, "logical_type": column.logical_type.value,
                    "sql_type": column.sql_type,
                }
                fields.append(pa.field(
                    column.canonical_name, physical, nullable=column.nullable,
                    metadata={b"gdds.canonical_type": json.dumps(canonical_type).encode("utf-8")},
                ))
                arrays.append(pa.array(columns[index], type=physical))
            backing = pa.Table.from_arrays(arrays, schema=pa.schema(
                fields, metadata={b"gdds.canonical_mapping_version": b"1"},
            ))
            # Conversion is eager before the caller snapshots native remaining M.
            # Drop the Python lists/array wrappers before moving the Arrow backing
            # from this temporary envelope into its shared retained reservation.
            del columns, arrays, fields
        retained = ArrowSourceTableReader(source, backing, context)
        del backing
        with retained.arrow_stream() as stream:
            yield source_arrow_metadata(source, stream), context
    finally:
        if retained is not None:
            retained.close()
        isolated.close()


def extract_arrow_special_device_catalog(result: SnapshotMaterializationResult) -> SpecialDeviceCatalog:
    """Filter ordinary Arrow tables in B; materialize only composite facts in Python."""
    from gateway_backend.capabilities.composite_signal.contracts import DEVICE_TABLE, SPECIAL_POINT_TABLES
    context = current_kernel_context()
    if context is None or result.summary is None or result.table_set is None:
        raise ValueError("catalog filtering requires a complete operation SQL summary")
    tables = {table.descriptor.table_name: table for table in result.table_set.tables}
    failed = {table.table_name for table in result.summary.tables if table.degraded_reason is DegradedReason.TABLE_FAILED}
    with ExitStack() as readers:
        metadata = {}
        control = context
        for name in (DEVICE_TABLE, *SPECIAL_POINT_TABLES):
            if name in failed:
                metadata[name] = {"canonical_name": name, "reader_ready": False}
                continue
            table = tables.get(name)
            if table is not None:
                item, control = readers.enter_context(snapshot_arrow_input(table))
                metadata[name] = item
        budgets = operation_business_budgets()
        filtered = filter_arrow_catalog(metadata, cancel_probe=control.cancel_probe, budgets=budgets,
            deadline_monotonic=control.deadline_monotonic, pool_threads=control.threads)
        return catalog_from_arrow_result(filtered, budgets=budgets, cancel_probe=control.cancel_probe,
            deadline_monotonic=control.deadline_monotonic)
