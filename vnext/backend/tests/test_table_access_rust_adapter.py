"""Installed native SQL parser adapter boundary tests."""

from __future__ import annotations

import time
from threading import Event

import pyarrow as pa
import pytest
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserDiagnosticCode,
)
from gateway_compute._native import __build_input__, _parse_sql_native


def _native_result(
    sql: bytes,
    cancel_probe: object | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, object]:
    return _parse_sql_native(
        sql,
        cancel_probe or NeverCancel(),
        deadline_monotonic,
        1,
    )


def test_installed_extension_matches_the_current_rust_tree() -> None:
    assert len(__build_input__) == 40


def test_native_parser_returns_an_owned_arrow_c_stream() -> None:
    result = _native_result(
        b"CREATE TABLE t (id INT NOT NULL, name VARCHAR(8) NULL);"
        b"INSERT INTO t VALUES (1, 'a'), (2, 'b');"
    )
    assert result["kind"] == "result"
    assert result["status"] == "COMPLETE"
    tables = result["tables"]
    assert isinstance(tables, list)
    stream = tables[0]["arrow_stream"]
    assert isinstance(stream, pa.RecordBatchReader)
    table = stream.read_all()
    assert table.num_rows == 2
    assert table.column("id").to_pylist() == [1, 2]
    assert table.column("name").to_pylist() == ["a", "b"]


def test_native_parser_bridges_initial_cancellation_and_deadline() -> None:
    sql = b"CREATE TABLE t (id INT NULL);"
    cancel = Event()
    cancel.set()
    cancelled = _native_result(sql, cancel)
    expired = _native_result(sql, deadline_monotonic=time.monotonic() - 1.0)
    for result, expected in (
        (cancelled, ParserDiagnosticCode.PARSER_CANCELLED.value),
        (expired, ParserDiagnosticCode.PARSER_TIMEOUT.value),
    ):
        assert result["kind"] == "result"
        diagnostics = result["diagnostics"]
        assert isinstance(diagnostics, list)
        assert diagnostics[0]["code"] == expected


@pytest.mark.serial
def test_native_parser_observes_cancellation_while_detached() -> None:
    class CancelAfterInitialProbe:
        probes = 0

        def is_set(self) -> bool:
            self.probes += 1
            return self.probes > 1

    sql = (
        b"CREATE TABLE t (id INT NULL); INSERT INTO t VALUES "
        + b",".join([b"(1)"] * 200_000)
        + b";"
    )
    result = _native_result(sql, CancelAfterInitialProbe())
    assert result["kind"] == "result"
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, list)
    assert diagnostics[0]["code"] == ParserDiagnosticCode.PARSER_CANCELLED.value


def test_adapter_reuses_its_fixed_process_pool() -> None:
    _native_result(b"CREATE TABLE t (id INT NULL);")
    with pytest.raises(ValueError, match="initialized with 1 threads"):
        _parse_sql_native(b"CREATE TABLE t (id INT NULL);", NeverCancel(), None, 2)
