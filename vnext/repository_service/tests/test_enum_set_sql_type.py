"""Parameterized unit tests for ENUM/SET grammar, values, and manifest spelling."""

from __future__ import annotations

import pytest

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    SqlTypeMalformedError,
    SqlValueConversionError,
    TableCatalog,
    UnknownTypePolicy,
    arrow_type,
    compile_table_plan,
    is_known_sql_type,
    normalize_sql_type,
)
from gateway_repository_service.enum_set_sql import (
    SQL_TYPE_MALFORMED_CODE,
    SQL_VALUE_ILLEGAL_CODE,
    EnumSetSqlTypeKind,
    SqlValueIllegalError,
    classify_enum_set_sql_type,
    parse_enum_value,
    parse_set_value,
    quote_sql_string,
)
from gateway_repository_service.versioned_import.models import validate_manifest_sql_type

_MAX_ENUM_SET_BYTES = 64 * 1024


ENUM_SET_NORMALIZE_CASES: tuple[tuple[str, str, str], ...] = (
    ("ENUM", "enum('a','b')", "ENUM('a','b')"),
    ("ENUM", "ENUM('a','b')", "ENUM('a','b')"),
    ("ENUM", "enum ( 'a' , 'b' )", "ENUM('a','b')"),
    ("ENUM", "enum('A','B')", "ENUM('A','B')"),
    ("ENUM", "enum('it''s')", "ENUM('it''s')"),
    ("ENUM", "enum('a  b')", "ENUM('a  b')"),
    ("ENUM", "enum('a collate b')", "ENUM('a collate b')"),
    ("ENUM", "enum('a','b') CHARACTER SET utf8mb4", "ENUM('a','b')"),
    ("ENUM", "enum('a','b') COLLATE utf8mb4_bin", "ENUM('a','b')"),
    (
        "ENUM",
        "enum('a','b') CHARACTER SET utf8mb4 COLLATE utf8mb4_bin",
        "ENUM('a','b')",
    ),
    ("ENUM", "enum('α','β')", "ENUM('α','β')"),
    ("ENUM", "enum('')", "ENUM('')"),
    ("SET", "set('x','X')", "SET('x','X')"),
    ("SET", "SET ( 'x' , 'X' )", "SET('x','X')"),
    ("SET", "set('X','x')", "SET('X','x')"),
)


ENUM_SET_MALFORMED_TYPES: tuple[tuple[str, str], ...] = (
    ("ENUM", "ENUM"),
    ("ENUM", "ENUM()"),
    ("ENUM", "ENUM('a','b',)"),
    ("ENUM", 'ENUM("a")'),
    ("ENUM", "ENUM(`a`)"),
    ("ENUM", "ENUM('a\\'b')"),
    ("ENUM", "ENUM('a"),
    ("ENUM", "ENUM('a','a')"),
    ("ENUM", "ENUM('" + ("a" * 256) + "')"),
    ("ENUM", "ENUM('a') CHARSET utf8"),
    ("ENUM", "ENUM('a') BINARY"),
    ("ENUM", "ENUM('a') ZEROFILL"),
    ("SET", "SET()"),
    ("SET", "SET('')"),
    ("SET", "SET('a','')"),
    ("SET", "SET('a,b')"),
    ("SET", "SET('a','a')"),
    ("SET", "SET(" + ",".join("'%02d'" % index for index in range(65)) + ")"),
)


ENUM_SET_ILLEGAL_VALUES: tuple[tuple[str, object], ...] = (
    ("ENUM('a','b')", "c"),
    ("ENUM('a','b')", 1),
    ("ENUM('a','b')", ""),
    ("ENUM('a','b')", b"a"),
    ("ENUM('a','b')", True),
    ("SET('a','b')", "c"),
    ("SET('a','b')", "a,a"),
    ("SET('a','b')", "a,"),
    ("SET('a','b')", ["a", "a"]),
    ("SET('a','b')", ["a", "c"]),
    ("SET('a','b')", ["a", 1]),
    ("SET('a','b')", 1),
    ("SET('a','b')", ("a",)),
    ("SET('a','b')", b"a"),
)


