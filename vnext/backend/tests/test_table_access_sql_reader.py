"""SQL reader lifecycle, reopen, cancel and timeout."""

from __future__ import annotations

import time

import pytest
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
    TableAccessError,
)
from gateway_backend.capabilities.table_access.sql import SqlTableReader
from gateway_shared_kernel import SignedIntegerScalar, StringScalar
from tests.support.table_access_sql import parse_text, sql_request
from gateway_backend.capabilities.table_access import parse_sql

_SQL = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
    "INSERT INTO t VALUES (1, 'a'), (2, 'b'), (3, 'c');"
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


class ArmableCancel:
    def __init__(self) -> None:
        self.armed = False

    def is_set(self) -> bool:
        return self.armed


def test_reader_single_consumer_reopen_and_close() -> None:
    result = parse_text(_SQL)
    assert result.status is ParseStatus.COMPLETE
    reader = result.tables[0].reader
    assert isinstance(reader, SqlTableReader)
    rows = tuple(reader.iter_rows())
    ids: list[str] = []
    for cell, _name in rows:
        assert isinstance(cell, SignedIntegerScalar)
        ids.append(cell.decimal)
    assert ids == ["1", "2", "3"]
    with pytest.raises(ValueError, match="single-consumer"):
        tuple(reader.iter_rows())
    reopened = reader.reopen()
    reader.close()
    with pytest.raises(TableAccessError) as closed:
        reader.descriptor()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED
    assert [cell.decimal for cell, _name in tuple(reopened.iter_rows()) if isinstance(cell, SignedIntegerScalar)] == [
        "1",
        "2",
        "3",
    ]
    reopened.close()
    reopened.close()


def test_insert_column_list_permutes_to_descriptor_order() -> None:
    sql = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
        "INSERT INTO t (name, id) VALUES ('z', 9);"
    )
    result = parse_text(sql)
    reader = result.tables[0].reader
    assert reader is not None
    row = tuple(reader.iter_rows())[0]
    assert isinstance(row[0], SignedIntegerScalar)
    assert isinstance(row[1], StringScalar)
    assert row[0].decimal == "9"
    assert row[1].text == "z"


def test_expired_deadline_fails_without_reader() -> None:
    request = sql_request(_SQL, ParserInvocationContext(NeverCancel(), time.monotonic() - 1.0))
    result = parse_sql(request)
    assert result.status is ParseStatus.FAILED
    assert result.tables == ()
    assert result.diagnostics[0].code is ParserDiagnosticCode.PARSER_TIMEOUT


def test_cancel_probe_fails_without_reader() -> None:
    request = sql_request(_SQL, ParserInvocationContext(CountCancel(1)))
    result = parse_sql(request)
    assert result.status is ParseStatus.FAILED
    assert result.diagnostics[0].code is ParserDiagnosticCode.PARSER_CANCELLED


def test_reader_stream_error_invalidates_reader_instance() -> None:
    cancel = ArmableCancel()
    result = parse_text(_SQL, context=ParserInvocationContext(cancel))
    reader = result.tables[0].reader
    assert isinstance(reader, SqlTableReader)
    cancel.armed = True
    with pytest.raises(TableAccessError) as stream_error:
        tuple(reader.iter_rows())
    assert stream_error.value.code is ParserDiagnosticCode.PARSER_CANCELLED
    with pytest.raises(TableAccessError) as invalidated:
        reader.descriptor()
    assert invalidated.value.code is ParserDiagnosticCode.PARSER_CANCELLED
    reader.close()
    with pytest.raises(TableAccessError) as closed:
        reader.descriptor()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED


def test_reader_checks_cancellation_at_successful_eof_commit_point() -> None:
    cancel = ArmableCancel()
    result = parse_text(
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);",
        context=ParserInvocationContext(cancel),
    )
    reader = result.tables[0].reader
    assert isinstance(reader, SqlTableReader)
    iterator = reader.iter_rows()
    next(iterator)
    cancel.armed = True
    with pytest.raises(TableAccessError) as stream_error:
        next(iterator)
    assert stream_error.value.code is ParserDiagnosticCode.PARSER_CANCELLED
    with pytest.raises(TableAccessError) as invalidated:
        reader.descriptor()
    assert invalidated.value.code is ParserDiagnosticCode.PARSER_CANCELLED
