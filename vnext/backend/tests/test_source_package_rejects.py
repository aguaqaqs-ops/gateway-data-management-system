"""SourcePackage staging reject cases. One parameter table, no SQL/XML parse."""

from __future__ import annotations

import tarfile
from dataclasses import dataclass, replace

import compression.zstd
import pytest
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, ManifestVerificationError
from gateway_backend.capabilities.source_package_staging.contracts import (
    RESOURCE_BUDGETS,
    NeverCancel,
    PackageKind,
    ResourceBudgets,
    SourcePackageInput,
    StagingDiagnosticCode,
    StagingInvocationContext,
    StagingStatus,
    StagingTransport,
)
from gateway_backend.capabilities.source_package_staging.staging import stage_source_package
from tests.support.source_package_fixtures import (
    load_bytes,
    pack_tar_gz,
    pack_tar_gz_infos,
    pack_zip,
    pack_zip_symlink,
)

_CONTEXT = StagingInvocationContext(NeverCancel())
_SQL = load_bytes("package/valid/s1-minimal-tar-gz/sql/dbcfg.sql")
_TIGHT_ENTRIES = replace(RESOURCE_BUDGETS, max_source_package_entries=1)
_TIGHT_COMPRESSED = replace(RESOURCE_BUDGETS, max_source_package_compressed_bytes=1)
_TIGHT_SQL_DOCUMENT = replace(
    RESOURCE_BUDGETS,
    max_sql_document_bytes=len(_SQL) - 1,
)
_TIGHT_XML_DOCUMENT = replace(
    RESOURCE_BUDGETS,
    max_xml_document_bytes=1,
)


def _symlink_tar() -> bytes:
    info = tarfile.TarInfo(name="sql/dbcfg.sql")
    info.type = tarfile.SYMTYPE
    info.linkname = "elsewhere"
    return pack_tar_gz_infos([(info, None)])


def _hardlink_tar() -> bytes:
    info = tarfile.TarInfo(name="sql/dbcfg.sql")
    info.type = tarfile.LNKTYPE
    info.linkname = "elsewhere"
    return pack_tar_gz_infos([(info, None)])


def _fifo_tar() -> bytes:
    info = tarfile.TarInfo(name="sql/dbcfg.sql")
    info.type = tarfile.FIFOTYPE
    return pack_tar_gz_infos([(info, None)])


@dataclass(frozen=True, slots=True)
class StagingRejectCase:
    label: str
    kind: PackageKind
    code: StagingDiagnosticCode
    payload: bytes | None = None
    directory_entries: tuple[tuple[str, bytes], ...] | None = None
    transport: StagingTransport = StagingTransport.IDENTITY
    budgets: ResourceBudgets = RESOURCE_BUDGETS
    budget_name: str | None = None


