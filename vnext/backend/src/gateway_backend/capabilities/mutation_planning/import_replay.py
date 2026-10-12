"""Public import mutation replay materialization for RepositoryImportArtifact."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.mutation_planning._digest import (
    key_bytes_for_ordering,
    row_digest_from_image,
)
from gateway_backend.capabilities.mutation_planning._planner import plan_storage_mutation
from gateway_backend.capabilities.mutation_planning._repository_replay_renderer import (
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
    ImportReplayTableSnapshot,
    ProjectionResult,
)


class ImportReplayError(ValueError):
    """Raised when snapshot import replay materialization fails."""


def build_import_mutation_snapshots(
    projection_snapshots: tuple[ImportReplayTableSnapshot, ...],
) -> tuple[MutationTableSnapshot, ...]:
    snapshots: list[MutationTableSnapshot] = []
    for projection_snapshot in projection_snapshots:
        retained = projection_snapshot.manifest_table.retained_columns
        keyed_rows: list[MutationKeyedRow] = []
        for row in projection_snapshot.rows:
            image = PersistedRowImage(columns=row.image_columns)
            keyed_rows.append(
                MutationKeyedRow(
                    key=CanonicalStorageKey(columns=row.key_columns),
                    image=image,
                    row_digest=row_digest_from_image(image, retained_columns=retained),
                )
            )
        keyed_rows.sort(key=lambda item: key_bytes_for_ordering(item.key))
        snapshots.append(
            MutationTableSnapshot(
                manifest_table=projection_snapshot.manifest_table,
                storage_view=projection_snapshot.storage_view,
                rows=tuple(keyed_rows),
            )
        )
    return tuple(snapshots)


def render_import_mutation_dml(
    result: ProjectionResult,
    snapshots: tuple[MutationTableSnapshot, ...],
    *,
    repository_base_digest: DigestRef,
    removed_tables: tuple[str, ...],
) -> bytes:
    if type(removed_tables) is not tuple:
        raise ImportReplayError("removed_tables must be a tuple")
    if any(type(name) is not str or not name for name in removed_tables):
        raise ImportReplayError("removed_tables must contain non-empty table names")
    if removed_tables != tuple(sorted(set(removed_tables), key=lambda name: name.encode("utf-8"))):
        raise ImportReplayError("removed_tables must contain sorted unique table names")
    manifest = result.manifest
    if manifest is None:
        raise ImportReplayError("projection manifest is required")
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
            base_repository_ref_digest=repository_base_digest,
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
    if planned.status is MutationPlanStatus.NOOP:
        if manifest.tables or snapshots or not removed_tables:
            raise ImportReplayError("mutation planning failed for repository import replay")
        return b""
    if planned.status is not MutationPlanStatus.READY or planned.change_set_closure is None:
        raise ImportReplayError("mutation planning failed for repository import replay")
    outcome = render_change_set_replay(planned.change_set_closure)
    if outcome.status != "READY" or outcome.sql_bytes is None:
        raise ImportReplayError("mutation DML rendering failed")
    return outcome.sql_bytes
