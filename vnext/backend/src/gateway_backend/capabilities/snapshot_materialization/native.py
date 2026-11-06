"""Bounded Arrow business entry points, before the production caller cutover.

Only filtered composite facts become Python rows. General SQL/canonical tables
stay in Arrow C Streams; snapshot and manifest metadata retain their owners.
"""

from __future__ import annotations

import struct
import time
from collections.abc import Callable, Mapping
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
    check_metadata_budget((tables, plan), budgets)
    return cast(
        KernelResult,
        native(
            tables,
            [table["arrow_stream"] for table in tables],
            plan,
            cancel_probe,
            budgets,
            deadline_monotonic,
            pool_threads,
        ),
    )


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
    result: KernelResult,
    *,
    budgets: KernelBudgets,
    cancel_probe: CancelProbe,
    deadline_monotonic: float | None,
) -> SpecialDeviceCatalog:
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
                # Arrow buffers plus copied scalar/payload/fact objects remain
                # alive together. This upper bound is checked before conversion.
                extra = batch.nbytes * 16 + batch.num_rows * (len(columns) * 512 + 1024)
                live += extra
                if live > budgets["max_live_bytes"] or live > budgets["max_output_bytes"]:
                    raise MemoryError("filtered composite facts exceed business budget")
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
    )
