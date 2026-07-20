"""CanonicalIdentifier ASCII fold."""

from __future__ import annotations

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.unicode import validate_unicode_string


def canonicalize_identifier(identifier: str) -> str:
    """Fold ASCII A-Z to a-z; no trim and no Unicode case folding."""
    if identifier == "":
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_IDENTIFIER_EMPTY,
            "identifier must not be empty",
        )
    validate_unicode_string(identifier)
    return "".join(
        chr(ord(char) + 32) if "A" <= char <= "Z" else char for char in identifier
    )
