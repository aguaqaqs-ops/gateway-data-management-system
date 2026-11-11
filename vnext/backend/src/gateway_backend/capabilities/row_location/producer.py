"""One table at a time, bind published STANDARD identities to final files."""
from __future__ import annotations

from collections.abc import Iterator, Generator
from contextlib import closing, contextmanager, ExitStack
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.store import put_with_built_ref
from gateway_backend.capabilities.business_navigation import FilterRecord
from gateway_backend.capabilities.business_navigation.contracts import RowValues
from gateway_backend.capabilities.business_navigation import scalar_reason
from gateway_backend.capabilities.comparison import (
    ComparisonRecordsHandle, begin_records_operation, standard_identity_scanner, standard_identity_policy,
    RecordsPublicationContext, RecordsPublicationPolicy, write_arrow_parquet,
)
from gateway_backend.capabilities.comparison.contracts import RecordsClosureEntry, TableComparisonTask
from gateway_backend.capabilities.snapshot_materialization import canonical_comparison_input
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTable
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceTableRefs
from gateway_backend.capabilities.table_access import current_kernel_context
from .inputs import final_parquet_batches
from .contracts import LOCATOR_SCHEMA, RowLocationResult

_ROW_KINDS = frozenset({"ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"})

@dataclass(slots=True)
class _Row:
    kind: str
    before_index: int | None = None
    current_index: int | None = None
    before: RowValues | None = None
    current: RowValues | None = None


@contextmanager
def _canonical_batches(table: SnapshotTable) -> Iterator[Iterator[pa.RecordBatch]]:
    stream, owner = canonical_comparison_input(table)
    with closing(owner), closing(stream):
        yield iter(stream)


def identity_batches(
    table: SnapshotTable, policy_json: str, *, ref: ArtifactRef | None = None,
    store: ArtifactStorePort | None = None,
) -> Generator[tuple[pa.RecordBatch, list[str], list[bytes]], None, None]:
    """Keep decoded input/output and occurrence state within one operation M."""
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("row location requires an operation context")
    source = (_canonical_batches(table) if ref is None else
        final_parquet_batches(table.descriptor, ref, store) if store is not None else None)
    if source is None:
        raise ValueError("final row location requires an artifact store")
    with source as batches:
        # Input decode is already admitted above. Return the unused native
        # envelope immediately on close; never create a second operation owner.
        with closing(begin_records_operation(
                native_budget_bytes=context.memory.available_bytes // 2,
                cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)) as phase:
            with closing(standard_identity_scanner(phase, policy_json)) as scanner:
                for batch in batches:
                    context.checkpoint()
                    with pa.RecordBatchReader.from_batches(batch.schema, [batch]) as stream:
                        identities, order_keys = scanner.scan(stream, batch.nbytes + 4096)
                    if len(identities) != batch.num_rows or len(order_keys) != batch.num_rows:
                        raise ValueError("native identity scan row count differs")
                    yield batch, identities, order_keys
                context.checkpoint()


def _filter_context(batch: pa.RecordBatch, index: int, column: str | None, sql: str | None) -> RowValues:
    if column is None or (position := batch.schema.get_field_index(column)) < 0:
        return {}
    value = batch.column(position)[index].as_py()
    # Unsupported typed values force the existing navigation whole-table path;
    # do not manufacture a JSON scalar or coerce a number-looking string.
    if scalar_reason(sql, value) is not None:
        return {}
    if value is not None and type(value) not in {int, str}:
        raise ValueError("navigation scalar contradicts its same-side descriptor")
    return {column: value}


def prepare_row_locations(
    task: TableComparisonTask, entry: RecordsClosureEntry | None,
    handle: ComparisonRecordsHandle | None, refs: SurfaceTableRefs,
    store: ArtifactStorePort, *, filter_column: str | None = None,
) -> RowLocationResult:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("row location requires the operation context")
    with ExitStack() as charges:
        result = _prepare_row_locations(task, entry, handle, refs, store,
            filter_column=filter_column, charges=charges)
        result.charges = charges.pop_all()
    context.resources.callback(result.close)
    return result


