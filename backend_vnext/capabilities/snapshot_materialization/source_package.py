from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import tempfile
import tarfile
from time import perf_counter
import uuid
from typing import Final
import zipfile
import gzip

from ...artifacts import ArtifactManifest, ArtifactRef, LocalArtifactStore
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ...formal_upload_benchmark import benchmark_elapsed_ms, log_formal_upload_benchmark_event
from .versions import (
    SOURCE_PACKAGE_ARTIFACT_CONTRACT_VERSION,
    SOURCE_PACKAGE_ARTIFACT_KIND,
    SOURCE_PACKAGE_CONTRACT_VERSION,
    SOURCE_PACKAGE_ENTRY_ARTIFACT_CONTRACT_VERSION,
    SOURCE_PACKAGE_ENTRY_ARTIFACT_KIND,
)


SQL_DUMP_REQUIRED_PATH: Final = "/sql/dbcfg.sql"
SOURCE_PACKAGE_DOCUMENT_KIND_SQL_DUMP: Final = "SQL_DUMP"
SOURCE_PACKAGE_ENTRY_KIND_FILE: Final = "FILE"
SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY: Final = "DIRECTORY"
SOURCE_PACKAGE_ENTRY_KIND_SYMLINK_UNSUPPORTED: Final = "SYMLINK_UNSUPPORTED"

