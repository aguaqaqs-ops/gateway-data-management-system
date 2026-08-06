"""Bounded streaming validator and extractor for Repository import packages."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from collections.abc import Buffer
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

_FORBIDDEN_TAR_TYPES = frozenset({
    tarfile.SYMTYPE,
    tarfile.LNKTYPE,
    tarfile.DIRTYPE,
    tarfile.FIFOTYPE,
    tarfile.CONTTYPE,
    tarfile.CHRTYPE,
    tarfile.BLKTYPE,
    tarfile.GNUTYPE_SPARSE,
    tarfile.GNUTYPE_LONGNAME,
    tarfile.GNUTYPE_LONGLINK,
    tarfile.XHDTYPE,
    tarfile.SOLARIS_XHDTYPE,
})


def validate_and_extract_import_package(
    *,
    artifact_path: Path,
    expected_size_bytes: int,
    expected_raw_sha256: str,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> ValidatedImportPackage:
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = _extract_import_package(
            artifact_path=artifact_path,
            staging_dir=staging_dir,
            settings=settings,
        )
    except Exception:
        _cleanup_staging(staging_dir)
        raise

    if result.observed_raw_size_bytes != expected_size_bytes:
        _cleanup_staging(staging_dir)
        raise ImportPackageRejected("artifact raw size does not match binding")
    if result.observed_raw_sha256 != expected_raw_sha256:
        _cleanup_staging(staging_dir)
        raise ImportPackageRejected("artifact raw sha256 does not match binding")
    return result


def _extract_import_package(
    *,
    artifact_path: Path,
    staging_dir: Path,
    settings: RepositoryServiceSettings,
) -> ValidatedImportPackage:
    manifest_path = staging_dir / STAGED_MANIFEST_FILENAME
    replay_sql_path = staging_dir / STAGED_REPLAY_SQL_FILENAME
    source = _CompressedArtifactSource(
        artifact_path=artifact_path,
        max_compressed_bytes=settings.max_upload_bytes,
        max_decompressed_stream_bytes=settings.max_decompressed_tar_stream_bytes,
    )
    try:
        tar_stream = _DecompressingTarReader(source)
        with tarfile.open(fileobj=tar_stream, mode="r|") as archive:
            manifest_size = _extract_required_member(
                archive=archive,
                expected_name=MANIFEST_ENTRY_NAME,
                destination=manifest_path,
                max_entry_bytes=settings.max_manifest_json_bytes,
                total_payload_bytes=0,
                max_total_payload_bytes=settings.max_total_expanded_entry_bytes,
            )
            _extract_required_member(
                archive=archive,
                expected_name=REPLAY_SQL_ENTRY_NAME,
                destination=replay_sql_path,
                max_entry_bytes=settings.max_replay_sql_bytes,
                total_payload_bytes=manifest_size,
                max_total_payload_bytes=settings.max_total_expanded_entry_bytes,
            )
            if archive.next() is not None:
                raise ImportPackageRejected("import package contains extra tar entries")
        source.finish_decompression()
    except (compression.zstd.ZstdError, EOFError, tarfile.TarError, OSError) as exc:
        raise ImportPackageRejected("import package is malformed") from exc
    finally:
        source.close()

    if manifest_size > settings.max_manifest_json_bytes:
        raise ImportPackageRejected("manifest.json exceeds expanded size limit")
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
        artifact_path: Path,
        max_compressed_bytes: int,
        max_decompressed_stream_bytes: int,
    ) -> None:
        self._file = artifact_path.open("rb")
        self._hasher = hashlib.sha256()
        self._compressed_bytes = 0
        self._max_compressed_bytes = max_compressed_bytes
        self._decompressor = compression.zstd.ZstdDecompressor()
        self._max_decompressed_stream_bytes = max_decompressed_stream_bytes
        self._decompressed_stream_bytes = 0
        self._compressed_buffer = b""
        self._decompressed_buffer = b""
        self._frame_finished = False
        self._finished = False

    @property
    def compressed_bytes(self) -> int:
        return self._compressed_bytes

    @property
    def raw_sha256_hex(self) -> str:
        return self._hasher.hexdigest()

    def close(self) -> None:
        self._file.close()

    def read_decompressed(self, size: int) -> bytes:
        if size <= 0:
            return b""
        while len(self._decompressed_buffer) < size:
            if not self._decompress_more():
                break
        result = self._decompressed_buffer[:size]
        self._decompressed_buffer = self._decompressed_buffer[size:]
        return result

    def finish_decompression(self) -> None:
        if self._finished:
            return
        while self._decompress_more():
            if self._decompressed_buffer:
                raise ImportPackageRejected("import package contains trailing tar data")
        if self._decompressor.unused_data:
            raise ImportPackageRejected("import package contains trailing compressed data")
        trailing = self._file.read(_COMPRESSED_READ_CHUNK_BYTES)
        if trailing:
            raise ImportPackageRejected("import package contains trailing compressed data")
        self._finished = True

    def _read_compressed_chunk(self) -> bytes:
        chunk = self._file.read(_COMPRESSED_READ_CHUNK_BYTES)
        if not chunk:
            return b""
        self._compressed_bytes += len(chunk)
        if self._compressed_bytes > self._max_compressed_bytes:
            raise ImportPackageRejected("compressed artifact exceeds upload size limit")
        self._hasher.update(chunk)
        return chunk

    def _decompress_more(self) -> bool:
        if self._frame_finished and not self._compressed_buffer:
            return False
        if not self._compressed_buffer and not self._frame_finished:
            self._compressed_buffer = self._read_compressed_chunk()
            if not self._compressed_buffer:
                self._frame_finished = True
                try:
                    output = self._decompressor.decompress(b"")
                except EOFError:
                    return False
                return self._accept_decompressed(output)
        if self._compressed_buffer:
            try:
                output = self._decompressor.decompress(self._compressed_buffer)
            except EOFError:
                self._frame_finished = True
                self._compressed_buffer = b""
                return False
            self._compressed_buffer = self._decompressor.unused_data
            return self._accept_decompressed(output)
        if not self._frame_finished:
            self._frame_finished = True
            try:
                output = self._decompressor.decompress(b"")
            except EOFError:
                return False
            return self._accept_decompressed(output)
        return False

    def _accept_decompressed(self, output: bytes) -> bool:
        if not output:
            return bool(self._compressed_buffer) or not self._frame_finished
        self._decompressed_stream_bytes += len(output)
        if self._decompressed_stream_bytes > self._max_decompressed_stream_bytes:
            raise ImportPackageRejected("decompressed tar stream exceeds size limit")
        self._decompressed_buffer += output
        return True


class _DecompressingTarReader(io.RawIOBase):
    def __init__(self, source: _CompressedArtifactSource) -> None:
        self._source = source

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Buffer) -> int | None:
        view = memoryview(buffer)
        data = self._source.read_decompressed(len(view))
        if not data:
            return 0
        view[: len(data)] = data
        return len(data)


def _extract_required_member(
    *,
    archive: tarfile.TarFile,
    expected_name: str,
    destination: Path,
    max_entry_bytes: int,
    total_payload_bytes: int,
    max_total_payload_bytes: int,
) -> int:
    member = archive.next()
    if member is None:
        raise ImportPackageRejected("import package is missing required tar entries")
    _validate_tar_member(member, expected_name=expected_name)
    if member.size > max_entry_bytes:
        raise ImportPackageRejected(f"{expected_name} exceeds expanded size limit")
    if total_payload_bytes + member.size > max_total_payload_bytes:
        raise ImportPackageRejected("import package total expanded payload exceeds size limit")
    payload = archive.extractfile(member)
    if payload is None:
        raise ImportPackageRejected(f"{expected_name} is not a regular file entry")
    written = 0
    with destination.open("wb") as handle:
        while True:
            chunk = payload.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            written += len(chunk)
            if written > max_entry_bytes:
                raise ImportPackageRejected(f"{expected_name} exceeds expanded size limit")
            if total_payload_bytes + written > max_total_payload_bytes:
                raise ImportPackageRejected("import package total expanded payload exceeds size limit")
            handle.write(chunk)
    if written != member.size:
        raise ImportPackageRejected(f"{expected_name} payload size does not match tar header")
    return written


def _validate_tar_member(member: tarfile.TarInfo, *, expected_name: str) -> None:
    if member.name != expected_name:
        raise ImportPackageRejected("import package tar entry name is invalid")
    if member.type in _FORBIDDEN_TAR_TYPES:
        raise ImportPackageRejected("import package tar entry type is not allowed")
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
