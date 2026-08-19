"""Table Access public contract skeleton tests. Does not parse SQL or XML."""

from __future__ import annotations

from dataclasses import fields

import pytest
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    PARSER_VERSION,
    RESOURCE_BUDGETS,
    DiagnosticSeverity,
    DiagnosticSource,
    MaterializedTableReader,
    NeverCancel,
    ParsedTable,
    ParseResult,
    ParseStatus,
    ParserDiagnostic,
    ParserDiagnosticCode,
    ParserInvocationContext,
    SourceColumnDescriptor,
    SourceTableDescriptor,
    SqlLogicalType,
    SqlParseRequest,
    SqlSourceInput,
    TableAccessError,
    XmlParseResult,
    XmlSourceInput,
    diagnostic_sort_key,
)
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, DigestRef, SignedIntegerScalar
from tests.support.table_access_fixtures import (
    load_expected,
    load_text,
    parse_result_from_expected,
    xml_parse_result_from_expected,
)

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)
_CONTEXT = ParserInvocationContext(NeverCancel())

_MIB = 1024 * 1024
_KIB = 1024

EXPECTED_RESOURCE_BUDGETS = (
    ("max_sql_source_bytes", 512 * _MIB),
    ("max_statement_bytes", 16 * _MIB),
    ("max_tables_per_source", 2048),
    ("max_columns_per_table", 512),
    ("max_identifier_code_points", 64),
    ("max_rows_per_table", 2_000_000),
    ("max_rows_per_source", 10_000_000),
    ("max_field_bytes", 4 * _MIB),
    ("max_insert_tuple_bytes", 16 * _MIB),
    ("max_reader_batch_rows", 1024),
    ("max_reader_batch_bytes", 8 * _MIB),
    ("max_xml_document_bytes", 64 * _MIB),
    ("max_xml_depth", 64),
    ("max_xml_nodes", 1_000_000),
    ("max_xml_attributes_per_element", 256),
    ("max_xml_attribute_bytes", 64 * _KIB),
    ("max_xml_text_node_bytes", 1 * _MIB),
    ("max_xml_expanded_name_bytes", 1024),
    ("max_diagnostics", 1024),
    ("max_diagnostic_message_bytes", 4 * _KIB),
    ("max_diagnostics_total_bytes", 256 * _KIB),
    ("max_enum_set_sql_type_bytes", 64 * _KIB),
)

SQL_GOLDEN_CASES = (
    "sql/valid/s1-minimal-create-insert",
    "sql/malformed/s1-unsupported-replace",
)
XML_GOLDEN_CASES = (
    "xml/valid/s1-minimal-element",
    "xml/malformed/s1-truncated",
    "xml/security/s1-doctype-rejected",
)

INVALID_SQL_SOURCE_CASES = (
    (
        "non-utf8-encoding",
        {"encoding": "latin-1"},
        "encoding must be utf-8",
    ),
    (
        "oversize",
        {"source_size_bytes": RESOURCE_BUDGETS.max_sql_source_bytes + 1},
        "source_size_bytes exceeds max_sql_source_bytes",
    ),
    (
        "contract-version",
        {"parser_input_contract_version": 2},
        "parser_input_contract_version must be 1",
    ),
)

INVALID_SQL_PARSE_REQUESTS = (
    (
        "size-mismatch",
        2,
        b"a",
        "source_size_bytes must equal",
    ),
    (
        "non-utf8-bytes",
        1,
        b"\xff",
        "sql_utf8 must be strict UTF-8",
    ),
)

FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "host_path",
        "path",
        "snapshot_id",
        "snapshot_digest",
        "retention_policy",
        "cache_key",
    }
)


def test_versions_and_budgets_match_s0() -> None:
    assert PARSER_INPUT_CONTRACT_VERSION == 1
    assert PARSER_VERSION == 1
    for name, expected in EXPECTED_RESOURCE_BUDGETS:
        assert getattr(RESOURCE_BUDGETS, name) == expected, name


@pytest.mark.parametrize("case_dir", SQL_GOLDEN_CASES)
def test_sql_golden_expected_round_trips_without_parsing(case_dir: str) -> None:
    assert load_text(f"{case_dir}/input.sql")
    payload = load_expected(f"{case_dir}/expected.json")
    result = parse_result_from_expected(payload)
    assert result.status.value == payload["status"]
    assert payload["case_id"].startswith("s1-")


@pytest.mark.parametrize("case_dir", XML_GOLDEN_CASES)
def test_xml_golden_expected_round_trips_without_parsing(case_dir: str) -> None:
    assert load_text(f"{case_dir}/input.xml")
    payload = load_expected(f"{case_dir}/expected.json")
    result = xml_parse_result_from_expected(payload)
    assert result.status.value == payload["status"]
    assert payload["case_id"].startswith("s1-")
    if result.status is ParseStatus.FAILED:
        assert result.events == ()


