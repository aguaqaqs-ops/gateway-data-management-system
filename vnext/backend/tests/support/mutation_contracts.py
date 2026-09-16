"""Helpers for mutation contract and planning tests."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.mutation_planning._digest import row_digest_from_image
from gateway_backend.capabilities.mutation_planning._repository_replay_renderer import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    CANONICAL_ENCODING_VERSION,
    CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
    CHANGE_SET_MANIFEST_CONTRACT_VERSION,
    MUTATION_CONTRACT_VERSION,
    RENDERER_CAPABILITY_CONTRACT_VERSION,
    CanonicalStorageKey,
    ChangeSetArtifact,
    ChangeSetClosure,
    ChangeSetManifest,
    ChangeSetMutation,
    MutationKeyedRow,
    MutationPlanningInput,
    MutationPlanningRequest,
    MutationPolicy,
    MutationProjectionBinding,
    MutationRepositoryBase,
    MutationSourceIdentity,
    MutationTableSnapshot,
    MutationTargetKind,
    MutationThresholdPolicy,
    PersistedRowImage,
    RendererCapabilityDeclaration,
    RowMutationOperation,
    TableMutationKind,
    TableMutationSummary,
    compute_change_set_digest,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    STORAGE_PROJECTION_VERSION,
)
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_ID,
    RULESET_VERSION,
    CanonicalKeyPolicy,
    OrderedPolicy,
    StorageRuleView,
)

_DIGEST_A = DigestRef("sha256:" + "aa" * 32)
_DIGEST_B = DigestRef("sha256:" + "bb" * 32)
_DIGEST_C = DigestRef("sha256:" + "cc" * 32)
_DIGEST_D = DigestRef("sha256:" + "dd" * 32)
_DIGEST_E = DigestRef("sha256:" + "ee" * 32)
_SCHEMA_DIGEST = DigestRef("sha256:" + "11" * 32)
_CONTENT_DIGEST = DigestRef("sha256:" + "22" * 32)


def digest(fill: str) -> DigestRef:
    return DigestRef("sha256:" + fill * 32)


def int_cell(value: str) -> dict[str, object]:
    return {"kind": "signed-integer", "decimal": value}


def renderer_capability(
    *,
    target_kind: MutationTargetKind = MutationTargetKind.CANONICAL_REPOSITORY_REPLAY,
) -> RendererCapabilityDeclaration:
    if target_kind is MutationTargetKind.CANONICAL_REPOSITORY_REPLAY:
        return REPOSITORY_REPLAY_RENDERER_CAPABILITY
    return RendererCapabilityDeclaration(
        target_kind=target_kind,
        capability_version="v1",
        capability_digest=DigestRef("sha256:" + "ff" * 32),
        capability_contract_version=RENDERER_CAPABILITY_CONTRACT_VERSION,
    )


def projection_binding(
    *,
    before_manifest: DigestRef | None = None,
    after_manifest: DigestRef | None = None,
) -> MutationProjectionBinding:
    return MutationProjectionBinding(
        before_storage_projection_digest=_DIGEST_A,
        after_storage_projection_digest=_DIGEST_B,
        before_manifest_digest=before_manifest or _DIGEST_C,
        after_manifest_digest=after_manifest or _DIGEST_D,
        table_ruleset_digest=_DIGEST_E,
    )


def planning_input(
    *,
    policy: MutationPolicy = MutationPolicy.REBUILD_ALWAYS,
    renderer: RendererCapabilityDeclaration | None = None,
    binding: MutationProjectionBinding | None = None,
) -> MutationPlanningInput:
    return MutationPlanningInput(
        mutation_policy=policy,
        projection_binding=binding or projection_binding(),
        repository_base=MutationRepositoryBase(base_repository_ref_digest=_DIGEST_A),
        source_identity=MutationSourceIdentity(source_identity_digest=_DIGEST_B),
        renderer_capability=renderer or renderer_capability(),
        threshold_policy=MutationThresholdPolicy(),
        mutation_contract_version=MUTATION_CONTRACT_VERSION,
        canonical_encoding_version=CANONICAL_ENCODING_VERSION,
    )


def storage_view(*, table: str = "orders") -> StorageRuleView:
    return StorageRuleView(
        canonical_table=table,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        retained_columns=("board", "link_no", "status"),
        canonical_key_columns=("board", "link_no"),
        dropped_columns=(),
        structural_columns=(),
    )


def manifest_table(
    *,
    table: str = "orders",
    row_count: int = 0,
    schema_digest: DigestRef | None = _SCHEMA_DIGEST,
    content_digest: DigestRef | None = _CONTENT_DIGEST,
) -> CanonicalizationManifestTable:
    return CanonicalizationManifestTable(
        name=table,
        source_row_count=row_count,
        canonical_row_count=row_count,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        retained_columns=("board", "link_no", "status"),
        structural_columns=(),
        dropped_columns=(),
        canonical_key_columns=("board", "link_no"),
        canonical_schema_digest=schema_digest,
        content_digest=content_digest,
    )


def manifest(
    *,
    tables: tuple[CanonicalizationManifestTable, ...] = (),
    manifest_digest: DigestRef | None = None,
) -> CanonicalizationManifest:
    digest_value = manifest_digest or raw_blob_digest(f"manifest:{tables!r}".encode())
    return CanonicalizationManifest(
        contract_version=CANONICALIZATION_MANIFEST_CONTRACT,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=RULESET_ID,
        ruleset_version=RULESET_VERSION,
        ruleset_digest=_DIGEST_E,
        source_artifact_digest=_DIGEST_A,
        tables=tables,
        manifest_digest=digest_value,
    )


def storage_key(*, board: str = "1", link_no: str = "2") -> CanonicalStorageKey:
    return CanonicalStorageKey(
        columns=(
            ("board", int_cell(board)),
            ("link_no", int_cell(link_no)),
        )
    )


def row_image(*, board: str = "1", link_no: str = "2", status: str = "9") -> PersistedRowImage:
    return PersistedRowImage(
        columns=(
            ("board", int_cell(board)),
            ("link_no", int_cell(link_no)),
            ("status", int_cell(status)),
        )
    )


def keyed_row(
    *,
    board: str = "1",
    link_no: str = "2",
    status: str = "9",
) -> MutationKeyedRow:
    image = row_image(board=board, link_no=link_no, status=status)
    return MutationKeyedRow(
        key=storage_key(board=board, link_no=link_no),
        image=image,
        row_digest=row_digest_from_image(
            image,
            retained_columns=("board", "link_no", "status"),
        ),
    )


def table_snapshot(
    *,
    table: str = "orders",
    rows: tuple[MutationKeyedRow, ...] = (),
    schema_digest: DigestRef | None = _SCHEMA_DIGEST,
    content_digest: DigestRef | None = _CONTENT_DIGEST,
) -> MutationTableSnapshot:
    return MutationTableSnapshot(
        manifest_table=manifest_table(
            table=table,
            row_count=len(rows),
            schema_digest=schema_digest,
            content_digest=content_digest,
        ),
        storage_view=storage_view(table=table),
        rows=rows,
    )


def planning_request(
    *,
    policy: MutationPolicy = MutationPolicy.REBUILD_ALWAYS,
    before_tables: tuple[MutationTableSnapshot, ...] = (),
    after_tables: tuple[MutationTableSnapshot, ...] = (),
    destructive_confirmation_granted: bool = False,
) -> MutationPlanningRequest:
    before_manifest = manifest(tables=tuple(item.manifest_table for item in before_tables))
    after_manifest = manifest(tables=tuple(item.manifest_table for item in after_tables))
    binding = projection_binding(
        before_manifest=before_manifest.manifest_digest,
        after_manifest=after_manifest.manifest_digest,
    )
    return MutationPlanningRequest(
        planning_input=planning_input(policy=policy, binding=binding),
        before_manifest=before_manifest,
        after_manifest=after_manifest,
        before_tables=before_tables,
        after_tables=after_tables,
        destructive_confirmation_granted=destructive_confirmation_granted,
    )


def table_summary(
    *,
    table: str = "orders",
    operation: TableMutationKind = TableMutationKind.PATCH_DML,
) -> TableMutationSummary:
    return TableMutationSummary(
        canonical_table=table,
        operation=operation,
        changed_row_count=1,
        before_row_count=10,
        after_row_count=10,
    )


def delete_mutation(
    *,
    table: str = "orders",
    board: str = "1",
    link_no: str = "2",
) -> ChangeSetMutation:
    return ChangeSetMutation(
        canonical_table=table,
        operation=RowMutationOperation.DELETE,
        canonical_storage_key=storage_key(board=board, link_no=link_no),
        before_row_digest=raw_blob_digest(f"before:{board}:{link_no}".encode()),
    )


def insert_mutation(
    *,
    table: str = "orders",
    board: str = "3",
    link_no: str = "4",
) -> ChangeSetMutation:
    return ChangeSetMutation(
        canonical_table=table,
        operation=RowMutationOperation.INSERT,
        canonical_storage_key=storage_key(board=board, link_no=link_no),
        after_image=row_image(board=board, link_no=link_no),
    )


def change_set_manifest(
    *,
    summaries: tuple[TableMutationSummary, ...] = (),
    mutations: tuple[ChangeSetMutation, ...] = (),
    planning: MutationPlanningInput | None = None,
) -> ChangeSetManifest:
    request = planning or planning_input()
    binding = request.projection_binding
    change_set_digest = compute_change_set_digest(mutations)
    renderer = request.renderer_capability
    return ChangeSetManifest(
        manifest_contract_version=CHANGE_SET_MANIFEST_CONTRACT_VERSION,
        artifact_contract_version=CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
        mutation_contract_version=MUTATION_CONTRACT_VERSION,
        canonical_encoding_version=CANONICAL_ENCODING_VERSION,
        source_identity_digest=request.source_identity.source_identity_digest,
        base_repository_ref_digest=request.repository_base.base_repository_ref_digest,
        target_identity=renderer,
        storage_projection_digest=binding,
        table_ruleset_digest=binding.table_ruleset_digest,
        mutation_policy=request.mutation_policy,
        threshold_policy=request.threshold_policy,
        table_summaries=summaries,
        change_set_digest=change_set_digest,
        renderer_capability=renderer,
    )


def change_set_artifact(
    *,
    summaries: tuple[TableMutationSummary, ...] = (),
    mutations: tuple[ChangeSetMutation, ...] = (),
) -> ChangeSetArtifact:
    return ChangeSetArtifact(
        manifest=change_set_manifest(summaries=summaries, mutations=mutations),
        mutations=mutations,
    )


def change_set_closure(
    *,
    summaries: tuple[TableMutationSummary, ...] = (),
    mutations: tuple[ChangeSetMutation, ...] = (),
) -> ChangeSetClosure:
    artifact = change_set_artifact(summaries=summaries, mutations=mutations)
    return ChangeSetClosure(manifest=artifact.manifest, mutations=artifact.mutations)