STAGING_REJECTS = (
    StagingRejectCase(
        "dotdot-segment",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("sql/../dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "empty-segment",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("sql//dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "backslash",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("sql\\dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "nul",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("sql/\x00dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "windows-drive",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("C:/sql/dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "file-uri",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.PATH_TRAVERSAL,
        directory_entries=(("file:sql/dbcfg.sql", _SQL),),
    ),
    StagingRejectCase(
        "tar-symlink",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
        payload=_symlink_tar(),
    ),
    StagingRejectCase(
        "tar-hardlink",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
        payload=_hardlink_tar(),
    ),
    StagingRejectCase(
        "zip-symlink",
        PackageKind.ZIP,
        StagingDiagnosticCode.SYMLINK_UNSUPPORTED,
        payload=pack_zip_symlink("sql/dbcfg.sql"),
    ),
    StagingRejectCase(
        "non-regular-fifo",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
        payload=_fifo_tar(),
    ),
    StagingRejectCase(
        "tar-zst-disguised-as-tar-gz",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.TAR_ZST_FORBIDDEN,
        payload=compression.zstd.compress(pack_tar_gz({"sql/dbcfg.sql": _SQL})),
    ),
    StagingRejectCase(
        "missing-required-sql",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.MISSING_REQUIRED_SQL,
        payload=pack_tar_gz({"readme.txt": b"no sql"}),
    ),
    StagingRejectCase(
        "duplicate-required-sql",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.DUPLICATE_REQUIRED_SQL,
        directory_entries=(("sql/dbcfg.sql", _SQL), ("./sql/dbcfg.sql", _SQL)),
    ),
    StagingRejectCase(
        "required-path-case-collision",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.CANONICAL_PATH_COLLISION,
        directory_entries=(("sql/dbcfg.sql", _SQL), ("SQL/dbcfg.sql", _SQL)),
    ),
    StagingRejectCase(
        "over-entry-count",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
        directory_entries=(("sql/dbcfg.sql", _SQL), ("readme.txt", b"x")),
        budgets=_TIGHT_ENTRIES,
        budget_name="max_source_package_entries",
    ),
    StagingRejectCase(
        "truncated-archive",
        PackageKind.TAR_GZ,
        StagingDiagnosticCode.MALFORMED_ARCHIVE,
        payload=pack_tar_gz({"sql/dbcfg.sql": _SQL})[:12],
    ),
    StagingRejectCase(
        "directory-zstd-unsupported",
        PackageKind.DIRECTORY,
        StagingDiagnosticCode.SOURCE_PACKAGE_UNSUPPORTED,
        directory_entries=(("sql/dbcfg.sql", _SQL),),
        transport=StagingTransport.ZSTD,
    ),
    StagingRejectCase(
        "oversize-compressed",
        PackageKind.SQL_FILE,
        StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
        payload=_SQL,
        budgets=_TIGHT_COMPRESSED,
        budget_name="max_source_package_compressed_bytes",
    ),
    StagingRejectCase(
        "zip-sql-document-budget",
        PackageKind.ZIP,
        StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
        payload=pack_zip({"sql/dbcfg.sql": _SQL}),
        budgets=_TIGHT_SQL_DOCUMENT,
        budget_name="max_sql_document_bytes",
    ),
    StagingRejectCase(
        "zip-xml-document-budget",
        PackageKind.ZIP,
        StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
        payload=pack_zip({"sql/dbcfg.sql": _SQL, "comps/logic/logics.xml": b"<x/>"}),
        budgets=_TIGHT_XML_DOCUMENT,
        budget_name="max_xml_document_bytes",
    ),
)


@pytest.mark.parametrize("case", STAGING_REJECTS, ids=lambda item: item.label)
def test_staging_rejects_fail_closed(case: StagingRejectCase) -> None:
    store = InMemoryArtifactStore()
    result = stage_source_package(
        SourcePackageInput(
            package_kind=case.kind,
            transport=case.transport,
            context=_CONTEXT,
            payload=case.payload,
            directory_entries=case.directory_entries,
        ),
        store,
        budgets=case.budgets,
    )
    assert result.status is StagingStatus.FAILED
    assert result.source_package_id is None
    assert result.artifact_ref is None
    assert result.required_sql_document_ref is None
    assert result.optional_xml_document_ref is None
    assert result.empty_composite_logic is False
    assert result.entries == ()
    assert result.diagnostics[0].code is case.code
    if case.budget_name is not None:
        assert result.diagnostics[0].budget_name == case.budget_name


def test_artifact_publish_failure_is_a_failed_result() -> None:
    class FailingStore(InMemoryArtifactStore):
        def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
            raise ManifestVerificationError("injected artifact write failure")

    result = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=_CONTEXT,
            payload=pack_tar_gz({"sql/dbcfg.sql": _SQL}),
        ),
        FailingStore(),
    )
    assert result.status is StagingStatus.FAILED
    assert result.diagnostics[0].code is StagingDiagnosticCode.ARTIFACT_PUBLISH_FAILED


def test_staging_checks_cancellation_at_entry_boundary() -> None:
    class CancelAfter:
        calls = 0

        def is_set(self) -> bool:
            self.calls += 1
            return self.calls >= 3

    probe = CancelAfter()
    result = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=StagingInvocationContext(probe),
            payload=pack_tar_gz({"sql/dbcfg.sql": _SQL, "readme.txt": b"x"}),
        ),
        InMemoryArtifactStore(),
    )
    assert result.status is StagingStatus.FAILED
    assert result.diagnostics[0].code is StagingDiagnosticCode.STAGING_CANCELLED
