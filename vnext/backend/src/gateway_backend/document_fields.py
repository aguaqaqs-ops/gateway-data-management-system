"""Shared strict document field readers for capability and application codecs."""

from __future__ import annotations


def document_string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


__all__ = ["document_string"]
