"""Bounded upload streaming and archive file-like admission tests."""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import AsyncIterator, Awaitable
from io import BytesIO
from contextlib import ExitStack
from typing import cast
from gateway_backend.infrastructure.artifact_store.scratch import ScratchSpace, ScratchFile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from gateway_backend.http.errors import ApiError
import gateway_backend.http.routes.upload_revisions as upload_revisions
import gateway_backend.http.orchestration.multipart_upload as multipart_upload
from gateway_backend.http.orchestration.multipart_stream import (
    ParsedMultipartUpload,
    StagedUploadPart,
    iter_file_chunks,
    parse_streaming_multipart,
)
import gateway_backend.http.orchestration.multipart_stream as multipart_stream
from gateway_backend.http.orchestration.source_package_admission import (
    UploadStreamTimeoutError,
    UploadStreamTimeoutReason,
    validate_source_package_archive,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.routes.upload_revisions import accept_upload_route
from tests.support.upload_http_packages import INITIAL_BYTES

pytestmark = pytest.mark.unit

_BOUNDARY = "----gateway-test-boundary"


def test_iter_file_chunks_yields_an_iterator_not_a_joined_list(tmp_path: Path, scratch_space: ScratchSpace) -> None:
    path = tmp_path / "part.bin"
    path.write_bytes(b"abcdef")
    with scratch_space.file(owner="upload:chunk-test") as (source, output):
        output.write(path.read_bytes())
        output.flush()
        chunks = iter_file_chunks(source, chunk_size=2)
        assert not isinstance(chunks, list)
        assert tuple(chunks) == (b"ab", b"cd", b"ef")


def test_validate_source_package_archive_accepts_file_handle(scratch_space: ScratchSpace) -> None:
    validate_source_package_archive(BytesIO(INITIAL_BYTES), compressed_bytes=len(INITIAL_BYTES))


@pytest.mark.serial
def test_stalled_body_times_out_while_waiting_for_next_chunk(scratch_space: ScratchSpace) -> None:
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
                scratch=scratch_space,
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=stalled_stream(),
                idle_timeout_seconds=0.01,
            )
        assert caught.value.reason is UploadStreamTimeoutReason.IDLE

    started = time.monotonic()
    asyncio.run(run())
    assert time.monotonic() - started < 0.12


@pytest.mark.serial
def test_total_stream_timeout_has_total_reason(scratch_space: ScratchSpace) -> None:
    async def stalled_stream() -> AsyncIterator[bytes]:
        await asyncio.sleep(0.1)
        yield b""

    async def run() -> None:
        with pytest.raises(UploadStreamTimeoutError) as caught:
            await parse_streaming_multipart(
                scratch=scratch_space,
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=stalled_stream(),
                idle_timeout_seconds=1.0,
                total_timeout_seconds=0.01,
            )
        assert caught.value.reason is UploadStreamTimeoutReason.TOTAL

    asyncio.run(run())


def test_low_rate_stream_within_size_derived_total_budget_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
scratch_space: ScratchSpace
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
                scratch=scratch_space,
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
            parsed.close()

    asyncio.run(run())


def test_idle_stream_timeout_maps_to_http_408_with_reason(
    monkeypatch: pytest.MonkeyPatch,
scratch_space: ScratchSpace
) -> None:
    async def timeout(**_kwargs: object) -> object:
        raise UploadStreamTimeoutError(UploadStreamTimeoutReason.IDLE)

    monkeypatch.setattr(upload_revisions, "parse_streaming_multipart", timeout)

    class Gate:
        in_flight = 0
        release_count = 0

        def try_acquire(self) -> bool:
            self.in_flight += 1
            return True

        def allows_new_work(self) -> bool:
            return True

        def release(self) -> None:
            self.in_flight -= 1
            self.release_count += 1

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
    gate = Gate()
    deps = SimpleNamespace(admission_gate=gate, scratch=scratch_space)
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
        assert gate.in_flight == 0
        assert gate.release_count == 1

    asyncio.run(run())


