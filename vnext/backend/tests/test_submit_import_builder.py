"""Submit import builder publication and checkpoint reuse tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
    SnapshotTableBinding,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    resolve_canonical_snapshot_bindings,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    durable_manifest_bytes,
    project_canonical_table_set,
)
from gateway_backend.capabilities.storage_projection._ordered import GID_PSEUDO_MIN
from gateway_backend.capabilities.storage_projection.package import unpack_repository_import_entries
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from tests.support.snapshot_materialization import materialize_sql
from tests.support.storage_projection import (
    as_row,
    digest_ref,
    dummy_digest,
    int_cell,
    int_column,
    null_cell,
    set_cell,
    set_column,
    table_input,
    varchar_cell,
    varchar_column,
)

pytestmark = pytest.mark.unit

_NET_CFG_COLUMNS = (
    varchar_column("board"),
    int_column("link_no"),
    int_column("no", nullable=True),
)
_NET_CFG_ROWS = (
    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
    as_row(varchar_cell("eth1"), int_cell(2), int_cell(20)),
)
_SNAPSHOT_DIGEST = dummy_digest().value


def _build_input(*, snapshot_tables: tuple[SnapshotTableBinding, ...] | None = None) -> PrepareImportBuildInput:
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    return PrepareImportBuildInput(
        submit_attempt_id="sa-import-1",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        input_closure_digest="sha256:closure",
        canonical_table_set_closure_ref="canonical-table-closure",
        canonical_table_set_closure_digest="sha256:closure",
        canonicalization_manifest_ref="canonicalization-manifest",
        canonicalization_manifest_digest="sha256:manifest",
        source_artifact_digest=_SNAPSHOT_DIGEST,
        repository_base_digest=_SNAPSHOT_DIGEST,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=(
            snapshot_tables
            if snapshot_tables is not None
            else (
                SnapshotTableBinding(
                    artifact_id="snap-net-cfg",
                    media_type="application/json",
                    size_bytes=1,
                    raw_sha256=_SNAPSHOT_DIGEST,
                ),
            )
        ),
    )


def test_empty_canonical_closure_resolves_without_table_artifacts() -> None:
    store = InMemoryArtifactStore()
    materialized = materialize_sql(
        "SET FOREIGN_KEY_CHECKS=0;",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert materialized.status is SnapshotMaterializationStatus.COMPLETE
    assert materialized.table_set is not None
    assert materialized.table_set.tables == ()
    projection = project_canonical_table_set(
        materialized.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert projection.manifest is not None
    assert projection.manifest.manifest_digest is not None
    manifest_bytes = durable_manifest_bytes(projection.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="empty-canonical-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_bytes),
        raw_sha256=raw_blob_digest(manifest_bytes),
    )
    closure_bytes = canonicalize_json_value(
        {
            "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
            "tables": [],
        }
    )
    closure_ref = ArtifactRef(
        artifact_id="empty-canonical-closure",
        media_type="application/jcs",
        size_bytes=len(closure_bytes),
        raw_sha256=raw_blob_digest(closure_bytes),
    )
    store.put(manifest_bytes, manifest_ref)
    store.put(closure_bytes, closure_ref)

    bindings, refs = resolve_canonical_snapshot_bindings(
        operation_artifact_refs=(closure_ref, manifest_ref),
        canonical_table_set_closure_ref=closure_ref.artifact_id,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref.artifact_id,
        canonicalization_manifest_digest=projection.manifest.manifest_digest.value,
        read_artifact=store.locate,
    )

    assert bindings == ()
    assert refs == (closure_ref, manifest_ref)
    assert _build_input(snapshot_tables=bindings).snapshot_tables == ()


def _projection_inputs() -> tuple[ProjectionTableInput, ...]:
    reader, binding = table_input(
        "net_cfg",
        columns=_NET_CFG_COLUMNS,
        primary_key_columns=("board", "link_no"),
        rows=_NET_CFG_ROWS,
    )
    return (
        ProjectionTableInput(
            canonical_table="net_cfg",
            reader=reader,
            source_binding=binding,
        ),
    )


def _replay_sql_from_package(payload: bytes) -> str:
    _, replay_sql = unpack_repository_import_entries(payload)
    return replay_sql.decode("utf-8")


def test_rebuild_always_publish_is_deterministic_for_same_inputs() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    first_store = InMemoryArtifactStore()
    second_store = InMemoryArtifactStore()
    first = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=first_store,
        projection_inputs=_projection_inputs(),
    )
    second = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=second_store,
        projection_inputs=_projection_inputs(),
    )
    assert first.replay is False
    assert second.replay is False
    assert (
        first.checkpoint.canonicalization_manifest_ref.raw_sha256
        == second.checkpoint.canonicalization_manifest_ref.raw_sha256
    )
    assert (
        first.checkpoint.backend_import_artifact_ref.raw_sha256
        == second.checkpoint.backend_import_artifact_ref.raw_sha256
    )


def test_rebuild_replay_includes_ddl_and_inserts() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(),
        store=store,
        projection_inputs=_projection_inputs(),
    )
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE `net_cfg`" in replay_sql
    assert "INSERT INTO `net_cfg`" in replay_sql
    assert "VALUES ('eth0', 1)" in replay_sql


def test_ordered_blank_gid_replay_matches_projection() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    reader, binding = table_input(
        "b1_n1_iec104_syx_list",
        columns=(
            int_column("gid", nullable=True),
            int_column("no"),
            varchar_column("value"),
        ),
        primary_key_columns=("gid",),
        rows=(
            as_row(int_cell(5), int_cell(1), varchar_cell("y")),
            as_row(null_cell(), int_cell(2), varchar_cell("x")),
        ),
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(),
        store=store,
        projection_inputs=(
            ProjectionTableInput(
                canonical_table="b1_n1_iec104_syx_list",
                reader=reader,
                source_binding=binding,
            ),
        ),
    )
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert f"VALUES ({GID_PSEUDO_MIN}, 2, 'x')" in replay_sql
    assert "VALUES (NULL" not in replay_sql


def test_set_column_input_publishes_successfully() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    reader, binding = table_input(
        "net_cfg",
        columns=(
            varchar_column("board"),
            int_column("link_no"),
            set_column("flags", "SET('a','b')"),
        ),
        primary_key_columns=("board", "link_no"),
        rows=(as_row(varchar_cell("eth0"), int_cell(1), set_cell("a")),),
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(),
        store=store,
        projection_inputs=(
            ProjectionTableInput(
                canonical_table="net_cfg",
                reader=reader,
                source_binding=binding,
            ),
        ),
    )
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert "INSERT INTO `net_cfg`" in replay_sql
    assert "'a'" in replay_sql


def test_skipped_table_does_not_break_publication() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    net_reader, net_binding = table_input(
        "net_cfg",
        columns=_NET_CFG_COLUMNS,
        primary_key_columns=("board", "link_no"),
        rows=_NET_CFG_ROWS,
    )
    skip_reader, skip_binding = table_input(
        "device_model_table",
        columns=(int_column("id"),),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1)),),
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(),
        store=store,
        projection_inputs=(
            ProjectionTableInput(
                canonical_table="net_cfg",
                reader=net_reader,
                source_binding=net_binding,
            ),
            ProjectionTableInput(
                canonical_table="device_model_table",
                reader=skip_reader,
                source_binding=skip_binding,
            ),
        ),
    )
    assert published.checkpoint.backend_import_artifact_ref.artifact_id.startswith("r4-package-")


def test_checkpoint_reuse_read_back_preserves_package_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    reused = reuse_prepare_import_checkpoint(
        build_input=build_input,
        checkpoint=published.checkpoint,
        publication=adapter,
        store=store,
    )
    assert reused.replay is True
    assert (
        reused.checkpoint.backend_import_artifact_ref
        == published.checkpoint.backend_import_artifact_ref
    )
    assert (
        reused.checkpoint.canonicalization_manifest_ref
        == published.checkpoint.canonicalization_manifest_ref
    )
    payload = adapter.read_back_package(checkpoint=reused.checkpoint, store=store)
    assert len(payload) == published.checkpoint.package_raw_size


def test_orphan_bytes_before_checkpoint_do_not_change_published_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    orphan_count = len(store._artifacts)
    second = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    assert len(store._artifacts) > orphan_count
    reused = reuse_prepare_import_checkpoint(
        build_input=build_input,
        checkpoint=published.checkpoint,
        publication=adapter,
        store=store,
    )
    assert (
        reused.checkpoint.backend_import_artifact_ref.raw_sha256
        == published.checkpoint.backend_import_artifact_ref.raw_sha256
    )
    assert (
        second.checkpoint.backend_import_artifact_ref.artifact_id
        != reused.checkpoint.backend_import_artifact_ref.artifact_id
    )


def test_publish_writes_only_manifest_and_package_artifacts() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(),
        store=store,
        projection_inputs=_projection_inputs(),
    )
    artifact_ids = set(store._artifacts)
    assert published.checkpoint.canonicalization_manifest_ref.artifact_id in artifact_ids
    assert published.checkpoint.backend_import_artifact_ref.artifact_id in artifact_ids
    assert not any(artifact_id.startswith("change-set-closure-") for artifact_id in artifact_ids)


def test_build_and_publish_from_pinned_parquet_artifact_succeeds() -> None:
    store = InMemoryArtifactStore()
    sql = (
        "CREATE TABLE `unknown_widget` (`id` INT NOT NULL PRIMARY KEY, `flags` SET('x','y') NOT NULL);"
        "INSERT INTO `unknown_widget` VALUES (1, 'x');"
    )
    result = materialize_sql(
        sql,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    table = result.table_set.tables[0]
    assert table.artifact is not None
    binding = SnapshotTableBinding(
        artifact_id=table.artifact.manifest_ref.artifact_id,
        media_type=table.artifact.manifest_ref.media_type,
        size_bytes=table.artifact.manifest_ref.size_bytes,
        raw_sha256=table.artifact.manifest_ref.raw_sha256.value,
    )
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-import-parquet",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        input_closure_digest="sha256:closure-parquet",
        canonical_table_set_closure_ref="canonical-table-closure-parquet",
        canonical_table_set_closure_digest="sha256:closure-parquet",
        canonicalization_manifest_ref="canonicalization-manifest-parquet",
        canonicalization_manifest_digest="sha256:manifest-parquet",
        source_artifact_digest=table.artifact.manifest.snapshot_digest.value,
        repository_base_digest=table.artifact.manifest.snapshot_digest.value,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=(binding,),
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(build_input=build_input, store=store)
    assert published.replay is False
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert "INSERT INTO `unknown_widget`" in replay_sql


def test_repository_base_digest_may_differ_from_source_artifact_digest() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    build_input = replace(
        _build_input(),
        repository_base_digest=digest_ref("cc").value,
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    assert published.checkpoint.canonicalization_manifest_digest


def test_repository_base_digest_reaches_mutation_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.capabilities.mutation_planning._planner import plan_storage_mutation as real_plan
    from gateway_backend.capabilities.mutation_planning.contracts import MutationPlanningRequest

    captured: list[MutationPlanningRequest] = []

    def _capture(request: MutationPlanningRequest) -> object:
        captured.append(request)
        return real_plan(request)

    monkeypatch.setattr(
        "gateway_backend.capabilities.mutation_planning.import_replay.plan_storage_mutation",
        _capture,
    )
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    source_digest = dummy_digest()
    base_digest = digest_ref("cc")
    build_input = replace(
        _build_input(),
        source_artifact_digest=source_digest.value,
        repository_base_digest=base_digest.value,
    )
    adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    assert captured
    request = captured[0]
    assert request.planning_input.repository_base.base_repository_ref_digest == base_digest
    assert request.planning_input.source_identity.source_identity_digest == source_digest


def test_reuse_rejects_mismatched_semantic_manifest_digest() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    mismatched = replace(
        published.checkpoint,
        canonicalization_manifest_digest=digest_ref("ff").value,
    )
    with pytest.raises(SubmitImportBuilderError, match="semantic manifest digest"):
        reuse_prepare_import_checkpoint(
            build_input=build_input,
            checkpoint=mismatched,
            publication=adapter,
            store=store,
        )


def test_reuse_rejects_mismatched_input_closure_digest() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    mismatched = PrepareImportBuildInput(
        submit_attempt_id=build_input.submit_attempt_id,
        builder_mutation_policy=build_input.builder_mutation_policy,
        input_closure_digest="sha256:other",
        canonical_table_set_closure_ref=build_input.canonical_table_set_closure_ref,
        canonical_table_set_closure_digest="sha256:other",
        canonicalization_manifest_ref=build_input.canonicalization_manifest_ref,
        canonicalization_manifest_digest=build_input.canonicalization_manifest_digest,
        source_artifact_digest=build_input.source_artifact_digest,
        repository_base_digest=build_input.repository_base_digest,
        storage_projection_version=build_input.storage_projection_version,
        ruleset_id=build_input.ruleset_id,
        ruleset_version=build_input.ruleset_version,
        ruleset_digest=build_input.ruleset_digest,
        snapshot_tables=build_input.snapshot_tables,
    )
    with pytest.raises(SubmitImportBuilderError, match="input closure digest"):
        reuse_prepare_import_checkpoint(
            build_input=mismatched,
            checkpoint=published.checkpoint,
            publication=adapter,
            store=store,
        )
