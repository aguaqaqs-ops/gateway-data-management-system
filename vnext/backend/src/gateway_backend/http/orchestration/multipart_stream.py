"""Bounded streaming multipart parser for AcceptUpload."""

from __future__ import annotations

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
from gateway_backend.http.orchestration.source_package_admission import UploadLimitExceededError
from gateway_backend.settings import (
    FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS,
)

_STREAM_CHUNK_SIZE = 64 * 1024
_MANIFEST_MAX_BYTES = 64 * 1024
_MAX_FILES = 3


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


class _StreamingMultipartParser:
    def __init__(self, *, staging_dir: Path, max_compressed: int, timeout_seconds: float) -> None:
        self._staging_dir = staging_dir
        self._max_compressed = max_compressed
        self._timeout_seconds = timeout_seconds
        self._started = time.monotonic()
        self._charset = "utf-8"
        self._current = _ActivePart(name="", is_manifest=False)
        self._header_name = b""
        self._header_value = b""
        self._headers: list[tuple[bytes, bytes]] = []
        self._content_disposition: bytes | None = None
        self._manifest: bytes | None = None
        self._files: dict[str, StagedUploadPart] = {}
        self._file_count = 0

    def on_part_begin(self) -> None:
        self._current = _ActivePart(name="", is_manifest=False)
        self._header_name = b""
        self._header_value = b""
        self._headers = []
        self._content_disposition = None

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        field = self._header_name.lower()
        if field == b"content-disposition":
            self._content_disposition = self._header_value
        self._headers.append((field, self._header_value))
        self._header_name = b""
        self._header_value = b""

    def on_headers_finished(self) -> None:
        _disposition, options = parse_options_header(self._content_disposition)
        raw_name = options.get(b"name")
        if raw_name is None:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="multipart part is missing a name",
                status_code=422,
            )
        name = raw_name.decode("latin-1")
        self._current.name = name
        self._current.is_manifest = name == "manifest"
        if self._current.is_manifest:
            return
        if name in self._files:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message=f"duplicate multipart part {name!r}",
                status_code=422,
            )
        self._file_count += 1
        if self._file_count > _MAX_FILES:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="too many multipart file parts",
                status_code=422,
            )
        path = self._staging_dir / f"part-{self._file_count}-{name}"
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
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="multipart file part is missing a body",
                status_code=422,
            )
        self._current.size_bytes += len(payload)
        if self._current.size_bytes > self._max_compressed:
            raise UploadLimitExceededError("compressed source package exceeds budget")
        handle.write(payload)

    def on_part_end(self) -> None:
        if self._current.is_manifest:
            if self._manifest is not None:
                raise ApiError(
                    code="REQUEST_VALIDATION_FAILED",
                    message="duplicate multipart part 'manifest'",
                    status_code=422,
                )
            self._manifest = bytes(self._current.data)
            return
        handle = self._current.handle
        path = self._current.path
        if handle is not None:
            handle.close()
            self._current.handle = None
        if path is None:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="multipart file part is missing a body",
                status_code=422,
            )
        self._files[self._current.name] = StagedUploadPart(
            name=self._current.name,
            path=path,
            size_bytes=self._current.size_bytes,
        )

    def on_end(self) -> None:
        return None

    def check_timeout(self) -> None:
        if time.monotonic() - self._started > self._timeout_seconds:
            raise UploadLimitExceededError("upload stream timed out")

    def result(self) -> ParsedMultipartUpload:
        if self._manifest is None:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="manifest multipart part is required",
                status_code=422,
            )
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


async def parse_streaming_multipart(
    *,
    headers: Headers,
    stream: AsyncIterator[bytes],
    max_compressed: int = FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    timeout_seconds: float = FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS,
) -> ParsedMultipartUpload:
    content_type = headers.get("content-type")
    if content_type is None:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="multipart Content-Type is required",
            status_code=422,
        )
    _media, params = parse_options_header(content_type.encode("latin-1"))
    boundary = params.get(b"boundary")
    if boundary is None:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="multipart boundary is required",
            status_code=422,
        )
    staging_dir = Path(tempfile.mkdtemp(prefix="gateway-upload-"))
    parser_state = _StreamingMultipartParser(
        staging_dir=staging_dir,
        max_compressed=max_compressed,
        timeout_seconds=timeout_seconds,
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
    try:
        async for chunk in stream:
            parser_state.check_timeout()
            if chunk:
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