_SOURCE_PACKAGE_STORE = LocalArtifactStore(
    Path(tempfile.gettempdir()) / "backend_vnext_source_package_store"
)
_SOURCE_PACKAGE_REGISTRY: dict[str, "SourcePackage"] = {}


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _diagnostics_payload(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[DiagnosticRecord, ...]:
    return tuple(diagnostics)


def _coerce_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _normalize_package_path(path_value: str) -> str:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("package paths must be non-empty strings")
    normalized = path_value.replace("\\", "/").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    normalized = posixpath.normpath(normalized)
    if normalized in {"", "."}:
        raise ValueError("package paths must not be empty")
    if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise ValueError(f"invalid package path traversal: {path_value!r}")
    return "/" + normalized.lower()


def _normalize_original_path(path_value: str) -> str:
    normalized = path_value.replace("\\", "/").strip()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    normalized = posixpath.normpath(normalized)
    if normalized in {"", "."}:
        raise ValueError("package entry path must not be empty")
    if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise ValueError(f"invalid package entry path traversal: {path_value!r}")
    return normalized


def _guess_package_kind(source_path: Path | None, source_bytes: bytes | None) -> str:
    if source_path is not None:
        if source_path.is_dir():
            return "DIRECTORY"
        suffixes = [suffix.lower() for suffix in source_path.suffixes]
        if suffixes[-2:] == [".tar", ".gz"] or source_path.suffix.lower() == ".tgz":
            return "TAR_GZ"
        if source_path.suffix.lower() == ".zip":
            return "ZIP"
        if source_path.suffix.lower() == ".gz":
            return "SQL_GZ"
        return "SQL_FILE"
    if source_bytes is not None and source_bytes.startswith(b"\x1f\x8b"):
        return "SQL_GZ"
    return "SQL_FILE"


def _normalize_package_kind(package_kind: str | None, source_path: Path | None, source_bytes: bytes | None) -> str:
    kind = (package_kind or _guess_package_kind(source_path, source_bytes)).upper()
    if kind not in {
        "DIRECTORY",
        "ZIP",
        "TAR_GZ",
        "SQL_FILE",
        "SQL_GZ",
    }:
        raise ValueError(f"unsupported package kind: {package_kind!r}")
    return kind


def _read_path_bytes(path: Path, package_kind: str) -> bytes:
    if package_kind == "SQL_FILE":
        return path.read_bytes()
    if package_kind == "SQL_GZ":
        return gzip.decompress(path.read_bytes())
    if package_kind == "ZIP":
        return path.read_bytes()
    if package_kind == "TAR_GZ":
        return path.read_bytes()
    if package_kind == "DIRECTORY":
        raise ValueError("directory packages are expanded entry-by-entry")
    return path.read_bytes()


def _load_package_entries(
    input_value: "SourcePackageInput",
    package_kind: str,
) -> tuple[tuple["SourcePackageEntry", ...], dict[str, bytes], dict[str, Path], tuple[DiagnosticRecord, ...]]:
    diagnostics: list[DiagnosticRecord] = []
    entries: dict[str, SourcePackageEntry] = {}
    entry_bytes_by_path: dict[str, bytes] = {}
    entry_paths_by_path: dict[str, Path] = {}

    if package_kind in {"SQL_FILE", "SQL_GZ"}:
        sql_bytes = _resolve_sql_bytes(input_value, package_kind)
        normalized_path = SQL_DUMP_REQUIRED_PATH
        entry = SourcePackageEntry(
            normalized_path=normalized_path,
            original_path=normalized_path.lstrip("/"),
            entry_kind=SOURCE_PACKAGE_ENTRY_KIND_FILE,
            size_bytes=len(sql_bytes),
            content_digest=DigestRef.from_bytes(sql_bytes),
            media_type_hint="text/x-sql",
            role_hint="required_sql_document",
        )
        entries[normalized_path] = entry
        entry_bytes_by_path[normalized_path] = sql_bytes
        return tuple(entries.values()), entry_bytes_by_path, entry_paths_by_path, tuple(diagnostics)

    if input_value.source_path is None:
        if input_value.source_bytes is None:
            raise ValueError("source_path or source_bytes is required for package kinds other than SQL compat")
        raise ValueError("source_bytes-only package staging is not yet supported for archive/container inputs")

    path = input_value.source_path
    if not path.exists():
        raise FileNotFoundError(str(path))
    if package_kind == "DIRECTORY":
        read_started_at = perf_counter()
        file_count = 0
        for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
            original_path = file_path.relative_to(path).as_posix()
            normalized_path = _normalize_package_path(original_path)
            entry_bytes = file_path.read_bytes()
            file_count += 1
            _register_package_entry(
                entries,
                entry_bytes_by_path,
                normalized_path=normalized_path,
                original_path=original_path,
                entry_kind=SOURCE_PACKAGE_ENTRY_KIND_FILE,
                entry_bytes=entry_bytes,
                media_type_hint=_guess_media_type(file_path.name),
            )
        log_formal_upload_benchmark_event(
            "source_package.stage.directory_file_read",
            benchmark_run_id=input_value.benchmark_run_id,
            source_origin=input_value.source_origin,
            package_kind=package_kind,
            streaming=False,
            file_count=file_count,
            entry_bytes_total=sum(len(value) for value in entry_bytes_by_path.values()),
            duration_ms=benchmark_elapsed_ms(read_started_at),
        )
        for dir_path in sorted(p for p in path.rglob("*") if p.is_dir()):
            original_path = dir_path.relative_to(path).as_posix()
            normalized_path = _normalize_package_path(original_path)
            if normalized_path in entries:
                continue
            entries[normalized_path] = SourcePackageEntry(
                normalized_path=normalized_path,
                original_path=original_path,
                entry_kind=SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY,
                size_bytes=0,
                content_digest=None,
            )
        return tuple(entries[key] for key in sorted(entries)), entry_bytes_by_path, entry_paths_by_path, tuple(diagnostics)

    if package_kind == "ZIP":
        with zipfile.ZipFile(path) as archive:
            list_started_at = perf_counter()
            members = sorted(archive.infolist(), key=lambda item: item.filename)
            log_formal_upload_benchmark_event(
                "source_package.stage.zip_list_members",
                benchmark_run_id=input_value.benchmark_run_id,
                source_origin=input_value.source_origin,
                package_kind=package_kind,
                streaming=False,
                member_count=len(members),
                duration_ms=benchmark_elapsed_ms(list_started_at),
            )
            read_started_at = perf_counter()
            file_count = 0
            for member in members:
                if member.is_dir():
                    normalized_path = _normalize_package_path(member.filename)
                    if normalized_path not in entries:
                        entries[normalized_path] = SourcePackageEntry(
                            normalized_path=normalized_path,
                            original_path=_normalize_original_path(member.filename),
                            entry_kind=SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY,
                            size_bytes=0,
                            content_digest=None,
                        )
                    continue
                original_path = _normalize_original_path(member.filename)
                normalized_path = _normalize_package_path(member.filename)
                entry_bytes = archive.read(member)
                file_count += 1
                _register_package_entry(
                    entries,
                    entry_bytes_by_path,
                    normalized_path=normalized_path,
                    original_path=original_path,
                    entry_kind=SOURCE_PACKAGE_ENTRY_KIND_FILE,
                    entry_bytes=entry_bytes,
                    media_type_hint=_guess_media_type(original_path),
                )
            log_formal_upload_benchmark_event(
                "source_package.stage.zip_member_read",
                benchmark_run_id=input_value.benchmark_run_id,
                source_origin=input_value.source_origin,
                package_kind=package_kind,
                streaming=False,
                file_count=file_count,
                entry_bytes_total=sum(len(value) for value in entry_bytes_by_path.values()),
                duration_ms=benchmark_elapsed_ms(read_started_at),
            )
        return tuple(entries[key] for key in sorted(entries)), entry_bytes_by_path, entry_paths_by_path, tuple(diagnostics)

    if package_kind == "TAR_GZ":
        read_started_at = perf_counter()
        required_path = _normalize_package_path(input_value.required_path)
        member_count = 0
        required_extracted = False
        with tarfile.open(path, mode="r|gz") as archive:
            file_count = 0
            extracted_file_count = 0
            for member in archive:
                member_count += 1
                original_path = _normalize_original_path(member.name)
                normalized_path = _normalize_package_path(member.name)
                if normalized_path in entries:
                    raise ValueError(f"duplicate package entry path after normalization: {normalized_path}")
                if member.isdir():
                    entries[normalized_path] = SourcePackageEntry(
                        normalized_path=normalized_path,
                        original_path=original_path,
                        entry_kind=SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY,
                        size_bytes=0,
                        content_digest=None,
                    )
                    continue
                if member.issym() or member.islnk():
                    raise ValueError(f"symlink entries are not supported: {member.name}")
                file_count += 1
                if normalized_path != required_path:
                    entries[normalized_path] = SourcePackageEntry(
                        normalized_path=normalized_path,
                        original_path=original_path,
                        entry_kind=SOURCE_PACKAGE_ENTRY_KIND_FILE,
                        size_bytes=member.size,
                        content_digest=None,
                        media_type_hint=_guess_media_type(original_path),
                    )
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError(f"unable to read tar member: {member.name}")
                staging_path, content_digest, size_bytes = _stream_required_tar_member_to_file(
                    extracted,
                    source_origin=input_value.source_origin,
                )
                if size_bytes != member.size:
                    staging_path.unlink(missing_ok=True)
                    raise ValueError(f"tar member size mismatch: {member.name}")
                required_extracted = True
                extracted_file_count += 1
                entries[normalized_path] = SourcePackageEntry(
                    normalized_path=normalized_path,
                    original_path=original_path,
                    entry_kind=SOURCE_PACKAGE_ENTRY_KIND_FILE,
                    size_bytes=size_bytes,
                    content_digest=content_digest,
                    media_type_hint=_guess_media_type(original_path),
                    role_hint="required_sql_document",
                )
                entry_paths_by_path[normalized_path] = staging_path
        log_formal_upload_benchmark_event(
            "source_package.stage.streaming_extract",
            benchmark_run_id=input_value.benchmark_run_id,
            source_origin=input_value.source_origin,
            package_kind=package_kind,
            streaming=True,
            member_count=member_count,
            file_count=file_count,
            extracted_file_count=extracted_file_count,
            required_extracted=required_extracted,
            entry_bytes_total=sum(entry.size_bytes for entry in entries.values()),
            extracted_bytes_total=sum(path.stat().st_size for path in entry_paths_by_path.values()),
            duration_ms=benchmark_elapsed_ms(read_started_at),
        )
        return tuple(entries[key] for key in sorted(entries)), entry_bytes_by_path, entry_paths_by_path, tuple(diagnostics)

    raise AssertionError(f"unhandled package kind: {package_kind}")


def _stream_required_tar_member_to_file(
    extracted,
    *,
    source_origin: str | None,
) -> tuple[Path, DigestRef, int]:
    del source_origin
    staging_dir = _SOURCE_PACKAGE_STORE.root / "streaming-source-members"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{uuid.uuid4().hex}.sql"
    hasher = hashlib.sha256()
    size_bytes = 0
    try:
        with staging_path.open("wb") as target:
            while True:
                chunk = extracted.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                size_bytes += len(chunk)
                target.write(chunk)
        return staging_path, DigestRef.from_hex(hasher.hexdigest()), size_bytes
    except BaseException:
        staging_path.unlink(missing_ok=True)
        raise


def _register_package_entry(
    entries: dict[str, "SourcePackageEntry"],
    entry_bytes_by_path: dict[str, bytes],
    *,
    normalized_path: str,
    original_path: str,
    entry_kind: str,
    entry_bytes: bytes,
    media_type_hint: str | None,
) -> None:
    if normalized_path in entries:
        raise ValueError(f"duplicate package entry path after normalization: {normalized_path}")
    entries[normalized_path] = SourcePackageEntry(
        normalized_path=normalized_path,
        original_path=original_path,
        entry_kind=entry_kind,
        size_bytes=len(entry_bytes),
        content_digest=DigestRef.from_bytes(entry_bytes),
        media_type_hint=media_type_hint,
    )
    entry_bytes_by_path[normalized_path] = entry_bytes


def _resolve_sql_bytes(input_value: "SourcePackageInput", package_kind: str) -> bytes:
    if input_value.source_text is not None:
        return input_value.source_text.encode("utf-8")
    if input_value.source_bytes is not None:
        raw_bytes = bytes(input_value.source_bytes)
        if package_kind == "SQL_GZ":
            return gzip.decompress(raw_bytes)
        return raw_bytes
    if input_value.source_path is not None:
        if package_kind == "SQL_GZ":
            return gzip.decompress(input_value.source_path.read_bytes())
        return input_value.source_path.read_bytes()
    raise ValueError("a SQL compat input must provide source_text, source_bytes or source_path")


def _guess_media_type(filename: str) -> str | None:
    lower = filename.lower()
    if lower.endswith(".sql"):
        return "text/x-sql"
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith(".csv"):
        return "text/csv"
    return None


def _build_package_manifest_payload(
    *,
    source_origin: str | None,
    package_kind: str,
    entries: Sequence[SourcePackageEntry],
    required_path: str,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_PACKAGE_CONTRACT_VERSION,
        "source_origin": source_origin,
        "package_kind": package_kind,
        "required_path": required_path,
        "entries": [
            {
                "normalized_path": entry.normalized_path,
                "original_path": entry.original_path,
                "entry_kind": entry.entry_kind,
                "size_bytes": entry.size_bytes,
                "content_digest": None if entry.content_digest is None else entry.content_digest.to_payload(),
                "media_type_hint": entry.media_type_hint,
                "role_hint": entry.role_hint,
            }
            for entry in entries
        ],
    }


def _build_required_entries_manifest_payload(
    *,
    required_path: str,
    entry: SourcePackageEntry,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_PACKAGE_CONTRACT_VERSION,
        "required_path": required_path,
        "entry": {
            "normalized_path": entry.normalized_path,
            "original_path": entry.original_path,
            "entry_kind": entry.entry_kind,
            "size_bytes": entry.size_bytes,
            "content_digest": None if entry.content_digest is None else entry.content_digest.to_payload(),
            "media_type_hint": entry.media_type_hint,
            "role_hint": entry.role_hint,
        },
    }


def _entry_payload(
    entry: "SourcePackageEntry",
    *,
    include_content_ref: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "normalized_path": entry.normalized_path,
        "original_path": entry.original_path,
        "entry_kind": entry.entry_kind,
        "size_bytes": entry.size_bytes,
        "content_digest": None if entry.content_digest is None else entry.content_digest.to_payload(),
        "media_type_hint": entry.media_type_hint,
        "role_hint": entry.role_hint,
    }
    if include_content_ref:
        payload["content_artifact_ref"] = (
            None if entry.content_artifact_ref is None else entry.content_artifact_ref.to_payload()
        )
    return payload


def _build_source_package_manifest_payload(
    *,
    source_package_id: str,
    source_origin: str | None,
    package_kind: str,
    entries: Sequence[SourcePackageEntry],
    required_path: str,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_PACKAGE_ARTIFACT_CONTRACT_VERSION,
        "source_package_id": source_package_id,
        "source_origin": source_origin,
        "package_kind": package_kind,
        "required_path": required_path,
        "entries": [_entry_payload(entry, include_content_ref=True) for entry in entries],
    }


def _package_digest_payload(
    *,
    source_origin: str | None,
    package_kind: str,
    package_manifest_digest: DigestRef,
    required_entries_manifest_digest: DigestRef | None,
    size_bytes: int,
) -> dict[str, object]:
    return {
        "schema_version": SOURCE_PACKAGE_CONTRACT_VERSION,
        "source_origin": source_origin,
        "package_kind": package_kind,
        "package_manifest_digest": package_manifest_digest.to_payload(),
        "required_entries_manifest_digest": (
            None
            if required_entries_manifest_digest is None
            else required_entries_manifest_digest.to_payload()
        ),
        "size_bytes": size_bytes,
    }


def _source_package_from_payload(
    payload: Mapping[str, object],
    *,
    artifact_ref: ArtifactRef,
) -> "SourcePackage":
    source_origin = payload.get("source_origin")
    package_kind = str(payload["package_kind"])
    required_path = str(payload.get("required_path", SQL_DUMP_REQUIRED_PATH))
    normalized_required_path = _normalize_package_path(required_path)
    entries_payload = payload.get("entries", [])
    if not isinstance(entries_payload, list):
        raise TypeError("source package entries payload must be a list")
    entries: list[SourcePackageEntry] = []
    for item in entries_payload:
        if not isinstance(item, Mapping):
            raise TypeError("source package entry payload must be a mapping")
        content_digest_value = item.get("content_digest")
        content_ref_payload = item.get("content_artifact_ref")
        normalized_path = _normalize_package_path(str(item["normalized_path"]))
        if (
            str(item["entry_kind"]) == SOURCE_PACKAGE_ENTRY_KIND_FILE
            and normalized_path == normalized_required_path
            and not isinstance(content_ref_payload, Mapping)
        ):
            raise ValueError("source package file entry missing content_artifact_ref")
        entries.append(
            SourcePackageEntry(
                normalized_path=normalized_path,
                original_path=_normalize_original_path(str(item["original_path"]))
                if item.get("original_path") is not None
                else None,
                entry_kind=str(item["entry_kind"]),
                size_bytes=int(item["size_bytes"]),
                content_digest=(
                    None
                    if content_digest_value is None
                    else DigestRef.parse(str(content_digest_value))
                ),
                media_type_hint=(
                    None if item.get("media_type_hint") is None else str(item["media_type_hint"])
                ),
                role_hint=(
                    None if item.get("role_hint") is None else str(item["role_hint"])
                ),
                content_artifact_ref=(
                    None
                    if content_ref_payload is None
                    else ArtifactRef.from_payload(content_ref_payload)
                ),
            )
        )
    package_manifest_digest = DigestRef.from_payload(
        _build_package_manifest_payload(
            source_origin=source_origin if source_origin is None else str(source_origin),
            package_kind=package_kind,
            entries=entries,
            required_path=required_path,
        )
    )
    required_entries_manifest_digest = None
    required_entry = _find_entry(entries, required_path)
    if required_entry is not None:
        required_entries_manifest_digest = DigestRef.from_payload(
            _build_required_entries_manifest_payload(
                required_path=required_path,
                entry=required_entry,
            )
        )
    source_package_digest = DigestRef.from_payload(
        _package_digest_payload(
            source_origin=source_origin if source_origin is None else str(source_origin),
            package_kind=package_kind,
            package_manifest_digest=package_manifest_digest,
            required_entries_manifest_digest=required_entries_manifest_digest,
            size_bytes=sum(entry.size_bytes for entry in entries),
        )
    )
    source_package = SourcePackage(
        source_package_id=str(payload["source_package_id"]),
        source_origin=None if source_origin is None else str(source_origin),
        package_kind=package_kind,
        source_package_digest=source_package_digest,
        package_manifest_digest=package_manifest_digest,
        required_entries_manifest_digest=required_entries_manifest_digest,
        entries=tuple(entries),
        artifact_ref=artifact_ref,
        size_bytes=sum(entry.size_bytes for entry in entries),
        created_by=None,
        created_at=datetime.now(timezone.utc),
        retention_policy="DEFAULT",
    )
    _SOURCE_PACKAGE_REGISTRY[source_package.source_package_id] = source_package
    return source_package


def _find_entry(entries: Sequence[SourcePackageEntry], required_path: str) -> SourcePackageEntry | None:
    normalized_required_path = _normalize_package_path(required_path)
    matching = [entry for entry in entries if entry.normalized_path == normalized_required_path]
    if not matching:
        return None
    if len(matching) > 1:
        raise ValueError(f"required path is not unique: {required_path}")
    return matching[0]


@dataclass(frozen=True, slots=True)
class SourcePackageEntry:
    normalized_path: str
    original_path: str | None = None
    entry_kind: str = SOURCE_PACKAGE_ENTRY_KIND_FILE
    size_bytes: int = 0
    content_digest: DigestRef | str | None = None
    media_type_hint: str | None = None
    role_hint: str | None = None
    content_artifact_ref: ArtifactRef | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_path", _normalize_package_path(self.normalized_path))
        if self.original_path is not None and (
            not isinstance(self.original_path, str) or not self.original_path.strip()
        ):
            raise ValueError("original_path must be a non-empty string or None")
        if not isinstance(self.entry_kind, str) or not self.entry_kind.strip():
            raise ValueError("entry_kind must be a non-empty string")
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        object.__setattr__(self, "content_digest", _coerce_digest(self.content_digest))
        if self.media_type_hint is not None and (
            not isinstance(self.media_type_hint, str) or not self.media_type_hint.strip()
        ):
            raise ValueError("media_type_hint must be a non-empty string or None")
        if self.role_hint is not None and (not isinstance(self.role_hint, str) or not self.role_hint.strip()):
            raise ValueError("role_hint must be a non-empty string or None")
        if self.content_artifact_ref is not None and not isinstance(self.content_artifact_ref, ArtifactRef):
            raise TypeError("content_artifact_ref must be an ArtifactRef or None")
        if self.entry_kind == SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY and self.content_artifact_ref is not None:
            raise ValueError("directory entries must not carry content_artifact_ref")
        if (
            self.content_artifact_ref is not None
            and self.content_digest is not None
            and self.content_artifact_ref.content_digest != self.content_digest
        ):
            raise ValueError("content_artifact_ref content digest must match entry content_digest")
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))


