"""Unicode scalar validation shared by JCS, identifiers, and strings."""

from __future__ import annotations

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode


def validate_unicode_string(text: str) -> None:
    for codepoint in map(ord, text):
        if 0xD800 <= codepoint <= 0xDFFF:
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_INVALID_UNICODE,
                "string contains lone UTF-16 surrogate",
            )
        if is_unicode_noncharacter(codepoint):
            raise CanonicalEncodingError(
                CanonicalErrorCode.CANONICAL_UNICODE_NONCHARACTER,
                "string contains Unicode noncharacter",
            )


def is_unicode_noncharacter(codepoint: int) -> bool:
    if 0xFDD0 <= codepoint <= 0xFDEF:
        return True
    return (codepoint & 0xFFFE) == 0xFFFE and 0xFFFE <= codepoint <= 0x10FFFF


def decode_utf8(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_INVALID_UTF8,
            "input is not valid UTF-8",
        ) from exc
