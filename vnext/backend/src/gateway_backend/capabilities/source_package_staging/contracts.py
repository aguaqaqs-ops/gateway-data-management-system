"""Public contracts owned by the Source Package Staging capability.

Owner: Source Package Staging capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-handoff.md

This module owns bounded package admission, path/archive refusal, and public
document refs. SQL/XML interpretation and materialization types are outside this
package. Downstream consumers may import this package surface only.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import ArtifactRef

SOURCE_PACKAGE_CONTRACT_VERSION = 1
REQUIRED_SQL_PATH = "/sql/dbcfg.sql"
OPTIONAL_XML_PATH = "/comps/logic/logics.xml"
_MIB = 1024 * 1024
_KIB = 1024
_UTF8 = "utf-8"


class PackageKind(StrEnum):
    TAR_GZ = "TAR_GZ"
    ZIP = "ZIP"
    DIRECTORY = "DIRECTORY"
    SQL_FILE = "SQL_FILE"
    SQL_GZ = "SQL_GZ"


class StagingTransport(StrEnum):
    IDENTITY = "IDENTITY"
    ZSTD = "ZSTD"


class CompressionAlgorithm(StrEnum):
    NONE = "NONE"
    GZIP = "GZIP"
    ZSTD = "ZSTD"


class StagingStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class EntryKind(StrEnum):
    FILE = "FILE"
    DIRECTORY = "DIRECTORY"
    SYMLINK_UNSUPPORTED = "SYMLINK_UNSUPPORTED"


class DocumentKind(StrEnum):
    SQL_DUMP = "SQL_DUMP"
    XML = "XML"


class StagingDiagnosticCode(StrEnum):
    SOURCE_PACKAGE_INVALID = "SOURCE_PACKAGE_INVALID"
    SOURCE_PACKAGE_UNSUPPORTED = "SOURCE_PACKAGE_UNSUPPORTED"
    SOURCE_PACKAGE_DIGEST_MISMATCH = "SOURCE_PACKAGE_DIGEST_MISMATCH"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    SYMLINK_UNSUPPORTED = "SYMLINK_UNSUPPORTED"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    MISSING_REQUIRED_SQL = "MISSING_REQUIRED_SQL"
    DUPLICATE_REQUIRED_SQL = "DUPLICATE_REQUIRED_SQL"
    CANONICAL_PATH_COLLISION = "CANONICAL_PATH_COLLISION"
    TAR_ZST_FORBIDDEN = "TAR_ZST_FORBIDDEN"
    STAGING_CANCELLED = "STAGING_CANCELLED"
    STAGING_TIMEOUT = "STAGING_TIMEOUT"
    MALFORMED_ARCHIVE = "MALFORMED_ARCHIVE"
    ARTIFACT_PUBLISH_FAILED = "ARTIFACT_PUBLISH_FAILED"


class DiagnosticSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class ResourceBudgets:
    max_source_package_compressed_bytes: int
    max_source_package_expanded_bytes: int
    max_source_package_entries: int
    max_normalized_path_bytes: int
    max_path_segments: int
    max_sql_document_bytes: int
    max_xml_document_bytes: int
    max_diagnostics: int
    max_diagnostic_message_bytes: int


RESOURCE_BUDGETS = ResourceBudgets(
    max_source_package_compressed_bytes=256 * _MIB,
    max_source_package_expanded_bytes=1024 * _MIB,
    max_source_package_entries=8192,
    max_normalized_path_bytes=1024,
    max_path_segments=32,
    max_sql_document_bytes=512 * _MIB,
    max_xml_document_bytes=64 * _MIB,
    max_diagnostics=1024,
    max_diagnostic_message_bytes=4 * _KIB,
)


class CancelProbe(Protocol):
    def is_set(self) -> bool:
        """Return True when the caller has requested cooperative cancellation."""


@dataclass(frozen=True, slots=True)
class NeverCancel:
    def is_set(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class StagingInvocationContext:
    cancel_requested: CancelProbe
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.deadline_monotonic is not None:
            if type(self.deadline_monotonic) is not float or not math.isfinite(self.deadline_monotonic):
                raise ValueError("deadline_monotonic must be a finite float or None")


@dataclass(frozen=True, slots=True)
class StagingDiagnostic:
    code: StagingDiagnosticCode
    severity: DiagnosticSeverity
    message: str
    normalized_path: str | None = None
    budget_name: str | None = None

    def __post_init__(self) -> None:
        if type(self.code) is not StagingDiagnosticCode:
            raise ValueError("code must be StagingDiagnosticCode")
        if type(self.severity) is not DiagnosticSeverity:
            raise ValueError("severity must be DiagnosticSeverity")
        if type(self.message) is not str or self.message == "":
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode(_UTF8)) > RESOURCE_BUDGETS.max_diagnostic_message_bytes:
            raise ValueError("message exceeds max_diagnostic_message_bytes")
        if self.normalized_path is not None:
            _require_normalized_path(self.normalized_path)
        if self.budget_name is not None and (
            type(self.budget_name) is not str or self.budget_name == ""
        ):
            raise ValueError("budget_name must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class SourcePackageEntry:
    normalized_path: str
    entry_kind: EntryKind
    size_bytes: int
    content_digest: DigestRef | None = None
    original_path: str | None = None

    def __post_init__(self) -> None:
        _require_normalized_path(self.normalized_path)
        if type(self.entry_kind) is not EntryKind:
            raise ValueError("entry_kind must be EntryKind")
        _require_non_negative_int(self.size_bytes, "size_bytes")
        if self.content_digest is not None and type(self.content_digest) is not DigestRef:
            raise ValueError("content_digest must be DigestRef or None")
        if self.original_path is not None:
            if type(self.original_path) is not str or self.original_path == "":
                raise ValueError("original_path must be a non-empty string or None")
            if "\x00" in self.original_path or "\\" in self.original_path:
                raise ValueError("original_path must not contain NUL or backslash")


@dataclass(frozen=True, slots=True)
class SourceDocumentRef:
    source_package_id: str
    normalized_path: str
    document_kind: DocumentKind
    document_content_digest: DigestRef
    size_bytes: int
    entry_manifest_digest: DigestRef
    artifact_ref: ArtifactRef
    encoding_hint: str | None = None

    def __post_init__(self) -> None:
        _require_opaque_id(self.source_package_id, "source_package_id")
        _require_normalized_path(self.normalized_path)
        if type(self.document_kind) is not DocumentKind:
            raise ValueError("document_kind must be DocumentKind")
        if type(self.document_content_digest) is not DigestRef:
            raise ValueError("document_content_digest must be DigestRef")
        _require_non_negative_int(self.size_bytes, "size_bytes")
        if type(self.entry_manifest_digest) is not DigestRef:
            raise ValueError("entry_manifest_digest must be DigestRef")
        if type(self.artifact_ref) is not ArtifactRef:
            raise ValueError("artifact_ref must be ArtifactRef")
        if self.encoding_hint is not None and self.encoding_hint != _UTF8:
            raise ValueError("encoding_hint must be utf-8 or None")


@dataclass(frozen=True, slots=True)
class SqlDumpSource:
    source_document_ref: SourceDocumentRef
    sql_source_digest: DigestRef
    parser_input_contract_version: int
    encoding: str
    source_size_bytes: int

    def __post_init__(self) -> None:
        if type(self.source_document_ref) is not SourceDocumentRef:
            raise ValueError("source_document_ref must be SourceDocumentRef")
        if self.source_document_ref.document_kind is not DocumentKind.SQL_DUMP:
            raise ValueError("source_document_ref must be SQL_DUMP")
        if type(self.sql_source_digest) is not DigestRef:
            raise ValueError("sql_source_digest must be DigestRef")
        if self.sql_source_digest != self.source_document_ref.document_content_digest:
            raise ValueError("sql_source_digest must equal document_content_digest")
        if self.parser_input_contract_version != 1:
            raise ValueError("parser_input_contract_version must be 1")
        if self.encoding != _UTF8:
            raise ValueError("encoding must be utf-8")
        _require_non_negative_int(self.source_size_bytes, "source_size_bytes")
        if self.source_size_bytes != self.source_document_ref.size_bytes:
            raise ValueError("source_size_bytes must equal document size_bytes")


@dataclass(frozen=True, slots=True)
class SourcePackageInput:
    package_kind: PackageKind
    transport: StagingTransport
    context: StagingInvocationContext
    payload: bytes | None = None
    directory_entries: tuple[tuple[str, bytes], ...] | None = None
    retention_policy: str = "DEFAULT"
    source_origin: str | None = None
    expected_required_sql_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if type(self.package_kind) is not PackageKind:
            raise ValueError("package_kind must be PackageKind")
        if type(self.transport) is not StagingTransport:
            raise ValueError("transport must be StagingTransport")
        if type(self.context) is not StagingInvocationContext:
            raise ValueError("context must be StagingInvocationContext")
        if type(self.retention_policy) is not str or self.retention_policy == "":
            raise ValueError("retention_policy must be a non-empty string")
        if self.source_origin is not None and (
            type(self.source_origin) is not str or self.source_origin == ""
        ):
            raise ValueError("source_origin must be a non-empty string or None")
        if self.expected_required_sql_digest is not None and (
            type(self.expected_required_sql_digest) is not DigestRef
        ):
            raise ValueError("expected_required_sql_digest must be DigestRef or None")
        if self.package_kind is PackageKind.DIRECTORY:
            if self.payload is not None:
                raise ValueError("DIRECTORY forbids payload bytes")
            if self.directory_entries is None:
                raise ValueError("DIRECTORY requires directory_entries")
            _require_directory_entries(self.directory_entries)
            return
        if self.directory_entries is not None:
            raise ValueError("directory_entries is only valid for DIRECTORY")
        if type(self.payload) is not bytes:
            raise ValueError("payload must be bytes")


@dataclass(frozen=True, slots=True)
class SourcePackageStagingResult:
    status: StagingStatus
    compression: CompressionAlgorithm
    diagnostics: tuple[StagingDiagnostic, ...]
    source_package_id: str | None = None
    source_package_digest: DigestRef | None = None
    package_manifest_digest: DigestRef | None = None
    required_entries_manifest_digest: DigestRef | None = None
    entries: tuple[SourcePackageEntry, ...] = ()
    artifact_ref: ArtifactRef | None = None
    required_sql_document_ref: SourceDocumentRef | None = None
    optional_xml_document_ref: SourceDocumentRef | None = None
    empty_composite_logic: bool = False

    def __post_init__(self) -> None:
        if type(self.status) is not StagingStatus:
            raise ValueError("status must be StagingStatus")
        if type(self.compression) is not CompressionAlgorithm:
            raise ValueError("compression must be CompressionAlgorithm")
        if type(self.diagnostics) is not tuple:
            raise ValueError("diagnostics must be a tuple")
        for diagnostic in self.diagnostics:
            if type(diagnostic) is not StagingDiagnostic:
                raise ValueError("diagnostics must contain StagingDiagnostic")
        if type(self.entries) is not tuple:
            raise ValueError("entries must be a tuple")
        for entry in self.entries:
            if type(entry) is not SourcePackageEntry:
                raise ValueError("entries must contain SourcePackageEntry")
        if type(self.empty_composite_logic) is not bool:
            raise ValueError("empty_composite_logic must be bool")
        if self.status is StagingStatus.FAILED:
            _require_failed_result(self)
            return
        _require_complete_result(self)


def resolve_sql_dump_source(document_ref: SourceDocumentRef) -> SqlDumpSource:
    """Build SqlDumpSource from a staged SQL document ref. No text rewrite."""

    return SqlDumpSource(
        source_document_ref=document_ref,
        sql_source_digest=document_ref.document_content_digest,
        parser_input_contract_version=1,
        encoding=_UTF8,
        source_size_bytes=document_ref.size_bytes,
    )


def _require_non_negative_int(value: object, label: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative int")


def _require_opaque_id(value: object, label: str) -> None:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError(f"{label} must not be a path-shaped identity")


def _require_normalized_path(value: object) -> None:
    if type(value) is not str or not value.startswith("/") or value == "/":
        raise ValueError("normalized_path must be a package-internal absolute path")
    if "\\" in value or "\x00" in value or "//" in value:
        raise ValueError("normalized_path must not contain NUL, backslash, or empty segments")
    if any(segment in {".", ".."} for segment in value.split("/")[1:]):
        raise ValueError("normalized_path must not contain . or .. segments")


def _require_directory_entries(entries: tuple[tuple[str, bytes], ...]) -> None:
    if type(entries) is not tuple:
        raise ValueError("directory_entries must be a tuple")
    for item in entries:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("directory_entries must contain (path, bytes) pairs")
        path, payload = item
        if type(path) is not str or path == "":
            raise ValueError("directory entry path must be a non-empty string")
        if type(payload) is not bytes:
            raise ValueError("directory entry payload must be bytes")


def _require_failed_result(result: SourcePackageStagingResult) -> None:
    if result.source_package_id is not None:
        raise ValueError("FAILED must not publish source_package_id")
    if result.source_package_digest is not None:
        raise ValueError("FAILED must not publish source_package_digest")
    if result.package_manifest_digest is not None:
        raise ValueError("FAILED must not publish package_manifest_digest")
    if result.required_entries_manifest_digest is not None:
        raise ValueError("FAILED must not publish required_entries_manifest_digest")
    if result.entries != ():
        raise ValueError("FAILED must not publish entries")
    if result.artifact_ref is not None:
        raise ValueError("FAILED must not publish artifact_ref")
    if result.required_sql_document_ref is not None:
        raise ValueError("FAILED must not publish required_sql_document_ref")
    if result.optional_xml_document_ref is not None:
        raise ValueError("FAILED must not publish optional_xml_document_ref")
    if result.empty_composite_logic:
        raise ValueError("FAILED must not publish empty_composite_logic")
    if not result.diagnostics:
        raise ValueError("FAILED requires diagnostics")


def _require_complete_result(result: SourcePackageStagingResult) -> None:
    if result.source_package_id is None:
        raise ValueError("COMPLETE requires source_package_id")
    _require_opaque_id(result.source_package_id, "source_package_id")
    if type(result.source_package_digest) is not DigestRef:
        raise ValueError("COMPLETE requires source_package_digest")
    if type(result.package_manifest_digest) is not DigestRef:
        raise ValueError("COMPLETE requires package_manifest_digest")
    if type(result.required_entries_manifest_digest) is not DigestRef:
        raise ValueError("COMPLETE requires required_entries_manifest_digest")
    if type(result.artifact_ref) is not ArtifactRef:
        raise ValueError("COMPLETE requires artifact_ref")
    if type(result.required_sql_document_ref) is not SourceDocumentRef:
        raise ValueError("COMPLETE requires required_sql_document_ref")
    if result.required_sql_document_ref.normalized_path != REQUIRED_SQL_PATH:
        raise ValueError("required SQL document must be /sql/dbcfg.sql")
    if result.optional_xml_document_ref is None:
        if not result.empty_composite_logic:
            raise ValueError("missing XML requires empty_composite_logic")
        return
    if type(result.optional_xml_document_ref) is not SourceDocumentRef:
        raise ValueError("optional_xml_document_ref must be SourceDocumentRef or None")
    if result.optional_xml_document_ref.normalized_path != OPTIONAL_XML_PATH:
        raise ValueError("optional XML document must be /comps/logic/logics.xml")
    if result.empty_composite_logic:
        raise ValueError("present XML forbids empty_composite_logic")


def iter_entry_paths(entries: tuple[SourcePackageEntry, ...]) -> Iterator[str]:
    for entry in entries:
        yield entry.normalized_path
