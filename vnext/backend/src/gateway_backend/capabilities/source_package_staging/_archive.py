"""Bounded archive member iteration for SourcePackage kinds."""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass

import compression.zstd

from gateway_backend.capabilities.source_package_staging._paths import PathFault, normalize_package_path
from gateway_backend.capabilities.source_package_staging.contracts import (
    OPTIONAL_XML_PATH,
    REQUIRED_SQL_PATH,
    EntryKind,
    PackageKind,
    ResourceBudgets,
    StagingDiagnosticCode,
    StagingTransport,
)

_CHUNK = 65536
_UNIX_SYMLINK_MASK = 0o170000
_UNIX_SYMLINK_TYPE = 0o120000
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class StagingFault(Exception):
    def __init__(
        self,
        code: StagingDiagnosticCode,
        message: str,
        *,
        budget_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.budget_name = budget_name


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    original_path: str
    normalized_path: str
    entry_kind: EntryKind
    size_bytes: int
    content: bytes | None


@dataclass
class ExpansionCounter:
    compressed_bytes: int
    expanded_bytes: int
    entry_count: int


def apply_transport(
    payload: bytes,
    transport: StagingTransport,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> bytes:
    if transport is StagingTransport.IDENTITY:
        return payload
    decompressor = compression.zstd.ZstdDecompressor()
    remaining = budgets.max_source_package_expanded_bytes - counter.expanded_bytes
    if remaining <= 0:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "expanded SourcePackage exceeds budget",
            budget_name="max_source_package_expanded_bytes",
        )
    try:
        output = decompressor.decompress(payload, max_length=remaining)
    except (compression.zstd.ZstdError, EOFError) as exc:
        raise StagingFault(
            StagingDiagnosticCode.MALFORMED_ARCHIVE,
            "zstd payload is malformed",
        ) from exc
    if not decompressor.eof:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "expanded SourcePackage exceeds budget",
            budget_name="max_source_package_expanded_bytes",
        )
    counter.expanded_bytes += len(output)
    return output


def iter_members(
    package_kind: PackageKind,
    payload: bytes | None,
    directory_entries: tuple[tuple[str, bytes], ...] | None,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> Iterator[ArchiveMember]:
    if package_kind is PackageKind.DIRECTORY:
        if directory_entries is None:
            raise StagingFault(
                StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
                "DIRECTORY requires directory_entries",
            )
        yield from _iter_directory(directory_entries, budgets, counter)
        return
    if payload is None:
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "package payload bytes are required",
        )
    if package_kind is PackageKind.SQL_FILE:
        yield _single_sql_member(
            payload,
            budgets,
            counter,
            original_path="dbcfg.sql",
            count_expanded=True,
        )
        return
    if package_kind is PackageKind.SQL_GZ:
        sql_bytes = _gzip_decompress(payload, budgets, counter, limit=budgets.max_sql_document_bytes)
        yield _single_sql_member(
            sql_bytes,
            budgets,
            counter,
            original_path="dbcfg.sql.gz",
            count_expanded=False,
        )
        return
    if package_kind is PackageKind.TAR_GZ:
        yield from _iter_tar_gz(payload, budgets, counter)
        return
    if package_kind is PackageKind.ZIP:
        yield from _iter_zip(payload, budgets, counter)
        return
    raise StagingFault(
        StagingDiagnosticCode.SOURCE_PACKAGE_UNSUPPORTED,
        "package kind is not supported",
    )


def should_materialize(normalized_path: str) -> bool:
    return normalized_path in {REQUIRED_SQL_PATH, OPTIONAL_XML_PATH}


def _single_sql_member(
    sql_bytes: bytes,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
    *,
    original_path: str,
    count_expanded: bool,
) -> ArchiveMember:
    _account_entry(counter, budgets)
    if count_expanded:
        _account_expanded(counter, budgets, len(sql_bytes))
    if len(sql_bytes) > budgets.max_sql_document_bytes:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "SQL document exceeds max_sql_document_bytes",
            budget_name="max_sql_document_bytes",
        )
    return ArchiveMember(
        original_path=original_path,
        normalized_path=REQUIRED_SQL_PATH,
        entry_kind=EntryKind.FILE,
        size_bytes=len(sql_bytes),
        content=sql_bytes,
    )