def _prepare_row_locations(
    task: TableComparisonTask, entry: RecordsClosureEntry | None,
    handle: ComparisonRecordsHandle | None, refs: SurfaceTableRefs,
    store: ArtifactStorePort, *, filter_column: str | None, charges: ExitStack,
) -> RowLocationResult:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("row location requires the operation context")
    if entry is None or handle is None:
        return RowLocationResult((), 0, None)
    if task.before_descriptor is None or task.current_descriptor is None or task.policy is None:
        raise ValueError("published row records require both logical table sides")
    # The published family bounds the wanted dictionary, output indexes,
    # FilterRecords and their constant-size JSON/sort/Arrow writer overhead.
    charges.enter_context(context.memory.reserve(entry.record_count * 4096 + 65536))
    rows: dict[str, _Row] = {}
    actual_count = 0
    with handle.record_batches("STANDARD") as stream:
        for batch in stream:
            context.checkpoint()
            actual_count += batch.num_rows
            kinds = batch.column(batch.schema.get_field_index("record_kind"))
            identities = batch.column(batch.schema.get_field_index("row_identity"))
            for index in range(batch.num_rows):
                kind = kinds[index].as_py()
                if kind not in _ROW_KINDS:
                    continue
                identity = identities[index].as_py()
                if type(identity) is not bytes or len(identity) != 32:
                    raise ValueError("published row identity is invalid")
                key = "sha256:" + identity.hex()
                if key in rows:
                    raise ValueError("published row identities are ambiguous")
                rows[key] = _Row(kind)
    if actual_count != entry.record_count:
        raise ValueError("published records count differs from native records")
    if not rows:
        return RowLocationResult((), 0, None)
    policy_json = canonicalize_json_value(standard_identity_policy(task)).decode()
    scanned = 0
    for side, table, ref in (("before", task.before_table, refs.before_table_ref),
                             ("current", task.current_table, refs.current_table_ref)):
        if table is None:
            raise ValueError("row location canonical side is unavailable")
        descriptor = table.descriptor
        sql = next((c.scalar_type for c in descriptor.columns if c.name == filter_column), None)
        matched: set[str] = set()
        position = 0
        for batch, identities, _ in identity_batches(table, policy_json, ref=ref, store=store):
            for index, identity in enumerate(identities):
                row = rows.get(identity)
                if row is None:
                    continue
                if (side == "before" and row.kind == "ROW_ADDED") or (side == "current" and row.kind == "ROW_DELETED"):
                    raise ValueError("published record contradicts logical side presence")
                if identity in matched:
                    raise ValueError("row identity matches multiple physical rows")
                matched.add(identity)
                values = _filter_context(batch, index, filter_column, sql)
                # Variable-width values may be much larger than the constant
                # per-record envelope; charge before retaining their maps/JSON.
                extra = sum(len(value) * 16 for value in values.values() if type(value) is str)
                if extra:
                    charges.enter_context(context.memory.reserve(extra))
                setattr(row, side, values)
                if ref is not None:
                    setattr(row, side + "_index", position + index)
            position += batch.num_rows
            del batch, identities, _
        scanned += position
        expected = {identity for identity, row in rows.items()
            if row.kind != ("ROW_ADDED" if side == "before" else "ROW_DELETED")}
        if matched != expected:
            raise ValueError("published record has no unique final/canonical row")
    ordered = sorted(rows)
    data: dict[str, list[Any]] = {name: [] for name in LOCATOR_SCHEMA.names}
    records = []
    for identity in ordered:
        context.checkpoint()
        row = rows[identity]
        data["row_identity"].append(bytes.fromhex(identity[7:]))
        data["before_row_index"].append(row.before_index)
        data["current_row_index"].append(row.current_index)
        for side, ref in (("before", refs.before_table_ref), ("current", refs.current_table_ref)):
            values = getattr(row, side)
            encoded = (canonicalize_json_value(dict(values)).decode() if filter_column is not None
                and ref is None and values is not None else None)
            data[side + "_filter_context_json"].append(encoded)
        records.append(FilterRecord(identity, row.kind, row.before, row.current))
    batch = pa.RecordBatch.from_pydict(data, schema=LOCATOR_SCHEMA)
    return RowLocationResult(tuple(records), scanned, batch)


def publish_row_locations(
    result: RowLocationResult, store: ArtifactStorePort, *, filtered: bool,
) -> ArtifactRef | None:
    """Publish once, after the actual navigation decides whether contexts apply."""
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("row locator publication requires the operation context")
    batch = result.batch
    if batch is None:
        return None
    if not filtered:
        batch = pa.RecordBatch.from_arrays([batch.column(0), batch.column(1), batch.column(2),
            pa.nulls(batch.num_rows, type=pa.string()), pa.nulls(batch.num_rows, type=pa.string())], schema=LOCATOR_SCHEMA)
    raw = write_arrow_parquet((batch,), LOCATOR_SCHEMA, RecordsPublicationPolicy(),
        RecordsPublicationContext(checkpoint=context.checkpoint))
    ref = put_with_built_ref(store, raw,
        artifact_id=build_artifact_id(ArtifactLocation.COMPARISON, "row-locator", raw_blob_digest(raw).value),
        media_type="application/vnd.apache.parquet")
    return ref