@dataclass(frozen=True, slots=True)
class SourceDocumentRef:
    source_package_id: str
    normalized_path: str
    document_kind: str = SOURCE_PACKAGE_DOCUMENT_KIND_SQL_DUMP
    document_content_digest: DigestRef | str | None = None
    size_bytes: int = 0
    encoding_hint: str | None = None
    entry_manifest_digest: DigestRef | str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.source_package_id, str) or not self.source_package_id.strip():
            raise ValueError("source_package_id must be a non-empty string")
        object.__setattr__(self, "normalized_path", _normalize_package_path(self.normalized_path))
        if self.document_kind != SOURCE_PACKAGE_DOCUMENT_KIND_SQL_DUMP:
            raise ValueError("only SQL dump documents are supported in this stage")
        object.__setattr__(self, "document_content_digest", _coerce_digest(self.document_content_digest))
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.encoding_hint is not None and (
            not isinstance(self.encoding_hint, str) or not self.encoding_hint.strip()
        ):
            raise ValueError("encoding_hint must be a non-empty string or None")
        object.__setattr__(self, "entry_manifest_digest", _coerce_digest(self.entry_manifest_digest))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.document_content_digest is None or self.entry_manifest_digest is None:
            raise ValueError("document_content_digest and entry_manifest_digest are required")


