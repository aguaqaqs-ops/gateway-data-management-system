"""Identity contract tests."""

from __future__ import annotations

import pytest

from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from gateway_repository_contracts.identities import (
    CURSOR_MAX_BYTES,
    ArtifactId,
    CallerIdentity,
    CommitId,
    CurrentCatalogGenerationId,
    CurrentTableGenerationId,
    CursorToken,
    IdempotencyKey,
    RefName,
    RepositoryId,
    RepositoryIncarnationId,
    RepositoryOperationId,
)

VALID_UUID_V7 = "01234567-89ab-7cde-8f01-23456789abcd"
VALID_UUID_V7_B = "89abcdef-0123-7abc-9def-0123456789ab"


@pytest.mark.parametrize(
    ("identity_type", "wire"),
    [
        (RepositoryId, VALID_UUID_V7),
        (RepositoryOperationId, VALID_UUID_V7_B),
        (ArtifactId, VALID_UUID_V7),
        (CallerIdentity, VALID_UUID_V7_B),
        (RepositoryIncarnationId, "incarnation-1"),
        (CommitId, "commit-provider-token"),
        (IdempotencyKey, "client-key-1"),
        (CurrentTableGenerationId, "gen-table-1"),
        (CurrentCatalogGenerationId, "gen-catalog-1"),
        (CursorToken, "cursor-opaque"),
        (RefName, "main/release-1"),
    ],
)
def test_identity_round_trip(identity_type: type[object], wire: str) -> None:
    parsed = identity_type.from_wire(wire)  # type: ignore[attr-defined]
    assert parsed.to_wire() == wire
    assert identity_type.from_wire(wire) == parsed  # type: ignore[attr-defined]


def test_cross_type_inequality() -> None:
    repo = RepositoryId.from_wire(VALID_UUID_V7)
    operation = RepositoryOperationId.from_wire(VALID_UUID_V7)
    assert repo != operation
    assert repo.to_wire() == operation.to_wire()


def test_identities_are_hashable() -> None:
    values = {
        RepositoryId.from_wire(VALID_UUID_V7),
        CommitId.from_wire("commit-1"),
        RefName.from_wire("refs/heads/main"),
    }
    assert len(values) == 3


@pytest.mark.parametrize(
    "wire",
    [
        VALID_UUID_V7.upper(),
        "01234567-89ab-4cde-8f01-23456789abcd",
        "01234567-89ab-6cde-8f01-23456789abcd",
        "01234567-89ab-7cde-cf01-23456789abcd",
        f" {VALID_UUID_V7}",
        f"{VALID_UUID_V7} ",
        123,
        "",
    ],
)
def test_uuid_v7_rejects_invalid_inputs(wire: object) -> None:
    with pytest.raises(RepositoryContractError) as exc:
        RepositoryId.from_wire(wire)
    assert exc.value.code is RepositoryContractErrorCode.IDENTITY_INVALID


def test_opaque_identity_rejects_non_ascii() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        CurrentTableGenerationId.from_wire("café-generation")
    assert exc.value.code is RepositoryContractErrorCode.IDENTITY_INVALID


def test_opaque_identity_byte_boundary_lengths() -> None:
    from gateway_repository_contracts.identities import OPAQUE_MAX_BYTES

    CurrentTableGenerationId.from_wire("a" * OPAQUE_MAX_BYTES)
    with pytest.raises(RepositoryContractError):
        CurrentTableGenerationId.from_wire("a" * (OPAQUE_MAX_BYTES + 1))


@pytest.mark.parametrize(
    "wire",
    [
        "a b",
        "a\tb",
    ],
)
def test_opaque_and_cursor_reject_whitespace_in_printable_ascii(wire: str) -> None:
    with pytest.raises(RepositoryContractError) as exc:
        CommitId.from_wire(wire)
    assert exc.value.code is RepositoryContractErrorCode.IDENTITY_INVALID
    with pytest.raises(RepositoryContractError) as exc:
        CursorToken.from_wire(wire)
    assert exc.value.code is RepositoryContractErrorCode.IDENTITY_INVALID


@pytest.mark.parametrize(
    "wire",
    [
        "_gateway/internal",
        "foo/_internal",
        ".",
        "..",
        "a//b",
        "/leading",
        "trailing/",
        "a\\b",
        "a" * 64,
        "x" * 256,
        "café",
    ],
)
def test_ref_name_rejects_invalid_values(wire: str) -> None:
    with pytest.raises(RepositoryContractError):
        RefName.from_wire(wire)


def test_cursor_token_boundary_lengths() -> None:
    ok = "a" * CURSOR_MAX_BYTES
    CursorToken.from_wire(ok)
    with pytest.raises(RepositoryContractError):
        CursorToken.from_wire("a" * (CURSOR_MAX_BYTES + 1))
    with pytest.raises(RepositoryContractError):
        CursorToken.from_wire("")
    with pytest.raises(RepositoryContractError):
        CursorToken.from_wire("café")


def test_direct_constructor_rejects_invalid_uuid() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        RepositoryId(VALID_UUID_V7.upper())
    assert exc.value.code is RepositoryContractErrorCode.IDENTITY_INVALID


def test_direct_constructor_accepts_valid_uuid() -> None:
    repo = RepositoryId(VALID_UUID_V7)
    assert repo.to_wire() == VALID_UUID_V7


def test_direct_constructor_rejects_invalid_ref_name() -> None:
    with pytest.raises(RepositoryContractError):
        RefName("_gateway/internal")
