"""Focused tests for versioned read contracts."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from gateway_repository_contracts import (
    COMMIT_NOT_FOUND_CODE,
    CommitIdString,
    GetVersionedCatalogResponse,
    REF_NOT_FOUND_CODE,
    REPOSITORY_NOT_FOUND_CODE,
    ResolveVersionedRefResponse,
    StreamVersionedTableRowsQuery,
    TABLE_NOT_FOUND_CODE,
    UNKNOWN_SQL_TYPE_CODE,
    VERSIONED_READ_ARROW_MEDIA_TYPE,
    VersionedCatalog,
    VersionedColumn,
    VersionedTable,
    UnknownTypePolicy,
)
from gateway_repository_contracts.identifiers import (
    VersionedIdentifierString,
    VersionedTableNameString,
    validate_versioned_identifier,
)


class _IdentifierProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: VersionedIdentifierString


class _TableNameProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: VersionedTableNameString


class _CommitProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: CommitIdString


def _code_points(count: int, char: str = "a") -> str:
    return char * count


IDENTIFIER_VALID_CASES = [
    ("a", "a"),
    ("A", "A"),
    ("é", "é"),
    ("中文", "中文"),
    ("a b", "a b"),
    (_code_points(64), _code_points(64)),
]

IDENTIFIER_INVALID_CASES = [
    ("", "identifier length"),
    (_code_points(65), "identifier length"),
    ("\x00", "NUL"),
    ("\x01", "ASCII control"),
    ("\x7f", "ASCII control"),
    ("a/b", "path separators"),
    (r"a\b", "path separators"),
]

TABLE_NAME_INVALID_EDGE_WHITESPACE_CASES = [
    (" leading", "leading or trailing whitespace"),
    ("trailing ", "leading or trailing whitespace"),
    (" both ", "leading or trailing whitespace"),
]

COMMIT_VALID_CASES = [
    "opaque-token",
    r"back\slash-token",
    "plain'quote",
    "not-a-dolt-hash'; DROP TABLE t; --",
    "a" * 1024,
    "é",
    "Ā",
    "中文",
    "𐀀",
]

COMMIT_INVALID_CASES = [
    ("", "at least 1 character"),
    ("a" * 1025, "at most 1024 characters"),
]


@pytest.mark.parametrize(("raw", "expected"), IDENTIFIER_VALID_CASES)
def test_versioned_identifier_accepts_valid_values(raw: str, expected: str) -> None:
    probe = _IdentifierProbe(value=raw)
    assert probe.value == expected


@pytest.mark.parametrize(("raw", "message"), IDENTIFIER_INVALID_CASES)
def test_versioned_identifier_rejects_invalid_values(raw: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _IdentifierProbe(value=raw)


@pytest.mark.parametrize(("raw", "expected"), IDENTIFIER_VALID_CASES)
def test_versioned_table_name_accepts_valid_values(raw: str, expected: str) -> None:
    probe = _TableNameProbe(value=raw)
    assert probe.value == expected


@pytest.mark.parametrize(("raw", "message"), TABLE_NAME_INVALID_EDGE_WHITESPACE_CASES)
def test_versioned_table_name_rejects_edge_whitespace(raw: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _TableNameProbe(value=raw)


@pytest.mark.parametrize(("raw", "message"), IDENTIFIER_INVALID_CASES)
def test_versioned_table_name_rejects_invalid_values(raw: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _TableNameProbe(value=raw)


def test_column_identifier_allows_embedded_whitespace_but_table_name_does_not() -> None:
    assert _IdentifierProbe(value="My Column").value == "My Column"
    with pytest.raises(ValidationError, match="leading or trailing whitespace"):
        _TableNameProbe(value=" My Column")


def test_identifier_validation_preserves_case_and_unicode() -> None:
    value = "ÄbĆ"
    assert validate_versioned_identifier(value, reject_edge_whitespace=False) == value


@pytest.mark.parametrize("commit_id", COMMIT_VALID_CASES)
def test_commit_id_accepts_opaque_literals(commit_id: str) -> None:
    assert _CommitProbe(value=commit_id).value == commit_id


@pytest.mark.parametrize(("commit_id", "message"), COMMIT_INVALID_CASES)
def test_commit_id_rejects_length_boundaries(commit_id: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _CommitProbe(value=commit_id)


def test_resolve_response_requires_main_literal() -> None:
    response = ResolveVersionedRefResponse(ref_name="main", commit_id="opaque-commit")
    assert response.ref_name == "main"
    assert response.commit_id == "opaque-commit"


def test_stream_rows_query_defaults_unknown_type_policy_to_reject() -> None:
    query = StreamVersionedTableRowsQuery(table_name="items")
    assert query.unknown_type_policy == UnknownTypePolicy.REJECT


def test_unknown_type_policy_is_closed_enum() -> None:
    with pytest.raises(ValidationError):
        StreamVersionedTableRowsQuery(table_name="items", unknown_type_policy="LATEST")  # type: ignore[arg-type]


def test_versioned_catalog_dto_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VersionedCatalog(
            commit_id="c1",
            tables=(),
            extra_field=True,  # type: ignore[call-arg]
        )


def test_versioned_table_round_trip_model_dump() -> None:
    table = VersionedTable(
        name="items",
        columns=(
            VersionedColumn(name="id", sql_type="BIGINT", nullable=False),
            VersionedColumn(name="label", sql_type="VARCHAR(32)", nullable=False),
        ),
        primary_key=("id",),
        row_count=2,
    )
    catalog = VersionedCatalog(commit_id="commit-1", tables=(table,))
    response = GetVersionedCatalogResponse(catalog=catalog)
    dumped = response.model_dump(mode="json")
    assert dumped == {
        "catalog": {
            "commit_id": "commit-1",
            "tables": [
                {
                    "name": "items",
                    "columns": [
                        {"name": "id", "sql_type": "BIGINT", "nullable": False},
                        {"name": "label", "sql_type": "VARCHAR(32)", "nullable": False},
                    ],
                    "primary_key": ["id"],
                    "row_count": 2,
                }
            ],
        }
    }


def test_public_exports_include_read_constants() -> None:
    from gateway_repository_contracts import (
        REQUEST_VALIDATION_FAILED_CODE,
        SERVICE_NOT_READY_CODE,
        VERSIONED_READ_ERROR_CODES,
    )

    assert VERSIONED_READ_ARROW_MEDIA_TYPE == "application/vnd.apache.arrow.stream"
    assert REPOSITORY_NOT_FOUND_CODE == "REPOSITORY_NOT_FOUND"
    assert REF_NOT_FOUND_CODE == "REF_NOT_FOUND"
    assert COMMIT_NOT_FOUND_CODE == "COMMIT_NOT_FOUND"
    assert TABLE_NOT_FOUND_CODE == "TABLE_NOT_FOUND"
    assert UNKNOWN_SQL_TYPE_CODE == "UNKNOWN_SQL_TYPE"
    assert SERVICE_NOT_READY_CODE == "SERVICE_NOT_READY"
    assert REQUEST_VALIDATION_FAILED_CODE == "REQUEST_VALIDATION_FAILED"
    assert "SERVICE_NOT_READY" in VERSIONED_READ_ERROR_CODES


def test_resolve_request_uses_main_literal() -> None:
    from gateway_repository_contracts import ResolveVersionedRefRequest

    request = ResolveVersionedRefRequest(
        repository_id=UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"),
        ref_name="main",
    )
    assert request.ref_name == "main"


@pytest.mark.parametrize("invalid_value", [123, 1.5, None, b"bytes"])
def test_versioned_identifier_rejects_non_string_values(invalid_value: object) -> None:
    with pytest.raises(ValidationError):
        _IdentifierProbe(value=invalid_value)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_value", [123, 1.5, None, b"bytes"])
def test_versioned_table_name_rejects_non_string_values(invalid_value: object) -> None:
    with pytest.raises(ValidationError):
        _TableNameProbe(value=invalid_value)  # type: ignore[arg-type]


def test_stream_rows_query_openapi_schema_declares_table_name_constraints() -> None:
    from gateway_repository_contracts import StreamVersionedTableRowsQuery

    schema = StreamVersionedTableRowsQuery.model_json_schema()
    table_name = schema["properties"]["table_name"]
    assert table_name["minLength"] == 1
    assert table_name["maxLength"] == 64
    assert "pattern" in table_name


def test_versioned_catalog_schema_declares_identifier_constraints() -> None:
    from gateway_repository_contracts import VersionedCatalog

    schema = VersionedCatalog.model_json_schema()
    table_name = schema["$defs"]["VersionedTable"]["properties"]["name"]
    column_name = schema["$defs"]["VersionedColumn"]["properties"]["name"]
    primary_key_items = schema["$defs"]["VersionedTable"]["properties"]["primary_key"]["items"]
    for field_schema in (table_name, column_name, primary_key_items):
        assert field_schema["minLength"] == 1
        assert field_schema["maxLength"] == 64
        assert "pattern" in field_schema


def test_versioned_read_error_codes_cover_failure_matrix() -> None:
    from gateway_repository_contracts import VERSIONED_READ_ERROR_CODES

    assert VERSIONED_READ_ERROR_CODES == {
        "REPOSITORY_NOT_FOUND",
        "REF_NOT_FOUND",
        "COMMIT_NOT_FOUND",
        "TABLE_NOT_FOUND",
        "UNKNOWN_SQL_TYPE",
        "SERVICE_NOT_READY",
        "REQUEST_VALIDATION_FAILED",
    }