@dataclass(frozen=True, slots=True)
class SourcePackage:
    source_package_id: str
    source_origin: str | None
    package_kind: str
    source_package_digest: DigestRef | str
    package_manifest_digest: DigestRef | str
    required_entries_manifest_digest: DigestRef | str | None = None
    entries: tuple[SourcePackageEntry, ...] = field(default_factory=tuple)
    artifact_ref: ArtifactRef | None = None
    size_bytes: int = 0
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    retention_policy: str = "DEFAULT"
    diagnostics_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_package_id, str) or not self.source_package_id.strip():
            raise ValueError("source_package_id must be a non-empty string")
        if self.source_origin is not None and (
            not isinstance(self.source_origin, str) or not self.source_origin.strip()
        ):
            raise ValueError("source_origin must be a non-empty string or None")
        if not isinstance(self.package_kind, str) or not self.package_kind.strip():
            raise ValueError("package_kind must be a non-empty string")
        object.__setattr__(self, "source_package_digest", _coerce_digest(self.source_package_digest))
        object.__setattr__(self, "package_manifest_digest", _coerce_digest(self.package_manifest_digest))
        object.__setattr__(
            self,
            "required_entries_manifest_digest",
            _coerce_digest(self.required_entries_manifest_digest),
        )
        if self.artifact_ref is not None and not isinstance(self.artifact_ref, ArtifactRef):
            raise TypeError("artifact_ref must be an ArtifactRef or None")
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.created_by is not None and (
            not isinstance(self.created_by, str) or not self.created_by.strip()
        ):
            raise ValueError("created_by must be a non-empty string or None")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.expires_at is not None and not isinstance(self.expires_at, datetime):
            raise TypeError("expires_at must be a datetime or None")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if not isinstance(self.retention_policy, str) or not self.retention_policy.strip():
            raise ValueError("retention_policy must be a non-empty string")
        if self.diagnostics_ref is not None and (
            not isinstance(self.diagnostics_ref, str) or not self.diagnostics_ref.strip()
        ):
            raise ValueError("diagnostics_ref must be a non-empty string or None")
        normalized_entries: list[SourcePackageEntry] = []
        seen_paths: set[str] = set()
        for entry in self.entries:
            if not isinstance(entry, SourcePackageEntry):
                raise TypeError("entries must contain SourcePackageEntry values")
            if entry.normalized_path in seen_paths:
                raise ValueError(f"duplicate normalized package entry path: {entry.normalized_path}")
            seen_paths.add(entry.normalized_path)
            normalized_entries.append(entry)
        object.__setattr__(self, "entries", tuple(normalized_entries))

    @property
    def source_package_digest_payload(self) -> dict[str, object]:
        return _package_digest_payload(
            source_origin=self.source_origin,
            package_kind=self.package_kind,
            package_manifest_digest=self.package_manifest_digest,
            required_entries_manifest_digest=self.required_entries_manifest_digest,
            size_bytes=self.size_bytes,
        )


