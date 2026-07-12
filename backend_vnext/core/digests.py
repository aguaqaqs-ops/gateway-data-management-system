from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
import re
from typing import Final


SHA256_PREFIX: Final = "sha256:"
SHA256_HEX_RE: Final = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(payload: object) -> bytes:
    normalized = _normalize_json_value(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def stable_sha256(payload: object) -> str:
    if isinstance(payload, (bytes, bytearray, memoryview)):
        data = bytes(payload)
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = canonical_json_bytes(payload)
    return f"{SHA256_PREFIX}{hashlib.sha256(data).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DigestRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("digest ref must be a string")
        if not self.value.startswith(SHA256_PREFIX):
            raise ValueError("digest ref must use sha256 prefix")
        hex_digest = self.value.removeprefix(SHA256_PREFIX)
        if SHA256_HEX_RE.fullmatch(hex_digest) is None:
            raise ValueError("digest ref must contain 64 lowercase hex digits")

    @classmethod
    def parse(cls, value: str) -> "DigestRef":
        return cls(value=value)

    @classmethod
    def from_hex(cls, hex_digest: str) -> "DigestRef":
        return cls(value=f"{SHA256_PREFIX}{hex_digest}")

    @classmethod
    def from_payload(cls, payload: object) -> "DigestRef":
        return cls(value=stable_sha256(payload))

    @classmethod
    def from_bytes(cls, payload: bytes) -> "DigestRef":
        return cls(value=stable_sha256(payload))

    @property
    def hex_digest(self) -> str:
        return self.value.removeprefix(SHA256_PREFIX)

    def to_payload(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


def _normalize_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not allowed in canonical JSON")
        return value
    if isinstance(value, DigestRef):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _normalize_json_value(value.value)
    if is_dataclass(value):
        return {
            field.name: _normalize_json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    "canonical JSON only supports string mapping keys"
                )
            normalized[key] = _normalize_json_value(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized_items = [_normalize_json_value(item) for item in value]
        normalized_items.sort(key=canonical_json_bytes)
        return normalized_items
    raise TypeError(f"unsupported JSON value type: {type(value)!r}")
