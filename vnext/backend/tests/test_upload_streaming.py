"""Bounded upload streaming and archive file-like admission tests."""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import Headers

from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.multipart_stream import (
    iter_file_chunks,
    parse_streaming_multipart,
)
from gateway_backend.http.orchestration.source_package_admission import (
    UploadLimitExceededError,
    validate_source_package_archive,
)
from tests.support.upload_http_packages import INITIAL_BYTES

pytestmark = pytest.mark.unit

_BOUNDARY = "----gateway-test-boundary"


def test_iter_file_chunks_yields_an_iterator_not_a_joined_list(tmp_path: Path) -> None:
    path = tmp_path / "part.bin"
    path.write_bytes(b"abcdef")
    chunks = iter_file_chunks(path, chunk_size=2)
    assert not isinstance(chunks, list)
    assert tuple(chunks) == (b"ab", b"cd", b"ef")


def test_validate_source_package_archive_accepts_file_handle() -> None:
    validate_source_package_archive(BytesIO(INITIAL_BYTES), compressed_bytes=len(INITIAL_BYTES))


@pytest.mark.serial
def test_stalled_body_times_out_while_waiting_for_next_chunk() -> None:
    async def stalled_stream() -> AsyncIterator[bytes]:
        yield (
            f"--{_BOUNDARY}\r\n"
            'Content-Disposition: form-data; name="manifest"\r\n\r\n'
            "{"
        ).encode("ascii")
        await asyncio.sleep(0.15)

    async def run() -> None:
        with pytest.raises(UploadLimitExceededError, match="timed out"):
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=stalled_stream(),
                timeout_seconds=0.01,
            )

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 0.12


def test_non_multipart_content_type_is_rejected_before_parsing_body() -> None:
    payload = _multipart_body([("manifest", b"{}"), ("modified", b"abc")])

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"application/json; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        error = caught.value
        assert error.status_code == 422
        assert error.code == "REQUEST_VALIDATION_FAILED"

    asyncio.run(run())


def test_caller_controlled_part_name_is_rejected_without_pathname_escape() -> None:
    payload = _multipart_body([("x/y", b"not-a-path")])

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        error = caught.value
        assert error.status_code == 422
        assert error.code == "REQUEST_VALIDATION_FAILED"
        assert not isinstance(error.__cause__, FileNotFoundError)

    asyncio.run(run())


def test_overlong_multipart_header_is_rejected() -> None:
    payload = (
        f"--{_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="manifest"\r\n'
        f"X-Overflow: {'a' * 5000}\r\n"
        "\r\n"
        "{}\r\n"
        f"--{_BOUNDARY}--\r\n"
    ).encode("ascii")

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        assert caught.value.status_code == 422
        assert caught.value.code == "REQUEST_VALIDATION_FAILED"

    asyncio.run(run())


def test_file_part_uses_server_owned_staging_name() -> None:
    payload = _multipart_body([("manifest", b"{}"), ("modified", b"abc")])

    async def run() -> None:
        parsed = await parse_streaming_multipart(
            headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
            stream=_one_chunk(payload),
        )
        try:
            staged = parsed.file_parts["modified"]
            assert staged.name == "modified"
            assert staged.path.name == "part-1"
            assert staged.path.parent == parsed.staging_dir
            assert "modified" not in staged.path.name
        finally:
            shutil.rmtree(parsed.staging_dir, ignore_errors=True)

    asyncio.run(run())


async def _one_chunk(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


def _multipart_body(parts: list[tuple[str, bytes]]) -> bytes:
    chunks: list[bytes] = []
    for name, body in parts:
        chunks.append(
            (
                f"--{_BOUNDARY}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                "\r\n"
            ).encode("ascii")
            + body
            + b"\r\n"
        )
    chunks.append(f"--{_BOUNDARY}--\r\n".encode("ascii"))
    return b"".join(chunks)
