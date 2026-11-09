"""Bounded in-memory neutral table codec; persistence belongs to cache ports.

Facts, artifact and risk orders are separate Arrow views. Restoring them uses
only the real Comparison facade, then the ordinary current-pair publishers.
"""
from __future__ import annotations

import json
from contextlib import ExitStack, closing
from dataclasses import dataclass, field, fields
from io import BytesIO
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.contracts import (
    BlankExtension, BlankSummary, ComparisonSchemaChanges, ComparisonTableFact,
    ComparisonTableStatus, OrderedExtension, OrderedStatus, OrderedSummary,
    OrderedTableProcessingMode, ReplayGuarantee, SchemaChangeSource, SchemaEvolution,
    TableComparisonTask,
)
from gateway_backend.capabilities.comparison.task_input import (
    TABLE_CACHE_FORMAT, TableTaskIdentity, semantic_value,
)
from gateway_backend.capabilities.table_access.kernel import KernelExecutionContext

MAX_CACHE_MANIFEST_BYTES = 1024 * 1024
MAX_CACHE_VIEW_BYTES = 1024 * 1024**2
MAX_CACHE_ROWS = 2_000_000
MAX_FACT_ROW_BYTES = 8 * 1024**2
FAMILIES = ("STANDARD", "ORDERED", "BLANK")


@dataclass(frozen=True, slots=True)
class ComparisonCacheView:
    name: str
    schema: pa.Schema
    raw: bytes
    raw_digest: DigestRef
    batch_rows: tuple[int, ...]

    @property
    def row_count(self) -> int:
        return sum(self.batch_rows)


@dataclass(slots=True)
class ComparisonCachePayload:
    repository_id: str
    artifact_scope: str
    task_digest: DigestRef
    task_kind: str
    detail_policy: str
    table_fact_jcs: bytes
    native_metadata_json: str | None
    families: tuple[str, ...]
    views: tuple[ComparisonCacheView, ...]
    format: str = TABLE_CACHE_FORMAT
    complete: bool = True
    charges: ExitStack = field(default_factory=ExitStack, repr=False)

    def close(self) -> None:
        self.views = ()
        self.table_fact_jcs = b""
        self.native_metadata_json = None
        self.charges.close()


