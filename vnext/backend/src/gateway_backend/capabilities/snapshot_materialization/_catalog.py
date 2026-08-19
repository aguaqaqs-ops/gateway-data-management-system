"""Extract the special-device catalog from a SQL SnapshotTableSet."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel import (
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.composite_signal.contracts import (
    DEVICE_TABLE,
    SPECIAL_DEV_ADDR,
    SPECIAL_POINT_TABLES,
    CompositeDiagnosticCode,
    SpecialDevice,
    SpecialDeviceCatalog,
    SpecialPointFact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DegradedReason,
    SnapshotColumnDescriptor,
    SnapshotMaterializationResult,
    SnapshotTable,
)
from gateway_backend.capabilities.table_access.contracts import (
    SourceCell,
    SourceRow,
    SqlSetValue,
)

_IJSON_MIN = -(2**53) + 1
_IJSON_MAX = 2**53 - 1
_DEVICE_COLUMNS = ("gid", "dev_addr", "description")
_POINT_COLUMNS = ("gid", "name", "dev_addr")


class CatalogError(Exception):
    def __init__(self, code: CompositeDiagnosticCode, message: str, *, table: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.table = table


def extract_special_device_catalog(result: SnapshotMaterializationResult) -> SpecialDeviceCatalog:
    if result.summary is None:
        raise CatalogError(
            CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
            "SQL materialization did not publish a summary",
        )
    failed = {
        table.table_name
        for table in result.summary.tables
        if table.degraded_reason is DegradedReason.TABLE_FAILED
    }
    if DEVICE_TABLE in failed:
        raise CatalogError(
            CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
            "device table failed and cannot prove special-device identity",
            table=DEVICE_TABLE,
        )
    for name in SPECIAL_POINT_TABLES:
        if name in failed:
            raise CatalogError(
                CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                f"special point table {name!r} failed and cannot prove catalog invariants",
                table=name,
            )
    published = {
        table.descriptor.table_name: table
        for table in (result.table_set.tables if result.table_set is not None else ())
    }
    devices = _read_devices(published.get(DEVICE_TABLE))
    points: list[SpecialPointFact] = []
    for name in SPECIAL_POINT_TABLES:
        table = published.get(name)
        if table is None:
            continue
        points.extend(_read_points(name, table))
    return SpecialDeviceCatalog(devices=devices, points=tuple(points))


def _read_devices(table: SnapshotTable | None) -> tuple[SpecialDevice, ...]:
    if table is None or table.reader is None:
        return ()
    columns = _column_index(table)
    for name in _DEVICE_COLUMNS:
        if name not in columns:
            raise CatalogError(
                CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                f"device table is missing required column {name!r}",
                table=DEVICE_TABLE,
            )
    devices: list[SpecialDevice] = []
    isolated = table.reader.reopen()
    try:
        for row in isolated.iter_rows():
            gid = _int_cell(row, columns, "gid", DEVICE_TABLE)
            addr = _int_cell(row, columns, "dev_addr", DEVICE_TABLE)
            description = _text_cell(row, columns, "description", DEVICE_TABLE)
            if gid is None or addr is None or description is None:
                raise CatalogError(
                    CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                    "device identity columns must be non-null",
                    table=DEVICE_TABLE,
                )
            devices.append(SpecialDevice(gid=gid, dev_addr=addr, description=description))
    finally:
        isolated.close()
    return tuple(devices)


def _read_points(table_name: str, table: SnapshotTable) -> tuple[SpecialPointFact, ...]:
    if table.reader is None:
        raise CatalogError(
            CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
            f"special point table {table_name!r} has no reader",
            table=table_name,
        )
    columns = _column_index(table)
    for name in _POINT_COLUMNS:
        if name not in columns:
            raise CatalogError(
                CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                f"special point table {table_name!r} is missing required column {name!r}",
                table=table_name,
            )
    source_columns = table.descriptor.columns
    points: list[SpecialPointFact] = []
    isolated = table.reader.reopen()
    try:
        for row in isolated.iter_rows():
            addr = _int_cell(row, columns, "dev_addr", table_name)
            if addr != SPECIAL_DEV_ADDR:
                continue
            gid = _int_cell(row, columns, "gid", table_name)
            point_name = _text_cell(row, columns, "name", table_name)
            if gid is None or point_name is None:
                raise CatalogError(
                    CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
                    "special point identity columns must be non-null",
                    table=table_name,
                )
            points.append(
                SpecialPointFact(
                    source_table=table_name,
                    point_gid=gid,
                    dev_addr=addr,
                    point_name=point_name,
                    payload=_payload(source_columns, row),
                )
            )
    finally:
        isolated.close()
    return tuple(points)


def _column_index(table: SnapshotTable) -> dict[str, int]:
    return {column.name: index for index, column in enumerate(table.descriptor.columns)}


def _int_cell(row: SourceRow, columns: dict[str, int], name: str, table: str) -> int | None:
    cell = row[columns[name]]
    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, SignedIntegerScalar):
        return int(cell.decimal)
    if isinstance(cell, UnsignedIntegerScalar):
        return int(cell.decimal)
    raise CatalogError(
        CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
        f"column {name!r} must be an integer",
        table=table,
    )


def _text_cell(row: SourceRow, columns: dict[str, int], name: str, table: str) -> str | None:
    cell = row[columns[name]]
    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, StringScalar):
        return cell.text
    raise CatalogError(
        CompositeDiagnosticCode.CATALOG_UNAVAILABLE,
        f"column {name!r} must be text",
        table=table,
    )


def _payload(
    columns: tuple[SnapshotColumnDescriptor, ...], row: SourceRow
) -> tuple[tuple[str, Any], ...]:
    items: list[tuple[str, Any]] = []
    for column, cell in zip(columns, row, strict=True):
        items.append((column.name, _json_value(cell)))
    items.sort(key=lambda item: item[0])
    return tuple(items)


def _json_value(cell: SourceCell) -> Any:
    if isinstance(cell, NullScalar):
        return None
    if isinstance(cell, BooleanScalar):
        return cell.value
    if isinstance(cell, StringScalar):
        return cell.text
    if isinstance(cell, SignedIntegerScalar | UnsignedIntegerScalar):
        value = int(cell.decimal)
        if _IJSON_MIN <= value <= _IJSON_MAX:
            return value
        return cell.decimal
    if isinstance(cell, DecimalScalar):
        return cell.decimal
    if isinstance(cell, SqlSetValue):
        return list(cell.members)
    if isinstance(cell, DateScalar | DateTimeScalar | TimestampScalar | TimeDurationScalar):
        return cell.text
    hex_value = getattr(cell, "bits_hex", None)
    if type(hex_value) is str:
        return hex_value
    raw = getattr(cell, "raw_bytes", None)
    if type(raw) is bytes:
        return raw.hex()
    return None