def _oversized_enum_spelling() -> str:
    label = "a" * 255
    members = ",".join(quote_sql_string(f"{label}{index:03d}") for index in range(260))
    spelling = f"ENUM({members})"
    assert len(spelling.encode("utf-8")) > _MAX_ENUM_SET_BYTES
    return spelling


def _enum_spelling_of_bytes(size: int) -> str:
    labels: list[str] = []
    used = len("ENUM()")
    index = 0
    while True:
        label = f"{index:x}"
        extra = len(quote_sql_string(label)) + (1 if labels else 0)
        if used + extra > size:
            break
        labels.append(label)
        used += extra
        index += 1
    if labels:
        last = labels[-1]
        pad = size - used
        room = 255 - len(last)
        if pad > 0 and room > 0:
            labels[-1] = last + ("x" * min(pad, room))
            used = len("ENUM()") + sum(len(quote_sql_string(item)) for item in labels) + max(
                0, len(labels) - 1
            )
    spelling = f"ENUM({','.join(quote_sql_string(label) for label in labels)})"
    if len(spelling.encode("utf-8")) < size and labels:
        needed = size - len(spelling.encode("utf-8"))
        last = labels[-1]
        if len(last) + needed <= 255:
            labels[-1] = last + ("y" * needed)
            spelling = f"ENUM({','.join(quote_sql_string(label) for label in labels)})"
    return spelling


@pytest.mark.parametrize(("data_type", "column_type", "expected"), ENUM_SET_NORMALIZE_CASES)
def test_enum_set_normalize_sql_type(
    data_type: str,
    column_type: str,
    expected: str,
) -> None:
    assert normalize_sql_type(data_type, column_type) == expected
    classification, parsed = classify_enum_set_sql_type(column_type)
    assert classification == EnumSetSqlTypeKind.VALID
    assert parsed is not None
    assert parsed.normalized == expected
    assert is_known_sql_type(expected)


def test_enum_set_declaration_order_is_identity() -> None:
    assert normalize_sql_type("ENUM", "enum('a','b')") != normalize_sql_type(
        "ENUM", "enum('b','a')"
    )
    assert normalize_sql_type("SET", "set('x','X')") != normalize_sql_type(
        "SET", "set('X','x')"
    )


@pytest.mark.parametrize(("data_type", "column_type"), ENUM_SET_MALFORMED_TYPES)
def test_enum_set_malformed_type_never_unknown(
    data_type: str,
    column_type: str,
) -> None:
    with pytest.raises(SqlTypeMalformedError) as exc_info:
        normalize_sql_type(data_type, column_type)
    assert exc_info.value.code == SQL_TYPE_MALFORMED_CODE
    with pytest.raises(SqlTypeMalformedError):
        arrow_type(column_type, UnknownTypePolicy.STRINGIFY)
    with pytest.raises(SqlTypeMalformedError):
        is_known_sql_type(column_type)
    classification, parsed = classify_enum_set_sql_type(column_type)
    assert classification == EnumSetSqlTypeKind.MALFORMED
    assert parsed is None


def test_enum_set_normalized_spelling_over_64kib_is_malformed() -> None:
    spelling = _oversized_enum_spelling()
    with pytest.raises(SqlTypeMalformedError) as exc_info:
        normalize_sql_type("ENUM", spelling)
    assert exc_info.value.code == SQL_TYPE_MALFORMED_CODE


def test_non_family_types_are_not_enum_set() -> None:
    classification, parsed = classify_enum_set_sql_type("VARCHAR(10)")
    assert classification == EnumSetSqlTypeKind.NOT_ENUM_SET
    assert parsed is None
    classification, parsed = classify_enum_set_sql_type("ENUMCHAR('a')")
    assert classification == EnumSetSqlTypeKind.NOT_ENUM_SET
    assert parsed is None
    classification, parsed = classify_enum_set_sql_type("YEAR")
    assert classification == EnumSetSqlTypeKind.NOT_ENUM_SET
    assert parsed is None


