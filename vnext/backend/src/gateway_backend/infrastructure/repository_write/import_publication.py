"""RepositoryImportArtifact v1 writer and Submit import publication adapter."""

from __future__ import annotations

from dataclasses import replace

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SnapshotTableBinding,
)
from gateway_backend.application.submission.errors import SubmitImportPublicationError
from gateway_backend.artifacts import ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.mutation_planning import (
    ImportReplayError as MutationImportReplayError,
    build_import_mutation_snapshots,
    render_import_mutation_dml,
)
from gateway_backend.capabilities.snapshot_materialization import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import ArtifactSourceBinding
from gateway_backend.capabilities.storage_projection import (
    MANIFEST_ENTRY_NAME,
    PACKAGE_VERSION,
    ImportReplayError as ProjectionImportReplayError,
    ProjectionInvocationContext,
    ProjectionDiagnostic,
    CanonicalizationManifest,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    ProjectionResult,
    PublicationError,
    STORAGE_PROJECTION_VERSION,
    RepositoryImportArtifactInput,
    REPLAY_SQL_ENTRY_NAME,
    WrittenImportPackage,
    NeverCancel,
    build_import_projection_snapshots,
    open_canonicalization_manifest,
    publish_canonicalization,
    project_storage,
    render_repository_import_schema_replay_sql,
    validate_repository_import_package,
)
from gateway_backend.capabilities.table_rules import TableRulesetSnapshot, migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BackendArtifactRef, BuilderMutationPolicy

__all__ = [
    "MANIFEST_ENTRY_NAME",
    "REPLAY_SQL_ENTRY_NAME",
    "RepositoryImportArtifactError",
    "SubmitImportPublicationAdapter",
    "WrittenImportPackage",
]


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


