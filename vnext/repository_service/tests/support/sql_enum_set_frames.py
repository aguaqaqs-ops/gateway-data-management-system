"""Test-only ENUM/SET content frames matching Shared Canonical Encoding §3.2.

Production Repository sources must not import Shared Kernel. These helpers
only reconstruct the published string/null scalar_frame and sequence_frame
layout for golden comparison.
"""

from __future__ import annotations

import base64

_TAG_NULL = 0x00
_TAG_STRING = 0x20


def encode_base64url(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise TypeError("encode_base64url requires bytes")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def encode_uleb128(value: int) -> bytes:
    if type(value) is not int or value < 0:
        raise ValueError("ULEB128 value must be a non-negative int")
    if value == 0:
        return b"\x00"
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def encode_null_scalar_frame() -> bytes:
    return bytes([_TAG_NULL]) + encode_uleb128(0)


def encode_string_scalar_frame(text: str) -> tuple[bytes, bytes]:
    payload = text.encode("utf-8")
    frame = bytes([_TAG_STRING]) + encode_uleb128(len(payload)) + payload
    return payload, frame


def encode_sequence_frame(item_frames: tuple[bytes, ...]) -> bytes:
    parts = bytearray(encode_uleb128(len(item_frames)))
    for item in item_frames:
        parts.extend(encode_uleb128(len(item)))
        parts.extend(item)
    return bytes(parts)
