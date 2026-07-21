"""Numeric / text / temporal / anomaly scalar candidate seeds."""

from __future__ import annotations

import struct
from typing import Any

from gateway_shared_kernel.testing.cases import CaseSeed
from gateway_shared_kernel.testing.codec import encode_base64url

_INTEGER_BITS = (8, 16, 24, 32, 64)


def _utf8(text: str) -> dict[str, Any]:
    return {"kind": "utf8-logical-literal", "text": text}


def _raw(data: bytes) -> dict[str, Any]:
    return {"kind": "raw-logical-literal", "bytes_base64url": encode_base64url(data)}


def _signed(bits: int) -> dict[str, Any]:
    return {"kind": "signed-integer", "bits": bits}


def _unsigned(bits: int) -> dict[str, Any]:
    return {"kind": "unsigned-integer", "bits": bits}


def _bounds(signed: bool, bits: int) -> tuple[int, int]:
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def scalar_seeds() -> list[CaseSeed]:
    seeds: list[CaseSeed] = [
        CaseSeed(
            case_id="scalar.null.empty",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "null"}, "source": _utf8("")},
        ),
        CaseSeed(
            case_id="scalar.boolean.true",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "boolean"}, "source": _utf8("true")},
        ),
        CaseSeed(
            case_id="scalar.signed-integer.leading-plus",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": _signed(32), "source": _utf8("+001")},
        ),
        CaseSeed(
            case_id="scalar.signed-integer.negative-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": _signed(32), "source": _utf8("-0")},
        ),
        CaseSeed(
            case_id="scalar.decimal.canonical-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
                "source": _utf8("0.00"),
            },
        ),
        CaseSeed(
            case_id="scalar.decimal.leading-trailing-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "decimal", "precision": 10, "scale": 4},
                "source": _utf8("0010.1200"),
            },
        ),
        CaseSeed(
            case_id="scalar.decimal.boundary-65-30",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "decimal", "precision": 65, "scale": 30},
                "source": _utf8("1." + ("0" * 29) + "1"),
            },
        ),
        CaseSeed(
            case_id="scalar.float32.zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "float32"}, "source": _utf8("0")},
        ),
        CaseSeed(
            case_id="scalar.float32.negative-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "float32"}, "source": _utf8("-0.0")},
        ),
        CaseSeed(
            case_id="scalar.float32.finite-max",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "float32"},
                "source": _utf8("3.4028235e38"),
            },
        ),
        CaseSeed(
            case_id="scalar.float64.zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "float64"}, "source": _utf8("0")},
        ),
        CaseSeed(
            case_id="scalar.float64.negative-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={"declared_type": {"kind": "float64"}, "source": _utf8("-0.0")},
        ),
        CaseSeed(
            case_id="scalar.float32.subnormal",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "float32"},
                "typed_value": {"kind": "float32", "bits_hex": "00000001"},
            },
        ),
        CaseSeed(
            case_id="scalar.float64.subnormal",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "float64"},
                "source": _utf8("5e-324"),
            },
        ),
        CaseSeed(
            case_id="scalar.float32.rounding-boundary",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "float32"},
                "source": _utf8("16777217"),
            },
        ),
        CaseSeed(
            case_id="scalar.float64.rounding-boundary",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "float64"},
                # 2^53 + 1 ties-to-even toward 2^53.
                "source": _utf8("9007199254740993"),
            },
        ),
        CaseSeed(
            case_id="scalar.float64.finite-max",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "float64"},
                "typed_value": {
                    "kind": "float64",
                    "bits_hex": f"{struct.unpack('>Q', struct.pack('>d', 1.7976931348623157e308))[0]:016x}",
                },
            },
        ),
        CaseSeed(
            case_id="scalar.string.empty",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "string"},
                "typed_value": {"kind": "string", "text": ""},
            },
        ),
        CaseSeed(
            case_id="scalar.frame.uleb128.length-127",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "string"},
                "typed_value": {"kind": "string", "text": "a" * 127},
            },
        ),
        CaseSeed(
            case_id="scalar.frame.uleb128.length-128",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "string"},
                "typed_value": {"kind": "string", "text": "a" * 128},
            },
        ),
        CaseSeed(
            case_id="scalar.string.multibyte",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "string"},
                "typed_value": {"kind": "string", "text": "你好"},
            },
        ),
        CaseSeed(
            case_id="scalar.string.non-bmp",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "string"},
                "typed_value": {"kind": "string", "text": "\U0001f600"},
            },
        ),
        CaseSeed(
            case_id="scalar.binary.empty",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "binary"},
                "typed_value": {
                    "kind": "binary",
                    "bytes_base64url": encode_base64url(b""),
                },
            },
        ),
        CaseSeed(
            case_id="scalar.binary.leading-zero",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "binary"},
                "typed_value": {
                    "kind": "binary",
                    "bytes_base64url": encode_base64url(b"\x00\x01"),
                },
            },
        ),
        CaseSeed(
            case_id="scalar.date.leap-day",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "date"},
                "source": _utf8("2024-02-29"),
            },
        ),
        CaseSeed(
            case_id="scalar.datetime.fraction",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "datetime"},
                "source": _utf8("2024-01-02T03:04:05.123456"),
            },
        ),
        CaseSeed(
            case_id="scalar.timestamp.fraction",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "timestamp"},
                "source": _utf8("2024-01-02T03:04:05.1Z"),
            },
        ),
        CaseSeed(
            case_id="scalar.time-duration.zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "time-duration"},
                "source": _utf8("00:00:00"),
            },
        ),
        CaseSeed(
            case_id="scalar.time-duration.hours-99",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "time-duration"},
                "source": _utf8("99:00:00"),
            },
        ),
        CaseSeed(
            case_id="scalar.time-duration.hours-100",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "time-duration"},
                "source": _utf8("100:00:00"),
            },
        ),
        CaseSeed(
            case_id="scalar.time-duration.hours-838",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "time-duration"},
                "source": _utf8("838:59:59"),
            },
        ),
        CaseSeed(
            case_id="scalar.time-duration.negative-zero",
            bucket="scalar",
            operation="normalize-logical-literal",
            input={
                "declared_type": {"kind": "time-duration"},
                "source": _utf8("-00:00:00"),
            },
        ),
        CaseSeed(
            case_id="scalar.anomaly.valid-envelope",
            bucket="scalar",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "source-literal-anomaly"},
                "typed_value": {
                    "kind": "source-literal-anomaly",
                    "envelope": {
                        "declared_type": {"kind": "date"},
                        "raw_base64url": encode_base64url(b"bad"),
                        "raw_encoding": "utf8",
                        "reason": "owner-reason",
                    },
                },
            },
        ),
    ]

    for bits in _INTEGER_BITS:
        lo, hi = _bounds(True, bits)
        seeds.append(
            CaseSeed(
                case_id=f"scalar.signed-integer.{bits}.min",
                bucket="scalar",
                operation="normalize-logical-literal",
                input={"declared_type": _signed(bits), "source": _utf8(str(lo))},
            )
        )
        seeds.append(
            CaseSeed(
                case_id=f"scalar.signed-integer.{bits}.max",
                bucket="scalar",
                operation="normalize-logical-literal",
                input={"declared_type": _signed(bits), "source": _utf8(str(hi))},
            )
        )
        seeds.append(
            CaseSeed(
                case_id=f"invalid.scalar.signed-integer.{bits}.overflow",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={"declared_type": _signed(bits), "source": _utf8(str(hi + 1))},
                expected_error="CANONICAL_INTEGER_OUT_OF_RANGE",
            )
        )
        ulo, uhi = _bounds(False, bits)
        seeds.append(
            CaseSeed(
                case_id=f"scalar.unsigned-integer.{bits}.min",
                bucket="scalar",
                operation="normalize-logical-literal",
                input={"declared_type": _unsigned(bits), "source": _utf8(str(ulo))},
            )
        )
        seeds.append(
            CaseSeed(
                case_id=f"scalar.unsigned-integer.{bits}.max",
                bucket="scalar",
                operation="normalize-logical-literal",
                input={"declared_type": _unsigned(bits), "source": _utf8(str(uhi))},
            )
        )
        seeds.append(
            CaseSeed(
                case_id=f"invalid.scalar.unsigned-integer.{bits}.overflow",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": _unsigned(bits),
                    "source": _utf8(str(uhi + 1)),
                },
                expected_error="CANONICAL_INTEGER_OUT_OF_RANGE",
            )
        )

    for width in (1, 8, 9, 64):
        byte_len = (width + 7) // 8
        raw = bytes(byte_len)
        seeds.append(
            CaseSeed(
                case_id=f"scalar.bit.width-{width}",
                bucket="scalar",
                operation="encode-typed-scalar",
                input={
                    "declared_type": {"kind": "bit", "bit_width": width},
                    "typed_value": {
                        "kind": "bit",
                        "bytes_base64url": encode_base64url(raw),
                    },
                },
            )
        )

    # BIT unused high bit failure: bit_width=1 but payload has high bit set in sole byte
    seeds.append(
        CaseSeed(
            case_id="invalid.scalar.bit.unused-high-bit",
            bucket="invalid",
            operation="encode-typed-scalar",
            input={
                "declared_type": {"kind": "bit", "bit_width": 1},
                "typed_value": {
                    "kind": "bit",
                    "bytes_base64url": encode_base64url(b"\x02"),
                },
            },
            expected_error="CANONICAL_TYPE_MISMATCH",
        )
    )

    seeds.extend(
        [
            CaseSeed(
                case_id="invalid.scalar.decimal.exponent",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
                    "source": _utf8("1e2"),
                },
                expected_error="CANONICAL_DECIMAL_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.decimal.plus",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
                    "source": _utf8("+1.0"),
                },
                expected_error="CANONICAL_DECIMAL_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.decimal.precision-exceeds",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
                    "source": _utf8("123456789.01"),
                },
                expected_error="CANONICAL_DECIMAL_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.decimal.scale-exceeds",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
                    "source": _utf8("1.123"),
                },
                expected_error="CANONICAL_DECIMAL_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.float32.nonfinite",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "float32"},
                    "source": _utf8("3.5e38"),
                },
                expected_error="CANONICAL_FLOAT_NON_FINITE",
            ),
            CaseSeed(
                case_id="invalid.scalar.float64.nonfinite",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "float64"},
                    "source": _utf8("1e1000"),
                },
                expected_error="CANONICAL_FLOAT_NON_FINITE",
            ),
            CaseSeed(
                case_id="invalid.scalar.date.invalid",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "date"},
                    "source": _utf8("2023-02-29"),
                },
                expected_error="CANONICAL_TEMPORAL_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.time-duration.out-of-range",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "time-duration"},
                    "source": _utf8("839:00:00"),
                },
                expected_error="CANONICAL_TIME_OUT_OF_RANGE",
            ),
            CaseSeed(
                case_id="invalid.scalar.anomaly.invalid-base64url",
                bucket="invalid",
                operation="encode-typed-scalar",
                input={
                    "declared_type": {"kind": "source-literal-anomaly"},
                    "typed_value": {
                        "kind": "source-literal-anomaly",
                        "envelope": {
                            "declared_type": {"kind": "date"},
                            # Schema-valid alphabet/length, but non-canonical decode round-trip.
                            "raw_base64url": "aa",
                            "raw_encoding": "utf8",
                            "reason": "owner-reason",
                        },
                    },
                },
                expected_error="CANONICAL_ANOMALY_INVALID",
            ),
            CaseSeed(
                case_id="invalid.scalar.string.invalid-utf8",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "string"},
                    "source": _raw(b"\xff"),
                },
                expected_error="CANONICAL_INVALID_UTF8",
            ),
            CaseSeed(
                case_id="invalid.scalar.string.noncharacter",
                bucket="invalid",
                operation="normalize-logical-literal",
                input={
                    "declared_type": {"kind": "string"},
                    "source": _raw("\uFFFF".encode("utf-8")),
                },
                expected_error="CANONICAL_UNICODE_NONCHARACTER",
            ),
        ]
    )
    return seeds