def _format_projection_diagnostics(prefix: str, diagnostics: tuple[ProjectionDiagnostic, ...]) -> str:
    if not diagnostics:
        return f"{prefix}: FAILED"
    first = diagnostics[0]
    table_suffix = f" (table={first.table_name})" if first.table_name else ""
    message = f"{prefix}: {first.code.value}: {first.message}{table_suffix}"
    if len(diagnostics) > 1:
        also = "; ".join(
            f"{item.code.value}:{item.message}"
            + (f"@{item.table_name}" if item.table_name else "")
            for item in diagnostics[1:3]
        )
        message += f"; also={also}"
        if len(diagnostics) > 3:
            message += f"; diagnostics={len(diagnostics)}"
    return message


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
        if projection_inputs:
            projection_request = ProjectionRequest(
                ruleset=ruleset,
                storage_projection_version=STORAGE_PROJECTION_VERSION,
                tables=projection_inputs,
                context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
            )
            projection = project_storage(projection_request)
        else:
            projection = _empty_projection_from_frozen_manifest(build_input, store=store)
        if projection.status is not ProjectionStatus.COMPLETE:
            raise SubmitImportPublicationError(
                _format_projection_diagnostics(
                    "storage projection failed",
                    projection.diagnostics,
                )
            )
        if projection.manifest is None or projection.import_input is None:
            raise SubmitImportPublicationError("COMPLETE projection is missing manifest or import input")
        frozen_manifest = _open_frozen_manifest(build_input, store=store)
        projection = _assert_projection_identity(
            build_input,
            projection,
            frozen_manifest=frozen_manifest,
        )
        if projection.import_input is None:
            raise SubmitImportPublicationError("frozen projection import input is missing")
        reopened_inputs = _reopen_projection_inputs(projection_inputs)
        reopened_readers = tuple(item.reader for item in reopened_inputs)
        try:
            try:
                if reopened_inputs:
                    reopened_request = ProjectionRequest(
                        ruleset=ruleset,
                        storage_projection_version=STORAGE_PROJECTION_VERSION,
                        tables=reopened_inputs,
                        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
                    )
                    projection_snapshots = build_import_projection_snapshots(
                        reopened_request,
                        projection,
                    )
                    after_tables = build_import_mutation_snapshots(projection_snapshots)
                else:
                    after_tables = ()
                schema_sql = render_repository_import_schema_replay_sql(
                    projection.import_input,
                    removed_tables=build_input.removed_tables,
                )
                mutation_dml = render_import_mutation_dml(
                    projection,
                    after_tables,
                    repository_base_digest=DigestRef(build_input.repository_base_digest),
                    removed_tables=build_input.removed_tables,
                )
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
            raise SubmitImportPublicationError(
                _format_projection_diagnostics(
                    "canonical publication failed",
                    published.diagnostics,
                )
            )
        publication = published.publication
        package_ref = _backend_ref_from_store_ref(publication.package_ref)
        manifest_ref = _backend_ref_from_store_ref(publication.manifest_ref)
        checkpoint = PrepareImportCheckpoint(
            schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
            attempt_id=build_input.submit_attempt_id,
            canonical_table_set_closure_ref=build_input.canonical_table_set_closure_ref.artifact_id,
            canonical_table_set_closure_digest=build_input.canonical_table_set_closure_digest,
            input_canonicalization_manifest_ref=(
                build_input.canonicalization_manifest_ref.artifact_id
            ),
            input_canonicalization_manifest_digest=build_input.canonicalization_manifest_digest,
            expected_parent_commit_id=build_input.expected_parent_commit_id,
            removed_tables=build_input.removed_tables,
            canonicalization_manifest_ref=manifest_ref,
            canonicalization_manifest_digest=publication.manifest_digest.value,
            backend_import_artifact_ref=package_ref,
            package_raw_size=package_ref.size_bytes,
            package_raw_sha256=package_ref.raw_sha256,
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
        if manifest.manifest_digest is None:
            raise SubmitImportPublicationError("stored manifest is missing manifest_digest")
        semantic_digest = manifest.manifest_digest.value
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


def _assert_rebuild_policy(build_input: PrepareImportBuildInput) -> None:
    if build_input.builder_mutation_policy is not BuilderMutationPolicy.REBUILD_ALWAYS:
        raise SubmitImportPublicationError("builder_mutation_policy must be REBUILD_ALWAYS")


def _backend_ref_from_store_ref(ref: ArtifactRef) -> BackendArtifactRef:
    if type(ref) is not ArtifactRef:
        raise SubmitImportPublicationError("published artifact ref is invalid")
    return BackendArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )


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
    projection: ProjectionResult,
    *,
    frozen_manifest: CanonicalizationManifest,
) -> ProjectionResult:
    if type(projection) is not ProjectionResult or projection.manifest is None:
        raise SubmitImportPublicationError("projection manifest is required")
    import_input = projection.import_input
    if import_input is None:
        raise SubmitImportPublicationError("projection import input is required")
    current_manifest = projection.manifest
    expected_ruleset = (
        build_input.ruleset_id,
        build_input.ruleset_version,
        build_input.ruleset_digest,
        build_input.storage_projection_version,
    )
    frozen_ruleset = (
        frozen_manifest.ruleset_id,
        frozen_manifest.ruleset_version,
        frozen_manifest.ruleset_digest.value,
        frozen_manifest.storage_projection_version,
    )
    if expected_ruleset != frozen_ruleset:
        raise SubmitImportPublicationError("frozen canonicalization manifest ruleset identity mismatch")
    if (
        frozen_manifest.manifest_digest is None
        or frozen_manifest.manifest_digest.value != build_input.canonicalization_manifest_digest
    ):
        raise SubmitImportPublicationError("frozen canonicalization manifest digest mismatch")
    if current_manifest.source_artifact_digest.value != build_input.source_artifact_digest:
        raise SubmitImportPublicationError("rebuilt canonical tables do not match the frozen source binding")
    if (
        current_manifest.ruleset_id != frozen_manifest.ruleset_id
        or current_manifest.ruleset_version != frozen_manifest.ruleset_version
        or current_manifest.ruleset_digest != frozen_manifest.ruleset_digest
        or current_manifest.storage_projection_version != frozen_manifest.storage_projection_version
    ):
        raise SubmitImportPublicationError("rebuilt canonical tables use a different ruleset identity")

    frozen_tables = {item.name: item for item in frozen_manifest.tables}
    current_tables = {item.name: item for item in current_manifest.tables}
    projected_tables = {item.canonical_table: item for item in projection.tables}
    import_tables = {item.name: item for item in import_input.tables}
    expected_names = set(frozen_tables)
    if (
        set(current_tables) != expected_names
        or set(projected_tables) != expected_names
        or set(import_tables) != expected_names
    ):
        raise SubmitImportPublicationError("rebuilt canonical table set does not match frozen closure")

    for name, frozen_table in frozen_tables.items():
        current_table = current_tables[name]
        projected_table = projected_tables[name]
        import_table = import_tables[name]
        view = projected_table.storage_view
        if (
            current_table.canonical_row_count != frozen_table.canonical_row_count
            or projected_table.row_count != frozen_table.canonical_row_count
            or current_table.canonical_schema_digest != frozen_table.canonical_schema_digest
            or projected_table.schema_digest != frozen_table.canonical_schema_digest
            or current_table.content_digest != frozen_table.content_digest
            or projected_table.content_digest != frozen_table.content_digest
            or current_table.ordering_digest != frozen_table.ordering_digest
            or projected_table.ordering_digest != frozen_table.ordering_digest
            or current_table.canonical_key_policy is not frozen_table.canonical_key_policy
            or view.canonical_key_policy is not frozen_table.canonical_key_policy
            or current_table.ordered_policy is not frozen_table.ordered_policy
            or view.ordered_policy is not frozen_table.ordered_policy
            or current_table.retained_columns != frozen_table.retained_columns
            or view.retained_columns != frozen_table.retained_columns
            or current_table.structural_columns != frozen_table.structural_columns
            or view.structural_columns != frozen_table.structural_columns
            or current_table.canonical_key_columns != frozen_table.canonical_key_columns
            or view.canonical_key_columns != frozen_table.canonical_key_columns
            or tuple(column.name for column in import_table.columns) != frozen_table.retained_columns
            or import_table.primary_key != frozen_table.canonical_key_columns
            or import_table.row_count != frozen_table.canonical_row_count
        ):
            raise SubmitImportPublicationError(
                f"rebuilt canonical table {name} does not match frozen manifest"
            )

    assert frozen_manifest.manifest_digest is not None
    return replace(
        projection,
        manifest=frozen_manifest,
        import_input=replace(
            import_input,
            canonicalization_manifest_digest=frozen_manifest.manifest_digest,
        ),
    )


