"""Generated mysqldump fragments shared by the two Table Access implementations."""

from __future__ import annotations

from hypothesis import given, settings, strategies as st
from gateway_backend.capabilities.table_access.contracts import ParseResult
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


def _signature(result: ParseResult) -> tuple[object, ...]:
    tables = tuple(
        (
            table.descriptor,
            None if table.reader is None else tuple(table.reader.iter_rows()),
        )
        for table in result.tables
    )
    diagnostics = tuple(
        (item.code, item.table, item.column, item.byte_offset) for item in result.diagnostics
    )
    return result.status, tables, diagnostics


_ROW = st.tuples(
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.one_of(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
            max_size=48,
        ),
        st.sampled_from(("quote' slash\\ comma,()", "line\nnext", "tab\tvalue", "")),
    ),
)
_INSERTS = st.lists(st.lists(_ROW, min_size=1, max_size=5), min_size=0, max_size=4)
_PREFIXES = st.sampled_from(
    ("", "SET FOREIGN_KEY_CHECKS=0;\n", "/*!40101 SET NAMES utf8mb4 */;\n")
)
_SUFFIXES = st.sampled_from(("", "SET FOREIGN_KEY_CHECKS=1;\n", "-- generated dump\n"))


@settings(max_examples=64, deadline=None, database=None, derandomize=True)
@given(inserts=_INSERTS, prefix=_PREFIXES, suffix=_SUFFIXES)
def test_generated_insert_dumps_match_reference(
    inserts: list[list[tuple[int, str]]], prefix: str, suffix: str
) -> None:
    sql = prefix + "CREATE TABLE t (id BIGINT NULL, note VARCHAR(128) NULL);\n"
    for rows in inserts:
        values = ", ".join(f"({identifier}, {_mysql_string(note)})" for identifier, note in rows)
        sql += f"INSERT INTO t VALUES {values};\n"
    sql += suffix

    python_result = parse_text(sql, implementation="python")
    rust_result = parse_text(sql, implementation="rust")
    assert _signature(rust_result) == _signature(python_result)
