"""Generated typed mysqldump fragments compared with the Python reference."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from hypothesis import given, settings, strategies as st
from hypothesis.strategies import SearchStrategy
from gateway_backend.capabilities.table_access.contracts import ParseResult, ParseStatus
from tests.support.table_access_sql import parse_text


def _mysql_string(value: str) -> str:
    escapes = {
        "\\": "\\\\",
        "'": "''",
        "\0": "\\0",
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\r": "\\r",
        "\x1a": "\\Z",
    }
    return "'" + "".join(escapes.get(character, character) for character in value) + "'"


_COLUMN_TYPES = (
    ("signed_value", "BIGINT"),
    ("unsigned_value", "BIGINT UNSIGNED"),
    ("decimal_value", "DECIMAL(18,6)"),
    ("float_value", "FLOAT"),
    ("double_value", "DOUBLE"),
    ("date_value", "DATE"),
    ("datetime_value", "DATETIME(6)"),
    ("timestamp_value", "TIMESTAMP(6)"),
    ("time_value", "TIME(6)"),
    ("bit_binary", "BIT(16)"),
    ("bit_decimal", "BIT(16)"),
    ("binary_hex", "BINARY(8)"),
    ("varbinary_hex", "VARBINARY(8)"),
    ("varbinary_prefix", "VARBINARY(16)"),
    ("json_value", "JSON"),
    ("enum_value", "ENUM('red','green','blue')"),
    ("set_value", "SET('red','green','blue')"),
    ("nullable_text", "VARCHAR(32)"),
)

_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    max_size=32,
)
_JSON_LEAF: SearchStrategy[object] = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    _TEXT,
    st.floats(min_value=-1e50, max_value=1e50, allow_nan=False, allow_infinity=False),
)
_JSON_VALUE = st.recursive(
    _JSON_LEAF,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(_TEXT, children, max_size=3),
    ),
    max_leaves=10,
)


def _json_sql(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return _mysql_string(encoded)


def _format_time(parts: tuple[bool, int, int, int, int]) -> str:
    negative, hours, minutes, seconds, micros = parts
    sign = "-" if negative and (hours or minutes or seconds or micros) else ""
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{micros:06d}"


def _row_strategy(include_json_overflow: bool) -> SearchStrategy[dict[str, str]]:
    finite_json = st.one_of(
        _JSON_VALUE.map(_json_sql),
        st.just(_json_sql({"outer": [{"inner": "quote: \\\"; slash: \\\\"}]})),
    )
    json_values = (
        st.one_of(finite_json, st.just(_mysql_string('{"overflow":1e400}')))
        if include_json_overflow
        else finite_json
    )
    binary_bytes = st.one_of(
        st.just(b""),
        st.just(b"\0" * 8),
        st.binary(max_size=8),
    )
    ascii_binary = st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        max_size=16,
    ).map(lambda value: "_binary " + _mysql_string(value))
    signed = st.one_of(
        st.sampled_from((-(2**63), -1, 0, 1, 2**63 - 1)),
        st.integers(min_value=-(2**63), max_value=2**63 - 1),
    ).map(str)
    unsigned = st.one_of(
        st.sampled_from((0, 1, 2**64 - 2, 2**64 - 1)),
        st.integers(min_value=0, max_value=2**64 - 1),
    ).map(str)
    decimal = st.one_of(
        st.sampled_from(
            (
                Decimal("-999999999999.999999"),
                Decimal("-1.000000"),
                Decimal("0.000000"),
                Decimal("1.000000"),
                Decimal("999999999999.999999"),
            )
        ),
        st.decimals(
            min_value=Decimal("-999999999999.999999"),
            max_value=Decimal("999999999999.999999"),
            places=6,
            allow_nan=False,
            allow_infinity=False,
        ),
    ).map(lambda value: format(value, "f"))
    float32 = st.one_of(
        st.sampled_from((-1.0000000150474662e30, -1.0, 0.0, 1.0, 1.0000000150474662e30)),
        st.floats(
            min_value=-1.0000000150474662e30,
            max_value=1.0000000150474662e30,
            width=32,
            allow_nan=False,
            allow_infinity=False,
        ),
    ).map(repr)
    float64 = st.one_of(
        st.sampled_from((-1e100, -1.0, 0.0, 1.0, 1e100)),
        st.floats(
            min_value=-1e100,
            max_value=1e100,
            allow_nan=False,
            allow_infinity=False,
        ),
    ).map(repr)
    dates = st.dates(min_value=date(1000, 1, 1), max_value=date(9999, 12, 31)).map(
        lambda value: _mysql_string(value.isoformat())
    )
    datetimes = st.datetimes(
        min_value=datetime(1000, 1, 1),
        max_value=datetime(9999, 12, 31, 23, 59, 59, 999999),
        timezones=st.none(),
    ).map(lambda value: _mysql_string(value.strftime("%Y-%m-%d %H:%M:%S.%f")))
    timestamps = st.datetimes(
        min_value=datetime(1970, 1, 1),
        max_value=datetime(2037, 12, 31, 23, 59, 59, 999999),
        timezones=st.none(),
    ).map(lambda value: _mysql_string(value.strftime("%Y-%m-%d %H:%M:%S.%f")))
    times = st.tuples(
        st.booleans(),
        st.integers(min_value=0, max_value=838),
        st.integers(min_value=0, max_value=59),
        st.integers(min_value=0, max_value=59),
        st.integers(min_value=0, max_value=999999),
    ).map(lambda parts: _mysql_string(_format_time(parts)))
    bit_values = st.one_of(
        st.sampled_from((0, 1, 32768, 65535)),
        st.integers(min_value=0, max_value=65535),
    )
    fixed_binary = binary_bytes.map(lambda value: "x'" + value.hex() + "'")
    variable_binary = binary_bytes.map(lambda value: "0x" + value.hex())
    fields: dict[str, SearchStrategy[str]] = {
        "signed_value": signed,
        "unsigned_value": unsigned,
        "decimal_value": decimal,
        "float_value": float32,
        "double_value": float64,
        "date_value": dates,
        "datetime_value": datetimes,
        "timestamp_value": timestamps,
        "time_value": times,
        "bit_binary": bit_values.map(lambda value: f"b'{value:016b}'"),
        "bit_decimal": bit_values.map(str),
        "binary_hex": fixed_binary,
        "varbinary_hex": variable_binary,
        "varbinary_prefix": ascii_binary,
        "json_value": json_values,
        "enum_value": st.sampled_from(("red", "green", "blue")).map(_mysql_string),
        "set_value": st.sampled_from(("", "red", "green", "blue", "red,blue")).map(
            _mysql_string
        ),
        "nullable_text": _TEXT.map(_mysql_string),
    }
    return st.fixed_dictionaries(
        {
            name: st.one_of(st.just("NULL"), fields[name])
            for name, _sql_type in _COLUMN_TYPES
        }
    )


@st.composite
def _documents(
    draw: Any,
    include_json_overflow: bool = False,
) -> tuple[list[list[dict[str, str]]], list[tuple[str, str]]]:
    table_count = draw(st.integers(min_value=2, max_value=3))
    rows = [
        draw(st.lists(_row_strategy(include_json_overflow), min_size=1, max_size=2))
        for _ in range(table_count)
    ]
    comments = tuple(
        (
            draw(st.sampled_from(("", "/* ddl boundary */\n", "-- ddl boundary\n", "# ddl boundary\n"))),
            draw(st.sampled_from(("", "/* insert boundary */\n", "-- insert boundary\n", "# insert boundary\n"))),
        )
        for _ in range(table_count)
    )
    return rows, list(comments)


def _render_document(
    document: tuple[list[list[dict[str, str]]], list[tuple[str, str]]],
) -> str:
    rows_by_table, comments = document
    columns = tuple(name for name, _sql_type in _COLUMN_TYPES)
    definitions = ", ".join(
        f"`{name}` {sql_type} NULL" for name, sql_type in _COLUMN_TYPES
    )
    statements: list[str] = []
    for table_index, (rows, comment_pair) in enumerate(
        zip(rows_by_table, comments, strict=True)
    ):
        table_name = f"t{table_index}"
        statements.append(comment_pair[0])
        statements.append(f"CREATE TABLE `{table_name}` ({definitions});\n")
        statements.append("/*!40101 SET NAMES utf8mb4 */;\n")
        statements.append(comment_pair[1])
        insert_columns = columns if table_index % 2 else tuple(reversed(columns))
        column_sql = ", ".join(f"`{name}`" for name in insert_columns)
        row_sql = ", ".join(
            "(" + ", ".join(row[name] for name in insert_columns) + ")"
            for row in rows
        )
        statements.append(
            f"INSERT INTO `{table_name}` ({column_sql}) VALUES {row_sql};\n"
        )
    return "".join(statements)


def _signature(result: ParseResult) -> tuple[object, ...]:
    tables = tuple(
        (
            table.descriptor,
            None if table.reader is None else tuple(table.reader.iter_rows()),
        )
        for table in result.tables
    )
    diagnostics = tuple(
        (item.code, item.table, item.byte_offset) for item in result.diagnostics
    )
    return result.status, tables, diagnostics


@settings(max_examples=128, deadline=None, database=None, derandomize=True)
@given(document=_documents(include_json_overflow=True))
def test_generated_typed_mysqldump_fragments_match_reference(
    document: tuple[list[list[dict[str, str]]], list[tuple[str, str]]],
) -> None:
    sql = _render_document(document)
    python_result = parse_text(sql, implementation="python")
    rust_result = parse_text(sql, implementation="rust")
    assert _signature(rust_result) == _signature(python_result)


def _mutate_invalid(sql: str, mutation: str) -> str:
    if mutation == "truncate-final-tuple":
        final_tuple_close = sql.rfind(");")
        assert final_tuple_close >= 0
        return sql[:final_tuple_close] + ";\n"
    if mutation == "unterminated-string":
        return sql + "INSERT INTO `t0` (`signed_value`) VALUES ('unterminated;\n"
    raise AssertionError(f"unknown SQL mutation: {mutation}")


@settings(max_examples=64, deadline=None, database=None, derandomize=True)
@given(
    document=_documents(include_json_overflow=False),
    mutation=st.sampled_from(("truncate-final-tuple", "unterminated-string")),
)
def test_mutated_invalid_dumps_match_status_and_diagnostics(
    document: tuple[list[list[dict[str, str]]], list[tuple[str, str]]],
    mutation: str,
) -> None:
    sql = _mutate_invalid(_render_document(document), mutation)
    python_result = parse_text(sql, implementation="python")
    rust_result = parse_text(sql, implementation="rust")
    assert python_result.status in (ParseStatus.FAILED, ParseStatus.PARTIAL)
    assert python_result.diagnostics
    assert rust_result.status is python_result.status
    assert tuple(
        (item.code, item.table, item.byte_offset) for item in rust_result.diagnostics
    ) == tuple(
        (item.code, item.table, item.byte_offset) for item in python_result.diagnostics
    )
