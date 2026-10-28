"""Bounded streaming multipart parser for AcceptUpload."""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, cast

import python_multipart as multipart
from python_multipart.multipart import parse_options_header
from starlette.datastructures import Headers

from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.source_package_admission import (
    UploadLimitExceededError,
    UploadStreamTimeoutError,
    UploadStreamTimeoutReason,
)
from gateway_backend.application.workspace.contracts import (
    FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    FIXED_UPLOAD_IDLE_TIMEOUT_SECONDS,
    FIXED_UPLOAD_TOTAL_TIMEOUT_SECONDS,
)

_STREAM_CHUNK_SIZE = 64 * 1024
_MANIFEST_MAX_BYTES = 64 * 1024
_MAX_FILES = 3
_HEADER_NAME_MAX_BYTES = 256
_HEADER_VALUE_MAX_BYTES = 4 * 1024
_HEADERS_PER_PART_MAX = 16
_HEADERS_TOTAL_MAX_BYTES = 8 * 1024
_PART_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass
class StagedUploadPart:
    name: str
    path: Path
    size_bytes: int


@dataclass
class ParsedMultipartUpload:
    manifest_bytes: bytes
    file_parts: dict[str, StagedUploadPart]
    staging_dir: Path


@dataclass
class _ActivePart:
    name: str
    is_manifest: bool
    data: bytearray = field(default_factory=bytearray)
    path: Path | None = None
    handle: IO[bytes] | None = None
    size_bytes: int = 0


def _multipart_validation_error(message: str) -> ApiError:
    return ApiError(
        code="REQUEST_VALIDATION_FAILED",
        message=message,
        status_code=422,
    )


class _StreamingMultipartParser:
    def __init__(
        self,
        *,
        staging_dir: Path,
        max_compressed: int,
        idle_timeout_seconds: float,
        total_timeout_seconds: float,
    ) -> None:
        self._staging_dir = staging_dir
        self._max_compressed = max_compressed
        self._idle_timeout_seconds = idle_timeout_seconds
        self._total_timeout_seconds = total_timeout_seconds
        self._started = time.monotonic()
        self._last_activity = self._started
        self._current = _ActivePart(name="", is_manifest=False)
        self._header_name = b""
        self._header_value = b""
        self._headers_in_part = 0
        self._header_bytes_total = 0
        self._content_disposition: bytes | None = None
        self._manifest: bytes | None = None
        self._files: dict[str, StagedUploadPart] = {}
        self._file_count = 0

    def on_part_begin(self) -> None:
        self._current = _ActivePart(name="", is_manifest=False)
        self._header_name = b""
        self._header_value = b""
        self._headers_in_part = 0
        self._content_disposition = None

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]
        self._enforce_header_budget(self._header_name, _HEADER_NAME_MAX_BYTES, "multipart header name")

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]
        self._enforce_header_budget(self._header_value, _HEADER_VALUE_MAX_BYTES, "multipart header value")

    def on_header_end(self) -> None:
        field = self._header_name.lower()
        header_bytes = len(self._header_name) + len(self._header_value)
        self._header_bytes_total += header_bytes
        if self._header_bytes_total > _HEADERS_TOTAL_MAX_BYTES:
            raise _multipart_validation_error("multipart headers exceed bounded budget")
        self._headers_in_part += 1
        if self._headers_in_part > _HEADERS_PER_PART_MAX:
            raise _multipart_validation_error("too many multipart headers on one part")
        if field == b"content-disposition":
            self._content_disposition = self._header_value
        self._header_name = b""
        self._header_value = b""

    def on_headers_finished(self) -> None:
        _disposition, options = parse_options_header(self._content_disposition)
        raw_name = options.get(b"name")
        if raw_name is None:
            raise _multipart_validation_error("multipart part is missing a name")
        name = raw_name.decode("latin-1")
        if _PART_NAME_PATTERN.fullmatch(name) is None:
            raise _multipart_validation_error("multipart part name is invalid")
        self._current.name = name
        self._current.is_manifest = name == "manifest"
        if self._current.is_manifest:
            return
        if name in self._files:
            raise _multipart_validation_error(f"duplicate multipart part {name!r}")
        self._file_count += 1
        if self._file_count > _MAX_FILES:
            raise _multipart_validation_error("too many multipart file parts")
        path = self._staging_dir / f"part-{self._file_count}"
        self._current.path = path
        self._current.handle = path.open("wb")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        payload = data[start:end]
        if self._current.is_manifest:
            self._current.data.extend(payload)
            if len(self._current.data) > _MANIFEST_MAX_BYTES:
                raise UploadLimitExceededError("upload exceeds bounded budget")
            return
        handle = self._current.handle
        if handle is None:
            raise _multipart_validation_error("multipart file part is missing a body")
        self._current.size_bytes += len(payload)
        if self._current.size_bytes > self._max_compressed:
            raise UploadLimitExceededError("compressed source package exceeds budget")
        handle.write(payload)

    def on_part_end(self) -> None:
        if self._current.is_manifest:
            if self._manifest is not None:
                raise _multipart_validation_error("duplicate multipart part 'manifest'")
            self._manifest = bytes(self._current.data)
            return
        handle = self._current.handle
        path = self._current.path
        if handle is not None:
            handle.close()
            self._current.handle = None
        if path is None:
            raise _multipart_validation_error("multipart file part is missing a body")
        self._files[self._current.name] = StagedUploadPart(
            name=self._current.name,
            path=path,
            size_bytes=self._current.size_bytes,
        )

    def on_end(self) -> None:
        return None

    def check_timeout(self) -> None:
        now = time.monotonic()
        total_deadline = self._started + self._total_timeout_seconds
        idle_deadline = self._last_activity + self._idle_timeout_seconds
        if now >= min(total_deadline, idle_deadline):
            raise self.timeout_error()

    def timeout_error(self) -> UploadStreamTimeoutError:
        total_deadline = self._started + self._total_timeout_seconds
        idle_deadline = self._last_activity + self._idle_timeout_seconds
        reason = (
            UploadStreamTimeoutReason.TOTAL
            if total_deadline <= idle_deadline
            else UploadStreamTimeoutReason.IDLE
        )
        return UploadStreamTimeoutError(reason)

    def record_data(self) -> None:
        self._last_activity = time.monotonic()

    def timeout_after(self, now: float) -> float:
        total_deadline = self._started + self._total_timeout_seconds
        idle_deadline = self._last_activity + self._idle_timeout_seconds
        return min(total_deadline, idle_deadline) - now

    def result(self) -> ParsedMultipartUpload:
        if self._manifest is None:
            raise _multipart_validation_error("manifest multipart part is required")
        return ParsedMultipartUpload(
            manifest_bytes=self._manifest,
            file_parts=self._files,
            staging_dir=self._staging_dir,
        )

    def close_open_handles(self) -> None:
        handle = self._current.handle
        if handle is not None:
            handle.close()
            self._current.handle = None

    def _enforce_header_budget(self, accumulated: bytes, limit: int, label: str) -> None:
        if len(accumulated) > limit:
            raise _multipart_validation_error(f"{label} exceeds bounded budget")
        pending_total = self._header_bytes_total + len(accumulated)
        if pending_total > _HEADERS_TOTAL_MAX_BYTES:
            raise _multipart_validation_error("multipart headers exceed bounded budget")


