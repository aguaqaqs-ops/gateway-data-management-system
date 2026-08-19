"""Bounded SourcePackage staging walking path.

Produces public refs and artifact metadata only. Does not interpret SQL or XML.
"""

from __future__ import annotations

import secrets
import time

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactStorePort,
    ManifestVerificationError,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.source_package_staging._archive import (
    ArchiveMember,
    ExpansionCounter,
    StagingFault,
    apply_transport,
    iter_members,
)
from gateway_backend.capabilities.source_package_staging.contracts import (
    OPTIONAL_XML_PATH,
    REQUIRED_SQL_PATH,
    RESOURCE_BUDGETS,
    SOURCE_PACKAGE_CONTRACT_VERSION,
    CompressionAlgorithm,
    DiagnosticSeverity,
    DocumentKind,
    EntryKind,
    PackageKind,
    ResourceBudgets,
    SourceDocumentRef,
    SourcePackageEntry,
    SourcePackageInput,
    SourcePackageStagingResult,
    StagingDiagnostic,
    StagingDiagnosticCode,
    StagingStatus,
    StagingTransport,
)


def stage_source_package(
    source: SourcePackageInput,
    store: ArtifactStorePort,
    *,
    budgets: ResourceBudgets = RESOURCE_BUDGETS,
) -> SourcePackageStagingResult:
    """Stage a SourcePackage into opaque refs. Fail closed without publishing refs."""

    if type(source) is not SourcePackageInput:
        raise ValueError("source must be SourcePackageInput")
    compression = _compression_for(source)
    try:
        _check_deadline(source)
        members, package_bytes = _collect_members(source, budgets)
        return _complete(source, store, members, package_bytes, compression)
    except StagingFault as exc:
        return _failed(exc, compression, budgets)
    except ManifestVerificationError as exc:
        return _failed(
            StagingFault(
                StagingDiagnosticCode.ARTIFACT_PUBLISH_FAILED,
                str(exc) or "source artifact publish failed",
            ),
            compression,
            budgets,
        )


def _collect_members(
    source: SourcePackageInput,
    budgets: ResourceBudgets,
) -> tuple[tuple[ArchiveMember, ...], bytes]:
    if source.package_kind is PackageKind.DIRECTORY and source.transport is StagingTransport.ZSTD:
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_UNSUPPORTED,
            "DIRECTORY does not use zstd transport",
        )
    payload = source.payload
    counter = ExpansionCounter(compressed_bytes=0, expanded_bytes=0, entry_count=0)
    if payload is not None:
        counter.compressed_bytes = len(payload)
        if counter.compressed_bytes > budgets.max_source_package_compressed_bytes:
            raise StagingFault(
                StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
                "compressed ingress exceeds max_source_package_compressed_bytes",
                budget_name="max_source_package_compressed_bytes",
            )
        payload = apply_transport(payload, source.transport, budgets, counter)
    collected: list[ArchiveMember] = []
    for member in iter_members(source.package_kind, payload, source.directory_entries, budgets, counter):
        _check_deadline(source)
        collected.append(member)
    members = tuple(collected)
    package_bytes = payload if payload is not None else _directory_package_bytes(members)
    return members, package_bytes


