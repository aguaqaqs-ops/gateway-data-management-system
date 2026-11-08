"""Bounded Arrow business entry points, before the production caller cutover.

Only filtered composite facts become Python rows. General SQL/canonical tables
stay in Arrow C Streams; snapshot and manifest metadata retain their owners.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from typing import Any, cast

import pyarrow as pa
from gateway_compute._native import _catalog_filter_native, _sql_materialize_native

from gateway_backend.capabilities.composite_signal.contracts import (
    DEVICE_TABLE,
    SPECIAL_POINT_TABLES,
    CompositeDiagnosticCode,
    SpecialDevice,
    SpecialDeviceCatalog,
    SpecialPointFact,
)
from gateway_backend.capabilities.snapshot_materialization._catalog import CatalogError
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationStage
from gateway_backend.capabilities.table_access.contracts import CancelProbe
from gateway_backend.capabilities.table_access import current_kernel_context, KernelMemoryLimit, merge_kernel_control

ArrowMetadata = dict[str, Any]
KernelBudgets = dict[str, int]
KernelResult = dict[str, Any]


def check_metadata_budget(value: object, budgets: KernelBudgets) -> None:
    """Check strings/container overhead before constructing native metadata."""
    used = 0

    def visit(item: object, depth: int) -> None:
        nonlocal used
        if depth > 12:
            raise ValueError("business metadata nesting exceeds limit")
        used += 128
        if type(item) is str:
            used += len(item) * 4
        if used > budgets["max_metadata_bytes"] or used * 8 > budgets["max_live_bytes"]:
            raise MemoryError("business metadata budget exceeded")
        if type(item) is tuple or type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                visit(key, depth + 1)
                if key != "arrow_stream":
                    visit(child, depth + 1)
        elif item is not None and type(item) not in (str, bool, int):
            raise ValueError("business metadata contains an unsupported value")

    visit(value, 0)


def call_arrow_kernel(
    native: Callable[..., Any],
    tables: list[ArrowMetadata],
    plan: dict[str, Any],
    *,
    cancel_probe: object,
    budgets: KernelBudgets,
    deadline_monotonic: float | None,
    pool_threads: int,
) -> KernelResult:
    context = current_kernel_context()
    if context is not None:
        context = merge_kernel_control(context, cast(CancelProbe, cancel_probe), deadline_monotonic)
        context.checkpoint()
        budgets = {**budgets, "max_live_bytes": min(budgets["max_live_bytes"], context.memory.available_bytes)}
        cancel_probe = context.cancel_probe
        deadline_monotonic = context.deadline_monotonic
        pool_threads = context.threads
        context.memory.record_stage_admission("business-kernel", budgets["max_live_bytes"])
    check_metadata_budget((tables, plan), budgets)
    try:
        result = cast(KernelResult, native(tables, plan, cancel_probe, budgets, deadline_monotonic, pool_threads))
    except BaseException as exc:
        if context is not None:
            # C Stream implementations normalize Python generator failures.
            # Recover the actual caller control before classifying that wrapper.
            context.checkpoint()
            if isinstance(exc, MemoryError):
                raise KernelMemoryLimit("business kernel operation memory reservation exceeded") from exc
        raise
    if context is not None:
        context.checkpoint()
    return result


def materialize_arrow_table(
    table: ArrowMetadata,
    *,
    effective_compare_key_columns: tuple[str, ...],
    stage: MaterializationStage,
    cancel_probe: object,
    budgets: KernelBudgets,
    deadline_monotonic: float | None,
    pool_threads: int,
) -> KernelResult:
    check_metadata_budget((table, effective_compare_key_columns), budgets)
    return call_arrow_kernel(
        _sql_materialize_native,
        [table],
        {"stage": stage.value, "effective_compare_key_columns": list(effective_compare_key_columns)},
        cancel_probe=cancel_probe,
        budgets=budgets,
        deadline_monotonic=deadline_monotonic,
        pool_threads=pool_threads,
    )


def filter_arrow_catalog(
    tables: Mapping[str, ArrowMetadata],
    *,
    cancel_probe: object,
    budgets: KernelBudgets,
    deadline_monotonic: float | None,
    pool_threads: int,
) -> KernelResult:
    selected: list[ArrowMetadata] = []
    # Check borrowed metadata before allocating the copied list or entering FFI.
    for name in (DEVICE_TABLE, *SPECIAL_POINT_TABLES):
        table = tables.get(name)
        if table is None:
            continue
        check_metadata_budget(table, budgets)
        if table.get("canonical_name") != name or not table.get("reader_ready"):
            raise CatalogError(
                CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                "catalog table failed or its name binding is invalid",
                table=name,
            )
        selected.append(table)
    return call_arrow_kernel(
        _catalog_filter_native,
        selected,
        {},
        cancel_probe=cancel_probe,
        budgets=budgets,
        deadline_monotonic=deadline_monotonic,
        pool_threads=pool_threads,
    )


def _payload_value(column: ArrowMetadata, value: Any) -> Any:
    if value is None:
        return None
    logical = column["logical_type"]
    declared = column["declared_type"]
    if logical == "set":
        return [] if value == "" else value.split(",")
    kind = declared["kind"] if declared is not None else None
    if kind in ("signed-integer", "unsigned-integer"):
        return value if -(2**53) + 1 <= value <= 2**53 - 1 else str(value)
    if kind == "float32":
        return struct.pack(">f", value).hex()
    if kind == "float64":
        return struct.pack(">d", value).hex()
    if kind in ("binary", "bit"):
        return value.hex()
    return value


def catalog_from_arrow_result(
    result: KernelResult, *, budgets: KernelBudgets, cancel_probe: CancelProbe,
    deadline_monotonic: float | None,
) -> SpecialDeviceCatalog:
    context = current_kernel_context()
    if context is None:
        raise ValueError("filtered catalog facts require an operation kernel context")
    backings: list[pa.Table] = []
    converted: list[ArrowMetadata] = []
    with ExitStack() as temporary:
        def reserve(size: int) -> None:
            temporary.enter_context(context.memory.reserve(size))
        output = result["output"]
        try:
            if output is not None:
                # Retain every filtered output buffer before allocating Python
                # facts, including batches the converter has not consumed yet.
                for metadata in output["tables"]:
                    with metadata["arrow_stream"] as stream:
                        backing = stream.read_all()
                    temporary.enter_context(context.memory.retain_arrow(backing))
                    backings.append(backing)
                    converted.append({**metadata, "arrow_stream": backing.to_reader()})
                if backings:
                    del backing
                result = {**result, "output": {**output, "tables": converted}}
            catalog, upper = _convert_catalog_from_arrow_result(result, budgets=budgets,
                cancel_probe=cancel_probe, deadline_monotonic=deadline_monotonic, reserve=reserve)
        finally:
            for metadata in converted:
                metadata["arrow_stream"].close()
            converted.clear()
            backings.clear()
    # Facts, _bind JSON/CompositeSignalPointRow and _derived_table encoded_rows/
    # hashes can overlap even without XML. This SQL-derived envelope covers that
    # lifetime conservatively through the operation, independently of XML/AST.
    context.memory.retain_metadata(catalog, upper)
    return catalog


def _convert_catalog_from_arrow_result(
    result: KernelResult,
    *,
    budgets: KernelBudgets,
    cancel_probe: CancelProbe,
    deadline_monotonic: float | None, reserve: Callable[[int], None],
) -> tuple[SpecialDeviceCatalog, int]:
    """The existing composite exception: only filtered catalog rows cross back."""
    output = result["output"]
    if output is None:
        diagnostic = result["diagnostics"][0]
        raise CatalogError(
            CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
            diagnostic["message"],
            table=diagnostic["table"],
        )
    devices: list[SpecialDevice] = []
    points: list[SpecialPointFact] = []
    live = 256
    reserve(live)
    def checkpoint() -> None:
        if cancel_probe.is_set():
            raise InterruptedError("composite facts conversion cancelled")
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise TimeoutError("composite facts conversion deadline elapsed")

    checkpoint()
    for metadata in output["tables"]:
        reader = metadata["arrow_stream"]
        assert isinstance(reader, pa.RecordBatchReader)
        columns = metadata["columns"]
        indexes = {column["canonical_name"]: index for index, column in enumerate(columns)}
        try:
            for batch in reader:
                checkpoint()
                # SQL-derived lifetime, including the no-XML path: facts/scalars
                # and SET/binary expansion <=8x UTF8 payload; _bind's escaped
                # payload JSON bytes + Python Unicode <=30x; _derived_table's
                # encoded cell-frame/hash scratch <=16x. 64x covers their
                # overlap. Field names repeat in each JSON object (up to 4-byte
                # Unicode and escaping); row/cell terms cover tuples, dataclass
                # fields, encoded_rows and digest/list headers. Arrow backing
                # and the later columnar conversion have separate reservations.
                names = sum(len(column["canonical_name"]) for column in columns)
                extra = batch.nbytes * 64 + batch.num_rows * (names * 256 + len(columns) * 1024 + 4096)
                live += extra
                if live > budgets["max_live_bytes"] or live > budgets["max_output_bytes"]:
                    raise MemoryError("filtered composite facts exceed business budget")
                reserve(extra)
                for row in range(batch.num_rows):
                    checkpoint()
                    if metadata["canonical_name"] == DEVICE_TABLE:
                        devices.append(
                            SpecialDevice(
                                gid=batch.column(indexes["gid"])[row].as_py(),
                                dev_addr=batch.column(indexes["dev_addr"])[row].as_py(),
                                description=batch.column(indexes["description"])[row].as_py(),
                            )
                        )
                    else:
                        payload = tuple(
                            sorted(
                                (
                                    column["canonical_name"],
                                    _payload_value(column, batch.column(index)[row].as_py()),
                                )
                                for index, column in enumerate(columns)
                            )
                        )
                        points.append(
                            SpecialPointFact(
                                source_table=metadata["canonical_name"],
                                point_gid=batch.column(indexes["gid"])[row].as_py(),
                                dev_addr=batch.column(indexes["dev_addr"])[row].as_py(),
                                point_name=batch.column(indexes["name"])[row].as_py(),
                                payload=payload,
                            )
                        )
        finally:
            reader.close()
    checkpoint()
    return SpecialDeviceCatalog(
        devices=tuple(devices),
        points=tuple(points),
        source_device_row_count=output["source_device_row_count"],
    ), live