@dataclass(frozen=True, slots=True)
class SourcePackageInput:
    source_path: Path | None = None
    source_bytes: bytes | None = None
    source_text: str | None = None
    package_kind: str | None = None
    source_origin: str | None = None
    producer_context: Mapping[str, object] = field(default_factory=dict)
    created_by: str | None = None
    retention_policy: str = "DEFAULT"
    required_path: str = SQL_DUMP_REQUIRED_PATH
    benchmark_run_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_path is None and self.source_bytes is None and self.source_text is None:
            raise ValueError("at least one of source_path, source_bytes or source_text is required")
        if self.source_path is not None and not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path or None")
        if self.source_bytes is not None and not isinstance(self.source_bytes, (bytes, bytearray, memoryview)):
            raise TypeError("source_bytes must be bytes-like or None")
        if self.source_text is not None and not isinstance(self.source_text, str):
            raise TypeError("source_text must be a string or None")
        if self.package_kind is not None and (
            not isinstance(self.package_kind, str) or not self.package_kind.strip()
        ):
            raise ValueError("package_kind must be a non-empty string or None")
        if self.source_origin is not None and (
            not isinstance(self.source_origin, str) or not self.source_origin.strip()
        ):
            raise ValueError("source_origin must be a non-empty string or None")
        object.__setattr__(self, "producer_context", _mapping_payload(self.producer_context))
        if self.created_by is not None and (not isinstance(self.created_by, str) or not self.created_by.strip()):
            raise ValueError("created_by must be a non-empty string or None")
        if not isinstance(self.retention_policy, str) or not self.retention_policy.strip():
            raise ValueError("retention_policy must be a non-empty string")
        if not isinstance(self.required_path, str) or not self.required_path.strip():
            raise ValueError("required_path must be a non-empty string")
        if self.benchmark_run_id is not None and not isinstance(self.benchmark_run_id, str):
            raise TypeError("benchmark_run_id must be a string or None")


@dataclass(frozen=True, slots=True)
class SourcePackageStagingResult:
    source_package_id: str
    source_package_digest: DigestRef | str
    package_manifest_digest: DigestRef | str
    required_entries_manifest_digest: DigestRef | str | None
    entries: tuple[SourcePackageEntry, ...]
    artifact_ref: ArtifactRef
    required_sql_document_ref: SourceDocumentRef | None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    source_package: SourcePackage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_package_id, str) or not self.source_package_id.strip():
            raise ValueError("source_package_id must be a non-empty string")
        object.__setattr__(self, "source_package_digest", _coerce_digest(self.source_package_digest))
        object.__setattr__(self, "package_manifest_digest", _coerce_digest(self.package_manifest_digest))
        object.__setattr__(
            self,
            "required_entries_manifest_digest",
            _coerce_digest(self.required_entries_manifest_digest),
        )
        if not isinstance(self.artifact_ref, ArtifactRef):
            raise TypeError("artifact_ref must be an ArtifactRef")
        if self.required_sql_document_ref is not None and not isinstance(self.required_sql_document_ref, SourceDocumentRef):
            raise TypeError("required_sql_document_ref must be a SourceDocumentRef or None")
        if self.source_package is not None and not isinstance(self.source_package, SourcePackage):
            raise TypeError("source_package must be a SourcePackage or None")
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        normalized_entries: list[SourcePackageEntry] = []
        for entry in self.entries:
            if not isinstance(entry, SourcePackageEntry):
                raise TypeError("entries must contain SourcePackageEntry values")
            normalized_entries.append(entry)
        object.__setattr__(self, "entries", tuple(normalized_entries))


