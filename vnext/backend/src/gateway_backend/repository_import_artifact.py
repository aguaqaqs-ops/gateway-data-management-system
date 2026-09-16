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
from gateway_backend.capabilities.mutation_planning import (
    ImportReplayError as MutationImportReplayError,
    build_import_mutation_snapshots,
    plan_storage_mutation,
)
from gateway_backend.capabilities.mutation_planning._dolt_renderer import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
    render_change_set_replay,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPlanStatus,
    MutationPlanningInput,
    MutationPlanningRequest,
    MutationPolicy,
    MutationProjectionBinding,
    MutationRepositoryBase,
    MutationSourceIdentity,
    MutationTableSnapshot,
    MutationThresholdPolicy,
)
from gateway_backend.capabilities.snapshot_materialization import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import ArtifactSourceBinding
from gateway_backend.capabilities.storage_projection import (
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    build_import_projection_snapshots,
    publish_canonicalization,
    project_storage,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.storage_projection.import_replay import (
    ImportReplayError as ProjectionImportReplayError,
)
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest,
    ProjectionResult,
    WrittenImportPackage,
)
from gateway_backend.capabilities.storage_projection.package import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    PackageError,
    pack_repository_import_entries,
    validate_repository_import_package,
)
from gateway_backend.capabilities.storage_projection.publish import (
    PublicationError,
    open_canonicalization_manifest,
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
        reopened_inputs = _reopen_projection_inputs(projection_inputs)
        reopened_request = ProjectionRequest(
            ruleset=ruleset,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=reopened_inputs,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
        reopened_readers = tuple(item.reader for item in reopened_inputs)
        try:
            try:
                projection_snapshots = build_import_projection_snapshots(reopened_request, projection)
                after_tables = build_import_mutation_snapshots(projection_snapshots)
                schema_sql = render_repository_import_schema_replay_sql(projection.import_input)
                mutation_dml = _render_import_mutation_dml(projection, after_tables)
                replay_sql = schema_sql + mutation_dml
            except (ProjectionImportReplayError, MutationImportReplayError) as exc:
                raise SubmitImportPublicationError(str(exc)) from exc
        finally:
            for reader in reopened_readers:
                try:
                    reader.close()
                except Exception:
                    continue
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
            canonicalization_manifest_digest=publication.manifest_digest.value,
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

    def verify_checkpoint_semantic_binding(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> None:
        manifest_ref = ArtifactRef(
            artifact_id=checkpoint.canonicalization_manifest_ref.artifact_id,
            media_type=checkpoint.canonicalization_manifest_ref.media_type,
            size_bytes=checkpoint.canonicalization_manifest_ref.size_bytes,
            raw_sha256=DigestRef(checkpoint.canonicalization_manifest_ref.raw_sha256),
        )
        try:
            manifest = open_canonicalization_manifest(store, manifest_ref)
        except PublicationError as exc:
            raise SubmitImportPublicationError(str(exc)) from exc
        semantic_digest = compute_manifest_digest(manifest).value
        if semantic_digest != checkpoint.canonicalization_manifest_digest:
            raise SubmitImportPublicationError(
                "checkpoint semantic manifest digest does not match stored manifest"
            )
        package_ref = ArtifactRef(
            artifact_id=checkpoint.backend_import_artifact_ref.artifact_id,
            media_type=checkpoint.backend_import_artifact_ref.media_type,
            size_bytes=checkpoint.backend_import_artifact_ref.size_bytes,
            raw_sha256=DigestRef(checkpoint.backend_import_artifact_ref.raw_sha256),
        )
        try:
            package_payload = store.locate(package_ref)
        except ManifestVerificationError as exc:
            raise SubmitImportPublicationError(str(exc) or "import package is missing or corrupt") from exc
        import_input = validate_repository_import_package(package_payload)
        if import_input.canonicalization_manifest_digest.value != checkpoint.canonicalization_manifest_digest:
            raise SubmitImportPublicationError(
                "package manifest digest does not match checkpoint semantic digest"
            )


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


def _render_import_mutation_dml(
    projection: ProjectionResult,
    snapshots: tuple[MutationTableSnapshot, ...],
) -> bytes:
    manifest = projection.manifest
    if manifest is None:
        raise SubmitImportPublicationError("projection manifest is required")
    empty_manifest = CanonicalizationManifest(
        contract_version=manifest.contract_version,
        storage_projection_version=manifest.storage_projection_version,
        ruleset_id=manifest.ruleset_id,
        ruleset_version=manifest.ruleset_version,
        ruleset_digest=manifest.ruleset_digest,
        source_artifact_digest=manifest.source_artifact_digest,
        tables=(),
        manifest_digest=DigestRef("sha256:" + "0f" * 32),
    )
    binding = MutationProjectionBinding(
        before_storage_projection_digest=manifest.manifest_digest or DigestRef("sha256:" + "00" * 32),
        after_storage_projection_digest=manifest.manifest_digest or DigestRef("sha256:" + "01" * 32),
        before_manifest_digest=empty_manifest.manifest_digest or DigestRef("sha256:" + "02" * 32),
        after_manifest_digest=manifest.manifest_digest or DigestRef("sha256:" + "03" * 32),
        table_ruleset_digest=manifest.ruleset_digest,
    )
    planning_input = MutationPlanningInput(
        mutation_policy=MutationPolicy.REBUILD_ALWAYS,
        projection_binding=binding,
        repository_base=MutationRepositoryBase(
            base_repository_ref_digest=manifest.source_artifact_digest,
        ),
        source_identity=MutationSourceIdentity(
            source_identity_digest=manifest.source_artifact_digest,
        ),
        renderer_capability=REPOSITORY_REPLAY_RENDERER_CAPABILITY,
        threshold_policy=MutationThresholdPolicy(),
    )
    request = MutationPlanningRequest(
        planning_input=planning_input,
        before_manifest=empty_manifest,
        after_manifest=manifest,
        before_tables=(),
        after_tables=snapshots,
        destructive_confirmation_granted=True,
    )
    planned = plan_storage_mutation(request)
    if planned.status is not MutationPlanStatus.READY or planned.change_set_closure is None:
        raise SubmitImportPublicationError("mutation planning failed for repository import replay")
    outcome = render_change_set_replay(planned.change_set_closure)
    if outcome.status != "READY" or outcome.sql_bytes is None:
        raise SubmitImportPublicationError("mutation DML rendering failed")
    return outcome.sql_bytes


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


def _reopen_projection_inputs(
    inputs: tuple[ProjectionTableInput, ...],
) -> tuple[ProjectionTableInput, ...]:
    reopened: list[ProjectionTableInput] = []
    for item in inputs:
        reader = item.reader
        new_reader = reader.reopen() if hasattr(reader, "reopen") else reader
        reopened.append(
            ProjectionTableInput(
                canonical_table=item.canonical_table,
                reader=new_reader,
                source_binding=item.source_binding,
                artifact=item.artifact,
            )
        )
    return tuple(reopened)


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