@pytest.mark.parametrize(("sql_type", "raw_value"), ENUM_SET_ILLEGAL_VALUES)
def test_enum_set_illegal_values_fail_closed(sql_type: str, raw_value: object) -> None:
    parser = parse_enum_value if sql_type.startswith("ENUM") else parse_set_value
    with pytest.raises(SqlValueIllegalError) as exc_info:
        parser(sql_type, raw_value)
    assert exc_info.value.code == SQL_VALUE_ILLEGAL_CODE
    catalog = TableCatalog(
        "records",
        (ColumnCatalog("value", sql_type, True, None),),
        1,
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    with pytest.raises(SqlValueConversionError) as conversion:
        plan.normalize_row((raw_value,))
    assert conversion.value.table == "records"
    assert conversion.value.column == "value"
    assert conversion.value.sql_type == sql_type


def test_enum_set_legal_values_and_null_empty_distinction() -> None:
    assert parse_enum_value("ENUM('a','b')", None) is None
    assert parse_enum_value("ENUM('a','b')", "a") == "a"
    assert parse_enum_value("ENUM('','a')", "") == ""
    assert parse_set_value("SET('a','b')", None) is None
    assert parse_set_value("SET('a','b')", []) == []
    assert parse_set_value("SET('a','b')", "") == []
    assert parse_set_value("SET('a','b')", "b,a") == ["a", "b"]
    assert parse_set_value("SET('a','b')", ["b", "a"]) == ["a", "b"]
    catalog = TableCatalog(
        "records",
        (
            ColumnCatalog("flag", "ENUM('a','b')", True, None),
            ColumnCatalog("tags", "SET('a','b')", True, None),
        ),
        1,
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.STRINGIFY)
    enum_field = plan.expected_schema.field("flag")
    set_field = plan.expected_schema.field("tags")
    assert enum_field.type == arrow_type("ENUM('a','b')", UnknownTypePolicy.REJECT)[0]
    assert enum_field.metadata[b"gateway.logical_type"] == b"enum"
    assert b"gateway.lossy" not in enum_field.metadata
    assert set_field.metadata[b"gateway.logical_type"] == b"set"
    normalized = plan.normalize_row(("b", "b,a"))
    assert normalized.values == ("b", ["a", "b"])
    empty = plan.normalize_row((None, ""))
    assert empty.values == (None, [])


def test_validate_manifest_sql_type_accepts_normalized_enum_set() -> None:
    assert validate_manifest_sql_type("ENUM('a','b')") == "ENUM('a','b')"
    assert validate_manifest_sql_type("SET('x','X')") == "SET('x','X')"
    assert validate_manifest_sql_type("ENUM('α','β')") == "ENUM('α','β')"


def test_validate_manifest_sql_type_rejects_unnormalized_or_malformed_enum() -> None:
    with pytest.raises(ValueError, match="bounded normalized physical spelling"):
        validate_manifest_sql_type("enum('a','b')")
    with pytest.raises(ValueError, match="bounded normalized physical spelling"):
        validate_manifest_sql_type("ENUM('a','b',)")
    with pytest.raises(ValueError, match="bounded normalized physical spelling"):
        validate_manifest_sql_type("ENUM('a') CHARSET utf8")


def test_validate_manifest_sql_type_enum_64kib_and_unknown_1024() -> None:
    at_limit = _enum_spelling_of_bytes(_MAX_ENUM_SET_BYTES)
    assert len(at_limit.encode("utf-8")) == _MAX_ENUM_SET_BYTES
    assert validate_manifest_sql_type(at_limit) == at_limit
    with pytest.raises(ValueError, match="length is out of bounds"):
        validate_manifest_sql_type("Y" * 1025)
    with pytest.raises(ValueError, match="bounded normalized physical spelling"):
        validate_manifest_sql_type(_oversized_enum_spelling())
