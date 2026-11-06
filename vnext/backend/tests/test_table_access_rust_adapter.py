"""Installed native SQL parser adapter boundary tests."""

from __future__ import annotations

import time
from collections.abc import Iterator
from threading import Event
from typing import cast

import pyarrow as pa
import pytest
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserDiagnosticCode,
)
from gateway_compute._native import _encode_canonical_ipc_native, _parse_sql_native

_CANONICAL_IPC_BUDGETS = {
    "max_rows": 2_000_000,
    "max_columns": 64,
    "max_descriptor_bytes": 64 * 1024,
    "max_input_batches": 64,
    "max_input_bytes": 64 * 1024 * 1024,
    "max_output_bytes": 64 * 1024 * 1024,
    "max_codec_peak_bytes": 256 * 1024 * 1024,
}


def _native_result(
    sql: bytes,
    cancel_probe: object | None = None,
    deadline_monotonic: float | None = None,
) -> dict[str, object]:
    return cast(
        dict[str, object],
        _parse_sql_native(
            sql,
            cancel_probe or NeverCancel(),
            deadline_monotonic,
            1,
        ),
    )


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


def test_native_canonical_ipc_encoder_consumes_arrow_c_stream() -> None:
    result = _native_result(
        b"CREATE TABLE t (id BIGINT NOT NULL, name VARCHAR(8) NULL);"
        b"INSERT INTO t VALUES (1, 'a'), (2, 'b');"
    )
    tables = result["tables"]
    assert isinstance(tables, list)
    table = cast(dict[str, object], tables[0])
    encoded = _encode_canonical_ipc_native(
        table["columns"],
        table["arrow_stream"],
        NeverCancel(),
        _CANONICAL_IPC_BUDGETS,
    )
    assert isinstance(encoded, bytes)
    reader = pa.ipc.open_file(pa.BufferReader(encoded))
    decoded = reader.read_all()
    assert decoded.column_names == ["id", "name"]
    assert decoded.column("id").to_pylist() == [1, 2]
    assert decoded.column("name").to_pylist() == ["a", "b"]
    assert decoded.schema.field("id").metadata == {
        b"gdds.canonical_type": (
            b'{"declared_type":{"bit_width":null,"bits":64,"kind":"signed-integer",'
            b'"precision":null,"scale":null},"labels":null,"logical_type":"standard",'
            b'"nullable":false,"sql_type":"BIGINT"}'
        )
    }


def test_native_canonical_ipc_encoder_applies_required_budgets_and_controls() -> None:
    result = _native_result(b"CREATE TABLE t (id BIGINT NULL); INSERT INTO t VALUES (1);")
    tables = result["tables"]
    assert isinstance(tables, list)
    table = cast(dict[str, object], tables[0])

    missing_budget = dict(_CANONICAL_IPC_BUDGETS)
    missing_budget.pop("max_input_bytes")
    with pytest.raises(ValueError, match="max_input_bytes"):
        _encode_canonical_ipc_native(
            table["columns"],
            table["arrow_stream"],
            NeverCancel(),
            missing_budget,
        )

    result = _native_result(b"CREATE TABLE t (id BIGINT NULL); INSERT INTO t VALUES (1);")
    tables = result["tables"]
    assert isinstance(tables, list)
    table = cast(dict[str, object], tables[0])
    with pytest.raises(TypeError):
        _encode_canonical_ipc_native(
            table["columns"],
            table["arrow_stream"],
            NeverCancel(),
        )

    result = _native_result(b"CREATE TABLE t (id BIGINT NULL); INSERT INTO t VALUES (1);")
    tables = result["tables"]
    assert isinstance(tables, list)
    table = cast(dict[str, object], tables[0])
    cancelled = Event()
    cancelled.set()
    with pytest.raises(InterruptedError, match="cancel"):
        _encode_canonical_ipc_native(
            table["columns"],
            table["arrow_stream"],
            cancelled,
            _CANONICAL_IPC_BUDGETS,
        )

    result = _native_result(b"CREATE TABLE t (id BIGINT NULL); INSERT INTO t VALUES (1);")
    tables = result["tables"]
    assert isinstance(tables, list)
    table = cast(dict[str, object], tables[0])
    with pytest.raises(TimeoutError, match="deadline"):
        _encode_canonical_ipc_native(
            table["columns"],
            table["arrow_stream"],
            NeverCancel(),
            _CANONICAL_IPC_BUDGETS,
            time.monotonic() - 1.0,
        )


def test_native_canonical_ipc_encoder_checks_batch_budgets_during_stream_read() -> None:
    result = _native_result(b"CREATE TABLE t (id BIGINT NULL);")
    tables = result["tables"]
    assert isinstance(tables, list)
    columns = cast(dict[str, object], tables[0])["columns"]
    schema = pa.schema([pa.field("id", pa.int64(), nullable=True)])
    batches = [
        pa.record_batch([pa.array([1, 2], type=pa.int64())], schema=schema),
        pa.record_batch([pa.array([3, 4], type=pa.int64())], schema=schema),
    ]

    def guarded_batches() -> Iterator[pa.RecordBatch]:
        yield from batches
        raise AssertionError("the encoder consumed beyond the input batch budget")

    reader = pa.RecordBatchReader.from_batches(schema, guarded_batches())
    budgets = dict(_CANONICAL_IPC_BUDGETS)
    budgets["max_input_batches"] = 1
    with pytest.raises(MemoryError, match="input batch limit"):
        _encode_canonical_ipc_native(
            columns,
            reader,
            NeverCancel(),
            budgets,
        )

    byte_limited = dict(_CANONICAL_IPC_BUDGETS)
    byte_limited["max_input_bytes"] = 1
    reader = pa.RecordBatchReader.from_batches(schema, batches[:1])
    with pytest.raises(MemoryError, match="input byte limit"):
        _encode_canonical_ipc_native(
            columns,
            reader,
            NeverCancel(),
            byte_limited,
        )


@pytest.mark.serial
def test_native_canonical_ipc_encoder_observes_cancel_while_gil_is_released() -> None:
    class CancelAfterInitialProbe:
        probes = 0

        def is_set(self) -> bool:
            self.probes += 1
            return self.probes > 1

    result = _native_result(b"CREATE TABLE t (id BIGINT NULL);")
    tables = result["tables"]
    assert isinstance(tables, list)
    columns = cast(dict[str, object], tables[0])["columns"]
    schema = pa.schema([pa.field("id", pa.int64(), nullable=True)])
    array = pa.array(range(1_500_000), type=pa.int64())
    reader = pa.RecordBatchReader.from_batches(
        schema,
        [pa.record_batch([array], schema=schema)],
    )
    probe = CancelAfterInitialProbe()
    with pytest.raises(InterruptedError, match="cancel"):
        _encode_canonical_ipc_native(
            columns,
            reader,
            probe,
            _CANONICAL_IPC_BUDGETS,
        )
    assert probe.probes > 1


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
