"""Bounded upload streaming and archive file-like admission tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from gateway_backend.http.orchestration.multipart_stream import iter_file_chunks
from gateway_backend.http.orchestration.source_package_admission import (
    validate_source_package_archive,
)
from tests.support.upload_http_packages import INITIAL_BYTES

pytestmark = pytest.mark.unit


def test_iter_file_chunks_yields_an_iterator_not_a_joined_list(tmp_path: Path) -> None:
    path = tmp_path / "part.bin"
    path.write_bytes(b"abcdef")
    chunks = iter_file_chunks(path, chunk_size=2)
    assert not isinstance(chunks, list)
    assert tuple(chunks) == (b"ab", b"cd", b"ef")


def test_validate_source_package_archive_accepts_file_handle() -> None:
    validate_source_package_archive(BytesIO(INITIAL_BYTES), compressed_bytes=len(INITIAL_BYTES))
