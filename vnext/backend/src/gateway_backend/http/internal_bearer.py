"""Leaf HTTP internal bearer adapters (no dependency on auth routing helpers)."""

from __future__ import annotations

from fastapi import Request

from gateway_backend.http.errors import ApiError


class FailClosedInternalBearerPort:
    def verify(self, request: Request) -> None:
        del request
        raise ApiError(
            code="AUTHENTICATION_REQUIRED",
            message="authentication required",
            status_code=401,
        )


__all__ = ["FailClosedInternalBearerPort"]
