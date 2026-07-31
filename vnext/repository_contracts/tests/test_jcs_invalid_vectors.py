"""Invalid JCS vector conformance tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from gateway_repository_contracts._jcs import canonicalize_jcs_bytes
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

VNEXT_ROOT = Path(__file__).resolve().parents[2]
NORMATIVE_VECTOR_ROOT = (
    VNEXT_ROOT / "fixtures" / "vectors" / "shared-kernel" / "canonical-encoding" / "v1"
)

VECTOR_FILE = NORMATIVE_VECTOR_ROOT / "invalid.jsonl"

_JCS_ERROR_MAP = {
    "CANONICAL_JCS_DUPLICATE_MEMBER": RepositoryContractErrorCode.WIRE_DUPLICATE_MEMBER,
    "CANONICAL_JCS_NON_FINITE_NUMBER": RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
    "CANONICAL_INVALID_UTF8": RepositoryContractErrorCode.WIRE_INVALID_UTF8,
    "CANONICAL_UNICODE_NONCHARACTER": RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
    "CANONICAL_JCS_NUMBER_OUT_OF_RANGE": RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
    "CANONICAL_INVALID_UNICODE": RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
    "CANONICAL_JCS_SYNTAX_INVALID": RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
}


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _load_jcs_invalid_cases() -> list[tuple[str, bytes, RepositoryContractErrorCode]]:
    cases: list[tuple[str, bytes, RepositoryContractErrorCode]] = []
    for line in VECTOR_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("operation") != "canonicalize-jcs":
            continue
        case_id = record["case_id"]
        input_bytes = _b64url_decode(record["input"]["json_utf8_base64url"])
        code_name = record["expected_error"]["code"]
        mapped = _JCS_ERROR_MAP.get(code_name)
        if mapped is None:
            continue
        cases.append((case_id, input_bytes, mapped))
    return cases


@pytest.mark.parametrize(("case_id", "input_bytes", "expected_code"), _load_jcs_invalid_cases())
def test_jcs_invalid_vector_cases(
    case_id: str, input_bytes: bytes, expected_code: RepositoryContractErrorCode
) -> None:
    del case_id
    with pytest.raises(RepositoryContractError) as exc:
        canonicalize_jcs_bytes(input_bytes)
    assert exc.value.code is expected_code