def _store_entry_artifacts(
    *,
    entries: Sequence[SourcePackageEntry],
    entry_bytes_by_path: Mapping[str, bytes],
    entry_paths_by_path: Mapping[str, Path],
    package_kind: str,
) -> tuple[SourcePackageEntry, ...]:
    entries_with_refs: list[SourcePackageEntry] = []
    for entry in entries:
        if entry.entry_kind != SOURCE_PACKAGE_ENTRY_KIND_FILE:
            entries_with_refs.append(entry)
            continue
        if entry.normalized_path in entry_paths_by_path:
            entry_path = entry_paths_by_path[entry.normalized_path]
            if entry.content_digest is None:
                raise ValueError(f"missing digest for source package entry: {entry.normalized_path}")
            entry_manifest = ArtifactManifest(
                artifact_kind=SOURCE_PACKAGE_ENTRY_ARTIFACT_KIND,
                artifact_contract_version=SOURCE_PACKAGE_ENTRY_ARTIFACT_CONTRACT_VERSION,
                content_digest=entry.content_digest,
                content_size_bytes=entry.size_bytes,
                metadata={
                    "normalized_path": entry.normalized_path,
                    "original_path": entry.original_path,
                    "package_kind": package_kind,
                    "media_type_hint": entry.media_type_hint,
                    "role_hint": entry.role_hint,
                },
            )
            stored = _SOURCE_PACKAGE_STORE.put_file(entry_manifest, entry_path)
            entries_with_refs.append(replace(entry, content_artifact_ref=stored.ref))
            continue
        if entry.normalized_path not in entry_bytes_by_path:
            entries_with_refs.append(entry)
            continue
        try:
            entry_bytes = entry_bytes_by_path[entry.normalized_path]
        except KeyError as exc:
            raise ValueError(f"missing bytes for source package entry: {entry.normalized_path}") from exc
        content_digest = DigestRef.from_bytes(entry_bytes)
        if entry.content_digest != content_digest:
            raise ValueError(f"source package entry digest mismatch: {entry.normalized_path}")
        entry_manifest = ArtifactManifest(
            artifact_kind=SOURCE_PACKAGE_ENTRY_ARTIFACT_KIND,
            artifact_contract_version=SOURCE_PACKAGE_ENTRY_ARTIFACT_CONTRACT_VERSION,
            content_digest=content_digest,
            content_size_bytes=len(entry_bytes),
            metadata={
                "normalized_path": entry.normalized_path,
                "original_path": entry.original_path,
                "package_kind": package_kind,
                "media_type_hint": entry.media_type_hint,
                "role_hint": entry.role_hint,
            },
        )
        stored = _SOURCE_PACKAGE_STORE.put_bytes(entry_manifest, entry_bytes)
        entries_with_refs.append(replace(entry, content_artifact_ref=stored.ref))
    return tuple(entries_with_refs)


