"""Owned download result and narrow integrity error shared by adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field


class BundleIntegrityError(ValueError):
    """Published bundle bytes contradict their owning contract."""


@dataclass(slots=True)
class PreparedBundleDownload:
    bundle_digest: str
    content_length: int
    filename: str
    etag: str
    stream: Iterator[bytes]
    _resources: ExitStack = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            close_stream = getattr(self.stream, "close", None)
            if close_stream is not None:
                close_stream()
        finally:
            self._resources.close()
