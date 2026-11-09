"""Stable C Arrow input vectors independent of B's temporary JSON probe."""

from __future__ import annotations

import pyarrow as pa
from gateway_compute._native import _encode_canonical_ipc_native

from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput, ComparisonPlan, ComparisonRequest, plan_comparison,
)
from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_columns
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, MaterializationPolicy, SnapshotTable,
)
from gateway_backend.capabilities.table_access import NeverCancel
from tests.support.snapshot_materialization import materialize_sql
from tests.support.table_rules import comparison_ruleset_for, ordered_record, standard_rule_record

_CODEC_BUDGETS = {
    "max_columns": 2048, "max_input_batches": 4096, "max_rows": 10_000_000,
    "max_descriptor_bytes": 16 * 1024**2, "max_input_bytes": 1024**3,
    "max_output_bytes": 1024**3, "max_codec_peak_bytes": 24 * 1024**3,
}


def bound(sql: str) -> BoundSnapshotInput:
    materialized = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert materialized.snapshot is not None
    assert materialized.summary is not None
    assert materialized.table_set is not None
    return BoundSnapshotInput(
        materialized.snapshot, materialized.summary, materialized.table_set,
    )


def plan(
    before: BoundSnapshotInput, current: BoundSnapshotInput, *, ordered: bool = False,
) -> ComparisonPlan:
    record = ordered_record(r"^t$") if ordered else standard_rule_record("t")
    result = plan_comparison(ComparisonRequest(
        pair_id="s3-c-frozen-arrow", before=before, current=current,
        rule_set=comparison_ruleset_for(record),
    ))
    assert isinstance(result, ComparisonPlan)
    return result


def canonical_stream(table: SnapshotTable) -> pa.RecordBatchReader:
    assert table.reader is not None
    if callable(getattr(table.reader, "arrow_stream", None)):
        isolated = table.reader.reopen()
        try:
            arrow_stream = getattr(isolated, "arrow_stream", None)
            if not callable(arrow_stream):
                raise AssertionError("reopened Arrow reader has no stream")
            with arrow_stream() as source:
                raw = _encode_canonical_ipc_native(
                    canonical_columns(table.descriptor), source, NeverCancel(), _CODEC_BUDGETS,
                )
        finally:
            isolated.close()
    else:
        assert table.batch_reader is not None
        isolated_batches = table.batch_reader.reopen()
        try:
            source = pa.RecordBatchReader.from_batches(
                isolated_batches.schema(), isolated_batches.iter_record_batches(),
            )
            try:
                raw = _encode_canonical_ipc_native(
                    canonical_columns(table.descriptor), source, NeverCancel(), _CODEC_BUDGETS,
                )
            finally:
                source.close()
        finally:
            isolated_batches.close()
    encoded = pa.ipc.open_file(pa.BufferReader(raw))
    batches = [encoded.get_batch(index) for index in range(encoded.num_record_batches)]
    return pa.RecordBatchReader.from_batches(encoded.schema, batches)


def blank_provenance(table: SnapshotTable) -> str:
    assert table.ordered_metadata is not None
    value = table.ordered_metadata.blank_provenance
    if value is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY:
        return "source"
    if value is BlankRowProvenance.CANONICAL_PSEUDO_GID:
        return "canonical"
    raise AssertionError("ordered comparison has no trusted blank provenance")
