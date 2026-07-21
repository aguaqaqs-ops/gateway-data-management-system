"""JCS valid/invalid candidate seeds."""

from __future__ import annotations

from gateway_shared_kernel.testing.cases import CaseSeed
from gateway_shared_kernel.testing.codec import encode_base64url


def jcs_seeds() -> list[CaseSeed]:
    seeds: list[CaseSeed] = [
        CaseSeed(
            case_id="jcs.object.ascii-key-order",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b'{"b":1,"a":2}')},
        ),
        CaseSeed(
            case_id="jcs.object.bmp-key-order",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={
                "json_utf8_base64url": encode_base64url(
                    '{"\u00e9":1,"a":2}'.encode()
                )
            },
        ),
        CaseSeed(
            case_id="jcs.object.non-bmp-key-order",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={
                "json_utf8_base64url": encode_base64url(
                    '{"\U0001f600":1,"a":2}'.encode()
                )
            },
        ),
        CaseSeed(
            case_id="jcs.string.escaping",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b'"a\\nb\\tc"')},
        ),
        CaseSeed(
            case_id="jcs.number.safe-integer-max",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"9007199254740991")},
        ),
        CaseSeed(
            case_id="jcs.number.safe-integer-min",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"-9007199254740991")},
        ),
        CaseSeed(
            case_id="jcs.number.negative-zero",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"-0.0")},
        ),
        CaseSeed(
            case_id="jcs.number.threshold-1e20-decimal",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"1e20")},
        ),
        CaseSeed(
            case_id="jcs.number.threshold-1e21-scientific",
            bucket="jcs",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"1e21")},
        ),
        CaseSeed(
            case_id="invalid.jcs.duplicate-member",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b'{"a":1,"a":2}')},
            expected_error="CANONICAL_JCS_DUPLICATE_MEMBER",
        ),
        CaseSeed(
            case_id="invalid.jcs.invalid-utf8",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"\xff")},
            expected_error="CANONICAL_INVALID_UTF8",
        ),
        CaseSeed(
            case_id="invalid.jcs.surrogate",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b'"\\uD800"')},
            expected_error="CANONICAL_INVALID_UNICODE",
        ),
        CaseSeed(
            case_id="invalid.jcs.noncharacter",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b'"\\uFFFF"')},
            expected_error="CANONICAL_UNICODE_NONCHARACTER",
        ),
        CaseSeed(
            case_id="invalid.jcs.nan",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"NaN")},
            expected_error="CANONICAL_JCS_NON_FINITE_NUMBER",
        ),
        CaseSeed(
            case_id="invalid.jcs.infinity",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"Infinity")},
            expected_error="CANONICAL_JCS_NON_FINITE_NUMBER",
        ),
        CaseSeed(
            case_id="invalid.jcs.number-out-of-range",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"9007199254740992")},
            expected_error="CANONICAL_JCS_NUMBER_OUT_OF_RANGE",
        ),
        CaseSeed(
            case_id="invalid.jcs.syntax",
            bucket="invalid",
            operation="canonicalize-jcs",
            input={"json_utf8_base64url": encode_base64url(b"{")},
            expected_error="CANONICAL_JCS_SYNTAX_INVALID",
        ),
    ]
    return seeds
