"""Accept-time SourcePackage archive, path, link and required-file checks."""

from __future__ import annotations

import io
from enum import StrEnum
from typing import BinaryIO

from gateway_backend.capabilities.source_package_staging import (
    REQUIRED_SQL_PATH,
    RESOURCE_BUDGETS,
    EntryKind,
    ExpansionCounter,
    PackageKind,
    StagingDiagnosticCode,
    StagingFault,
    iter_members,
)

_SUPPORTED_MEDIA_TYPES = frozenset({"application/gzip", "application/x-gzip"})


class UploadLimitExceededError(Exception):
    """Raised when upload exceeds bounded budgets."""


class UploadStreamTimeoutReason(StrEnum):
    IDLE = "IDLE"
    TOTAL = "TOTAL"


class UploadStreamTimeoutError(Exception):
    def __init__(self, reason: UploadStreamTimeoutReason) -> None:
        if type(reason) is not UploadStreamTimeoutReason:
            raise ValueError("reason must be UploadStreamTimeoutReason")
        self.reason = reason
        super().__init__(reason.value)


class UploadMediaUnsupportedError(Exception):
    """Raised when upload media type or archive format is unsupported."""


class UploadClosureInvalidError(Exception):
    """Raised when the uploaded package fails path, link or required-file checks."""


def assert_supported_source_media_type(media_type: str) -> None:
    if media_type not in _SUPPORTED_MEDIA_TYPES:
        raise UploadMediaUnsupportedError(f"unsupported upload media type {media_type!r}")


def validate_source_package_archive(
    payload: bytes | BinaryIO,
    *,
    compressed_bytes: int | None = None,
) -> None:
    source: bytes | BinaryIO
    if isinstance(payload, (bytes, bytearray)):
        size = len(payload)
        source = bytes(payload)
    else:
        if compressed_bytes is None:
            current = payload.tell()
            payload.seek(0, io.SEEK_END)
            size = payload.tell() - current
            payload.seek(current)
        else:
            size = compressed_bytes
        source = payload
    if size > RESOURCE_BUDGETS.max_source_package_compressed_bytes:
        raise UploadLimitExceededError("compressed source package exceeds budget")
    counter = ExpansionCounter(compressed_bytes=size, expanded_bytes=0, entry_count=0)
    saw_required_sql = False
    try:
        for member in iter_members(PackageKind.TAR_GZ, source, None, RESOURCE_BUDGETS, counter):
            if member.entry_kind is EntryKind.SYMLINK_UNSUPPORTED:
                raise UploadClosureInvalidError("symlink and hardlink members are refused")
            if member.normalized_path == REQUIRED_SQL_PATH:
                if saw_required_sql:
                    raise UploadClosureInvalidError("required SQL document is duplicated")
                saw_required_sql = True
    except StagingFault as exc:
        raise _map_staging_fault(exc) from exc
    if not saw_required_sql:
        raise UploadClosureInvalidError("required /sql/dbcfg.sql is missing")


def _map_staging_fault(exc: StagingFault) -> Exception:
    if exc.code is StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED:
        return UploadLimitExceededError(exc.message)
    if exc.code in {
        StagingDiagnosticCode.MALFORMED_ARCHIVE,
        StagingDiagnosticCode.SOURCE_PACKAGE_UNSUPPORTED,
        StagingDiagnosticCode.TAR_ZST_FORBIDDEN,
    }:
        return UploadMediaUnsupportedError(exc.message)
    if exc.code in {
        StagingDiagnosticCode.PATH_TRAVERSAL,
        StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
        StagingDiagnosticCode.MISSING_REQUIRED_SQL,
        StagingDiagnosticCode.DUPLICATE_REQUIRED_SQL,
        StagingDiagnosticCode.CANONICAL_PATH_COLLISION,
        StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
    }:
        return UploadClosureInvalidError(exc.message)
    return UploadMediaUnsupportedError(exc.message)
