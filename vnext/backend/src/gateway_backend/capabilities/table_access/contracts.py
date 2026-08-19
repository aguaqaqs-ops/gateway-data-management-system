"""Public contracts owned by the Table Access capability.

Owner: Table Access capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r2-s0-entry-and-budget-freeze.md

R3 materialization types, Repository DTO, cache/retention schema, and parser
algorithms are outside this module. Downstream consumers may import this
package surface only.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from gateway_shared_kernel import (
    DeclaredType,
    DeclaredTypeKind,
    DigestRef,
    TypedScalar,
)

PARSER_INPUT_CONTRACT_VERSION = 1
PARSER_VERSION = 1
_UTF8_ENCODING = "utf-8"
_MIB = 1024 * 1024
_KIB = 1024
_MAX_IDENTIFIER_CODE_POINTS = 64


class SqlLogicalType(StrEnum):
    STANDARD = "standard"
    JSON = "json"
    ENUM = "enum"
    SET = "set"
    UNKNOWN = "unknown"


class ParseStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class DiagnosticSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class DiagnosticSource(StrEnum):
    SQL = "sql"
    XML = "xml"


class ParserDiagnosticCode(StrEnum):
    SQL_TYPE_MALFORMED = "SQL_TYPE_MALFORMED"
    SQL_VALUE_ILLEGAL = "SQL_VALUE_ILLEGAL"
    UNKNOWN_SQL_TYPE = "UNKNOWN_SQL_TYPE"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    PARSER_CANCELLED = "PARSER_CANCELLED"
    PARSER_TIMEOUT = "PARSER_TIMEOUT"
    PARSER_DIAGNOSTICS_TRUNCATED = "PARSER_DIAGNOSTICS_TRUNCATED"
    READER_CLOSED = "READER_CLOSED"
    UNSUPPORTED_STATEMENT = "UNSUPPORTED_STATEMENT"
    DUPLICATE_TABLE = "DUPLICATE_TABLE"
    DUPLICATE_COLUMN = "DUPLICATE_COLUMN"
    DUPLICATE_PRIMARY_KEY = "DUPLICATE_PRIMARY_KEY"
    CANONICAL_IDENTIFIER_COLLISION = "CANONICAL_IDENTIFIER_COLLISION"
    ROW_SHAPE_MISMATCH = "ROW_SHAPE_MISMATCH"
    INCOMPLETE_INSERT = "INCOMPLETE_INSERT"
    MALFORMED_SQL = "MALFORMED_SQL"
    MALFORMED_XML = "MALFORMED_XML"
    XML_DTD_FORBIDDEN = "XML_DTD_FORBIDDEN"
    XML_EXTERNAL_ENTITY_FORBIDDEN = "XML_EXTERNAL_ENTITY_FORBIDDEN"
    XML_XINCLUDE_FORBIDDEN = "XML_XINCLUDE_FORBIDDEN"
    XML_NETWORK_FORBIDDEN = "XML_NETWORK_FORBIDDEN"
    XML_ENCODING_FORBIDDEN = "XML_ENCODING_FORBIDDEN"


class XmlEventKind(StrEnum):
    START_ELEMENT = "START_ELEMENT"
    END_ELEMENT = "END_ELEMENT"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class ResourceBudgets:
    max_sql_source_bytes: int
    max_statement_bytes: int
    max_tables_per_source: int
    max_columns_per_table: int
    max_identifier_code_points: int
    max_rows_per_table: int
    max_rows_per_source: int
    max_field_bytes: int
    max_insert_tuple_bytes: int
    max_reader_batch_rows: int
    max_reader_batch_bytes: int
    max_xml_document_bytes: int
    max_xml_depth: int
    max_xml_nodes: int
    max_xml_attributes_per_element: int
    max_xml_attribute_bytes: int
    max_xml_text_node_bytes: int
    max_xml_expanded_name_bytes: int
    max_diagnostics: int
    max_diagnostic_message_bytes: int
    max_diagnostics_total_bytes: int
    max_enum_set_sql_type_bytes: int


RESOURCE_BUDGETS = ResourceBudgets(
    max_sql_source_bytes=512 * _MIB,
    max_statement_bytes=16 * _MIB,
    max_tables_per_source=2048,
    max_columns_per_table=512,
    max_identifier_code_points=_MAX_IDENTIFIER_CODE_POINTS,
    max_rows_per_table=2_000_000,
    max_rows_per_source=10_000_000,
    max_field_bytes=4 * _MIB,
    max_insert_tuple_bytes=16 * _MIB,
    max_reader_batch_rows=1024,
    max_reader_batch_bytes=8 * _MIB,
    max_xml_document_bytes=64 * _MIB,
    max_xml_depth=64,
    max_xml_nodes=1_000_000,
    max_xml_attributes_per_element=256,
    max_xml_attribute_bytes=64 * _KIB,
    max_xml_text_node_bytes=1 * _MIB,
    max_xml_expanded_name_bytes=1024,
    max_diagnostics=1024,
    max_diagnostic_message_bytes=4 * _KIB,
    max_diagnostics_total_bytes=256 * _KIB,
    max_enum_set_sql_type_bytes=64 * _KIB,
)


class CancelProbe(Protocol):
    def is_set(self) -> bool:
        """Return True when the caller has requested cooperative cancellation."""


@dataclass(frozen=True, slots=True)
class NeverCancel:
    def is_set(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ParserInvocationContext:
    cancel_requested: CancelProbe
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.deadline_monotonic is not None:
            if type(self.deadline_monotonic) is not float or not math.isfinite(self.deadline_monotonic):
                raise ValueError("deadline_monotonic must be a finite float or None")


class TableAccessError(Exception):
    """Stable capability error for reader lifecycle and contract violations."""

    def __init__(self, code: ParserDiagnosticCode, message: str) -> None:
        if type(code) is not ParserDiagnosticCode:
            raise ValueError("code must be ParserDiagnosticCode")
        if type(message) is not str or message == "":
            raise ValueError("message must be a non-empty string")
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SqlSourceInput:
    document_content_digest: DigestRef
    sql_source_digest: DigestRef
    parser_input_contract_version: int
    encoding: str
    source_size_bytes: int

    def __post_init__(self) -> None:
        _require_digest(self.document_content_digest, "document_content_digest")
        _require_digest(self.sql_source_digest, "sql_source_digest")
        if self.parser_input_contract_version != PARSER_INPUT_CONTRACT_VERSION:
            raise ValueError("parser_input_contract_version must be 1")
        if self.encoding != _UTF8_ENCODING:
            raise ValueError("encoding must be utf-8")
        _require_non_negative_int(self.source_size_bytes, "source_size_bytes")
        if self.source_size_bytes > RESOURCE_BUDGETS.max_sql_source_bytes:
            raise ValueError("source_size_bytes exceeds max_sql_source_bytes")


@dataclass(frozen=True, slots=True)
class XmlSourceInput:
    document_content_digest: DigestRef
    xml_source_digest: DigestRef
    parser_input_contract_version: int
    encoding: str
    source_size_bytes: int

    def __post_init__(self) -> None:
        _require_digest(self.document_content_digest, "document_content_digest")
        _require_digest(self.xml_source_digest, "xml_source_digest")
        if self.parser_input_contract_version != PARSER_INPUT_CONTRACT_VERSION:
            raise ValueError("parser_input_contract_version must be 1")
        if self.encoding != _UTF8_ENCODING:
            raise ValueError("encoding must be utf-8")
        _require_non_negative_int(self.source_size_bytes, "source_size_bytes")
        if self.source_size_bytes > RESOURCE_BUDGETS.max_xml_document_bytes:
            raise ValueError("source_size_bytes exceeds max_xml_document_bytes")


@dataclass(frozen=True, slots=True)
class SqlParseRequest:
    source: SqlSourceInput
    sql_utf8: bytes
    context: ParserInvocationContext

    def __post_init__(self) -> None:
        if type(self.source) is not SqlSourceInput:
            raise ValueError("source must be SqlSourceInput")
        if type(self.context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if type(self.sql_utf8) is not bytes:
            raise ValueError("sql_utf8 must be bytes")
        if len(self.sql_utf8) != self.source.source_size_bytes:
            raise ValueError("source_size_bytes must equal len(sql_utf8)")
        if len(self.sql_utf8) > RESOURCE_BUDGETS.max_sql_source_bytes:
            raise ValueError("sql_utf8 exceeds max_sql_source_bytes")
        try:
            self.sql_utf8.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("sql_utf8 must be strict UTF-8") from exc


@dataclass(frozen=True, slots=True)
class XmlParseRequest:
    source: XmlSourceInput
    xml_utf8: bytes
    context: ParserInvocationContext

    def __post_init__(self) -> None:
        if type(self.source) is not XmlSourceInput:
            raise ValueError("source must be XmlSourceInput")
        if type(self.context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if type(self.xml_utf8) is not bytes:
            raise ValueError("xml_utf8 must be bytes")
        if len(self.xml_utf8) != self.source.source_size_bytes:
            raise ValueError("source_size_bytes must equal len(xml_utf8)")
        if len(self.xml_utf8) > RESOURCE_BUDGETS.max_xml_document_bytes:
            raise ValueError("xml_utf8 exceeds max_xml_document_bytes")
        try:
            self.xml_utf8.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("xml_utf8 must be strict UTF-8") from exc


@dataclass(frozen=True, slots=True)
class SourceColumnDescriptor:
    display_name: str
    canonical_name: str
    ordinal: int
    sql_type: str
    logical_type: SqlLogicalType
    declared_type: DeclaredType | None
    nullable: bool
    enum_or_set_labels: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.display_name, "display_name")
        _require_identifier(self.canonical_name, "canonical_name")
        _require_non_negative_int(self.ordinal, "ordinal")
        if type(self.sql_type) is not str or self.sql_type == "":
            raise ValueError("sql_type must be a non-empty string")
        if type(self.logical_type) is not SqlLogicalType:
            raise ValueError("logical_type must be SqlLogicalType")
        if type(self.nullable) is not bool:
            raise ValueError("nullable must be bool")
        if self.declared_type is not None and type(self.declared_type) is not DeclaredType:
            raise ValueError("declared_type must be DeclaredType or None")
        if self.enum_or_set_labels is not None:
            if type(self.enum_or_set_labels) is not tuple:
                raise ValueError("enum_or_set_labels must be a tuple or None")
            for label in self.enum_or_set_labels:
                if type(label) is not str:
                    raise ValueError("enum_or_set_labels must contain strings")
        if self.logical_type is SqlLogicalType.UNKNOWN:
            if self.declared_type is not None:
                raise ValueError("UNKNOWN column must not have declared_type")
            if self.enum_or_set_labels is not None:
                raise ValueError("UNKNOWN column must not have enum_or_set_labels")
            return
        if self.logical_type is SqlLogicalType.SET:
            if self.declared_type is not None:
                raise ValueError("SET column must not use DeclaredType")
            if self.enum_or_set_labels is None:
                raise ValueError("SET column requires enum_or_set_labels")
            return
        if self.logical_type is SqlLogicalType.ENUM:
            if self.declared_type is None or self.declared_type.kind is not DeclaredTypeKind.STRING:
                raise ValueError("ENUM column requires STRING declared_type")
            if self.enum_or_set_labels is None:
                raise ValueError("ENUM column requires enum_or_set_labels")
            return
        if self.enum_or_set_labels is not None:
            raise ValueError("non ENUM/SET column must not have enum_or_set_labels")
        if self.declared_type is None:
            raise ValueError("STANDARD/JSON column requires declared_type")
        if self.logical_type is SqlLogicalType.JSON:
            if self.declared_type.kind is not DeclaredTypeKind.STRING:
                raise ValueError("JSON column requires STRING declared_type")


@dataclass(frozen=True, slots=True)
class SourceTableDescriptor:
    display_name: str
    canonical_name: str
    columns: tuple[SourceColumnDescriptor, ...]
    primary_key_canonical_names: tuple[str, ...]
    reader_ready: bool

    def __post_init__(self) -> None:
        _require_identifier(self.display_name, "display_name")
        _require_identifier(self.canonical_name, "canonical_name")
        if type(self.columns) is not tuple:
            raise ValueError("columns must be a tuple")
        if len(self.columns) > RESOURCE_BUDGETS.max_columns_per_table:
            raise ValueError("columns exceed max_columns_per_table")
        if type(self.primary_key_canonical_names) is not tuple:
            raise ValueError("primary_key_canonical_names must be a tuple")
        if type(self.reader_ready) is not bool:
            raise ValueError("reader_ready must be bool")
        seen: set[str] = set()
        for index, column in enumerate(self.columns):
            if type(column) is not SourceColumnDescriptor:
                raise ValueError("columns must contain SourceColumnDescriptor")
            if column.ordinal != index:
                raise ValueError("column ordinal must match DDL order")
            if column.canonical_name in seen:
                raise ValueError("duplicate canonical column name")
            seen.add(column.canonical_name)
        column_names = {column.canonical_name for column in self.columns}
        pk_seen: set[str] = set()
        for name in self.primary_key_canonical_names:
            if type(name) is not str:
                raise ValueError("primary_key_canonical_names must contain strings")
            if name not in column_names:
                raise ValueError("primary key must reference a column")
            if name in pk_seen:
                raise ValueError("duplicate primary key column")
            pk_seen.add(name)
        unknown = any(column.logical_type is SqlLogicalType.UNKNOWN for column in self.columns)
        if self.reader_ready and unknown:
            raise ValueError("UNKNOWN column forbids reader_ready")
        if self.reader_ready and len(self.columns) == 0:
            raise ValueError("reader_ready table requires columns")


@dataclass(frozen=True, slots=True)
class SqlSetValue:
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.members) is not tuple:
            raise ValueError("members must be a tuple")
        for member in self.members:
            if type(member) is not str:
                raise ValueError("SET members must be strings")


SourceCell = TypedScalar | SqlSetValue
SourceRow = tuple[SourceCell, ...]


@dataclass(frozen=True, slots=True)
class ParserDiagnostic:
    code: ParserDiagnosticCode
    severity: DiagnosticSeverity
    source: DiagnosticSource
    byte_offset: int
    message: str
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not ParserDiagnosticCode:
            raise ValueError("code must be ParserDiagnosticCode")
        if type(self.severity) is not DiagnosticSeverity:
            raise ValueError("severity must be DiagnosticSeverity")
        if type(self.source) is not DiagnosticSource:
            raise ValueError("source must be DiagnosticSource")
        _require_non_negative_int(self.byte_offset, "byte_offset")
        if type(self.message) is not str or self.message == "":
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode("utf-8")) > RESOURCE_BUDGETS.max_diagnostic_message_bytes:
            raise ValueError("message exceeds max_diagnostic_message_bytes")
        if self.table is not None:
            _require_identifier(self.table, "table")
        if self.column is not None:
            _require_identifier(self.column, "column")


def diagnostic_sort_key(diagnostic: ParserDiagnostic) -> tuple[int, str]:
    """Stable diagnostic order: source offset, then code name."""
    if type(diagnostic) is not ParserDiagnostic:
        raise ValueError("diagnostic must be ParserDiagnostic")
    return (diagnostic.byte_offset, diagnostic.code.value)


class TableReader(Protocol):
    def descriptor(self) -> SourceTableDescriptor:
        """Return the frozen descriptor for this reader."""

    def iter_rows(self) -> Iterator[SourceRow]:
        """Yield positional rows once; non-rewind and single-consumer."""

    def close(self) -> None:
        """Idempotent close. Later access raises READER_CLOSED."""


class MaterializedTableReader:
    """In-memory reader that proves lifecycle without a SQL/XML parser."""

    def __init__(self, descriptor: SourceTableDescriptor, rows: tuple[SourceRow, ...]) -> None:
        if type(descriptor) is not SourceTableDescriptor:
            raise ValueError("descriptor must be SourceTableDescriptor")
        if not descriptor.reader_ready:
            raise ValueError("materialized reader requires reader_ready")
        if type(rows) is not tuple:
            raise ValueError("rows must be a tuple")
        if len(rows) > RESOURCE_BUDGETS.max_rows_per_table:
            raise ValueError("rows exceed max_rows_per_table")
        expected_width = len(descriptor.columns)
        for row in rows:
            if type(row) is not tuple:
                raise ValueError("each row must be a tuple")
            if len(row) != expected_width:
                raise ValueError("row width must match descriptor columns")
            for cell in row:
                if not _is_source_cell(cell):
                    raise ValueError("row cell is not a SourceCell")
        self._descriptor = descriptor
        self._rows = rows
        self._closed = False
        self._consumed = False

    def descriptor(self) -> SourceTableDescriptor:
        self._require_open()
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        self._require_open()
        if self._consumed:
            raise ValueError("table reader is single-consumer and non-rewind")
        self._consumed = True
        yield from self._rows

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> MaterializedTableReader:
        return MaterializedTableReader(self._descriptor, self._rows)

    def _require_open(self) -> None:
        if self._closed:
            raise TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader is closed")


@dataclass(frozen=True, slots=True)
class ParsedTable:
    descriptor: SourceTableDescriptor
    reader: TableReader | None

    def __post_init__(self) -> None:
        if type(self.descriptor) is not SourceTableDescriptor:
            raise ValueError("descriptor must be SourceTableDescriptor")
        if self.reader is None:
            if self.descriptor.reader_ready:
                raise ValueError("READY descriptor requires a reader")
            return
        if self.reader.descriptor() != self.descriptor:
            raise ValueError("reader descriptor must match table descriptor")
        if not self.descriptor.reader_ready:
            raise ValueError("non-ready descriptor cannot publish a reader")


@dataclass(frozen=True, slots=True)
class ParseResult:
    status: ParseStatus
    tables: tuple[ParsedTable, ...]
    diagnostics: tuple[ParserDiagnostic, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not ParseStatus:
            raise ValueError("status must be ParseStatus")
        if type(self.tables) is not tuple:
            raise ValueError("tables must be a tuple")
        if len(self.tables) > RESOURCE_BUDGETS.max_tables_per_source:
            raise ValueError("tables exceed max_tables_per_source")
        _require_diagnostics(self.diagnostics)
        seen: set[str] = set()
        ready_count = 0
        for table in self.tables:
            if type(table) is not ParsedTable:
                raise ValueError("tables must contain ParsedTable")
            if table.descriptor.canonical_name in seen:
                raise ValueError("duplicate canonical table name")
            seen.add(table.descriptor.canonical_name)
            if table.reader is not None:
                ready_count += 1
        if self.status is ParseStatus.COMPLETE:
            if ready_count != len(self.tables):
                raise ValueError("COMPLETE requires a reader for every table")
            return
        if self.status is ParseStatus.PARTIAL:
            if ready_count == 0 or ready_count == len(self.tables):
                raise ValueError("PARTIAL requires a mix of ready and failed tables")
            return
        if ready_count != 0:
            raise ValueError("FAILED must not publish a reader")


@dataclass(frozen=True, slots=True)
class XmlEvent:
    kind: XmlEventKind
    expanded_name: str | None = None
    attributes: tuple[tuple[str, str], ...] | None = None
    text: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not XmlEventKind:
            raise ValueError("kind must be XmlEventKind")
        if self.kind is XmlEventKind.TEXT:
            if self.expanded_name is not None or self.attributes is not None:
                raise ValueError("TEXT event forbids name and attributes")
            if type(self.text) is not str:
                raise ValueError("TEXT event requires text")
            if len(self.text.encode("utf-8")) > RESOURCE_BUDGETS.max_xml_text_node_bytes:
                raise ValueError("text exceeds max_xml_text_node_bytes")
            return
        if self.text is not None:
            raise ValueError("element event forbids text")
        _require_expanded_name(self.expanded_name)
        if self.kind is XmlEventKind.END_ELEMENT:
            if self.attributes is not None:
                raise ValueError("END_ELEMENT forbids attributes")
            return
        if self.attributes is None:
            raise ValueError("START_ELEMENT requires attributes tuple")
        if type(self.attributes) is not tuple:
            raise ValueError("attributes must be a tuple")
        if len(self.attributes) > RESOURCE_BUDGETS.max_xml_attributes_per_element:
            raise ValueError("attributes exceed max_xml_attributes_per_element")
        for name, value in self.attributes:
            _require_expanded_name(name)
            if type(value) is not str:
                raise ValueError("attribute value must be a string")
            if len(value.encode("utf-8")) > RESOURCE_BUDGETS.max_xml_attribute_bytes:
                raise ValueError("attribute exceeds max_xml_attribute_bytes")


@dataclass(frozen=True, slots=True)
class XmlParseResult:
    status: ParseStatus
    events: tuple[XmlEvent, ...]
    diagnostics: tuple[ParserDiagnostic, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not ParseStatus:
            raise ValueError("status must be ParseStatus")
        if self.status is ParseStatus.PARTIAL:
            raise ValueError("XML document result does not use PARTIAL")
        if type(self.events) is not tuple:
            raise ValueError("events must be a tuple")
        if len(self.events) > RESOURCE_BUDGETS.max_xml_nodes:
            raise ValueError("events exceed max_xml_nodes")
        for event in self.events:
            if type(event) is not XmlEvent:
                raise ValueError("events must contain XmlEvent")
        _require_diagnostics(self.diagnostics)
        if self.status is ParseStatus.FAILED and self.events:
            raise ValueError("FAILED XML result must not publish events")


def _require_digest(value: DigestRef, field: str) -> None:
    if type(value) is not DigestRef:
        raise ValueError(f"{field} must be DigestRef")


def _require_non_negative_int(value: int, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative int")


def _require_identifier(value: str, field: str) -> None:
    if type(value) is not str or value == "":
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > RESOURCE_BUDGETS.max_identifier_code_points:
        raise ValueError(f"{field} exceeds max_identifier_code_points")


def _require_expanded_name(value: str | None) -> None:
    if type(value) is not str or value == "":
        raise ValueError("expanded_name must be a non-empty string")
    if len(value.encode("utf-8")) > RESOURCE_BUDGETS.max_xml_expanded_name_bytes:
        raise ValueError("expanded_name exceeds max_xml_expanded_name_bytes")
    if value.startswith("{") and "}" not in value:
        raise ValueError("expanded_name namespace form is invalid")


def _require_diagnostics(diagnostics: tuple[ParserDiagnostic, ...]) -> None:
    if type(diagnostics) is not tuple:
        raise ValueError("diagnostics must be a tuple")
    if len(diagnostics) > RESOURCE_BUDGETS.max_diagnostics:
        raise ValueError("diagnostics exceed max_diagnostics")
    total = 0
    for diagnostic in diagnostics:
        if type(diagnostic) is not ParserDiagnostic:
            raise ValueError("diagnostics must contain ParserDiagnostic")
        total += len(diagnostic.message.encode("utf-8"))
    if total > RESOURCE_BUDGETS.max_diagnostics_total_bytes:
        raise ValueError("diagnostics exceed max_diagnostics_total_bytes")


def _is_source_cell(cell: object) -> bool:
    return isinstance(cell, SqlSetValue) or isinstance(cell, TypedScalar)
