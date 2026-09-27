"""Shared HTTP DTO validation constraints."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, Strict

from gateway_backend.operations.contracts import (
    IJSON_MAX_SAFE_INTEGER,
    MAX_DIAGNOSTIC_MESSAGE_BYTES,
    MAX_OPAQUE_ID_BYTES,
)

NonNegativeIJsonInt = Annotated[int, Strict(), Field(ge=0, le=IJSON_MAX_SAFE_INTEGER)]


def _coerce_opaque_id(value: object) -> str:
    if type(value) is not str:
        raise ValueError("id must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= MAX_OPAQUE_ID_BYTES:
        raise ValueError("id exceeds bounded opaque identifier size")
    return value


def _coerce_diagnostic_reason(value: object) -> str:
    if type(value) is not str:
        raise ValueError("reason must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= MAX_DIAGNOSTIC_MESSAGE_BYTES:
        raise ValueError("reason exceeds bounded diagnostic size")
    return value


BoundedOpaqueId = Annotated[str, BeforeValidator(_coerce_opaque_id)]
BoundedDiagnosticReason = Annotated[str, BeforeValidator(_coerce_diagnostic_reason)]


def _coerce_sha256_digest(value: object) -> str:
    if type(value) is not str:
        raise ValueError("digest must be a string")
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("digest must be sha256:<64 hex chars>")
    hex_part = value[7:]
    if len(hex_part) != 64 or any(char not in "0123456789abcdef" for char in hex_part):
        raise ValueError("digest must be sha256:<64 hex chars>")
    return value


Sha256Digest = Annotated[str, BeforeValidator(_coerce_sha256_digest)]

CommitIdString = Annotated[str, Field(min_length=1, max_length=1024)]
