"""Thin loader for table_access golden fixtures. Not a parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_backend.capabilities.table_access.contracts import (
    DiagnosticSeverity,
    DiagnosticSource,
    MaterializedTableReader,
    ParsedTable,
    ParseResult,
    ParseStatus,
    ParserDiagnostic,
    ParserDiagnosticCode,
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
    SqlLogicalType,
    SqlSetValue,
    XmlEvent,
    XmlEventKind,
    XmlParseResult,
)
from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "table-access"


def load_text(relative_path: str) -> str:
    return (FIXTURE_ROOT / relative_path).read_text(encoding="utf-8")


def load_expected(relative_path: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("expected.json must be an object")
    return payload


def parse_result_from_expected(payload: dict[str, Any]) -> ParseResult:
    tables = tuple(_parsed_table(item) for item in _require_list(payload, "tables"))
    return ParseResult(
        status=ParseStatus(_require_str(payload, "status")),
        tables=tables,
        diagnostics=_diagnostics(payload),
    )


def xml_parse_result_from_expected(payload: dict[str, Any]) -> XmlParseResult:
    events = tuple(_xml_event(item) for item in _require_list(payload, "events"))
    return XmlParseResult(
        status=ParseStatus(_require_str(payload, "status")),
        events=events,
        diagnostics=_diagnostics(payload),
    )


def _parsed_table(item: object) -> ParsedTable:
    if type(item) is not dict:
        raise ValueError("table entry must be an object")
    descriptor = SourceTableDescriptor(
        display_name=_require_str(item, "display_name"),
        canonical_name=_require_str(item, "canonical_name"),
        columns=tuple(
            _column(column, index)
            for index, column in enumerate(_require_list(item, "columns"))
        ),
        primary_key_canonical_names=tuple(
            _require_str_item(name) for name in _require_list(item, "primary_key_canonical_names")
        ),
        reader_ready=_require_bool(item, "reader_ready"),
    )
    raw_rows = _require_list(item, "rows")
    if descriptor.reader_ready:
        rows = tuple(_row(row) for row in raw_rows)
        return ParsedTable(descriptor, MaterializedTableReader(descriptor, rows))
    if raw_rows:
        raise ValueError("non-ready table must not include rows")
    return ParsedTable(descriptor, None)


def _column(item: object, ordinal: int) -> SourceColumnDescriptor:
    if type(item) is not dict:
        raise ValueError("column entry must be an object")
    labels = item.get("enum_or_set_labels")
    declared = item.get("declared_type")
    return SourceColumnDescriptor(
        display_name=_require_str(item, "display_name"),
        canonical_name=_require_str(item, "canonical_name"),
        ordinal=ordinal,
        sql_type=_require_str(item, "sql_type"),
        logical_type=SqlLogicalType(_require_str(item, "logical_type")),
        declared_type=None if declared is None else _declared_type(declared),
        nullable=_require_bool(item, "nullable"),
        enum_or_set_labels=None
        if labels is None
        else tuple(_require_str_item(label) for label in _require_list_value(labels)),
    )


def _declared_type(item: object) -> DeclaredType:
    if type(item) is not dict:
        raise ValueError("declared_type must be an object")
    return DeclaredType(
        kind=DeclaredTypeKind(_require_str(item, "kind")),
        bits=_optional_int(item, "bits"),
        precision=_optional_int(item, "precision"),
        scale=_optional_int(item, "scale"),
        bit_width=_optional_int(item, "bit_width"),
    )


def _row(item: object) -> SourceRow:
    if type(item) is not list:
        raise ValueError("row must be an array")
    return tuple(_cell(cell) for cell in item)


def _cell(item: object) -> SourceCell:
    if type(item) is not dict:
        raise ValueError("cell must be an object")
    kind = _require_str(item, "kind")
    if kind == "null":
        return NullScalar()
    if kind == "signed-integer":
        return SignedIntegerScalar(_require_str(item, "decimal"))
    if kind == "unsigned-integer":
        return UnsignedIntegerScalar(_require_str(item, "decimal"))
    if kind == "string":
        return StringScalar(_require_str(item, "text"))
    if kind == "boolean":
        return BooleanScalar(_require_bool(item, "value"))
    if kind == "decimal":
        return DecimalScalar(_require_str(item, "decimal"))
    if kind == "float32":
        return Float32Scalar(_require_str(item, "bits_hex"))
    if kind == "float64":
        return Float64Scalar(_require_str(item, "bits_hex"))
    if kind == "binary":
        return BinaryScalar(bytes.fromhex(_require_str(item, "hex")))
    if kind == "bit":
        return BitScalar(bytes.fromhex(_require_str(item, "hex")))
    if kind == "date":
        return DateScalar(_require_str(item, "text"))
    if kind == "datetime":
        return DateTimeScalar(_require_str(item, "text"))
    if kind == "timestamp":
        return TimestampScalar(_require_str(item, "text"))
    if kind == "time-duration":
        return TimeDurationScalar(_require_str(item, "text"))
    if kind == "set":
        return SqlSetValue(tuple(_require_str_item(member) for member in _require_list(item, "members")))
    raise ValueError(f"unsupported cell kind {kind}")


def _xml_event(item: object) -> XmlEvent:
    if type(item) is not dict:
        raise ValueError("event must be an object")
    attributes = item.get("attributes")
    parsed_attributes: tuple[tuple[str, str], ...] | None = None
    if attributes is not None:
        pairs: list[tuple[str, str]] = []
        for pair in _require_list_value(attributes):
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("attribute must be a [name, value] pair")
            pairs.append((_require_str_item(pair[0]), _require_str_item(pair[1])))
        parsed_attributes = tuple(pairs)
    return XmlEvent(
        kind=XmlEventKind(_require_str(item, "kind")),
        expanded_name=item.get("expanded_name"),
        attributes=parsed_attributes,
        text=item.get("text"),
    )


def _diagnostics(payload: dict[str, Any]) -> tuple[ParserDiagnostic, ...]:
    return tuple(
        ParserDiagnostic(
            code=ParserDiagnosticCode(_require_str(item, "code")),
            severity=DiagnosticSeverity(_require_str(item, "severity")),
            source=DiagnosticSource(_require_str(item, "source")),
            byte_offset=_require_int(item, "byte_offset"),
            message=_require_str(item, "message"),
            table=item.get("table"),
            column=item.get("column"),
        )
        for item in _require_list(payload, "diagnostics")
    )


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise ValueError(f"{key} must be a string")
    return value


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise ValueError(f"{key} must be a bool")
    return value


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an int")
    return value


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload[key] is None:
        return None
    return _require_int(payload, key)


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload[key]
    return _require_list_value(value)


def _require_list_value(value: object) -> list[Any]:
    if type(value) is not list:
        raise ValueError("expected a list")
    return value


def _require_str_item(value: object) -> str:
    if type(value) is not str:
        raise ValueError("list item must be a string")
    return value
