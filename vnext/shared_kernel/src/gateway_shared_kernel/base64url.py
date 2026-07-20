"""Strict unpadded base64url helpers."""

from __future__ import annotations

import base64
import binascii
import re

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode

_BASE64URL_CHARSET_RE = re.compile(r"^[A-Za-z0-9_-]*$")


def decode_base64url_strict(text: str) -> bytes:
    """Decode unpadded base64url and require round-trip identity."""
    if not isinstance(text, str):
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "base64url value must be a string",
        )
    if "=" in text or _BASE64URL_CHARSET_RE.fullmatch(text) is None:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "base64url must use unpadded URL-safe alphabet",
        )
    if len(text) % 4 == 1:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "base64url length modulo 4 must not be 1",
        )
    pad_len = (-len(text)) % 4
    try:
        raw = base64.urlsafe_b64decode(text + ("=" * pad_len))
    except (ValueError, binascii.Error) as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "base64url is not decodable",
        ) from exc
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if encoded != text:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_ANOMALY_INVALID,
            "base64url is not a canonical unpadded encoding",
        )
    return raw
