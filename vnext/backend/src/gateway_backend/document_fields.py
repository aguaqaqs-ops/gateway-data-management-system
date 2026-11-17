"""Shared strict document field readers for capability and application codecs."""

from __future__ import annotations


def document_string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def document_string_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw[key]
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"{key} must be a string list")
    return tuple(value)


__all__ = ["document_string", "document_string_tuple"]