def _iter_directory(
    directory_entries: tuple[tuple[str, bytes], ...],
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> Iterator[ArchiveMember]:
    for original_path, payload in directory_entries:
        _account_entry(counter, budgets)
        try:
            normalized = normalize_package_path(original_path, budgets)
        except PathFault as exc:
            raise StagingFault(exc.code, exc.message, budget_name=exc.budget_name) from exc
        _account_expanded(counter, budgets, len(payload))
        content = payload if should_materialize(normalized) else None
        if content is not None:
            _enforce_document_budget(normalized, content, budgets)
        yield ArchiveMember(
            original_path=original_path,
            normalized_path=normalized,
            entry_kind=EntryKind.FILE,
            size_bytes=len(payload),
            content=content,
        )


def _iter_tar_gz(
    payload: bytes,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> Iterator[ArchiveMember]:
    if payload.startswith(_ZSTD_MAGIC):
        raise StagingFault(
            StagingDiagnosticCode.TAR_ZST_FORBIDDEN,
            "zstd must not be admitted as TAR_GZ",
        )
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r|gz") as archive:
            while True:
                member = archive.next()
                if member is None:
                    break
                yield _from_tar_member(archive, member, budgets, counter)
    except StagingFault:
        raise
    except (tarfile.TarError, gzip.BadGzipFile, OSError, EOFError) as exc:
        raise StagingFault(
            StagingDiagnosticCode.MALFORMED_ARCHIVE,
            "TAR_GZ payload is malformed",
        ) from exc


def _from_tar_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> ArchiveMember:
    _account_entry(counter, budgets)
    original_path = member.name
    try:
        normalized = normalize_package_path(original_path, budgets)
    except PathFault as exc:
        if member.isreg():
            _consume_tar_payload(archive, member, budgets, counter)
        raise StagingFault(exc.code, exc.message, budget_name=exc.budget_name) from exc
    if member.issym() or member.islnk():
        raise StagingFault(
            StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
            "symlink and hardlink members are refused",
        )
    if member.isdir():
        _account_expanded(counter, budgets, 0)
        return ArchiveMember(
            original_path=original_path,
            normalized_path=normalized,
            entry_kind=EntryKind.DIRECTORY,
            size_bytes=0,
            content=None,
        )
    if not member.isreg():
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "non-regular archive members are refused",
        )
    if should_materialize(normalized):
        content = _read_tar_payload(
            archive,
            member,
            budgets,
            counter,
            limit=_document_limit(normalized, budgets),
        )
        _enforce_document_budget(normalized, content, budgets)
    else:
        _consume_tar_payload(archive, member, budgets, counter)
        content = None
    return ArchiveMember(
        original_path=original_path,
        normalized_path=normalized,
        entry_kind=EntryKind.FILE,
        size_bytes=member.size,
        content=content,
    )


def _read_tar_payload(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
    *,
    limit: int,
) -> bytes:
    extracted = archive.extractfile(member)
    if extracted is None:
        raise StagingFault(
            StagingDiagnosticCode.MALFORMED_ARCHIVE,
            "TAR_GZ regular member has no payload",
        )
    return _read_bounded(extracted, member.size, budgets, counter, limit=limit)


def _consume_tar_payload(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> None:
    extracted = archive.extractfile(member)
    if extracted is None:
        return
    _discard_bounded(extracted, budgets, counter)


def _iter_zip(
    payload: bytes,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> Iterator[ArchiveMember]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            for info in archive.infolist():
                yield _from_zip_info(archive, info, budgets, counter)
    except StagingFault:
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        raise StagingFault(
            StagingDiagnosticCode.MALFORMED_ARCHIVE,
            "ZIP payload is malformed",
        ) from exc


def _from_zip_info(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> ArchiveMember:
    _account_entry(counter, budgets)
    original_path = info.filename
    try:
        normalized = normalize_package_path(original_path, budgets)
    except PathFault as exc:
        raise StagingFault(exc.code, exc.message, budget_name=exc.budget_name) from exc
    if _zip_is_symlink(info):
        raise StagingFault(
            StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
            "symlink and hardlink members are refused",
        )
    if original_path.endswith("/") or info.is_dir():
        return ArchiveMember(
            original_path=original_path,
            normalized_path=normalized,
            entry_kind=EntryKind.DIRECTORY,
            size_bytes=0,
            content=None,
        )
    content: bytes | None = None
    if should_materialize(normalized):
        try:
            with archive.open(info, mode="r") as stream:
                content = _read_bounded(
                    stream,
                    info.file_size,
                    budgets,
                    counter,
                    limit=_document_limit(normalized, budgets),
                )
        except StagingFault:
            raise
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            raise StagingFault(
                StagingDiagnosticCode.MALFORMED_ARCHIVE,
                "ZIP member payload is malformed",
            ) from exc
        _enforce_document_budget(normalized, content, budgets)
    else:
        _account_expanded(counter, budgets, info.file_size)
    return ArchiveMember(
        original_path=original_path,
        normalized_path=normalized,
        entry_kind=EntryKind.FILE,
        size_bytes=info.file_size,
        content=content,
    )


def _zip_is_symlink(info: zipfile.ZipInfo) -> bool:
    probe = getattr(info, "is_symlink", None)
    if callable(probe) and probe():
        return True
    return (info.external_attr >> 16) & _UNIX_SYMLINK_MASK == _UNIX_SYMLINK_TYPE


def _gzip_decompress(
    payload: bytes,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
    *,
    limit: int,
) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
            return _read_bounded(stream, limit, budgets, counter)
    except StagingFault:
        raise
    except (gzip.BadGzipFile, OSError, EOFError) as exc:
        raise StagingFault(
            StagingDiagnosticCode.MALFORMED_ARCHIVE,
            "gzip payload is malformed",
        ) from exc


def _read_bounded(
    stream: object,
    declared_size: int,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
    *,
    limit: int | None = None,
) -> bytes:
    collected = bytearray()
    while True:
        chunk = stream.read(_CHUNK)  # type: ignore[attr-defined]
        if not chunk:
            break
        _account_expanded(counter, budgets, len(chunk))
        collected.extend(chunk)
        if declared_size >= 0 and len(collected) > declared_size:
            raise StagingFault(
                StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
                "decompressed bytes exceed the declared document budget",
                budget_name=(
                    "max_sql_document_bytes"
                    if limit == budgets.max_sql_document_bytes
                    else "max_xml_document_bytes"
                ),
            )
        if limit is not None and len(collected) > limit:
            raise StagingFault(
                StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
                "decompressed document exceeds its document budget",
                budget_name=(
                    "max_sql_document_bytes"
                    if limit == budgets.max_sql_document_bytes
                    else "max_xml_document_bytes"
                ),
            )
    return bytes(collected)


def _discard_bounded(
    stream: object,
    budgets: ResourceBudgets,
    counter: ExpansionCounter,
) -> None:
    while True:
        chunk = stream.read(_CHUNK)  # type: ignore[attr-defined]
        if not chunk:
            break
        _account_expanded(counter, budgets, len(chunk))


def _account_entry(counter: ExpansionCounter, budgets: ResourceBudgets) -> None:
    counter.entry_count += 1
    if counter.entry_count > budgets.max_source_package_entries:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "package exceeds max_source_package_entries",
            budget_name="max_source_package_entries",
        )


def _account_expanded(counter: ExpansionCounter, budgets: ResourceBudgets, size: int) -> None:
    counter.expanded_bytes += size
    if counter.expanded_bytes > budgets.max_source_package_expanded_bytes:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "expanded SourcePackage exceeds budget",
            budget_name="max_source_package_expanded_bytes",
        )


def _enforce_document_budget(normalized_path: str, content: bytes, budgets: ResourceBudgets) -> None:
    if normalized_path == REQUIRED_SQL_PATH and len(content) > budgets.max_sql_document_bytes:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "SQL document exceeds max_sql_document_bytes",
            budget_name="max_sql_document_bytes",
        )
    if normalized_path == OPTIONAL_XML_PATH and len(content) > budgets.max_xml_document_bytes:
        raise StagingFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "XML document exceeds max_xml_document_bytes",
            budget_name="max_xml_document_bytes",
        )


def _document_limit(normalized_path: str, budgets: ResourceBudgets) -> int:
    if normalized_path == REQUIRED_SQL_PATH:
        return budgets.max_sql_document_bytes
    if normalized_path == OPTIONAL_XML_PATH:
        return budgets.max_xml_document_bytes
    raise ValueError("document limit requested for an unknown path")