def _complete(
    source: SourcePackageInput,
    store: ArtifactStorePort,
    members: tuple[ArchiveMember, ...],
    package_bytes: bytes,
    compression: CompressionAlgorithm,
) -> SourcePackageStagingResult:
    _detect_collisions(members)
    sql_members = _files_at(members, REQUIRED_SQL_PATH)
    xml_members = _files_at(members, OPTIONAL_XML_PATH)
    if not sql_members:
        raise StagingFault(
            StagingDiagnosticCode.MISSING_REQUIRED_SQL,
            "required /sql/dbcfg.sql is missing",
        )
    if len(sql_members) > 1:
        raise StagingFault(
            StagingDiagnosticCode.DUPLICATE_REQUIRED_SQL,
            "required /sql/dbcfg.sql is not unique",
        )
    sql_member = sql_members[0]
    if sql_member.content is None:
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "required /sql/dbcfg.sql could not be materialized",
        )
    if (
        source.expected_required_sql_digest is not None
        and raw_blob_digest(sql_member.content) != source.expected_required_sql_digest
    ):
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_DIGEST_MISMATCH,
            "required SQL document digest does not match",
        )
    xml_member = xml_members[0] if xml_members else None
    if xml_member is not None and xml_member.content is None:
        raise StagingFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "optional XML document could not be materialized",
        )
    if len(xml_members) > 1:
        raise StagingFault(
            StagingDiagnosticCode.CANONICAL_PATH_COLLISION,
            "optional /comps/logic/logics.xml is not unique",
        )

    package_id = _new_id("source-package")
    entries = tuple(_to_entry(member) for member in members)
    manifest_digest = _manifest_digest(entries)
    source_package_digest = _source_package_digest(source.package_kind, manifest_digest)
    required_entries = tuple(
        entry
        for entry in entries
        if entry.normalized_path == REQUIRED_SQL_PATH
        or (xml_member is not None and entry.normalized_path == OPTIONAL_XML_PATH)
    )
    required_digest = _manifest_digest(required_entries)
    _check_deadline(source)
    package_ref = put_with_built_ref(
        store,
        package_bytes,
        artifact_id=_new_id("source-bytes"),
        media_type="application/octet-stream",
    )
    _check_deadline(source)
    sql_ref = _document_ref(store, package_id, sql_member, DocumentKind.SQL_DUMP)
    xml_ref = None
    if xml_member is not None:
        _check_deadline(source)
        xml_ref = _document_ref(store, package_id, xml_member, DocumentKind.XML)
    return SourcePackageStagingResult(
        status=StagingStatus.COMPLETE,
        compression=compression,
        diagnostics=(),
        source_package_id=package_id,
        source_package_digest=source_package_digest,
        package_manifest_digest=manifest_digest,
        required_entries_manifest_digest=required_digest,
        entries=entries,
        artifact_ref=package_ref,
        required_sql_document_ref=sql_ref,
        optional_xml_document_ref=xml_ref,
        empty_composite_logic=xml_ref is None,
    )


def _document_ref(
    store: ArtifactStorePort,
    package_id: str,
    member: ArchiveMember,
    kind: DocumentKind,
) -> SourceDocumentRef:
    assert member.content is not None
    content_digest = raw_blob_digest(member.content)
    entry = _to_entry(member)
    entry_manifest_digest = _manifest_digest((entry,))
    artifact_ref = put_with_built_ref(
        store,
        member.content,
        artifact_id=_new_id("source-doc"),
        media_type="application/octet-stream",
    )
    return SourceDocumentRef(
        source_package_id=package_id,
        normalized_path=member.normalized_path,
        document_kind=kind,
        document_content_digest=content_digest,
        size_bytes=member.size_bytes,
        entry_manifest_digest=entry_manifest_digest,
        artifact_ref=artifact_ref,
        encoding_hint="utf-8",
    )


def _to_entry(member: ArchiveMember) -> SourcePackageEntry:
    content_digest = raw_blob_digest(member.content) if member.content is not None else None
    return SourcePackageEntry(
        normalized_path=member.normalized_path,
        entry_kind=member.entry_kind,
        size_bytes=member.size_bytes,
        content_digest=content_digest,
        original_path=member.original_path,
    )