def _encode_view(name: str, reader: pa.RecordBatchReader,
                 context: KernelExecutionContext, charges: ExitStack) -> ComparisonCacheView:
    # Native families have at most ceil(MAX_CACHE_ROWS / 1024) batches. The
    # header reservation precedes Python's tuple/Arrow wrapper allocation.
    with context.memory.reserve(16 * 1024**2), closing(reader):
        batches = tuple(reader)
        schema = reader.schema
        rows = tuple(batch.num_rows for batch in batches)
        if (sum(rows) > MAX_CACHE_ROWS or any(count < 1 or count > 1024 for count in rows)
                or len(rows) > (MAX_CACHE_ROWS + 1023) // 1024):
            raise ValueError("neutral cache batch/count bound exceeded")
        if not rows:
            return ComparisonCacheView(name, schema, b"", raw_blob_digest(b""), ())
        schema_size = schema.serialize().size
        upper = 4 * (sum(batch.get_total_buffer_size() for batch in batches)
                     + schema_size * (len(batches) + 1) + len(batches) * 8192 + 65536)
        reservation = context.memory.reserve(upper)
        try:
            with BytesIO() as sink:
                with pa.ipc.new_stream(sink, schema) as writer:
                    for batch in batches:
                        context.checkpoint()
                        writer.write_batch(batch)
                        if sink.tell() > MAX_CACHE_VIEW_BYTES:
                            raise MemoryError("optional neutral cache view is too large")
                raw = sink.getvalue()
            if len(raw) * 2 > upper:
                raise MemoryError("neutral cache IPC exceeded its precharge")
            reservation.shrink_to(len(raw) * 2 + min(4096, upper - len(raw) * 2))
            charges.enter_context(reservation)
            return ComparisonCacheView(name, schema, raw, raw_blob_digest(raw), rows)
        except BaseException:
            reservation.close()
            raise


def _neutral_fact(fact: ComparisonTableFact) -> bytes:
    if (fact.records or (fact.ordered_extension is not None and fact.ordered_extension.records)
            or (fact.blank_extension is not None and fact.blank_extension.records)):
        raise ValueError("neutral table metadata cannot carry row records")
    removed = {"table_name", "before_descriptor", "current_descriptor", "table_fact_digest"}
    return canonicalize_json_value({f.name: semantic_value(getattr(fact, f.name))
        for f in fields(fact) if f.name not in removed})


def restore_table_fact(raw: bytes, task: TableComparisonTask) -> ComparisonTableFact:
    """Rebind the completed neutral outcome to this task's actual descriptors."""
    data: dict[str, Any] = json.loads(raw)
    schema = data.pop("schema_changes")
    schema["change_source"] = None if schema["change_source"] is None else SchemaChangeSource(schema["change_source"])
    schema["schema_evolution"] = SchemaEvolution(schema["schema_evolution"])
    for name in ("before_only_columns", "current_only_columns", "selected_columns",
                 "effective_compare_key_before", "effective_compare_key_current", "incompatible_columns"):
        schema[name] = tuple(schema[name])
    data["schema_changes"] = ComparisonSchemaChanges(**schema)
    for name in ("ordered_extension", "blank_extension"):
        value = data.get(name)
        if value is None:
            continue
        value["status"] = OrderedStatus(value["status"])
        value["replay_guarantee"] = ReplayGuarantee(value["replay_guarantee"])
        value["records"] = tuple(value["records"])
        value["diagnostics"] = tuple(value["diagnostics"])
        for key in ("before_ordered_digest", "current_ordered_digest", "before_occupancy_digest",
                    "current_occupancy_digest", "policy_digest"):
            if key in value and value[key] is not None:
                value[key] = DigestRef(value[key])
        if name == "ordered_extension":
            value["ordered_summary"] = OrderedSummary(**value["ordered_summary"])
            value["table_processing_mode"] = (None if value["table_processing_mode"] is None
                                               else OrderedTableProcessingMode(value["table_processing_mode"]))
            data[name] = OrderedExtension(**value)
        else:
            value["blank_summary"] = BlankSummary(**value["blank_summary"])
            data[name] = BlankExtension(**value)
    data["status"] = ComparisonTableStatus(data["status"])
    data["records"] = tuple(data["records"])
    data["diagnostics"] = tuple(data["diagnostics"])
    return ComparisonTableFact(table_name=task.table_name, before_descriptor=task.before_descriptor,
                               current_descriptor=task.current_descriptor, **data)


class _RestoreOwner:
    def __init__(self, charge: Any, payload: ComparisonCachePayload) -> None:
        self.charge = charge
        self.payload: ComparisonCachePayload | None = payload

    def close(self) -> None:
        self.payload = None
        self.charge.close()


def _open_view(view: ComparisonCacheView, context: KernelExecutionContext) -> pa.RecordBatchReader:
    context.checkpoint()
    if len(view.raw) > MAX_CACHE_VIEW_BYTES or raw_blob_digest(view.raw) != view.raw_digest:
        raise ValueError("neutral cache raw identity mismatch")
    if not view.batch_rows:
        if view.raw:
            raise ValueError("empty neutral view must not carry a file")
        return pa.RecordBatchReader.from_batches(view.schema, ())
    with pa.ipc.open_stream(pa.BufferReader(view.raw)) as reader:
        if reader.schema != view.schema:
            raise ValueError("neutral cache schema mismatch")
        batches = tuple(reader)
    if tuple(batch.num_rows for batch in batches) != view.batch_rows:
        raise ValueError("neutral cache batch boundaries mismatch")
    return pa.RecordBatchReader.from_batches(view.schema, batches)


class ComparisonCacheCodec:
    @staticmethod
    def encode(handle: native.ComparisonRecordsHandle | None, identity: TableTaskIdentity,
               fact: ComparisonTableFact, context: KernelExecutionContext) -> ComparisonCachePayload:
        context.require_active()
        charges = ExitStack()
        try:
            charges.enter_context(context.memory.reserve(MAX_CACHE_MANIFEST_BYTES * 4))
            fact_jcs = _neutral_fact(fact)
            metadata = None if handle is None else handle.cache_metadata_json()
            if len(fact_jcs) + len((metadata or "").encode()) > MAX_CACHE_MANIFEST_BYTES:
                raise MemoryError("optional neutral cache manifest is too large")
            families: tuple[str, ...] = ()
            views: list[ComparisonCacheView] = []
            if handle is not None:
                families = tuple(handle.cache_family_names())
                for family in FAMILIES:
                    views.append(_encode_view(f"facts/{family}", handle.facts_batches(family), context, charges))
                for family in families:
                    views.append(_encode_view(f"artifact/{family}", handle.neutral_record_batches(family), context, charges))
                views.append(_encode_view("risk/STANDARD", handle.risk_record_batches(), context, charges))
            return ComparisonCachePayload(identity.repository_id, identity.artifact_scope,
                identity.task_digest, identity.task_input.kind, identity.task_input.detail_policy.value,
                fact_jcs, metadata, families, tuple(views), charges=charges)
        except BaseException:
            charges.close()
            raise

    @staticmethod
    def restore(payload: ComparisonCachePayload, identity: TableTaskIdentity,
                task: TableComparisonTask, operation: native.ComparisonOperation,
                context: KernelExecutionContext) -> tuple[ComparisonTableFact, native.ComparisonRecordsHandle | None]:
        context.require_active()
        if (payload.format != TABLE_CACHE_FORMAT or not payload.complete
                or payload.repository_id != identity.repository_id
                or payload.artifact_scope != identity.artifact_scope
                or payload.task_digest != identity.task_digest
                or payload.task_kind != identity.task_input.kind
                or payload.detail_policy != identity.task_input.detail_policy.value):
            raise ValueError("neutral cache task/scope/version mismatch")
        if len(payload.table_fact_jcs) + len((payload.native_metadata_json or "").encode()) > MAX_CACHE_MANIFEST_BYTES:
            raise ValueError("neutral cache manifest exceeds bound")
        upper = 4 * (sum(len(view.raw) for view in payload.views) + MAX_CACHE_MANIFEST_BYTES)
        owner = _RestoreOwner(context.memory.reserve(upper), payload)
        try:
            fact = restore_table_fact(payload.table_fact_jcs, task)
            if payload.native_metadata_json is None:
                if payload.views or payload.families:
                    raise ValueError("metadata-only cache has row views")
                owner.close()
                return fact, None
            expected = tuple(f"facts/{family}" for family in FAMILIES) + tuple(
                f"artifact/{family}" for family in payload.families) + ("risk/STANDARD",)
            if (len(payload.views) > 7 or tuple(view.name for view in payload.views) != expected
                    or not payload.families or len(set(payload.families)) != len(payload.families)
                    or any(family not in FAMILIES for family in payload.families)):
                raise ValueError("neutral cache view closure mismatch")
            with ExitStack() as streams:
                readers = {view.name: streams.enter_context(closing(_open_view(view, context))) for view in payload.views}
                handle = native.restore_table_cache(operation, table_name=task.table_name,
                    metadata_json=payload.native_metadata_json, detail_policy=payload.detail_policy,
                    family_names=list(payload.families), facts=[readers[f"facts/{family}"] for family in FAMILIES],
                    artifacts=[readers[f"artifact/{family}"] for family in payload.families],
                    risk=readers["risk/STANDARD"], input_owner_charge=owner,
                    max_records=MAX_CACHE_ROWS, max_row_bytes=MAX_FACT_ROW_BYTES, max_input_bytes=upper)
            return fact, handle
        except BaseException:
            owner.close()
            raise
