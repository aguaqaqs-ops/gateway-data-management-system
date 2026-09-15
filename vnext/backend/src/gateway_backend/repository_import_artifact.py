"""RepositoryImportArtifact v1 writer and Submit import publication adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from gateway_shared_kernel import (
    DigestRef,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
    raw_blob_digest,
)

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
from gateway_backend.capabilities.mutation_planning._digest import row_digest_from_image
from gateway_backend.capabilities.mutation_planning._dolt_renderer import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
    render_change_set_replay,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    CanonicalStorageKey,
    MutationKeyedRow,
    MutationPlanStatus,
    MutationPlanningInput,
    MutationPlanningRequest,
    MutationPolicy,
    MutationProjectionBinding,
    MutationRepositoryBase,
    MutationSourceIdentity,
    MutationTableSnapshot,
    MutationThresholdPolicy,
    PersistedRowImage,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.mutation_planning import plan_storage_mutation
from gateway_backend.capabilities.snapshot_materialization import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    SnapshotColumnDescriptor,
)
from gateway_backend.capabilities.storage_projection import (
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    publish_canonicalization,
    project_storage,
)
from gateway_backend.capabilities.storage_projection.contracts import WrittenImportPackage
from gateway_backend.capabilities.storage_projection.package import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    PackageError,
    pack_repository_import_entries,
)
from gateway_backend.capabilities.table_access.contracts import SourceCell, SourceRow
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
        captured_inputs = _capture_projection_inputs(projection_inputs)
        projection = project_storage(
            ProjectionRequest(
                ruleset=ruleset,
                storage_projection_version=STORAGE_PROJECTION_VERSION,
                tables=projection_inputs,
                context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
            )
        )
        if projection.status is not ProjectionStatus.COMPLETE:
            code = projection.diagnostics[0].code.value if projection.diagnostics else "FAILED"
            raise SubmitImportPublicationError(f"storage projection failed: {code}")
        if projection.manifest is None or projection.import_input is None:
            raise SubmitImportPublicationError("COMPLETE projection is missing manifest or import input")
        after_tables = _mutation_snapshots_from_captured(captured_inputs, projection)
        replay_sql = _render_rebuild_replay_sql(projection, after_tables=after_tables, store=store)
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
        backend_ref = backend_artifact_ref_from_store_ref(publication.package_ref)
        checkpoint = PrepareImportCheckpoint(
            schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
            attempt_id=build_input.submit_attempt_id,
            canonicalization_manifest_ref=publication.manifest_ref.artifact_id,
            canonicalization_manifest_digest=publication.manifest_digest.value,
            backend_import_artifact_ref=backend_ref,
            package_raw_size=backend_ref.size_bytes,
            package_raw_sha256=backend_ref.raw_sha256,
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


def _render_rebuild_replay_sql(
    projection: ProjectionResult,
    *,
    after_tables: tuple[MutationTableSnapshot, ...],
    store: ArtifactStorePort,
) -> bytes:
    assert projection.manifest is not None
    before_manifest = _empty_manifest(projection.manifest)
    binding = MutationProjectionBinding(
        before_storage_projection_digest=DigestRef("sha256:" + "00" * 32),
        after_storage_projection_digest=DigestRef("sha256:" + "01" * 32),
        before_manifest_digest=before_manifest.manifest_digest or DigestRef("sha256:" + "02" * 32),
        after_manifest_digest=projection.manifest.manifest_digest or DigestRef("sha256:" + "03" * 32),
        table_ruleset_digest=projection.manifest.ruleset_digest,
    )
    planning_input = MutationPlanningInput(
        mutation_policy=MutationPolicy.REBUILD_ALWAYS,
        projection_binding=binding,
        repository_base=MutationRepositoryBase(
            base_repository_ref_digest=projection.manifest.source_artifact_digest,
        ),
        source_identity=MutationSourceIdentity(
            source_identity_digest=projection.manifest.source_artifact_digest,
        ),
        renderer_capability=REPOSITORY_REPLAY_RENDERER_CAPABILITY,
        threshold_policy=MutationThresholdPolicy(),
    )
    request = MutationPlanningRequest(
        planning_input=planning_input,
        before_manifest=before_manifest,
        after_manifest=projection.manifest,
        before_tables=(),
        after_tables=after_tables,
        destructive_confirmation_granted=True,
    )
    result = plan_storage_mutation(request, artifact_store=store)
    if result.status is not MutationPlanStatus.READY or result.change_set_closure is None:
        raise SubmitImportPublicationError("mutation planning failed for REBUILD_ALWAYS")
    outcome = render_change_set_replay(result.change_set_closure)
    if outcome.status != "READY" or outcome.sql_bytes is None:
        raise SubmitImportPublicationError("replay SQL rendering failed")
    return outcome.sql_bytes


def _empty_manifest(template: CanonicalizationManifest) -> CanonicalizationManifest:
    return CanonicalizationManifest(
        contract_version=template.contract_version,
        storage_projection_version=template.storage_projection_version,
        ruleset_id=template.ruleset_id,
        ruleset_version=template.ruleset_version,
        ruleset_digest=template.ruleset_digest,
        source_artifact_digest=template.source_artifact_digest,
        tables=(),
        manifest_digest=DigestRef("sha256:" + "0f" * 32),
    )


def _capture_projection_inputs(
    projection_inputs: tuple[ProjectionTableInput, ...],
) -> tuple[tuple[ProjectionTableInput, tuple[SourceRow, ...]], ...]:
    captured: list[tuple[ProjectionTableInput, tuple[SourceRow, ...]]] = []
    for item in projection_inputs:
        reader = item.reader.reopen() if hasattr(item.reader, "reopen") else item.reader
        try:
            captured.append((item, tuple(reader.iter_rows())))
        finally:
            reader.close()
    return tuple(captured)


def _mutation_snapshots_from_captured(
    captured_inputs: tuple[tuple[ProjectionTableInput, tuple[SourceRow, ...]], ...],
    projection: ProjectionResult,
) -> tuple[MutationTableSnapshot, ...]:
    assert projection.manifest is not None
    manifest_by_name = {table.name: table for table in projection.manifest.tables}
    projected_by_name = {table.canonical_table: table for table in projection.tables}
    snapshots: list[MutationTableSnapshot] = []
    for item, source_rows in captured_inputs:
        manifest_table = manifest_by_name[item.canonical_table]
        projected = projected_by_name[item.canonical_table]
        rows = _rows_from_source_rows(
            source_rows,
            manifest_table,
            item.source_binding.descriptor.columns,
        )
        snapshots.append(
            MutationTableSnapshot(
                manifest_table=manifest_table,
                storage_view=projected.storage_view,
                rows=rows,
            )
        )
    return tuple(snapshots)


def _rows_from_source_rows(
    source_rows: tuple[SourceRow, ...],
    manifest_table: CanonicalizationManifestTable,
    columns: tuple[SnapshotColumnDescriptor, ...],
) -> tuple[MutationKeyedRow, ...]:
    retained = manifest_table.retained_columns
    key_columns = manifest_table.canonical_key_columns
    keyed_rows: list[MutationKeyedRow] = []
    for source_row in source_rows:
        image_columns = _image_columns(source_row, retained, columns)
        image = PersistedRowImage(columns=image_columns)
        key_pairs = tuple(
            (column, dict(image_columns[index][1]))
            for index, column in enumerate(retained)
            if column in key_columns
        )
        keyed_rows.append(
            MutationKeyedRow(
                key=CanonicalStorageKey(columns=key_pairs),
                image=image,
                row_digest=row_digest_from_image(image, retained_columns=retained),
            )
        )
    return tuple(keyed_rows)


def _image_columns(
    source_row: SourceRow,
    retained: tuple[str, ...],
    columns: tuple[SnapshotColumnDescriptor, ...],
) -> tuple[tuple[str, dict[str, object]], ...]:
    if len(source_row) != len(columns):
        raise SubmitImportPublicationError("snapshot row shape mismatch")
    pairs: list[tuple[str, dict[str, object]]] = []
    for descriptor, cell in zip(columns, source_row, strict=True):
        if descriptor.name not in retained:
            continue
        pairs.append((descriptor.name, _canonical_cell(cell)))
    return tuple(pairs)


def _canonical_cell(cell: SourceCell) -> dict[str, object]:
    if isinstance(cell, NullScalar):
        return {"kind": "null"}
    if isinstance(cell, SignedIntegerScalar):
        return {"kind": "signed-integer", "decimal": cell.decimal}
    if isinstance(cell, UnsignedIntegerScalar):
        return {"kind": "unsigned-integer", "decimal": cell.decimal}
    if isinstance(cell, StringScalar):
        return {"kind": "string", "text": cell.text}
    raise SubmitImportPublicationError("unsupported snapshot cell for mutation replay")
