"""Shared Submission domain validation for user supplied reasons."""

from __future__ import annotations

from gateway_backend.domain.submission.errors import InvalidReviewReason

REASON_MAX_BYTES = 4096


def validate_submission_reason(reason: str, *, allow_multiline: bool) -> str:
    """Validate a bounded reason while preserving its original text."""

    if type(reason) is not str:
        raise InvalidReviewReason("reason must be a string")
    for char in reason:
        codepoint = ord(char)
        if (codepoint <= 0x001F or 0x007F <= codepoint <= 0x009F) and not (
            allow_multiline and codepoint in {0x0009, 0x000A, 0x000D}
        ):
            raise InvalidReviewReason("reason contains forbidden control characters")
        if 0xD800 <= codepoint <= 0xDFFF:
            raise InvalidReviewReason("reason contains surrogate code points")
        if _is_unicode_noncharacter(codepoint):
            raise InvalidReviewReason("reason contains noncharacter code points")
    encoded = reason.encode("utf-8")
    if not 1 <= len(encoded) <= REASON_MAX_BYTES:
        raise InvalidReviewReason("reason exceeds bounded size")
    if not any(not char.isspace() for char in reason):
        raise InvalidReviewReason("reason must contain at least one non-whitespace character")
    return reason


def _is_unicode_noncharacter(codepoint: int) -> bool:
    if 0xFDD0 <= codepoint <= 0xFDEF:
        return True
    return codepoint & 0xFFFF in {0xFFFE, 0xFFFF}
