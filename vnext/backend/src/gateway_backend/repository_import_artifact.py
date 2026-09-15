"""RepositoryImportArtifact v1 writer and Submit import publication adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SnapshotTableBinding,
)
from gateway_backend.artifacts import (
    ArtifactStorePort,
    ManifestVerificationError,
    backend_artifact_ref_from_store_ref,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import ArtifactSourceBinding
from gateway_backend.capabilities.storage_projection import (
    ImportReplayError,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    build_import_mutation_snapshots,
    publish_canonicalization,
    project_storage,
    render_repository_import_replay_sql,
)
from gateway_backend.capabilities.storage_projection.contracts import WrittenImportPackage
from gateway_backend.capabilities.storage_projection.package import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    PackageError,
    pack_repository_import_entries,
)
from gateway_backend.capabilities.table_rules.contracts import TableRulesetSnapshot
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy

__all__ = [
    "MANIFEST_ENTRY_NAME",
    "REPLAY_SQL_ENTRY_NAME",
    "RepositoryImportArtifactError",
    "SubmitImportPublicationAdapter",
    "SubmitImportPublicationError",
    "WrittenImportPackage",
    "build_repository_import_package",
    "write_repository_import_package",
]


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


class SubmitImportPublicationError(ValueError):
    """Raised when submit import publication fails closed."""


class SubmitImportPublicationAdapter:
    """REBUILD_ALWAYS adapter over Storage Projection and Mutation Planning."""

    def build_and_publish(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult:
        projection_inputs = _open_projection_inputs(build_input.snapshot_tables, store=store)
        return self.build_and_publish_from_inputs(
            build_input=build_input,
            store=store,
            projection_inputs=projection_inputs,
        )

    def build_and_publish_from_inputs(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
        projection_inputs: tuple[ProjectionTableInput, ...],
    ) -> PrepareImportPublicationResult:
        _assert_rebuild_policy(build_input)
        ruleset = _resolve_ruleset(build_input)
        projection_request = ProjectionRequest(
            ruleset=ruleset,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=projection_inputs,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
        projection = project_storage(projection_request)
        if projection.status is not ProjectionStatus.COMPLETE:
            code = projection.diagnostics[0].code.value if projection.diagnostics else "FAILED"
            raise SubmitImportPublicationError(f"storage projection failed: {code}")
        if projection.manifest is None or projection.import_input is None:
            raise SubmitImportPublicationError("COMPLETE projection is missing manifest or import input")
        _assert_projection_identity(build_input, projection)
        try:
            after_tables = build_import_mutation_snapshots(projection_request, projection)
            replay_sql = render_repository_import_replay_sql(projection, after_tables)
        except ImportReplayError as exc:
            raise SubmitImportPublicationError(str(exc)) from exc
        published = publish_canonicalization(
            projection,
            store=store,
            replay_sql=replay_sql,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
        if published.status is not ProjectionStatus.COMPLETE or published.publication is None:
            code = published.diagnostics[0].code.value if published.diagnostics else "FAILED"
            raise SubmitImportPublicationError(f"canonical publication failed: {code}")
        publication = published.publication
        package_ref = backend_artifact_ref_from_store_ref(publication.package_ref)
        manifest_ref = backend_artifact_ref_from_store_ref(publication.manifest_ref)
        checkpoint = PrepareImportCheckpoint(
            schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
            attempt_id=build_input.submit_attempt_id,
            canonicalization_manifest_ref=manifest_ref,
            backend_import_artifact_ref=package_ref,
            package_raw_size=package_ref.size_bytes,
            package_raw_sha256=package_ref.raw_sha256,
            input_closure_digest=build_input.input_closure_digest,
            builder_mutation_policy=build_input.builder_mutation_policy,
        )
        return PrepareImportPublicationResult(checkpoint=checkpoint, replay=False)

    def read_back_package(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> bytes:
        ref = ArtifactRef(
            artifact_id=checkpoint.backend_import_artifact_ref.artifact_id,
            media_type=checkpoint.backend_import_artifact_ref.media_type,
            size_bytes=checkpoint.backend_import_artifact_ref.size_bytes,
            raw_sha256=DigestRef(checkpoint.backend_import_artifact_ref.raw_sha256),
        )
        try:
            payload = store.locate(ref)
        except ManifestVerificationError as exc:
            raise SubmitImportPublicationError(str(exc) or "import package is missing or corrupt") from exc
        if raw_blob_digest(payload).value != checkpoint.package_raw_sha256:
            raise SubmitImportPublicationError("read-back package raw SHA mismatch")
        if len(payload) != checkpoint.package_raw_size:
            raise SubmitImportPublicationError("read-back package size mismatch")
        return payload


def build_repository_import_package(
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    if type(replay_sql) is not bytes:
        raise RepositoryImportArtifactError("replay.sql must be bytes")
    try:
        manifest_bytes = json.dumps(dict(manifest), separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryImportArtifactError(str(exc) or "manifest.json is not serializable") from exc
    try:
        return pack_repository_import_entries(manifest_bytes, replay_sql)
    except PackageError as exc:
        raise RepositoryImportArtifactError(str(exc)) from exc


def write_repository_import_package(
    path: Path,
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    written = build_repository_import_package(manifest=manifest, replay_sql=replay_sql)
    path.write_bytes(written.payload)
    return written


def _assert_rebuild_policy(build_input: PrepareImportBuildInput) -> None:
    if build_input.builder_mutation_policy is not BuilderMutationPolicy.REBUILD_ALWAYS:
        raise SubmitImportPublicationError("builder_mutation_policy must be REBUILD_ALWAYS")


def _resolve_ruleset(build_input: PrepareImportBuildInput) -> TableRulesetSnapshot:
    ruleset = migrated_table_ruleset_snapshot()
    if ruleset.ruleset_digest is None:
        raise SubmitImportPublicationError("ruleset digest is required")
    if (
        ruleset.ruleset_id != build_input.ruleset_id
        or ruleset.ruleset_version != build_input.ruleset_version
        or ruleset.ruleset_digest.value != build_input.ruleset_digest
    ):
        raise SubmitImportPublicationError("ruleset identity does not match build input")
    if build_input.storage_projection_version != STORAGE_PROJECTION_VERSION:
        raise SubmitImportPublicationError("unsupported storage_projection_version")
    return ruleset


def _assert_projection_identity(
    build_input: PrepareImportBuildInput,
    projection: object,
) -> None:
    from gateway_backend.capabilities.storage_projection.contracts import ProjectionResult

    if type(projection) is not ProjectionResult or projection.manifest is None:
        raise SubmitImportPublicationError("projection manifest is required")
    manifest = projection.manifest
    if build_input.source_artifact_digest != manifest.source_artifact_digest.value:
        raise SubmitImportPublicationError("source_artifact_digest does not match projection manifest")
    if build_input.repository_base_digest != manifest.source_artifact_digest.value:
        raise SubmitImportPublicationError("repository_base_digest does not match projection manifest")


def _open_projection_inputs(
    bindings: tuple[SnapshotTableBinding, ...],
    *,
    store: ArtifactStorePort,
) -> tuple[ProjectionTableInput, ...]:
    opened: list[ProjectionTableInput] = []
    for binding in bindings:
        manifest_ref = ArtifactRef(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=DigestRef(binding.raw_sha256),
        )
        table = open_snapshot_table_artifact(store, manifest_ref)
        if table.reader is None:
            raise SubmitImportPublicationError(f"snapshot table {binding.artifact_id} has no reader")
        if table.artifact is None:
            raise SubmitImportPublicationError(f"snapshot table {binding.artifact_id} has no artifact")
        source_binding = ArtifactSourceBinding(
            snapshot_digest=table.artifact.manifest.snapshot_digest,
            descriptor=table.descriptor,
        )
        opened.append(
            ProjectionTableInput(
                canonical_table=table.descriptor.table_name,
                reader=table.reader.reopen() if hasattr(table.reader, "reopen") else table.reader,
                source_binding=source_binding,
                artifact=table.artifact,
            )
        )
    return tuple(opened)
