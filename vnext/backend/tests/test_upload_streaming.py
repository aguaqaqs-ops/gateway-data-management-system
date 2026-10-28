"""Bounded upload streaming and archive file-like admission tests."""

from __future__ import annotations

import asyncio
import math
import shutil
import time
from collections.abc import AsyncIterator, Awaitable
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from gateway_backend.http.errors import ApiError
import gateway_backend.http.routes.upload_revisions as upload_revisions
from gateway_backend.http.orchestration.multipart_stream import (
    iter_file_chunks,
    parse_streaming_multipart,
)
import gateway_backend.http.orchestration.multipart_stream as multipart_stream
from gateway_backend.http.orchestration.source_package_admission import (
    UploadLimitExceededError,
    UploadStreamTimeoutError,
    UploadStreamTimeoutReason,
    validate_source_package_archive,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.routes.upload_revisions import accept_upload_route
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
        with pytest.raises(UploadStreamTimeoutError) as caught:
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=stalled_stream(),
                idle_timeout_seconds=0.01,
            )
        assert caught.value.reason is UploadStreamTimeoutReason.IDLE

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 0.12


@pytest.mark.serial
def test_total_stream_timeout_has_total_reason() -> None:
    async def stalled_stream() -> AsyncIterator[bytes]:
        await asyncio.sleep(0.1)
        yield b""

    async def run() -> None:
        with pytest.raises(UploadStreamTimeoutError) as caught:
            await parse_streaming_multipart(
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=stalled_stream(),
                idle_timeout_seconds=1.0,
                total_timeout_seconds=0.01,
            )
        assert caught.value.reason is UploadStreamTimeoutReason.TOTAL

    asyncio.run(run())


def test_low_rate_stream_within_size_derived_total_budget_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maximum = 32 * 1024 * 1024
    payload = _multipart_body(
        [("manifest", b"{}"), ("modified", b"x" * (256 * 1024))]
    )

    class Clock:
        now = 0.0

    clock = Clock()

    async def advance_per_chunk(awaitable: Awaitable[bytes], *, timeout: float) -> bytes:
        assert timeout > 0
        try:
            result = await awaitable
        except StopAsyncIteration:
            raise
        clock.now += 30.0
        return result

    async def slow_stream() -> AsyncIterator[bytes]:
        for offset in range(0, len(payload), 64 * 1024):
            yield payload[offset : offset + 64 * 1024]

    async def run() -> None:
        monkeypatch.setattr(
            multipart_stream,
            "time",
            SimpleNamespace(monotonic=lambda: clock.now),
        )
        monkeypatch.setattr(
            multipart_stream,
            "asyncio",
            SimpleNamespace(wait_for=advance_per_chunk),
        )
        parsed = await parse_streaming_multipart(
            headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
            stream=slow_stream(),
            max_compressed=maximum,
            idle_timeout_seconds=60.0,
            total_timeout_seconds=math.ceil(maximum * 8 / 1_000_000),
        )
        try:
            assert parsed.file_parts["modified"].size_bytes == 256 * 1024
            assert clock.now > 60.0
        finally:
            shutil.rmtree(parsed.staging_dir, ignore_errors=True)

    asyncio.run(run())


def test_idle_stream_timeout_maps_to_http_408_with_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def timeout(**_kwargs: object) -> object:
        raise UploadStreamTimeoutError(UploadStreamTimeoutReason.IDLE)

    monkeypatch.setattr(upload_revisions, "parse_streaming_multipart", timeout)

    class Gate:
        def try_acquire(self) -> bool:
            return True

        def allows_new_work(self) -> bool:
            return True

        def release(self) -> None:
            return None

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/workspaces/workspace-1/upload-revisions",
            "raw_path": b"/v1/workspaces/workspace-1/upload-revisions",
            "query_string": b"",
            "headers": [(b"idempotency-key", b"upload-1")],
            "server": ("test", 80),
            "client": ("test", 1234),
        },
        receive,
    )
    deps = SimpleNamespace(admission_gate=Gate())
    identity = IdentityContext(
        actor_id="actor-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        permissions=frozenset(),
    )

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await accept_upload_route("workspace-1", request, deps, identity)  # type: ignore[arg-type]
        assert caught.value.status_code == 408
        assert caught.value.code == "UPLOAD_STREAM_TIMEOUT"
        assert caught.value.details == {"reason": "IDLE"}

    asyncio.run(run())


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
