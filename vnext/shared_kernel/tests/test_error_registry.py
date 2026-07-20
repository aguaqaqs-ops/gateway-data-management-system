"""Registry completeness tests."""

from __future__ import annotations

from gateway_shared_kernel.errors import CanonicalErrorCode, FORMAL_STABLE_ERROR_CODES

_EXPECTED_CODES = frozenset(
    {
        "CANONICAL_INVALID_UTF8",
        "CANONICAL_INVALID_UNICODE",
        "CANONICAL_UNICODE_NONCHARACTER",
        "CANONICAL_JCS_SYNTAX_INVALID",
        "CANONICAL_JCS_DUPLICATE_MEMBER",
        "CANONICAL_JCS_NUMBER_OUT_OF_RANGE",
        "CANONICAL_JCS_NON_FINITE_NUMBER",
        "CANONICAL_IDENTIFIER_EMPTY",
        "CANONICAL_IDENTIFIER_COLLISION",
        "CANONICAL_TYPE_MISMATCH",
        "CANONICAL_INTEGER_OUT_OF_RANGE",
        "CANONICAL_DECIMAL_INVALID",
        "CANONICAL_FLOAT_NON_FINITE",
        "CANONICAL_TEMPORAL_INVALID",
        "CANONICAL_TIME_OUT_OF_RANGE",
        "CANONICAL_ANOMALY_INVALID",
        "CANONICAL_SCALAR_TAG_UNKNOWN",
        "CANONICAL_SCALAR_TAG_RESERVED",
        "CANONICAL_FRAME_TRUNCATED",
        "CANONICAL_ULEB128_NON_MINIMAL",
        "CANONICAL_ULEB128_OVERFLOW",
        "CANONICAL_FRAME_LENGTH_INVALID",
        "CANONICAL_COLLECTION_SEMANTICS_UNKNOWN",
        "CANONICAL_COLLECTION_DUPLICATE_ITEM",
        "CANONICAL_COLLECTION_DUPLICATE_KEY",
    }
)


def test_stable_error_registry_matches_formal_contract() -> None:
    actual = frozenset(code.value for code in CanonicalErrorCode)
    assert actual == _EXPECTED_CODES
    assert FORMAL_STABLE_ERROR_CODES == frozenset(CanonicalErrorCode)