def stage_source_package(input_value: SourcePackageInput | Path | str | bytes | bytearray | memoryview) -> SourcePackageStagingResult:
    package_input = _coerce_source_package_input(input_value)
    package_kind = _normalize_package_kind(
        package_input.package_kind,
        package_input.source_path,
        bytes(package_input.source_bytes) if package_input.source_bytes is not None else None,
    )
    total_started_at = perf_counter()
    load_started_at = perf_counter()
    entries, entry_bytes_by_path, entry_paths_by_path, diagnostics = _load_package_entries(package_input, package_kind)
    log_formal_upload_benchmark_event(
        "source_package.stage.load_entries",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        streaming=(package_kind == "TAR_GZ" and package_input.source_path is not None),
        entry_count=len(entries),
        entry_bytes_total=sum(entry.size_bytes for entry in entries),
        duration_ms=benchmark_elapsed_ms(load_started_at),
    )
    source_package_id = f"source-package:{uuid.uuid4().hex}"
    digest_started_at = perf_counter()
    package_manifest_payload = _build_package_manifest_payload(
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        entries=entries,
        required_path=package_input.required_path,
    )
    package_manifest_digest = DigestRef.from_payload(package_manifest_payload)
    required_entry = _find_entry(entries, package_input.required_path)
    if required_entry is None:
        raise ValueError(f"required SQL document not found: {package_input.required_path}")
    required_entries_manifest_digest = DigestRef.from_payload(
        _build_required_entries_manifest_payload(
            required_path=package_input.required_path,
            entry=required_entry,
        )
    )
    source_package_digest = DigestRef.from_payload(
        _package_digest_payload(
            source_origin=package_input.source_origin,
            package_kind=package_kind,
            package_manifest_digest=package_manifest_digest,
            required_entries_manifest_digest=required_entries_manifest_digest,
            size_bytes=sum(entry.size_bytes for entry in entries),
        )
    )
    log_formal_upload_benchmark_event(
        "source_package.stage.manifest_digests",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        entry_count=len(entries),
        duration_ms=benchmark_elapsed_ms(digest_started_at),
    )
    entry_artifact_started_at = perf_counter()
    entries_with_refs = _store_entry_artifacts(
        entries=entries,
        entry_bytes_by_path=entry_bytes_by_path,
        entry_paths_by_path=entry_paths_by_path,
        package_kind=package_kind,
    )
    log_formal_upload_benchmark_event(
        "source_package.stage.entry_artifact_put",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        file_count=sum(1 for entry in entries_with_refs if entry.entry_kind == SOURCE_PACKAGE_ENTRY_KIND_FILE),
        stored_file_count=sum(
            1
            for entry in entries_with_refs
            if entry.entry_kind == SOURCE_PACKAGE_ENTRY_KIND_FILE and entry.content_artifact_ref is not None
        ),
        metadata_only_file_count=sum(
            1
            for entry in entries_with_refs
            if entry.entry_kind == SOURCE_PACKAGE_ENTRY_KIND_FILE and entry.content_artifact_ref is None
        ),
        entry_bytes_total=sum(entry.size_bytes for entry in entries_with_refs),
        stored_bytes_total=sum(
            entry.size_bytes
            for entry in entries_with_refs
            if entry.entry_kind == SOURCE_PACKAGE_ENTRY_KIND_FILE and entry.content_artifact_ref is not None
        ),
        duration_ms=benchmark_elapsed_ms(entry_artifact_started_at),
    )
    for entry_path in entry_paths_by_path.values():
        entry_path.unlink(missing_ok=True)
    manifest_started_at = perf_counter()
    package_payload = _build_source_package_manifest_payload(
        source_package_id=source_package_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        entries=entries_with_refs,
        required_path=package_input.required_path,
    )
    package_payload_bytes = canonical_json_bytes(package_payload)
    log_formal_upload_benchmark_event(
        "source_package.stage.manifest_json_build",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        manifest_size_bytes=len(package_payload_bytes),
        duration_ms=benchmark_elapsed_ms(manifest_started_at),
    )
    package_artifact_manifest = ArtifactManifest(
        artifact_kind=SOURCE_PACKAGE_ARTIFACT_KIND,
        artifact_contract_version=SOURCE_PACKAGE_ARTIFACT_CONTRACT_VERSION,
        content_digest=DigestRef.from_bytes(package_payload_bytes),
        content_size_bytes=len(package_payload_bytes),
        metadata={
            "source_package_id": source_package_id,
            "package_kind": package_kind,
            "package_manifest_digest": package_manifest_digest.to_payload(),
            "required_entries_manifest_digest": required_entries_manifest_digest.to_payload(),
            "entry_count": len(entries_with_refs),
        },
        diagnostics=diagnostics,
        created_at=datetime.now(timezone.utc),
    )
    artifact_started_at = perf_counter()
    stored = _SOURCE_PACKAGE_STORE.put_bytes(package_artifact_manifest, package_payload_bytes)
    log_formal_upload_benchmark_event(
        "source_package.stage.artifact_put",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        manifest_size_bytes=len(package_payload_bytes),
        reused=stored.reused,
        duration_ms=benchmark_elapsed_ms(artifact_started_at),
    )
    source_package = SourcePackage(
        source_package_id=source_package_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        source_package_digest=source_package_digest,
        package_manifest_digest=package_manifest_digest,
        required_entries_manifest_digest=required_entries_manifest_digest,
        entries=entries_with_refs,
        artifact_ref=stored.ref,
        size_bytes=sum(entry.size_bytes for entry in entries_with_refs),
        created_by=package_input.created_by,
        retention_policy=package_input.retention_policy,
    )
    _SOURCE_PACKAGE_REGISTRY[source_package_id] = source_package
    resolve_started_at = perf_counter()
    required_sql_document_ref = resolve_required_sql_document(source_package, required_path=package_input.required_path)
    log_formal_upload_benchmark_event(
        "source_package.stage.resolve_required_sql",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        required_path=package_input.required_path,
        duration_ms=benchmark_elapsed_ms(resolve_started_at),
    )
    if package_input.source_origin is not None and any(entry.original_path != entry.normalized_path.lstrip("/") for entry in entries_with_refs):
        diagnostics = tuple(
            list(diagnostics)
            + [
                DiagnosticRecord(
                    code="snapshot.source-package.unconsumed-members",
                    message="source package contains additional members beyond the required SQL document",
                    phase="staging",
                    severity="WARNING",
                    details={"entry_count": len(entries_with_refs)},
                )
            ]
        )
    log_formal_upload_benchmark_event(
        "source_package.stage.total",
        benchmark_run_id=package_input.benchmark_run_id,
        source_origin=package_input.source_origin,
        package_kind=package_kind,
        streaming=(package_kind == "TAR_GZ" and package_input.source_path is not None),
        entry_count=len(entries_with_refs),
        entry_bytes_total=sum(entry.size_bytes for entry in entries_with_refs),
        duration_ms=benchmark_elapsed_ms(total_started_at),
    )
    return SourcePackageStagingResult(
        source_package_id=source_package_id,
        source_package_digest=source_package_digest,
        package_manifest_digest=package_manifest_digest,
        required_entries_manifest_digest=required_entries_manifest_digest,
        entries=entries_with_refs,
        artifact_ref=stored.ref,
        required_sql_document_ref=required_sql_document_ref,
        diagnostics=diagnostics,
        source_package=source_package,
    )


def resolve_required_sql_document(
    source_package_ref: SourcePackageStagingResult | SourcePackage | str | ArtifactRef | DigestRef,
    required_path: str = SQL_DUMP_REQUIRED_PATH,
) -> SourceDocumentRef:
    source_package = get_source_package(source_package_ref)
    required_entry = _find_entry(source_package.entries, required_path)
    if required_entry is None:
        raise ValueError(f"required SQL document not found: {required_path}")
    return SourceDocumentRef(
        source_package_id=source_package.source_package_id,
        normalized_path=_normalize_package_path(required_path),
        document_kind=SOURCE_PACKAGE_DOCUMENT_KIND_SQL_DUMP,
        document_content_digest=required_entry.content_digest,
        size_bytes=required_entry.size_bytes,
        encoding_hint=_encoding_hint_for_entry(required_entry),
        entry_manifest_digest=DigestRef.from_payload(
            _build_required_entries_manifest_payload(
                required_path=required_path,
                entry=required_entry,
            )
        ),
    )