def _open_frozen_manifest(
    build_input: PrepareImportBuildInput,
    *,
    store: ArtifactStorePort,
) -> CanonicalizationManifest:
    try:
        return open_canonicalization_manifest(store, build_input.canonicalization_manifest_ref)
    except PublicationError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc


def _empty_projection_from_frozen_manifest(
    build_input: PrepareImportBuildInput,
    *,
    store: ArtifactStorePort,
) -> ProjectionResult:
    try:
        manifest = open_canonicalization_manifest(
            store,
            build_input.canonicalization_manifest_ref,
        )
    except PublicationError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc
    if manifest.manifest_digest is None:
        raise SubmitImportPublicationError("frozen canonicalization manifest is missing its digest")
    if manifest.manifest_digest.value != build_input.canonicalization_manifest_digest:
        raise SubmitImportPublicationError("frozen canonicalization manifest digest mismatch")
    if manifest.source_artifact_digest.value != build_input.source_artifact_digest:
        raise SubmitImportPublicationError("source_artifact_digest does not match frozen manifest")
    if manifest.tables:
        raise SubmitImportPublicationError("empty canonical closure has a non-empty manifest")
    return ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=(),
        manifest=manifest,
        import_input=RepositoryImportArtifactInput(
            package_version=PACKAGE_VERSION,
            canonicalization_manifest_digest=manifest.manifest_digest,
            tables=(),
        ),
    )


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
        if table.descriptor.table_name != binding.table_name:
            raise SubmitImportPublicationError("snapshot table name does not match frozen closure")
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
