"""Public import mutation replay materialization for RepositoryImportArtifact."""

from __future__ import annotations

from dataclasses import replace

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
    ChangeSetClosure,
    MutationKeyedRow,
    MutationPlanStatus,
    MutationPlanningInput,
    MutationPlanningRequest,
    MutationPolicy,
    MutationProjectionBinding,
    MutationRepositoryBase,
    MutationPlanningResult,
    MutationSourceIdentity,
    MutationTableSnapshot,
    MutationThresholdPolicy,
    PersistedRowImage,
    RowMutationOperation,
    compute_change_set_digest,
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
        keyed_rows.sort(
            key=lambda item: (key_bytes_for_ordering(item.key), item.row_digest.value)
        )
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
    before_manifest: CanonicalizationManifest | None = None,
    before_snapshots: tuple[MutationTableSnapshot, ...] = (),
    mutation_policy: MutationPolicy = MutationPolicy.REBUILD_ALWAYS,
    rebuild_tables: tuple[str, ...] = (),
) -> bytes:
    if type(removed_tables) is not tuple:
        raise ImportReplayError("removed_tables must be a tuple")
    if any(type(name) is not str or not name for name in removed_tables):
        raise ImportReplayError("removed_tables must contain non-empty table names")
    if removed_tables != tuple(sorted(set(removed_tables), key=lambda name: name.encode("utf-8"))):
        raise ImportReplayError("removed_tables must contain sorted unique table names")
    manifest = result.manifest
    if manifest is None or manifest.manifest_digest is None:
        raise ImportReplayError("projection manifest is required")
    if rebuild_tables != tuple(sorted(set(rebuild_tables), key=lambda name: name.encode("utf-8"))):
        raise ImportReplayError("rebuild_tables must contain sorted unique table names")
    before = before_manifest
    if before is None:
        before = CanonicalizationManifest(
            contract_version=manifest.contract_version,
            storage_projection_version=manifest.storage_projection_version,
            ruleset_id=manifest.ruleset_id,
            ruleset_version=manifest.ruleset_version,
            ruleset_digest=manifest.ruleset_digest,
            source_artifact_digest=manifest.source_artifact_digest,
            tables=(),
            manifest_digest=DigestRef("sha256:" + "0f" * 32),
        )
    planned = plan_import_mutation(
        result,
        snapshots,
        repository_base_digest=repository_base_digest,
        before_manifest=before,
        before_snapshots=before_snapshots,
        mutation_policy=mutation_policy,
    )
    if planned.status is MutationPlanStatus.NOOP:
        if snapshots or before_snapshots:
            raise ImportReplayError("mutation planning failed for repository import replay")
        return b""
    if planned.status is not MutationPlanStatus.READY or planned.change_set_closure is None:
        raise ImportReplayError("mutation planning failed for repository import replay")
    return render_planned_import_mutation_dml(planned, rebuild_tables=rebuild_tables)


def render_planned_import_mutation_dml(
    planned: MutationPlanningResult,
    *,
    rebuild_tables: tuple[str, ...] = (),
) -> bytes:
    if type(rebuild_tables) is not tuple or rebuild_tables != tuple(
        sorted(set(rebuild_tables), key=lambda name: name.encode("utf-8"))
    ):
        raise ImportReplayError("rebuild_tables must contain sorted unique table names")
    if planned.status is MutationPlanStatus.NOOP:
        return b""
    if planned.status is not MutationPlanStatus.READY or planned.change_set_closure is None:
        raise ImportReplayError("mutation planning failed for repository import replay")
    closure = _omit_rebuild_deletes(planned.change_set_closure, set(rebuild_tables))
    outcome = render_change_set_replay(closure)
    if outcome.status != "READY" or outcome.sql_bytes is None:
        raise ImportReplayError("mutation DML rendering failed")
    return outcome.sql_bytes


def plan_import_mutation(
    result: ProjectionResult,
    after_snapshots: tuple[MutationTableSnapshot, ...],
    *,
    repository_base_digest: DigestRef,
    before_manifest: CanonicalizationManifest,
    before_snapshots: tuple[MutationTableSnapshot, ...] = (),
    mutation_policy: MutationPolicy = MutationPolicy.ADAPTIVE_PATCH,
) -> MutationPlanningResult:
    manifest = result.manifest
    if manifest is None or manifest.manifest_digest is None:
        raise ImportReplayError("projection manifest is required")
    if before_manifest.manifest_digest is None:
        raise ImportReplayError("parent manifest digest is required")
    if type(mutation_policy) is not MutationPolicy:
        raise ImportReplayError("mutation_policy is invalid")
    binding = MutationProjectionBinding(
        before_storage_projection_digest=before_manifest.manifest_digest,
        after_storage_projection_digest=manifest.manifest_digest,
        before_manifest_digest=before_manifest.manifest_digest,
        after_manifest_digest=manifest.manifest_digest,
        table_ruleset_digest=manifest.ruleset_digest,
    )
    planning_input = MutationPlanningInput(
        mutation_policy=mutation_policy,
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
        before_manifest=before_manifest,
        after_manifest=manifest,
        before_tables=before_snapshots,
        after_tables=after_snapshots,
        destructive_confirmation_granted=True,
    )
    return plan_storage_mutation(request)


def _omit_rebuild_deletes(
    closure: ChangeSetClosure,
    rebuild_tables: set[str],
) -> ChangeSetClosure:
    if not rebuild_tables:
        return closure
    mutations = tuple(
        mutation
        for mutation in closure.mutations
        if not (
            mutation.canonical_table in rebuild_tables
            and mutation.operation is RowMutationOperation.DELETE
        )
    )
    if mutations == closure.mutations:
        return closure
    manifest = replace(closure.manifest, change_set_digest=compute_change_set_digest(mutations))
    return ChangeSetClosure(manifest=manifest, mutations=mutations)