def _manifest_digest(entries: tuple[SourcePackageEntry, ...]) -> DigestRef:
    payload = {
        "contract_version": SOURCE_PACKAGE_CONTRACT_VERSION,
        "entries": [
            _entry_payload(entry)
            for entry in sorted(entries, key=lambda item: item.normalized_path)
        ],
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def _source_package_digest(kind: PackageKind, manifest_digest: DigestRef) -> DigestRef:
    payload = {
        "contract_version": SOURCE_PACKAGE_CONTRACT_VERSION,
        "package_kind": kind.value,
        "package_manifest_digest": manifest_digest.value,
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def _entry_payload(entry: SourcePackageEntry) -> dict[str, object]:
    payload: dict[str, object] = {
        "normalized_path": entry.normalized_path,
        "entry_kind": entry.entry_kind.value,
        "size_bytes": entry.size_bytes,
    }
    if entry.content_digest is not None:
        payload["content_digest"] = entry.content_digest.value
    return payload


def _directory_package_bytes(members: tuple[ArchiveMember, ...]) -> bytes:
    cleaned_entries: list[dict[str, object]] = []
    for member in sorted(members, key=lambda item: item.normalized_path):
        item: dict[str, object] = {
            "normalized_path": member.normalized_path,
            "size_bytes": member.size_bytes,
        }
        if member.content is not None:
            item["content_digest"] = raw_blob_digest(member.content).value
        cleaned_entries.append(item)
    return canonicalize_json_value(
        {
            "contract_version": SOURCE_PACKAGE_CONTRACT_VERSION,
            "entries": cleaned_entries,
        }
    )


def _files_at(members: tuple[ArchiveMember, ...], path: str) -> list[ArchiveMember]:
    return [
        member
        for member in members
        if member.normalized_path == path and member.entry_kind is EntryKind.FILE
    ]


def _detect_collisions(members: tuple[ArchiveMember, ...]) -> None:
    by_path: dict[str, ArchiveMember] = {}
    by_casefold: dict[str, str] = {}
    for member in members:
        if member.normalized_path in by_path:
            if member.normalized_path == REQUIRED_SQL_PATH:
                raise StagingFault(
                    StagingDiagnosticCode.DUPLICATE_REQUIRED_SQL,
                    "required /sql/dbcfg.sql is not unique",
                )
            raise StagingFault(
                StagingDiagnosticCode.CANONICAL_PATH_COLLISION,
                "package entries collide on normalized_path",
            )
        folded = member.normalized_path.casefold()
        previous = by_casefold.get(folded)
        if previous is not None and previous != member.normalized_path:
            raise StagingFault(
                StagingDiagnosticCode.CANONICAL_PATH_COLLISION,
                "package entries collide on canonical path",
            )
        by_path[member.normalized_path] = member
        by_casefold[folded] = member.normalized_path


def _compression_for(source: SourcePackageInput) -> CompressionAlgorithm:
    if source.transport is StagingTransport.ZSTD:
        return CompressionAlgorithm.ZSTD
    if source.package_kind in {PackageKind.TAR_GZ, PackageKind.SQL_GZ}:
        return CompressionAlgorithm.GZIP
    return CompressionAlgorithm.NONE


def _check_deadline(source: SourcePackageInput) -> None:
    if source.context.cancel_requested.is_set():
        raise StagingFault(
            StagingDiagnosticCode.STAGING_CANCELLED,
            "staging was cancelled",
        )
    deadline = source.context.deadline_monotonic
    if deadline is not None and time.monotonic() >= deadline:
        raise StagingFault(
            StagingDiagnosticCode.STAGING_TIMEOUT,
            "staging deadline has passed",
        )


def _failed(
    fault: StagingFault,
    compression: CompressionAlgorithm,
    budgets: ResourceBudgets,
) -> SourcePackageStagingResult:
    message = fault.message
    if len(message.encode("utf-8")) > budgets.max_diagnostic_message_bytes:
        message = message.encode("utf-8")[: budgets.max_diagnostic_message_bytes].decode(
            "utf-8",
            "ignore",
        )
        if message == "":
            message = fault.code.value
    diagnostic = StagingDiagnostic(
        code=fault.code,
        severity=DiagnosticSeverity.ERROR,
        message=message,
        budget_name=fault.budget_name,
    )
    return SourcePackageStagingResult(
        status=StagingStatus.FAILED,
        compression=compression,
        diagnostics=(diagnostic,),
    )


def _new_id(namespace: str) -> str:
    return build_artifact_id(namespace, secrets.token_hex(8))
