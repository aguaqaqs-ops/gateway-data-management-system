"""Required §5.4 case-id family coverage and semantic expected-bits checks."""

from __future__ import annotations

from gateway_shared_kernel.testing.cases.catalog import all_case_seeds
from gateway_shared_kernel.testing.dispatch import compute_expected

# Stable case_id markers that must remain present; not an exhaustive catalog.
_REQUIRED_CASE_IDS: frozenset[str] = frozenset(
    {
        # JCS number serialization thresholds
        "jcs.number.threshold-1e20-decimal",
        "jcs.number.threshold-1e21-scientific",
        # Float coverage
        "scalar.float32.zero",
        "scalar.float32.negative-zero",
        "scalar.float32.finite-max",
        "scalar.float32.subnormal",
        "scalar.float32.rounding-boundary",
        "invalid.scalar.float32.nonfinite",
        "scalar.float64.zero",
        "scalar.float64.negative-zero",
        "scalar.float64.subnormal",
        "scalar.float64.rounding-boundary",
        "invalid.scalar.float64.nonfinite",
        # Decimal invalid precision/scale
        "invalid.scalar.decimal.precision-exceeds",
        "invalid.scalar.decimal.scale-exceeds",
        # Scalar text invalid Unicode
        "invalid.scalar.string.invalid-utf8",
        "invalid.scalar.string.noncharacter",
        # ULEB128 length transition + overflow
        "scalar.frame.uleb128.length-127",
        "scalar.frame.uleb128.length-128",
        "invalid.frame.uleb128.overflow",
        "invalid.frame.uleb128.non-minimal",
        # Tag partition
        "invalid.frame.tag-reserved",
        "invalid.frame.tag-unknown",
        # Row semantic-digest independence
        "digest.row.empty",
        "digest.semantic.row-empty-frame",
    }
)

_EXPECTED_TYPED_BITS: dict[str, str] = {
    "scalar.float32.rounding-boundary": "4b800000",
    "scalar.float64.rounding-boundary": "4340000000000000",
    "scalar.float32.zero": "00000000",
    "scalar.float32.negative-zero": "00000000",
    "scalar.float32.finite-max": "7f7fffff",
    "scalar.float64.subnormal": "0000000000000001",
}


def test_required_case_id_families_present() -> None:
    ids = {seed.case_id for seed in all_case_seeds()}
    missing = sorted(_REQUIRED_CASE_IDS - ids)
    assert missing == [], f"missing required case_id families: {missing}"


def test_float_rounding_and_extrema_expected_bits() -> None:
    seeds = {seed.case_id: seed for seed in all_case_seeds()}
    for case_id, bits_hex in _EXPECTED_TYPED_BITS.items():
        seed = seeds[case_id]
        expected = compute_expected(seed.operation, seed.input)
        typed = expected["typed_value"]
        assert typed["bits_hex"] == bits_hex, (
            f"{case_id}: expected bits_hex={bits_hex}, got {typed['bits_hex']}"
        )
