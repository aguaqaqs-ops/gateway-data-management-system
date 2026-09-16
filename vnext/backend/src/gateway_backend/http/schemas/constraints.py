"""Shared HTTP DTO validation constraints."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, Strict

from gateway_backend.operations.contracts import (
    _IJSON_MAX_SAFE_INTEGER,
    _MAX_DIAGNOSTIC_MESSAGE_BYTES,
    _MAX_OPAQUE_ID_BYTES,
)

NonNegativeIJsonInt = Annotated[int, Strict(), Field(ge=0, le=_IJSON_MAX_SAFE_INTEGER)]


def _coerce_opaque_id(value: object) -> str:
    if type(value) is not str:
        raise ValueError("id must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_OPAQUE_ID_BYTES:
        raise ValueError("id exceeds bounded opaque identifier size")
    return value


def _coerce_diagnostic_reason(value: object) -> str:
    if type(value) is not str:
        raise ValueError("reason must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DIAGNOSTIC_MESSAGE_BYTES:
        raise ValueError("reason exceeds bounded diagnostic size")
    return value


BoundedOpaqueId = Annotated[str, BeforeValidator(_coerce_opaque_id)]
BoundedDiagnosticReason = Annotated[str, BeforeValidator(_coerce_diagnostic_reason)]
