"""Deterministic ordinary-file POSIX tar framing with byte-counted local PAX paths."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

TAR_BLOCK = 512
STREAM_CHUNK_BYTES = 64 * 1024
TAR_END = bytes(2 * TAR_BLOCK)


def _utf8_chunks(text: str) -> Iterator[bytes]:
    # Four UTF-8 bytes per code point keeps every allocation within 64 KiB.
    for offset in range(0, len(text), STREAM_CHUNK_BYTES // 4):
        yield text[offset:offset + STREAM_CHUNK_BYTES // 4].encode("utf-8", errors="strict")


def pax_record_length(key: str, value: str) -> int:
    body_size = len(key.encode("ascii")) + 2 + sum(map(len, _utf8_chunks(value)))
    size = body_size + 2
    while (updated := len(str(size)) + 1 + body_size) != size:
        size = updated
    return size


def pax_record_chunks(key: str, value: str) -> Iterator[bytes]:
    """length counts the entire UTF-8 record, including its own decimal prefix."""
    yield f"{pax_record_length(key, value)} {key}=".encode("ascii")
    yield from _utf8_chunks(value)
    yield b"\n"


def _padding(size: int) -> int:
    return (-size) % TAR_BLOCK


def _header(name: str, size: int, *, typeflag: bytes = b"0") -> bytes:
    if not 0 <= size < 8**11:
        raise ValueError("tar member size exceeds POSIX octal capacity")
    header = bytearray(TAR_BLOCK)
    encoded = name.encode("ascii")
    if len(encoded) > 100:
        raise ValueError("tar framing name exceeds POSIX name capacity")
    header[:len(encoded)] = encoded
    header[100:108] = b"0000644\0"
    header[108:116] = b"0000000\0"
    header[116:124] = b"0000000\0"
    header[124:136] = f"{size:011o}\0".encode("ascii")
    header[136:148] = b"00000000000\0"
    header[148:156] = b"        "
    header[156:157] = typeflag
    header[257:265] = b"ustar\x0000"
    header[148:156] = f"{sum(header):06o}\0 ".encode("ascii")
    return bytes(header)


@dataclass(frozen=True, slots=True)
class TarMember:
    path: str
    size: int

    def __post_init__(self) -> None:
        if type(self.size) is not int or not 0 <= self.size <= 2**53 - 1:
            raise ValueError("tar member size must be an I-JSON nonnegative integer")

    @property
    def uses_pax(self) -> bool:
        return self.pax_path or self.pax_size

    @property
    def pax_path(self) -> bool:
        return not self.path.isascii() or len(self.path) > 100

    @property
    def pax_size(self) -> bool:
        return self.size >= 8**11

    def _records(self) -> Iterator[tuple[str, str]]:
        if self.pax_path:
            yield "path", self.path
        if self.pax_size:
            yield "size", str(self.size)

    def _pax_length(self) -> int:
        return sum(pax_record_length(key, value) for key, value in self._records())

    @property
    def framed_size(self) -> int:
        result = TAR_BLOCK + self.size + _padding(self.size)
        if self.uses_pax:
            pax_size = self._pax_length()
            result += TAR_BLOCK + pax_size + _padding(pax_size)
        return result

    def prefix(self) -> Iterator[bytes]:
        if self.uses_pax:
            size = self._pax_length()
            yield _header("PaxHeaders/path", size, typeflag=b"x")
            for key, value in self._records():
                yield from pax_record_chunks(key, value)
            if padding := _padding(size):
                yield bytes(padding)
        yield _header("bundle-member" if self.pax_path else self.path, 0 if self.pax_size else self.size)

    def suffix(self) -> Iterator[bytes]:
        if padding := _padding(self.size):
            yield bytes(padding)
