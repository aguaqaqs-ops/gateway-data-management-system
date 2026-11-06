"""SQL reader lifecycle, reopen, cancel and timeout."""

from __future__ import annotations

import time

from typing import Protocol, cast

import pytest

from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
    TableAccessError,
    TableReader,
)

from gateway_shared_kernel import SignedIntegerScalar, StringScalar

from tests.support.table_access_sql import sql_request
from gateway_backend.capabilities.table_access import parse_arrow_sql

def parse_text(sql: str):
    return parse_arrow_sql(sql_request(sql))

class ReopenableTableReader(Protocol):
    def reopen(self) -> TableReader: ...

_SQL = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
    "INSERT INTO t VALUES (1, 'a'), (2, 'b'), (3, 'c');"
)

def test_reader_single_consumer_reopen_and_close() -> None:
    result = parse_text(_SQL)
    assert result.status is ParseStatus.COMPLETE
    reader = result.tables[0].reader
    assert reader is not None
    rows = tuple(reader.iter_rows())
    ids: list[str] = []
    for cell, _name in rows:
        assert isinstance(cell, SignedIntegerScalar)
        ids.append(cell.decimal)
    assert ids == ["1", "2", "3"]
    with pytest.raises(ValueError, match="single-consumer"):
        tuple(reader.iter_rows())
    reopened = cast(ReopenableTableReader, reader).reopen()
    reader.close()
    with pytest.raises(TableAccessError) as closed:
        reader.descriptor()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED
    assert [
        cell.decimal
        for cell, _name in tuple(reopened.iter_rows())
        if isinstance(cell, SignedIntegerScalar)
    ] == [
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
