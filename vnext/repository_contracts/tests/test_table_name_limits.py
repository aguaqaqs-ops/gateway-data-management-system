"""Table name hard limit tests."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from gateway_repository_contracts._stream_metadata import (
    TABLE_NAME_MAX_SCALARS,
    TABLE_NAME_MAX_UTF8_BYTES,
    validate_table_name,
)
from gateway_repository_contracts.errors import RepositoryContractError
from gateway_repository_contracts.stream import VersionedStreamHeaderMetadata
from gateway_repository_contracts.wire import load_schema_resource

VALID_UUID_V7 = "01234567-89ab-7cde-8f01-23456789abcd"
_SCHEMA_DIGEST = "a" * 64
_QUERY_DIGEST = "b" * 64


def test_table_name_accepts_64_ascii_scalars() -> None:
    name = "a" * TABLE_NAME_MAX_SCALARS
    assert validate_table_name(name) == name


def test_table_name_rejects_65_ascii_scalars() -> None:
    with pytest.raises(RepositoryContractError):
        validate_table_name("a" * (TABLE_NAME_MAX_SCALARS + 1))


def test_table_name_rejects_65_multibyte_scalars() -> None:
    name = "é" * (TABLE_NAME_MAX_SCALARS + 1)
    assert len(name) == TABLE_NAME_MAX_SCALARS + 1
    with pytest.raises(RepositoryContractError):
        validate_table_name(name)


def test_table_name_accepts_64_four_byte_scalars_at_utf8_boundary() -> None:
    name = "\U0001f600" * TABLE_NAME_MAX_SCALARS
    assert len(name) == TABLE_NAME_MAX_SCALARS
    assert len(name.encode("utf-8")) == TABLE_NAME_MAX_UTF8_BYTES
    validate_table_name(name)


def test_versioned_header_rejects_oversized_table_name() -> None:
    with pytest.raises(RepositoryContractError):
        VersionedStreamHeaderMetadata(
            repository_id=VALID_UUID_V7,
            repository_incarnation_id="incarnation-1",
            table_name="a" * (TABLE_NAME_MAX_SCALARS + 1),
            declared_schema_digest=_SCHEMA_DIGEST,
            query_options_digest=_QUERY_DIGEST,
            snapshot_commit_id="commit-1",
        )


def test_schema_rejects_65_scalar_table_name() -> None:
    schema = load_schema_resource("stream-metadata-v1.schema.json")
    table_name = "a" * (TABLE_NAME_MAX_SCALARS + 1)
    payload = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": "incarnation-1",
        "store_kind": "VERSIONED",
        "table_name": table_name,
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": "commit-1",
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(payload)
