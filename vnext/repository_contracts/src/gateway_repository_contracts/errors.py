"""Simple Repository wire errors."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from gateway_repository_contracts.types import BoundedOpaqueString


class SimpleError(BaseModel):
    """The v1 error shape: code, message, optional details and request ID."""

    model_config = ConfigDict(extra="forbid")

    code: BoundedOpaqueString
    message: BoundedOpaqueString
    details: dict[str, Any] | None = None
    request_id: BoundedOpaqueString | None = None
