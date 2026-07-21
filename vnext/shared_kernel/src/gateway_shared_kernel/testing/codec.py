"""Test-only base64url encode; decode reuses production helper."""

from __future__ import annotations

import base64

from gateway_shared_kernel.base64url import decode_base64url_strict

__all__ = ["decode_base64url_strict", "encode_base64url"]


def encode_base64url(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise TypeError("encode_base64url requires bytes")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
