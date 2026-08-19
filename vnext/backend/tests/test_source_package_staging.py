"""SourcePackage staging walking-path tests. Does not parse SQL or XML."""

from __future__ import annotations

import gzip

import compression.zstd
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.source_package_staging.contracts import (
    OPTIONAL_XML_PATH,
    REQUIRED_SQL_PATH,
    CompressionAlgorithm,
    NeverCancel,
    PackageKind,
    SourcePackageInput,
    SourcePackageStagingResult,
    StagingInvocationContext,
    StagingStatus,
    StagingTransport,
    resolve_sql_dump_source,
)
from gateway_backend.capabilities.source_package_staging.staging import stage_source_package
from gateway_shared_kernel import raw_blob_digest
from tests.support.source_package_fixtures import load_bytes, load_expected, pack_tar_gz, pack_zip

_CONTEXT = StagingInvocationContext(NeverCancel())
_SQL = load_bytes("package/valid/s1-minimal-tar-gz/sql/dbcfg.sql")
_XML = load_bytes("package/valid/s1-minimal-tar-gz/comps/logic/logics.xml")
_MEMBERS = {"sql/dbcfg.sql": _SQL, "comps/logic/logics.xml": _XML}


def _stage(
    kind: PackageKind,
    payload: bytes | None,
    *,
    directory_entries: tuple[tuple[str, bytes], ...] | None = None,
    retention_policy: str = "DEFAULT",
) -> tuple[SourcePackageStagingResult, InMemoryArtifactStore]:
    store = InMemoryArtifactStore()
    source = SourcePackageInput(
        package_kind=kind,
        transport=StagingTransport.IDENTITY,
        context=_CONTEXT,
        payload=payload,
        directory_entries=directory_entries,
        retention_policy=retention_policy,
    )
    return stage_source_package(source, store), store


def test_minimal_tar_gz_golden_shape() -> None:
    expected = load_expected("package/valid/s1-minimal-tar-gz/expected.json")
    payload = pack_tar_gz(_MEMBERS)
    result, store = _stage(PackageKind.TAR_GZ, payload)
    assert result.status is StagingStatus.COMPLETE
    assert result.empty_composite_logic is expected["empty_composite_logic"]
    assert result.required_sql_document_ref is not None
    assert result.required_sql_document_ref.normalized_path == expected["required_sql_path"]
    assert result.optional_xml_document_ref is not None
    assert result.optional_xml_document_ref.normalized_path == expected["optional_xml_path"]
    assert result.compression is CompressionAlgorithm.GZIP
    sql_source = resolve_sql_dump_source(result.required_sql_document_ref)
    assert sql_source.sql_source_digest == result.required_sql_document_ref.document_content_digest
    assert result.required_sql_document_ref.document_content_digest == raw_blob_digest(_SQL)
    assert result.optional_xml_document_ref.document_content_digest == raw_blob_digest(_XML)
    assert result.artifact_ref is not None
    assert store.locate(result.artifact_ref) == payload
    assert store.locate(result.required_sql_document_ref.artifact_ref) == _SQL


def test_missing_xml_is_stable_empty_source() -> None:
    expected = load_expected("package/valid/s1-missing-xml-empty/expected.json")
    sql = load_bytes("package/valid/s1-missing-xml-empty/sql/dbcfg.sql")
    result, _store = _stage(PackageKind.TAR_GZ, pack_tar_gz({"sql/dbcfg.sql": sql}))
    assert result.status is StagingStatus.COMPLETE
    assert result.empty_composite_logic is expected["empty_composite_logic"]
    assert result.optional_xml_document_ref is None
    assert result.diagnostics == ()


def test_zip_and_directory_and_sql_file_helpers() -> None:
    zip_result, _ = _stage(PackageKind.ZIP, pack_zip(_MEMBERS))
    directory_result, _ = _stage(
        PackageKind.DIRECTORY,
        None,
        directory_entries=tuple(_MEMBERS.items()),
    )
    sql_result, _ = _stage(PackageKind.SQL_FILE, _SQL)
    assert zip_result.status is StagingStatus.COMPLETE
    assert directory_result.status is StagingStatus.COMPLETE
    assert sql_result.status is StagingStatus.COMPLETE
    assert sql_result.required_sql_document_ref is not None
    assert sql_result.required_sql_document_ref.normalized_path == REQUIRED_SQL_PATH
    assert sql_result.empty_composite_logic is True
    assert sql_result.compression is CompressionAlgorithm.NONE


def test_sql_gz_and_zstd_transport() -> None:
    gz_result, _ = _stage(PackageKind.SQL_GZ, gzip.compress(_SQL, mtime=0))
    store = InMemoryArtifactStore()
    zstd_source = SourcePackageInput(
        package_kind=PackageKind.SQL_FILE,
        transport=StagingTransport.ZSTD,
        context=_CONTEXT,
        payload=compression.zstd.compress(_SQL),
    )
    zstd_result = stage_source_package(zstd_source, store)
    assert gz_result.status is StagingStatus.COMPLETE
    assert gz_result.compression is CompressionAlgorithm.GZIP
    assert zstd_result.status is StagingStatus.COMPLETE
    assert zstd_result.compression is CompressionAlgorithm.ZSTD
    assert zstd_result.required_sql_document_ref is not None
    assert store.locate(zstd_result.required_sql_document_ref.artifact_ref) == _SQL


def test_gzip_mtime_does_not_change_content_digests() -> None:
    first, _ = _stage(PackageKind.TAR_GZ, pack_tar_gz(_MEMBERS, mtime=0))
    second, _ = _stage(PackageKind.TAR_GZ, pack_tar_gz(_MEMBERS, mtime=1))
    assert first.status is StagingStatus.COMPLETE
    assert second.status is StagingStatus.COMPLETE
    assert first.source_package_digest == second.source_package_digest
    assert first.package_manifest_digest == second.package_manifest_digest
    assert first.required_sql_document_ref is not None
    assert second.required_sql_document_ref is not None
    assert (
        first.required_sql_document_ref.document_content_digest
        == second.required_sql_document_ref.document_content_digest
    )
    assert first.artifact_ref is not None
    assert second.artifact_ref is not None
    assert first.artifact_ref.raw_sha256 != second.artifact_ref.raw_sha256


def test_extra_members_are_metadata_only() -> None:
    members = {**_MEMBERS, "readme.txt": b"not a document"}
    result, _ = _stage(PackageKind.TAR_GZ, pack_tar_gz(members))
    assert result.status is StagingStatus.COMPLETE
    extra = [entry for entry in result.entries if entry.normalized_path == "/readme.txt"]
    assert len(extra) == 1
    assert extra[0].content_digest is None
    assert result.optional_xml_document_ref is not None
    assert result.optional_xml_document_ref.normalized_path == OPTIONAL_XML_PATH


def test_retention_policy_does_not_change_digest() -> None:
    payload = pack_tar_gz({"sql/dbcfg.sql": _SQL})
    first, _ = _stage(PackageKind.TAR_GZ, payload)
    second, _ = _stage(PackageKind.TAR_GZ, payload, retention_policy="SHORT")
    assert first.source_package_digest == second.source_package_digest
    assert first.source_package_id != second.source_package_id
