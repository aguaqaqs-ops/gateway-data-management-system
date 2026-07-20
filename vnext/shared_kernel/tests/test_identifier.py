"""canonicalize_identifier tests."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import (
    CanonicalEncodingError,
    CanonicalErrorCode,
    canonicalize_identifier,
)


def test_ascii_case_fold_only() -> None:
    assert canonicalize_identifier("AbC_1") == "abc_1"


def test_does_not_trim_or_unicode_fold() -> None:
    assert canonicalize_identifier("  A") == "  a"
    # Latin capital A with ring is not ASCII A-Z
    assert canonicalize_identifier("Å") == "Å"


def test_rejects_empty() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_identifier("")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_IDENTIFIER_EMPTY


def test_rejects_surrogate() -> None:
    with pytest.raises(CanonicalEncodingError) as exc_info:
        canonicalize_identifier("a\ud800b")
    assert exc_info.value.code is CanonicalErrorCode.CANONICAL_INVALID_UNICODE
