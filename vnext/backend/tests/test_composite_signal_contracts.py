"""Composite Signal EMPTY-source identity and public contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from gateway_backend.capabilities.composite_signal import materialize_composite_signal
from gateway_backend.capabilities.composite_signal import materialize_composite_signal
from gateway_backend.capabilities.composite_signal.contracts import (
    COMPOSITE_SIGNAL_CONTRACT_VERSION,
    COMPOSITE_SIGNAL_POINT_TABLE,
    EMPTY_COMPOSITE_LOGIC_DIGEST,
    EMPTY_COMPOSITE_LOGIC_MARKER_BYTES,
    SPECIAL_DEV_ADDR,
    CompositeLogicSource,
    CompositeSignalStatus,
    empty_composite_logic_source,
    present_composite_logic_source,
)
from gateway_shared_kernel import raw_blob_digest

_OWNER = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "gateway_backend"
    / "capabilities"
    / "composite_signal"
)
_FORBIDDEN = (
    "Snapshot",
    "parse_xml",
    "parse_sql",
    "host_path",
    "dolt",
    "NotImplementedError",
    "lxml",
)


def test_empty_marker_is_stable() -> None:
    assert EMPTY_COMPOSITE_LOGIC_MARKER_BYTES == b"gateway-vnext:composite-logic-empty:v1"
    assert EMPTY_COMPOSITE_LOGIC_DIGEST == raw_blob_digest(EMPTY_COMPOSITE_LOGIC_MARKER_BYTES)
    source = empty_composite_logic_source()
    assert source.empty is True
    assert source.document_content_digest is None
    assert source.composite_logic_source_digest == EMPTY_COMPOSITE_LOGIC_DIGEST


def test_empty_source_rejects_document_digest() -> None:
    with pytest.raises(ValueError, match="EMPTY source forbids document_content_digest"):
        CompositeLogicSource(
            empty=True,
            composite_logic_source_digest=EMPTY_COMPOSITE_LOGIC_DIGEST,
            document_content_digest=raw_blob_digest(b"<xml/>"),
        )


def test_non_empty_source_requires_matching_document_digest() -> None:
    digest = raw_blob_digest(b"<xml/>")
    source = CompositeLogicSource(
        empty=False,
        composite_logic_source_digest=digest,
        document_content_digest=digest,
    )
    assert source.empty is False
    with pytest.raises(ValueError, match="non-empty source digest must equal"):
        CompositeLogicSource(
            empty=False,
            composite_logic_source_digest=digest,
            document_content_digest=raw_blob_digest(b"<other/>"),
        )


def test_versions_and_public_entry_exist() -> None:
    assert COMPOSITE_SIGNAL_CONTRACT_VERSION == 1
    assert COMPOSITE_SIGNAL_POINT_TABLE == "composite_signal_point"
    assert SPECIAL_DEV_ADDR == 65532
    assert CompositeSignalStatus.COMPLETE.value == "COMPLETE"
    assert CompositeSignalStatus.FAILED.value == "FAILED"
    assert callable(materialize_composite_signal)
    assert callable(present_composite_logic_source)


def test_owner_source_avoids_forbidden_tokens() -> None:
    for source in _OWNER.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            assert token not in text, f"{source} contains forbidden token {token}"