async def parse_streaming_multipart(
    *,
    headers: Headers,
    stream: AsyncIterator[bytes],
    max_compressed: int = FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    idle_timeout_seconds: float = FIXED_UPLOAD_IDLE_TIMEOUT_SECONDS,
    total_timeout_seconds: float = FIXED_UPLOAD_TOTAL_TIMEOUT_SECONDS,
) -> ParsedMultipartUpload:
    content_type = headers.get("content-type")
    if content_type is None:
        raise _multipart_validation_error("multipart Content-Type is required")
    media, params = parse_options_header(content_type.encode("latin-1"))
    if media.lower() != b"multipart/form-data":
        raise _multipart_validation_error("Content-Type must be multipart/form-data")
    boundary = params.get(b"boundary")
    if boundary is None:
        raise _multipart_validation_error("multipart boundary is required")
    staging_dir = Path(tempfile.mkdtemp(prefix="gateway-upload-"))
    parser_state = _StreamingMultipartParser(
        staging_dir=staging_dir,
        max_compressed=max_compressed,
        idle_timeout_seconds=idle_timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
    )
    callbacks = {
        "on_part_begin": parser_state.on_part_begin,
        "on_part_data": parser_state.on_part_data,
        "on_part_end": parser_state.on_part_end,
        "on_header_field": parser_state.on_header_field,
        "on_header_value": parser_state.on_header_value,
        "on_header_end": parser_state.on_header_end,
        "on_headers_finished": parser_state.on_headers_finished,
        "on_end": parser_state.on_end,
    }
    parser = multipart.MultipartParser(boundary, cast(Any, callbacks))
    iterator = stream.__aiter__()
    try:
        while True:
            now = time.monotonic()
            remaining = parser_state.timeout_after(now)
            if remaining <= 0:
                parser_state.check_timeout()
            try:
                chunk = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                parser_state.check_timeout()
                break
            except TimeoutError:
                raise parser_state.timeout_error() from None
            parser_state.check_timeout()
            if chunk:
                parser_state.record_data()
                parser.write(chunk)
        parser.finalize()
        return parser_state.result()
    except BaseException:
        parser_state.close_open_handles()
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def iter_file_chunks(path: Path, *, chunk_size: int = _STREAM_CHUNK_SIZE) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk
