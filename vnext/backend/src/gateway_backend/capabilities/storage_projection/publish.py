"""Staging write, validation, and atomic canonical publication."""

from __future__ import annotations

import secrets
from dataclasses import replace

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    ManifestVerificationError,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest
from gateway_backend.capabilities.storage_projection._runtime import runtime_failure
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    CanonicalPublication,
    CanonicalPublicationResult,
    CanonicalizationManifest,
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
    ProjectionInvocationContext,
    ProjectionResult,
    ProjectionStatus,
    RepositoryImportArtifactInput,
)
from gateway_backend.capabilities.storage_projection.package import (
    PackageError,
    build_repository_import_package,
    canonicalization_manifest_from_bytes,
    durable_manifest_bytes,
    validate_repository_import_package,
)


class PublicationError(ValueError):
    def __init__(self, code: ProjectionDiagnosticCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _PublishFailed(Exception):
    def __init__(self, diagnostic: ProjectionDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def publish_canonicalization(
    result: ProjectionResult,
    *,
    store: ArtifactStorePort,
    replay_sql: bytes,
    context: ProjectionInvocationContext,
) -> CanonicalPublicationResult:
    try:
        publication = _publish(result, store=store, replay_sql=replay_sql, context=context)
    except _PublishFailed as exc:
        return CanonicalPublicationResult(
            status=ProjectionStatus.FAILED,
            diagnostics=(exc.diagnostic,),
        )
    return CanonicalPublicationResult(
        status=ProjectionStatus.COMPLETE,
        publication=publication,
    )


def publish_canonicalization_manifest(
    manifest: CanonicalizationManifest,
    store: ArtifactStorePort,
) -> ArtifactRef:
    """Persist the canonicalization manifest without building an import package."""
    if type(manifest) is not CanonicalizationManifest:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest must be CanonicalizationManifest",
        )
    if manifest.contract_version != CANONICALIZATION_MANIFEST_CONTRACT:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            f"new manifest writes require contract_version {CANONICALIZATION_MANIFEST_CONTRACT}",
        )
    if manifest.manifest_digest is None:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest write requires manifest_digest",
        )
    if compute_manifest_digest(replace(manifest, manifest_digest=None)) != manifest.manifest_digest:
        raise PublicationError(
            ProjectionDiagnosticCode.DIGEST_MISMATCH,
            "manifest digest mismatch",
        )
    try:
        payload = durable_manifest_bytes(manifest)
        ref = put_with_built_ref(
            store,
            payload,
            artifact_id=_opaque_id("canonicalization-manifest"),
            media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        )
        stored = store.locate(ref)
    except PackageError as exc:
        raise PublicationError(exc.code, exc.message) from exc
    except ManifestVerificationError as exc:
        raise PublicationError(
            ProjectionDiagnosticCode.PUBLICATION_FAILED,
            str(exc) or "manifest artifact write or read failed",
        ) from exc
    except OSError as exc:
        raise PublicationError(
            ProjectionDiagnosticCode.PUBLICATION_FAILED,
            str(exc) or "manifest artifact write or read failed",
        ) from exc
    if stored != payload:
        raise PublicationError(
            ProjectionDiagnosticCode.PUBLICATION_FAILED,
            "stored manifest bytes do not match",
        )
    try:
        opened = canonicalization_manifest_from_bytes(stored)
    except PackageError as exc:
        raise PublicationError(exc.code, exc.message) from exc
    if opened != manifest:
        raise PublicationError(
            ProjectionDiagnosticCode.DIGEST_MISMATCH,
            "durable manifest round-trip mismatch",
        )
    return ref


def open_canonicalization_manifest(store: ArtifactStorePort, ref: ArtifactRef) -> CanonicalizationManifest:
    if type(ref) is not ArtifactRef:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest ref must be ArtifactRef",
        )
    if ref.media_type != CANONICALIZATION_MANIFEST_MEDIA_TYPE:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "manifest ref media_type mismatch",
        )
    try:
        payload = store.locate(ref)
    except ManifestVerificationError as exc:
        raise PublicationError(
            ProjectionDiagnosticCode.PUBLICATION_FAILED,
            str(exc) or "durable manifest is missing or corrupt",
        ) from exc
    try:
        return canonicalization_manifest_from_bytes(payload)
    except PackageError as exc:
        raise PublicationError(exc.code, exc.message) from exc


def open_repository_import_package(
    store: ArtifactStorePort,
    ref: ArtifactRef,
) -> RepositoryImportArtifactInput:
    if type(ref) is not ArtifactRef:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "package ref must be ArtifactRef",
        )
    if ref.media_type != REPOSITORY_IMPORT_MEDIA_TYPE:
        raise PublicationError(
            ProjectionDiagnosticCode.BINDING_INVALID,
            "package ref media_type mismatch",
        )
    try:
        payload = store.locate(ref)
    except ManifestVerificationError as exc:
        raise PublicationError(
            ProjectionDiagnosticCode.PUBLICATION_FAILED,
            str(exc) or "import package is missing or corrupt",
        ) from exc
    try:
        return validate_repository_import_package(payload)
    except PackageError as exc:
        raise PublicationError(exc.code, exc.message) from exc


def _publish(
    result: ProjectionResult,
    *,
    store: ArtifactStorePort,
    replay_sql: bytes,
    context: ProjectionInvocationContext,
) -> CanonicalPublication:
    if type(result) is not ProjectionResult:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.BINDING_INVALID, "result must be ProjectionResult")
        )
    if type(context) is not ProjectionInvocationContext:
        raise _PublishFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "context must be ProjectionInvocationContext",
            )
        )
    _checkpoint(context)
    if result.status is not ProjectionStatus.COMPLETE:
        raise _PublishFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "publication requires a COMPLETE projection",
            )
        )
    manifest = result.manifest
    import_input = result.import_input
    if type(manifest) is not CanonicalizationManifest or type(import_input) is not RepositoryImportArtifactInput:
        raise _PublishFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "COMPLETE projection requires manifest and import input",
            )
        )
    _assert_publication_authority(result, manifest, import_input)
    _checkpoint(context)
    try:
        manifest_bytes = durable_manifest_bytes(manifest)
        package = build_repository_import_package(import_input=import_input, replay_sql=replay_sql)
    except PackageError as exc:
        raise _PublishFailed(_error(exc.code, exc.message)) from exc
    _checkpoint(context)
    manifest_ref = _put_bytes(
        store,
        manifest_bytes,
        namespace="r4-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        context=context,
    )
    stored_manifest = _locate(store, manifest_ref, context)
    if stored_manifest != manifest_bytes:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, "stored manifest bytes do not match")
        )
    try:
        opened_manifest = canonicalization_manifest_from_bytes(stored_manifest)
    except PackageError as exc:
        raise _PublishFailed(_error(exc.code, exc.message)) from exc
    if opened_manifest != manifest:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "durable manifest round-trip mismatch")
        )
    _checkpoint(context)
    package_ref = _put_bytes(
        store,
        package.payload,
        namespace="r4-package",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        context=context,
    )
    stored_package = _locate(store, package_ref, context)
    if stored_package != package.payload:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, "stored package bytes do not match")
        )
    try:
        opened_input = validate_repository_import_package(stored_package)
    except PackageError as exc:
        raise _PublishFailed(_error(exc.code, exc.message)) from exc
    if opened_input != import_input:
        raise _PublishFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "import package round-trip must preserve structural authority",
            )
        )
    if package_ref.raw_sha256.value != package.sha256:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "package raw SHA mismatch")
        )
    _checkpoint(context)
    assert manifest.manifest_digest is not None
    return CanonicalPublication(
        manifest_ref=manifest_ref,
        package_ref=package_ref,
        manifest_digest=manifest.manifest_digest,
    )


def _assert_publication_authority(
    result: ProjectionResult,
    manifest: CanonicalizationManifest,
    import_input: RepositoryImportArtifactInput,
) -> None:
    if manifest.manifest_digest is None:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.BINDING_INVALID, "COMPLETE projection requires manifest_digest")
        )
    recomputed = compute_manifest_digest(replace(manifest, manifest_digest=None))
    if recomputed != manifest.manifest_digest:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "manifest digest mismatch")
        )
    if import_input.canonicalization_manifest_digest != manifest.manifest_digest:
        raise _PublishFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "import input must bind the opaque manifest digest",
            )
        )
    projected = {table.canonical_table: table for table in result.tables}
    imported = {table.name: table for table in import_input.tables}
    recorded = {table.name: table for table in manifest.tables}
    if set(projected) != set(recorded) or set(imported) != set(recorded):
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.BINDING_INVALID, "published tables must match the manifest")
        )
    for name, manifest_table in recorded.items():
        projected_table = projected[name]
        imported_table = imported[name]
        if imported_table.row_count != manifest_table.canonical_row_count:
            raise _PublishFailed(
                _error(
                    ProjectionDiagnosticCode.ROW_INTEGRITY,
                    "import row_count must match canonical_row_count",
                    name,
                )
            )
        if projected_table.row_count != manifest_table.canonical_row_count:
            raise _PublishFailed(
                _error(
                    ProjectionDiagnosticCode.ROW_INTEGRITY,
                    "projected row_count must match canonical_row_count",
                    name,
                )
            )
        if imported_table.primary_key != manifest_table.canonical_key_columns:
            raise _PublishFailed(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "import primary_key must match canonical_key_columns",
                    name,
                )
            )
        imported_names = tuple(column.name for column in imported_table.columns)
        if imported_names != manifest_table.retained_columns:
            raise _PublishFailed(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "import columns must match retained_columns",
                    name,
                )
            )
        dropped_names = {item.name for item in manifest_table.dropped_columns}
        if dropped_names.intersection(imported_names):
            raise _PublishFailed(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "dropped columns must not appear in import schema",
                    name,
                )
            )
        for item in manifest_table.dropped_columns:
            if item.reason == "":
                raise _PublishFailed(
                    _error(
                        ProjectionDiagnosticCode.BINDING_INVALID,
                        "dropped column reason is required",
                        name,
                    )
                )
        if projected_table.schema_digest != manifest_table.canonical_schema_digest:
            raise _PublishFailed(
                _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "schema digest mismatch", name)
            )
        if projected_table.content_digest != manifest_table.content_digest:
            raise _PublishFailed(
                _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "content digest mismatch", name)
            )


def _put_bytes(
    store: ArtifactStorePort,
    payload: bytes,
    *,
    namespace: str,
    media_type: str,
    context: ProjectionInvocationContext,
) -> ArtifactRef:
    _checkpoint(context)
    try:
        ref = put_with_built_ref(
            store,
            payload,
            artifact_id=_opaque_id(namespace),
            media_type=media_type,
        )
    except ManifestVerificationError as exc:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, str(exc) or "artifact store write failed")
        ) from exc
    except OSError as exc:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, str(exc) or "artifact store write failed")
        ) from exc
    return ref


def _locate(
    store: ArtifactStorePort,
    ref: ArtifactRef,
    context: ProjectionInvocationContext,
) -> bytes:
    _checkpoint(context)
    try:
        return store.locate(ref)
    except ManifestVerificationError as exc:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, str(exc) or "artifact store read failed")
        ) from exc
    except OSError as exc:
        raise _PublishFailed(
            _error(ProjectionDiagnosticCode.PUBLICATION_FAILED, str(exc) or "artifact store read failed")
        ) from exc


def _checkpoint(context: ProjectionInvocationContext) -> None:
    diagnostic = runtime_failure(context)
    if diagnostic is not None:
        raise _PublishFailed(diagnostic)


def _opaque_id(namespace: str) -> str:
    return build_artifact_id(namespace, secrets.token_hex(8))


def _error(
    code: ProjectionDiagnosticCode,
    message: str,
    table_name: str | None = None,
) -> ProjectionDiagnostic:
    return ProjectionDiagnostic(
        code=code,
        severity=ProjectionDiagnosticSeverity.ERROR,
        message=message,
        table_name=table_name,
    )
