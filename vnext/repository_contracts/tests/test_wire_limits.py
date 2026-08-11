"""Tests for shared HTTP wire size limits."""

from __future__ import annotations

from gateway_repository_contracts.wire_limits import MAX_CATALOG_JSON_BYTES, MAX_WIRE_ERROR_JSON_BYTES


def test_wire_limits_are_ordered() -> None:
    assert MAX_WIRE_ERROR_JSON_BYTES == 64 * 1024
    assert MAX_CATALOG_JSON_BYTES == 256 * 1024
    assert MAX_CATALOG_JSON_BYTES > MAX_WIRE_ERROR_JSON_BYTES