def test_sql_source_input_has_no_forbidden_fields() -> None:
    names = {item.name for item in fields(SqlSourceInput)} | {
        item.name for item in fields(XmlSourceInput)
    }
    assert names.isdisjoint(FORBIDDEN_FIELD_NAMES)


@pytest.mark.parametrize(("label", "overrides", "message"), INVALID_SQL_SOURCE_CASES)
def test_sql_source_input_rejects_invalid_shapes(
    label: str, overrides: dict[str, object], message: str
) -> None:
    payload: dict[str, object] = {
        "document_content_digest": _ZERO_DIGEST,
        "sql_source_digest": _ZERO_DIGEST,
        "parser_input_contract_version": 1,
        "encoding": "utf-8",
        "source_size_bytes": 1,
    }
    payload.update(overrides)
    with pytest.raises(ValueError, match=message):
        SqlSourceInput(**payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(("label", "size", "sql_utf8", "message"), INVALID_SQL_PARSE_REQUESTS)
def test_sql_parse_request_rejects_invalid_bytes(
    label: str, size: int, sql_utf8: bytes, message: str
) -> None:
    source = SqlSourceInput(
        document_content_digest=_ZERO_DIGEST,
        sql_source_digest=_ZERO_DIGEST,
        parser_input_contract_version=1,
        encoding="utf-8",
        source_size_bytes=size,
    )
    with pytest.raises(ValueError, match=message):
        SqlParseRequest(source=source, sql_utf8=sql_utf8, context=_CONTEXT)


def test_parse_status_reader_invariants() -> None:
    ready = _ready_table("ok")
    failed = ParsedTable(_unknown_table("bad"), None)
    ParseResult(ParseStatus.COMPLETE, (ready,), ())
    ParseResult(ParseStatus.PARTIAL, (ready, failed), ())
    ParseResult(ParseStatus.FAILED, (failed,), ())
    with pytest.raises(ValueError, match="COMPLETE requires a reader"):
        ParseResult(ParseStatus.COMPLETE, (failed,), ())
    with pytest.raises(ValueError, match="PARTIAL requires a mix"):
        ParseResult(ParseStatus.PARTIAL, (ready,), ())
    with pytest.raises(ValueError, match="FAILED must not publish a reader"):
        ParseResult(ParseStatus.FAILED, (ready,), ())
    with pytest.raises(ValueError, match="does not use PARTIAL"):
        XmlParseResult(ParseStatus.PARTIAL, (), ())


def test_materialized_reader_close_and_single_consumer() -> None:
    table = _ready_table("ok")
    assert isinstance(table.reader, MaterializedTableReader)
    reader = table.reader
    assert tuple(reader.iter_rows()) == ((SignedIntegerScalar("1"),),)
    with pytest.raises(ValueError, match="single-consumer"):
        tuple(reader.iter_rows())
    reopened = reader.reopen()
    reader.close()
    with pytest.raises(TableAccessError) as closed:
        reader.descriptor()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED
    assert tuple(reopened.iter_rows()) == ((SignedIntegerScalar("1"),),)
    reopened.close()
    reopened.close()


def test_diagnostic_sort_key_orders_offset_then_code() -> None:
    later = ParserDiagnostic(
        code=ParserDiagnosticCode.MALFORMED_SQL,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.SQL,
        byte_offset=8,
        message="later",
    )
    earlier_unsupported = ParserDiagnostic(
        code=ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.SQL,
        byte_offset=1,
        message="early unsupported",
    )
    earlier_malformed = ParserDiagnostic(
        code=ParserDiagnosticCode.MALFORMED_SQL,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.SQL,
        byte_offset=1,
        message="early malformed",
    )
    ordered = tuple(
        sorted((later, earlier_unsupported, earlier_malformed), key=diagnostic_sort_key)
    )
    assert ordered == (earlier_malformed, earlier_unsupported, later)


def _int_column() -> SourceColumnDescriptor:
    return SourceColumnDescriptor(
        display_name="id",
        canonical_name="id",
        ordinal=0,
        sql_type="INT",
        logical_type=SqlLogicalType.STANDARD,
        declared_type=DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32),
        nullable=False,
    )


def _ready_table(name: str) -> ParsedTable:
    descriptor = SourceTableDescriptor(
        display_name=name,
        canonical_name=name,
        columns=(_int_column(),),
        primary_key_canonical_names=("id",),
        reader_ready=True,
    )
    reader = MaterializedTableReader(descriptor, ((SignedIntegerScalar("1"),),))
    return ParsedTable(descriptor, reader)


def _unknown_table(name: str) -> SourceTableDescriptor:
    column = SourceColumnDescriptor(
        display_name="payload",
        canonical_name="payload",
        ordinal=0,
        sql_type="YEAR",
        logical_type=SqlLogicalType.UNKNOWN,
        declared_type=None,
        nullable=True,
    )
    return SourceTableDescriptor(
        display_name=name,
        canonical_name=name,
        columns=(column,),
        primary_key_canonical_names=(),
        reader_ready=False,
    )
