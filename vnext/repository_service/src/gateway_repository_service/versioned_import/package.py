"""Bounded streaming validator and extractor for Repository import packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from io import BufferedReader
from pathlib import Path
from typing import Any

import compression.zstd
from pydantic import ValidationError

from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.models import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    STAGED_MANIFEST_FILENAME,
    STAGED_REPLAY_SQL_FILENAME,
    ImportManifest,
    ImportPackageRejected,
    ValidatedImportPackage,
)

COPY_CHUNK_BYTES = 64 * 1024
_COMPRESSED_READ_CHUNK_BYTES = 64 * 1024
_DECODE_CHUNK_BYTES = 64 * 1024
_TAR_BLOCK_SIZE = 512
_TAR_EOF_BLOCKS = b"\x00" * (_TAR_BLOCK_SIZE * 2)
_MAX_BUDGET_PROBE_ITERATIONS = 16


def validate_and_extract_import_package(
    *,
    artifact_path: Path,
    expected_size_bytes: int,
    expected_raw_sha256: str,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> ValidatedImportPackage:
    staging_dir.mkdir(parents=True, exist_ok=True)
    artifact_file = artifact_path.open("rb")
    try:
        bound_size = os.fstat(artifact_file.fileno()).st_size
        if bound_size != expected_size_bytes:
            _cleanup_staging(staging_dir)
            raise ImportPackageRejected("artifact raw size does not match binding")

        source = _CompressedArtifactSource(
            artifact_file=artifact_file,
            expected_size_bytes=expected_size_bytes,
            max_compressed_bytes=settings.max_upload_bytes,
            max_decompressed_stream_bytes=settings.max_decompressed_tar_stream_bytes,
            max_manifest_json_bytes=settings.max_manifest_json_bytes,
            max_replay_sql_bytes=settings.max_replay_sql_bytes,
            max_total_expanded_entry_bytes=settings.max_total_expanded_entry_bytes,
        )
        try:
            result = _extract_import_package(
                source=source,
                staging_dir=staging_dir,
            )
        except Exception:
            _cleanup_staging(staging_dir)
            raise
        finally:
            source.close()

        if result.observed_raw_size_bytes != expected_size_bytes:
            _cleanup_staging(staging_dir)
            raise ImportPackageRejected("artifact raw size does not match binding")
        if result.observed_raw_sha256 != expected_raw_sha256:
            _cleanup_staging(staging_dir)
            raise ImportPackageRejected("artifact raw sha256 does not match binding")
        return result
    finally:
        artifact_file.close()


def _extract_import_package(
    *,
    source: _CompressedArtifactSource,
    staging_dir: Path,
) -> ValidatedImportPackage:
    manifest_path = staging_dir / STAGED_MANIFEST_FILENAME
    replay_sql_path = staging_dir / STAGED_REPLAY_SQL_FILENAME
    try:
        stream = _DecompressedByteStream(source)
        extractor = _StrictTarExtractor(
            stream=stream,
            manifest_path=manifest_path,
            replay_sql_path=replay_sql_path,
            max_manifest_json_bytes=source.max_manifest_json_bytes,
            max_replay_sql_bytes=source.max_replay_sql_bytes,
            max_total_expanded_entry_bytes=source.max_total_expanded_entry_bytes,
        )
        manifest_size = extractor.extract()
        source.assert_no_decompressed_tail()
        source.finish_decompression()
    except (compression.zstd.ZstdError, EOFError, tarfile.TarError, OSError) as exc:
        raise ImportPackageRejected("import package is malformed") from exc

    manifest = _parse_manifest_file(manifest_path, manifest_size)
    return ValidatedImportPackage(
        manifest=manifest,
        manifest_path=manifest_path,
        replay_sql_path=replay_sql_path,
        observed_raw_size_bytes=source.compressed_bytes,
        observed_raw_sha256=source.raw_sha256_hex,
    )


class _CompressedArtifactSource:
    def __init__(
        self,
        *,
        artifact_file: BufferedReader,
        expected_size_bytes: int,
        max_compressed_bytes: int,
        max_decompressed_stream_bytes: int,
        max_manifest_json_bytes: int = 0,
        max_replay_sql_bytes: int = 0,
        max_total_expanded_entry_bytes: int = 0,
    ) -> None:
        self._file = artifact_file
        self._expected_size_bytes = expected_size_bytes
        self._hasher = hashlib.sha256()
        self._compressed_bytes = 0
        self._max_compressed_bytes = max_compressed_bytes
        self._decompressor = compression.zstd.ZstdDecompressor()
        self._max_decompressed_stream_bytes = max_decompressed_stream_bytes
        self._decompressed_stream_bytes = 0
        self._compressed_buffer = b""
        self._decompressed_buffer = bytearray()
        self._input_exhausted = False
        self._finished = False
        self.max_manifest_json_bytes = max_manifest_json_bytes
        self.max_replay_sql_bytes = max_replay_sql_bytes
        self.max_total_expanded_entry_bytes = max_total_expanded_entry_bytes

    @property
    def compressed_bytes(self) -> int:
        return self._compressed_bytes

    @property
    def raw_sha256_hex(self) -> str:
        return self._hasher.hexdigest()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def read_decompressed(self, size: int) -> bytes:
        if size <= 0:
            return b""
        while len(self._decompressed_buffer) < size:
            if not self._decompress_more():
                break
        result = bytes(self._decompressed_buffer[:size])
        del self._decompressed_buffer[:size]
        return result

    def read_decompressed_up_to(self, size: int) -> bytes:
        if size <= 0:
            return b""
        while len(self._decompressed_buffer) < size:
            if not self._decompress_more():
                break
        available = min(size, len(self._decompressed_buffer))
        result = bytes(self._decompressed_buffer[:available])
        del self._decompressed_buffer[:available]
        return result

    def assert_no_decompressed_tail(self) -> None:
        if self._decompressed_buffer:
            raise ImportPackageRejected("import package contains trailing tar data")
        if self.read_decompressed(1):
            raise ImportPackageRejected("import package contains trailing tar data")

    def finish_decompression(self) -> None:
        if self._finished:
            return
        while not self._decompressor.needs_input:
            if not self._decompress_more():
                break
            if self._decompressed_buffer:
                raise ImportPackageRejected("import package contains trailing tar data")
        while self._decompress_more():
            if self._decompressed_buffer:
                raise ImportPackageRejected("import package contains trailing tar data")
        if not self._decompressor.eof:
            raise ImportPackageRejected("import package zstd frame is incomplete")
        if self._decompressor.unused_data:
            raise ImportPackageRejected("import package contains trailing compressed data")
        if self._decompressed_buffer:
            raise ImportPackageRejected("import package contains trailing tar data")
        trailing = self._file.read(_COMPRESSED_READ_CHUNK_BYTES)
        if trailing:
            raise ImportPackageRejected("import package contains trailing compressed data")
        self._finished = True

    def _remaining_stream_budget(self) -> int:
        return self._max_decompressed_stream_bytes - self._decompressed_stream_bytes

    def _enforce_compressed_byte_limits(self) -> None:
        if self._compressed_bytes > self._expected_size_bytes:
            raise ImportPackageRejected("artifact raw size does not match binding")
        if self._compressed_bytes > self._max_compressed_bytes:
            raise ImportPackageRejected("compressed artifact exceeds upload size limit")

    def _read_compressed_chunk(self) -> bytes:
        chunk = self._file.read(_COMPRESSED_READ_CHUNK_BYTES)
        if not chunk:
            self._input_exhausted = True
            return b""
        self._compressed_bytes += len(chunk)
        self._enforce_compressed_byte_limits()
        self._hasher.update(chunk)
        return chunk

    def _decompress_more(self) -> bool:
        remaining = self._remaining_stream_budget()
        if remaining <= 0:
            return self._probe_decoder_at_budget_limit()

        call_limit = min(remaining, _DECODE_CHUNK_BYTES)
        try:
            if not self._decompressor.needs_input:
                output = self._decompressor.decompress(b"", max_length=call_limit)
            elif self._compressed_buffer:
                output = self._decompressor.decompress(self._compressed_buffer, max_length=call_limit)
                self._compressed_buffer = self._decompressor.unused_data
            else:
                chunk = self._read_compressed_chunk()
                if chunk:
                    output = self._decompressor.decompress(chunk, max_length=call_limit)
                    self._compressed_buffer = self._decompressor.unused_data
                elif self._decompressor.eof:
                    return False
                else:
                    output = self._decompressor.decompress(b"", max_length=call_limit)
        except EOFError:
            if not self._decompressor.eof:
                raise ImportPackageRejected("import package zstd frame is incomplete") from None
            return False

        if not output:
            if self._compressed_buffer or not self._input_exhausted or not self._decompressor.eof:
                return True
            return False
        return self._accept_decompressed(output)

    def _probe_decoder_at_budget_limit(self) -> bool:
        for _ in range(_MAX_BUDGET_PROBE_ITERATIONS):
            if self._decompressor.eof and self._decompressor.needs_input:
                return False
            try:
                probe = self._decompressor.decompress(b"", max_length=1)
            except EOFError:
                if self._decompressor.eof:
                    return False
                raise ImportPackageRejected("import package zstd frame is incomplete") from None
            if probe:
                raise ImportPackageRejected("decompressed tar stream exceeds size limit")
            if self._decompressor.eof:
                return False
            if not self._decompressor.needs_input:
                continue
            if self._compressed_buffer or not self._input_exhausted:
                self._feed_compressed_for_probe()
                continue
            raise ImportPackageRejected("import package zstd frame is incomplete")
        raise ImportPackageRejected("import package zstd frame is incomplete")

    def _feed_compressed_for_probe(self) -> None:
        if self._compressed_buffer:
            chunk = self._compressed_buffer
            self._compressed_buffer = b""
        else:
            chunk = self._read_compressed_chunk()
        if not chunk:
            return
        try:
            probe = self._decompressor.decompress(chunk, max_length=1)
        except EOFError:
            if not self._decompressor.eof:
                raise ImportPackageRejected("import package zstd frame is incomplete") from None
            return
        if probe:
            raise ImportPackageRejected("decompressed tar stream exceeds size limit")
        self._compressed_buffer = self._decompressor.unused_data

    def _accept_decompressed(self, output: bytes) -> bool:
        self._decompressed_stream_bytes += len(output)
        if self._decompressed_stream_bytes > self._max_decompressed_stream_bytes:
            raise ImportPackageRejected("decompressed tar stream exceeds size limit")
        self._decompressed_buffer.extend(output)
        return True


class _DecompressedByteStream:
    def __init__(self, source: _CompressedArtifactSource) -> None:
        self._source = source

    def read_exactly(self, size: int) -> bytes:
        if size <= 0:
            return b""
        data = self._source.read_decompressed(size)
        if len(data) != size:
            raise ImportPackageRejected("import package is malformed")
        return data

    def read_decompressed_up_to(self, size: int) -> bytes:
        return self._source.read_decompressed_up_to(size)


class _StrictTarExtractor:
    def __init__(
        self,
        *,
        stream: _DecompressedByteStream,
        manifest_path: Path,
        replay_sql_path: Path,
        max_manifest_json_bytes: int,
        max_replay_sql_bytes: int,
        max_total_expanded_entry_bytes: int,
    ) -> None:
        self._stream = stream
        self._manifest_path = manifest_path
        self._replay_sql_path = replay_sql_path
        self._max_manifest_json_bytes = max_manifest_json_bytes
        self._max_replay_sql_bytes = max_replay_sql_bytes
        self._max_total_expanded_entry_bytes = max_total_expanded_entry_bytes
        self._total_payload_bytes = 0

    def extract(self) -> int:
        manifest_size = self._extract_member(
            expected_name=MANIFEST_ENTRY_NAME,
            destination=self._manifest_path,
            max_entry_bytes=self._max_manifest_json_bytes,
        )
        self._extract_member(
            expected_name=REPLAY_SQL_ENTRY_NAME,
            destination=self._replay_sql_path,
            max_entry_bytes=self._max_replay_sql_bytes,
        )
        self._consume_required_eof_blocks()
        return manifest_size

    def _extract_member(
        self,
        *,
        expected_name: str,
        destination: Path,
        max_entry_bytes: int,
    ) -> int:
        header_block = self._stream.read_exactly(_TAR_BLOCK_SIZE)
        member = _parse_header_block(header_block, expected_name=expected_name)
        if member.size > max_entry_bytes:
            raise ImportPackageRejected(f"{expected_name} exceeds expanded size limit")
        if self._total_payload_bytes + member.size > self._max_total_expanded_entry_bytes:
            raise ImportPackageRejected("import package total expanded payload exceeds size limit")

        written = 0
        remaining = member.size
        with destination.open("wb") as handle:
            while remaining > 0:
                chunk_size = min(COPY_CHUNK_BYTES, remaining)
                chunk = self._stream.read_exactly(chunk_size)
                written += len(chunk)
                if written > max_entry_bytes:
                    raise ImportPackageRejected(f"{expected_name} exceeds expanded size limit")
                if self._total_payload_bytes + written > self._max_total_expanded_entry_bytes:
                    raise ImportPackageRejected("import package total expanded payload exceeds size limit")
                handle.write(chunk)
                remaining -= chunk_size

        if written != member.size:
            raise ImportPackageRejected(f"{expected_name} payload size does not match tar header")

        padding = (_TAR_BLOCK_SIZE - (member.size % _TAR_BLOCK_SIZE)) % _TAR_BLOCK_SIZE
        if padding:
            padding_block = self._stream.read_exactly(padding)
            if padding_block != b"\x00" * padding:
                raise ImportPackageRejected("import package tar padding is invalid")

        self._total_payload_bytes += written
        return written

    def _consume_required_eof_blocks(self) -> None:
        first = self._stream.read_exactly(_TAR_BLOCK_SIZE)
        second = self._stream.read_exactly(_TAR_BLOCK_SIZE)
        zero_block = b"\x00" * _TAR_BLOCK_SIZE
        if first != zero_block or second != zero_block:
            raise ImportPackageRejected("import package tar EOF is invalid")
        self._consume_trailing_zero_blocks()

    def _consume_trailing_zero_blocks(self) -> None:
        zero_block = b"\x00" * _TAR_BLOCK_SIZE
        while True:
            block = self._stream.read_decompressed_up_to(_TAR_BLOCK_SIZE)
            if not block:
                return
            if len(block) < _TAR_BLOCK_SIZE:
                raise ImportPackageRejected("import package contains trailing tar data")
            if block != zero_block:
                raise ImportPackageRejected("import package contains trailing tar data")


def _parse_header_block(block: bytes, *, expected_name: str) -> tarfile.TarInfo:
    if len(block) != _TAR_BLOCK_SIZE:
        raise ImportPackageRejected("import package tar header is invalid")
    typeflag = block[156:157]
    if typeflag != tarfile.REGTYPE:
        raise ImportPackageRejected("import package tar entry type is not allowed")
    try:
        member = tarfile.TarInfo.frombuf(block, "utf-8", "strict")
    except (tarfile.TarError, UnicodeError) as exc:
        raise ImportPackageRejected("import package tar header is invalid") from exc
    _validate_tar_member(member, expected_name=expected_name)
    return member


def _validate_tar_member(member: tarfile.TarInfo, *, expected_name: str) -> None:
    if member.name != expected_name:
        raise ImportPackageRejected("import package tar entry name is invalid")
    if member.type != tarfile.REGTYPE:
        raise ImportPackageRejected("import package tar entry is not a regular file")
    if member.isdev() or member.isdir() or member.issym() or member.islnk() or member.isfifo():
        raise ImportPackageRejected("import package tar entry is not a regular file")
    if member.issparse():
        raise ImportPackageRejected("import package sparse tar entries are not allowed")
    if member.pax_headers:
        raise ImportPackageRejected("import package extended tar metadata is not allowed")
    if member.size < 0:
        raise ImportPackageRejected("import package tar entry size is invalid")


def _parse_manifest_file(path: Path, size: int) -> ImportManifest:
    raw = path.read_bytes()
    if len(raw) != size:
        raise ImportPackageRejected("manifest.json payload size mismatch")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ImportPackageRejected("manifest.json is not strict UTF-8") from exc
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise ImportPackageRejected("manifest.json is not valid JSON") from exc
    except ImportPackageRejected:
        raise
    except Exception as exc:
        raise ImportPackageRejected("manifest.json is not valid JSON") from exc
    try:
        return ImportManifest.model_validate(payload)
    except ValidationError as exc:
        raise ImportPackageRejected("manifest.json failed closed validation") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ImportPackageRejected("manifest.json contains duplicate JSON object keys")
        seen.add(key)
        result[key] = value
    return result


def _cleanup_staging(staging_dir: Path) -> None:
    if not staging_dir.exists():
        return
    for child in staging_dir.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
    try:
        staging_dir.rmdir()
    except OSError:
        pass
