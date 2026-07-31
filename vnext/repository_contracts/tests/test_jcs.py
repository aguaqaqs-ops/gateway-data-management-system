"""RFC 8785 JCS encoder vector tests.

Vectors are read directly from the monorepo normative vector root.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from gateway_repository_contracts._jcs import canonicalize_jcs_bytes, encode_jcs_bytes
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

VNEXT_ROOT = Path(__file__).resolve().parents[2]
NORMATIVE_VECTOR_ROOT = (
    VNEXT_ROOT / "fixtures" / "vectors" / "shared-kernel" / "canonical-encoding" / "v1"
)

VECTOR_FILE = NORMATIVE_VECTOR_ROOT / "jcs.jsonl"


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _load_jcs_cases() -> list[tuple[str, bytes, bytes]]:
    cases: list[tuple[str, bytes, bytes]] = []
    for line in VECTOR_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        case_id = record["case_id"]
        input_bytes = _b64url_decode(record["input"]["json_utf8_base64url"])
        expected = _b64url_decode(record["expected"]["canonical_bytes_base64url"])
        cases.append((case_id, input_bytes, expected))
    return cases


@pytest.mark.parametrize(("case_id", "input_bytes", "expected"), _load_jcs_cases())
def test_jcs_vector_cases(case_id: str, input_bytes: bytes, expected: bytes) -> None:
    del case_id
    assert canonicalize_jcs_bytes(input_bytes) == expected


def test_encode_jcs_bytes_matches_canonicalize() -> None:
    payload = {"b": 1, "a": 2}
    encoded = encode_jcs_bytes(payload)
    assert encoded == canonicalize_jcs_bytes(b'{"b":1,"a":2}')


@pytest.mark.parametrize(
    ("input_bytes", "expected"),
    [
        (b"1e-5", b"0.00001"),
        (b"1e-6", b"0.000001"),
        (b"1e-7", b"1e-7"),
        (b"1e20", b"100000000000000000000"),
        (b"1e21", b"1e+21"),
    ],
)
def test_jcs_float_threshold_probes(input_bytes: bytes, expected: bytes) -> None:
    assert canonicalize_jcs_bytes(input_bytes) == expected


def test_jcs_whitespace_canonicalization() -> None:
    assert canonicalize_jcs_bytes(b" 1 ") == b"1"
    assert canonicalize_jcs_bytes(b"\t1\n") == b"1"


def test_jcs_rejects_nbsp_whitespace() -> None:
    nbsp = "\u00a0".encode()
    with pytest.raises(RepositoryContractError) as exc:
        canonicalize_jcs_bytes(nbsp + b"1" + nbsp)
    assert exc.value.code is RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID


@pytest.mark.parametrize(
    "value",
    [
        333333333.3333333,
        1.0000000000000002,
        5e-324,
    ],
)
def test_jcs_binary64_oracle_probes(value: float) -> None:
    import rfc8785

    assert encode_jcs_bytes(value) == rfc8785.dumps(value)


def test_jcs_seeded_float_differential_against_rfc8785() -> None:
    import random

    import rfc8785

    rng = random.Random(0)
    for _ in range(10_000):
        value = rng.uniform(-1e20, 1e20)
        if not (-1e308 < value < 1e308):
            continue
        assert encode_jcs_bytes(value) == rfc8785.dumps(value)