def get_source_package(source_package_ref: SourcePackageStagingResult | SourcePackage | str | ArtifactRef | DigestRef) -> SourcePackage:
    if isinstance(source_package_ref, SourcePackage):
        return source_package_ref
    if isinstance(source_package_ref, SourcePackageStagingResult):
        if source_package_ref.source_package is not None:
            return source_package_ref.source_package
        return get_source_package(source_package_ref.source_package_id)
    if isinstance(source_package_ref, str):
        if source_package_ref in _SOURCE_PACKAGE_REGISTRY:
            return _SOURCE_PACKAGE_REGISTRY[source_package_ref]
        raise KeyError(f"unknown source package id: {source_package_ref}")
    if isinstance(source_package_ref, DigestRef):
        for source_package in _SOURCE_PACKAGE_REGISTRY.values():
            if source_package.source_package_digest == source_package_ref:
                return source_package
        raise KeyError(f"unknown source package digest: {source_package_ref}")
    if isinstance(source_package_ref, ArtifactRef):
        for source_package in _SOURCE_PACKAGE_REGISTRY.values():
            if source_package.artifact_ref == source_package_ref:
                return source_package
        payload = read_source_package_artifact(source_package_ref)
        return _source_package_from_payload(payload, artifact_ref=source_package_ref)
    raise TypeError(f"unsupported source package reference: {type(source_package_ref)!r}")


def read_source_package_artifact(source_package_ref: SourcePackageStagingResult | SourcePackage | str | ArtifactRef | DigestRef) -> Mapping[str, object]:
    if isinstance(source_package_ref, ArtifactRef):
        stored = _SOURCE_PACKAGE_STORE.read(source_package_ref)
    else:
        source_package = get_source_package(source_package_ref)
        stored = _SOURCE_PACKAGE_STORE.read(source_package.artifact_ref)
    payload = json.loads(stored.content_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("source package artifact payload must be a mapping")
    return payload


def load_source_document_bytes(source_document_ref: SourceDocumentRef) -> bytes:
    source_package = get_source_package(source_document_ref.source_package_id)
    payload = read_source_package_artifact(source_package)
    entries_payload = payload.get("entries", [])
    if not isinstance(entries_payload, list):
        raise TypeError("source package artifact entries payload must be a list")
    for item in entries_payload:
        if not isinstance(item, Mapping):
            raise TypeError("source package artifact entry payload must be a mapping")
        if _normalize_package_path(str(item["normalized_path"])) != source_document_ref.normalized_path:
            continue
        content_ref_payload = item.get("content_artifact_ref")
        if not isinstance(content_ref_payload, Mapping):
            raise ValueError(
                f"source package entry has no content_artifact_ref: {source_document_ref.normalized_path}"
            )
        entry_ref = ArtifactRef.from_payload(content_ref_payload)
        entry_bytes = _SOURCE_PACKAGE_STORE.read_bytes(entry_ref)
        actual_digest = DigestRef.from_bytes(entry_bytes)
        if actual_digest != source_document_ref.document_content_digest:
            raise ValueError("source document digest mismatch")
        return entry_bytes
    raise KeyError(f"source document not found: {source_document_ref.normalized_path}")


def resolve_source_document_content_path(source_document_ref: SourceDocumentRef) -> Path:
    entry_payload = read_source_package_entry_payload(source_document_ref)
    content_ref_payload = entry_payload.get("content_artifact_ref")
    if not isinstance(content_ref_payload, Mapping):
        raise ValueError(
            f"source package entry has no content_artifact_ref: {source_document_ref.normalized_path}"
        )
    entry_ref = ArtifactRef.from_payload(content_ref_payload)
    if entry_ref.content_digest != source_document_ref.document_content_digest:
        raise ValueError("source document digest mismatch")
    content_path = _SOURCE_PACKAGE_STORE.content_path_unverified(entry_ref)
    if content_path.stat().st_size != source_document_ref.size_bytes:
        raise ValueError("source document size mismatch")
    return content_path


def read_source_package_entry_payload(source_document_ref: SourceDocumentRef) -> Mapping[str, object]:
    payload = read_source_package_artifact(source_document_ref.source_package_id)
    entries_payload = payload.get("entries", [])
    if not isinstance(entries_payload, list):
        raise TypeError("source package artifact entries payload must be a list")
    for item in entries_payload:
        if not isinstance(item, Mapping):
            raise TypeError("source package artifact entry payload must be a mapping")
        if _normalize_package_path(str(item["normalized_path"])) == source_document_ref.normalized_path:
            return item
    raise KeyError(f"source document not found: {source_document_ref.normalized_path}")


def _encoding_hint_for_entry(entry: SourcePackageEntry) -> str:
    if entry.media_type_hint == "text/x-sql":
        return "utf-8"
    return "utf-8"


def _coerce_source_package_input(
    input_value: SourcePackageInput | Path | str | bytes | bytearray | memoryview,
) -> SourcePackageInput:
    if isinstance(input_value, SourcePackageInput):
        return input_value
    if isinstance(input_value, Path):
        return SourcePackageInput(source_path=input_value)
    if isinstance(input_value, (bytes, bytearray, memoryview)):
        return SourcePackageInput(source_bytes=bytes(input_value))
    if isinstance(input_value, str):
        path = Path(input_value)
        if path.exists():
            return SourcePackageInput(source_path=path)
        return SourcePackageInput(source_text=input_value)
    raise TypeError(f"unsupported source package input: {type(input_value)!r}")


__all__ = [
    "SQL_DUMP_REQUIRED_PATH",
    "SOURCE_PACKAGE_ARTIFACT_CONTRACT_VERSION",
    "SOURCE_PACKAGE_ARTIFACT_KIND",
    "SOURCE_PACKAGE_CONTRACT_VERSION",
    "SOURCE_PACKAGE_DOCUMENT_KIND_SQL_DUMP",
    "SOURCE_PACKAGE_ENTRY_ARTIFACT_CONTRACT_VERSION",
    "SOURCE_PACKAGE_ENTRY_ARTIFACT_KIND",
    "SOURCE_PACKAGE_ENTRY_KIND_DIRECTORY",
    "SOURCE_PACKAGE_ENTRY_KIND_FILE",
    "SOURCE_PACKAGE_ENTRY_KIND_SYMLINK_UNSUPPORTED",
    "SourceDocumentRef",
    "SourcePackage",
    "SourcePackageEntry",
    "SourcePackageInput",
    "SourcePackageStagingResult",
    "get_source_package",
    "load_source_document_bytes",
    "read_source_package_artifact",
    "read_source_package_entry_payload",
    "resolve_source_document_content_path",
    "resolve_required_sql_document",
    "stage_source_package",
]