@pytest.mark.serial
def test_direct_task_cancellation_waits_for_upload_acceptance_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
scratch_space: ScratchSpace
) -> None:
    resources = ExitStack()
    session = resources.enter_context(scratch_space.session(owner="upload:cancellation-test"))
    source, handle = resources.enter_context(session.file(byte_limit=1024))
    handle.write(b"transaction-input")
    handle.flush()
    staged_path = cast(ScratchFile, source)._path
    staging_dir = staged_path.parent
    parsed = ParsedMultipartUpload(
        manifest_bytes=b"{}",
        file_parts={"modified": StagedUploadPart("modified", source, 17)},
        resources=resources, scratch=session,
    )
    started = threading.Event()
    finish_transaction = threading.Event()
    committed: list[bytes] = []

    class Gate:
        in_flight = 0
        release_count = 0

        def try_acquire(self) -> bool:
            self.in_flight += 1
            return True

        def allows_new_work(self) -> bool:
            return True

        def release(self) -> None:
            self.in_flight -= 1
            self.release_count += 1

    gate = Gate()

    async def parsed_upload(**_kwargs: object) -> ParsedMultipartUpload:
        return parsed

    def accept_transaction(**kwargs: object) -> object:
        upload = kwargs["parsed"]
        assert isinstance(upload, ParsedMultipartUpload)
        assert b"".join(iter_file_chunks(upload.file_parts["modified"].source)) == b"transaction-input"
        started.set()
        assert finish_transaction.wait(timeout=5)
        committed.append(b"".join(iter_file_chunks(upload.file_parts["modified"].source)))
        return object()

    monkeypatch.setattr(upload_revisions, "parse_streaming_multipart", parsed_upload)
    monkeypatch.setattr(multipart_upload, "_accept_staged_upload", accept_transaction)

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
            "headers": [
                (b"idempotency-key", b"upload-cancel"),
                (b"content-type", b"multipart/form-data; boundary=test"),
            ],
            "server": ("test", 80),
            "client": ("test", 1234),
        },
        receive,
    )
    identity = IdentityContext(
        actor_id="actor-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        permissions=frozenset(),
    )
    deps = SimpleNamespace(
        scratch=scratch_space,
        admission_gate=gate,
        scope_resolution=None,
        workspace_repository=None,
        submit_unit_of_work_factory=None,
        artifact_store=None,
        now=lambda: None,
    )

    async def run() -> None:
        task = asyncio.create_task(
            accept_upload_route("workspace-1", request, deps, identity)  # type: ignore[arg-type]
        )
        assert await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert staging_dir.is_dir()
        assert staged_path.read_bytes() == b"transaction-input"
        assert gate.in_flight == 1
        assert gate.release_count == 0

        finish_transaction.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert committed == [b"transaction-input"]
        assert not staging_dir.exists()
        assert not staged_path.exists()
        assert gate.in_flight == 0
        assert gate.release_count == 1

    asyncio.run(run())


def test_non_multipart_content_type_is_rejected_before_parsing_body(scratch_space: ScratchSpace) -> None:
    payload = _multipart_body([("manifest", b"{}"), ("modified", b"abc")])

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await parse_streaming_multipart(
                scratch=scratch_space,
                headers=Headers({"content-type": f"application/json; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        error = caught.value
        assert error.status_code == 422
        assert error.code == "REQUEST_VALIDATION_FAILED"

    asyncio.run(run())


def test_caller_controlled_part_name_is_rejected_without_pathname_escape(scratch_space: ScratchSpace) -> None:
    payload = _multipart_body([("x/y", b"not-a-path")])

    async def run() -> None:
        with pytest.raises(ApiError) as caught:
            await parse_streaming_multipart(
                scratch=scratch_space,
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        error = caught.value
        assert error.status_code == 422
        assert error.code == "REQUEST_VALIDATION_FAILED"
        assert not isinstance(error.__cause__, FileNotFoundError)

    asyncio.run(run())


def test_overlong_multipart_header_is_rejected(scratch_space: ScratchSpace) -> None:
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
                scratch=scratch_space,
                headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
                stream=_one_chunk(payload),
            )
        assert caught.value.status_code == 422
        assert caught.value.code == "REQUEST_VALIDATION_FAILED"

    asyncio.run(run())


def test_file_part_uses_server_owned_staging_name(scratch_space: ScratchSpace) -> None:
    payload = _multipart_body([("manifest", b"{}"), ("modified", b"abc")])

    async def run() -> None:
        parsed = await parse_streaming_multipart(
                scratch=scratch_space,
            headers=Headers({"content-type": f"multipart/form-data; boundary={_BOUNDARY}"}),
            stream=_one_chunk(payload),
        )
        try:
            staged = parsed.file_parts["modified"]
            assert staged.name == "modified"
            path = cast(ScratchFile, staged.source)._path
            assert path.name.startswith("file-")
            assert path.parent.parent == scratch_space._root
            assert "modified" not in path.name
        finally:
            parsed.close()

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


@pytest.mark.parametrize('fault', ('aggregate', 'construction', 'write'))
def test_multipart_owner_covers_all_parts_and_cleans_every_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    from gateway_backend.http.orchestration.source_package_admission import UploadLimitExceededError
    from gateway_backend.infrastructure.artifact_store.scratch import _BudgetedFile
    root = tmp_path / 'multipart-scratch'
    root.mkdir()
    space = ScratchSpace(root, max_bytes=5)
    body = _multipart_body([('manifest', b'{}'), ('one', b'abc'), ('two', b'def')])
    if fault == 'construction':
        def broken_parser(*args: object, **kwargs: object) -> object:
            raise ValueError('injected parser construction failure')
        monkeypatch.setattr('gateway_backend.http.orchestration.multipart_stream.multipart.MultipartParser', broken_parser)
    if fault == 'write':
        def full_disk(self: object, data: object) -> int:
            raise OSError(28, 'injected ENOSPC')
        monkeypatch.setattr(_BudgetedFile, 'write', full_disk)
    async def run() -> None:
        error = {'aggregate': UploadLimitExceededError, 'construction': ValueError, 'write': OSError}[fault]
        with pytest.raises(error):
            await parse_streaming_multipart(scratch=space,
                headers=Headers({'content-type': f'multipart/form-data; boundary={_BOUNDARY}'}),
                stream=_one_chunk(body), max_compressed=5)
    asyncio.run(run())
    assert not list(root.iterdir())
