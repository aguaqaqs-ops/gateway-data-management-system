"""Upload body source abstractions for bounded client streaming."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol, cast

DEFAULT_UPLOAD_CHUNK_SIZE = 64 * 1024


class NonRewindableUploadSourceError(RuntimeError):
    """Raised when a retryable upload failure cannot be retried without spooling."""

    def __init__(self, *, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class RewindableBody(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...

    def tell(self) -> int: ...


class NonRewindableBody(Protocol):
    declared_size: int

    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class UploadBodySource:
    """Declared-size upload source opened per HTTP attempt."""

    declared_size: int
    rewindable: bool
    _open_chunks: Callable[[], Iterator[bytes]]

    def open_chunks(self) -> Iterator[bytes]:
        return self._open_chunks()


def coerce_upload_body_source(
    body: UploadBodySource | bytes | bytearray | RewindableBody | NonRewindableBody,
    *,
    chunk_size: int = DEFAULT_UPLOAD_CHUNK_SIZE,
) -> UploadBodySource:
    if isinstance(body, UploadBodySource):
        return body

    if isinstance(body, (bytes, bytearray)):
        payload = bytes(body)
        return UploadBodySource(
            declared_size=len(payload),
            rewindable=True,
            _open_chunks=lambda: _iter_bytes_chunks(payload, chunk_size=chunk_size),
        )

    if _is_rewindable_body(body):
        rewindable = cast(RewindableBody, body)
        declared_size = _rewindable_declared_size(rewindable)
        return UploadBodySource(
            declared_size=declared_size,
            rewindable=True,
            _open_chunks=lambda: _iter_rewindable_chunks(rewindable, chunk_size=chunk_size),
        )

    if callable(getattr(body, "read", None)):
        nonrewindable = cast(NonRewindableBody, body)
        return UploadBodySource(
            declared_size=_nonrewindable_declared_size(nonrewindable),
            rewindable=False,
            _open_chunks=lambda: _iter_nonrewindable_chunks(
                nonrewindable,
                chunk_size=chunk_size,
            ),
        )

    raise NonRewindableUploadSourceError(
        status_code=0,
        message="upload source must be bytes, rewindable, or readable",
    )


def _is_rewindable_body(body: object) -> bool:
    return (
        callable(getattr(body, "seek", None))
        and callable(getattr(body, "read", None))
        and callable(getattr(body, "tell", None))
    )


def _rewindable_declared_size(body: RewindableBody) -> int:
    current = body.tell()
    body.seek(0, io.SEEK_END)
    declared_size = body.tell()
    body.seek(current, io.SEEK_SET)
    if declared_size < 0:
        raise NonRewindableUploadSourceError(
            status_code=0,
            message="upload source declared size is invalid",
        )
    return declared_size


def _nonrewindable_declared_size(body: NonRewindableBody) -> int:
    try:
        declared_size = body.declared_size
    except AttributeError as exc:
        raise NonRewindableUploadSourceError(
            status_code=0,
            message="nonrewindable upload source must expose declared_size",
        ) from exc
    if declared_size < 0:
        raise NonRewindableUploadSourceError(
            status_code=0,
            message="upload source declared size is invalid",
        )
    return declared_size


def _iter_bytes_chunks(payload: bytes, *, chunk_size: int) -> Iterator[bytes]:
    for offset in range(0, len(payload), chunk_size):
        yield payload[offset : offset + chunk_size]


def _iter_rewindable_chunks(body: RewindableBody, *, chunk_size: int) -> Iterator[bytes]:
    body.seek(0, io.SEEK_SET)
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise NonRewindableUploadSourceError(
                status_code=0,
                message="upload source must return bytes",
            )
        yield chunk


def _iter_nonrewindable_chunks(body: NonRewindableBody, *, chunk_size: int) -> Iterator[bytes]:
    while True:
        chunk = body.read(chunk_size)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise NonRewindableUploadSourceError(
                status_code=0,
                message="upload source must return bytes",
            )
        yield chunk
