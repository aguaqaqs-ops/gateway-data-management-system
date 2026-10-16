"""Submit import builder publication and checkpoint reuse tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
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
    derive_removed_tables,
    resolve_canonical_snapshot_bindings,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.application.submission.errors import PrepareCheckpointPayloadBindingError
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    NeverCancel,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionTableInput,
    ProjectionStatus,
    STORAGE_PROJECTION_VERSION,
    durable_manifest_bytes,
    project_canonical_table_set,
    project_storage,
)
from gateway_backend.capabilities.snapshot_materialization import materialize_projected_snapshot
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from gateway_backend.capabilities.storage_projection._ordered import GID_PSEUDO_MIN
from gateway_backend.capabilities.storage_projection.package import (
    unpack_repository_import_entries,
    validate_repository_import_package,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.infrastructure.repository_write.import_publication import (
    SubmitImportPublicationAdapter,
    _open_projection_inputs,
)
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


def _project_inputs(inputs: tuple[ProjectionTableInput, ...]) -> ProjectionResult:
    ruleset = migrated_table_ruleset_snapshot()
    projection_inputs = tuple(
        ProjectionTableInput(
            canonical_table=item.canonical_table,
            reader=item.reader.reopen() if hasattr(item.reader, "reopen") else item.reader,
            source_binding=item.source_binding,
            artifact=item.artifact,
            canonicalized_input=item.canonicalized_input,
        )
        for item in inputs
    )
    projection = project_storage(
        ProjectionRequest(
            ruleset=ruleset,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            tables=projection_inputs,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
    )
    assert projection.status is ProjectionStatus.COMPLETE
    assert projection.manifest is not None
    assert projection.manifest.manifest_digest is not None
    return projection


def _manifest_digest_for(inputs: tuple[ProjectionTableInput, ...]) -> str:
    projection = _project_inputs(inputs)
    assert projection.manifest is not None
    assert projection.manifest.manifest_digest is not None
    return projection.manifest.manifest_digest.value


def _build_input(
    *,
    store: InMemoryArtifactStore | None = None,
    snapshot_tables: tuple[SnapshotTableBinding, ...] | None = None,
    projection_inputs: tuple[ProjectionTableInput, ...] | None = None,
) -> PrepareImportBuildInput:
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    projection = _project_inputs(projection_inputs or _projection_inputs())
    assert projection.manifest is not None
    assert projection.manifest.manifest_digest is not None
    manifest_payload = durable_manifest_bytes(projection.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="canonicalization-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_payload),
        raw_sha256=raw_blob_digest(manifest_payload),
    )
    if store is not None:
        store.put(manifest_payload, manifest_ref)
    closure_digest = "sha256:" + "a" * 64
    return PrepareImportBuildInput(
        submit_attempt_id="sa-import-1",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        canonical_table_set_closure_ref=ArtifactRef(
            artifact_id="canonical-table-closure",
            media_type="application/jcs",
            size_bytes=1,
            raw_sha256=DigestRef(closure_digest),
        ),
        canonical_table_set_closure_digest=closure_digest,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=projection.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-commit-1",
        removed_tables=(),
        source_artifact_digest=projection.manifest.source_artifact_digest.value,
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
                    table_name="net_cfg",
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
    assert _build_input(
        snapshot_tables=bindings,
        projection_inputs=_projection_inputs(),
    ).snapshot_tables == ()


def test_empty_canonical_state_publishes_parent_table_removal() -> None:
    store = InMemoryArtifactStore()
    materialized = materialize_sql(
        "SET FOREIGN_KEY_CHECKS=0;",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert materialized.status is SnapshotMaterializationStatus.COMPLETE
    assert materialized.table_set is not None
    canonical = project_canonical_table_set(
        materialized.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert canonical.manifest is not None
    assert canonical.manifest.manifest_digest is not None
    manifest_bytes = durable_manifest_bytes(canonical.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="empty-state-removal-manifest",
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
        artifact_id="empty-state-removal-closure",
        media_type="application/jcs",
        size_bytes=len(closure_bytes),
        raw_sha256=raw_blob_digest(closure_bytes),
    )
    store.put(manifest_bytes, manifest_ref)
    store.put(closure_bytes, closure_ref)
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-empty-removal",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=canonical.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-with-old-table",
        removed_tables=("old_table",),
        source_artifact_digest=canonical.manifest.source_artifact_digest.value,
        repository_base_digest=_SNAPSHOT_DIGEST,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=(),
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(build_input=build_input, store=store)
    package = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(package)
    assert "DROP TABLE IF EXISTS `old_table`" in replay_sql
    assert "CREATE TABLE" not in replay_sql
    assert published.checkpoint.removed_tables == ("old_table",)


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


REMOVED_TABLE_CASES = (
    (("net_cfg", "old_config"), ("net_cfg",), ("old_config",)),
    (("net_cfg",), ("net_cfg",), ()),
    (("net_cfg", "old_config"), (), ("net_cfg", "old_config")),
)


@pytest.mark.parametrize(
    ("parent_names", "snapshot_names", "expected_removed"),
    REMOVED_TABLE_CASES,
)
def test_removed_tables_follow_the_complete_canonical_state(
    parent_names: tuple[str, ...],
    snapshot_names: tuple[str, ...],
    expected_removed: tuple[str, ...],
) -> None:
    snapshot_tables = tuple(
        SnapshotTableBinding(
            table_name=name,
            artifact_id=f"snapshot-{name}",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256=_SNAPSHOT_DIGEST,
        )
        for name in snapshot_names
    )
    assert derive_removed_tables(
        parent_table_names=parent_names,
        snapshot_tables=snapshot_tables,
    ) == expected_removed


def test_prepare_uses_frozen_manifest_after_storage_projection_drops_column() -> None:
    store = InMemoryArtifactStore()
    source = materialize_sql(
        "CREATE TABLE com_cfg (`index` INT NOT NULL, `no` INT NOT NULL, `value` VARCHAR(8), PRIMARY KEY (`index`));"
        "INSERT INTO com_cfg VALUES (1, 10, 'a');",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert source.status is SnapshotMaterializationStatus.COMPLETE
    assert source.snapshot is not None
    assert source.table_set is not None
    frozen = project_canonical_table_set(
        source.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert frozen.status is ProjectionStatus.COMPLETE
    assert frozen.manifest is not None
    assert frozen.manifest.manifest_digest is not None
    assert "no" in {column.name for column in frozen.manifest.tables[0].dropped_columns}
    assert "no" not in {column.name for column in frozen.tables[0].descriptor.columns}

    canonical_snapshot = materialize_projected_snapshot(
        source.snapshot,
        frozen.tables,
        artifact_store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    assert canonical_snapshot.status is SnapshotMaterializationStatus.COMPLETE
    assert canonical_snapshot.table_set is not None
    bindings = tuple(
        SnapshotTableBinding(
            table_name=table.descriptor.table_name,
            artifact_id=table.artifact.manifest_ref.artifact_id,
            media_type=table.artifact.manifest_ref.media_type,
            size_bytes=table.artifact.manifest_ref.size_bytes,
            raw_sha256=table.artifact.manifest_ref.raw_sha256.value,
        )
        for table in canonical_snapshot.table_set.tables
        if table.artifact is not None
    )
    assert len(bindings) == 1
    canonical_inputs = _open_projection_inputs(bindings, store=store)
    manifest_payload = durable_manifest_bytes(frozen.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="frozen-com_cfg-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_payload),
        raw_sha256=raw_blob_digest(manifest_payload),
    )
    store.put(manifest_payload, manifest_ref)
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-frozen-dropped-column",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        canonical_table_set_closure_ref=ArtifactRef(
            artifact_id="frozen-com_cfg-closure",
            media_type="application/jcs",
            size_bytes=1,
            raw_sha256=DigestRef("sha256:" + "a" * 64),
        ),
        canonical_table_set_closure_digest="sha256:" + "a" * 64,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=frozen.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-com_cfg",
        removed_tables=(),
        source_artifact_digest=canonical_inputs[0].source_binding.snapshot_digest.value,
        repository_base_digest=_SNAPSHOT_DIGEST,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=bindings,
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=canonical_inputs,
    )
    package = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    package_input = validate_repository_import_package(package)
    assert package_input.canonicalization_manifest_digest == frozen.manifest.manifest_digest
    assert published.checkpoint.canonicalization_manifest_digest == frozen.manifest.manifest_digest.value
    replay_sql = _replay_sql_from_package(package)
    assert "CREATE TABLE `com_cfg`" in replay_sql
    assert "`no`" not in replay_sql


def test_prepare_replays_canonical_ordered_pseudo_gid_snapshot() -> None:
    store = InMemoryArtifactStore()
    source = materialize_sql(
        "CREATE TABLE `b1_n1_iec104_syx_list` ("
        "`gid` INT NULL, `no` INT NOT NULL, `value` VARCHAR(16) NOT NULL, PRIMARY KEY (`no`));"
        "INSERT INTO `b1_n1_iec104_syx_list` VALUES "
        "(NULL, 3, 'blank-last'), (7, 2, 'real'), (NULL, 1, 'blank-first');",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert source.status is SnapshotMaterializationStatus.COMPLETE
    assert source.snapshot is not None
    assert source.table_set is not None
    frozen = project_canonical_table_set(
        source.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert frozen.status is ProjectionStatus.COMPLETE
    assert frozen.manifest is not None
    assert frozen.manifest.manifest_digest is not None
    assert frozen.manifest.tables[0].gid_pseudo_count == 2

    canonical_snapshot = materialize_projected_snapshot(
        source.snapshot,
        frozen.tables,
        artifact_store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    assert canonical_snapshot.status is SnapshotMaterializationStatus.COMPLETE
    assert canonical_snapshot.table_set is not None
    bindings = tuple(
        SnapshotTableBinding(
            table_name=table.descriptor.table_name,
            artifact_id=table.artifact.manifest_ref.artifact_id,
            media_type=table.artifact.manifest_ref.media_type,
            size_bytes=table.artifact.manifest_ref.size_bytes,
            raw_sha256=table.artifact.manifest_ref.raw_sha256.value,
        )
        for table in canonical_snapshot.table_set.tables
        if table.artifact is not None
    )
    assert len(bindings) == 1
    projection_inputs = _open_projection_inputs(bindings, store=store)
    assert projection_inputs[0].canonicalized_input is True

    canonical_table = canonical_snapshot.table_set.tables[0]
    assert canonical_table.artifact is not None
    closure_payload = canonicalize_json_value(
        {
            "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
            "tables": [
                {
                    "table_name": canonical_table.descriptor.table_name,
                    "manifest_ref": artifact_ref_to_dict(canonical_table.artifact.manifest_ref),
                }
            ],
        }
    )
    closure_ref = ArtifactRef(
        artifact_id="ordered-canonical-table-closure",
        media_type="application/jcs",
        size_bytes=len(closure_payload),
        raw_sha256=raw_blob_digest(closure_payload),
    )
    store.put(closure_payload, closure_ref)
    manifest_payload = durable_manifest_bytes(frozen.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="ordered-canonicalization-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_payload),
        raw_sha256=raw_blob_digest(manifest_payload),
    )
    store.put(manifest_payload, manifest_ref)
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-ordered-pseudo-replay",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=frozen.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-ordered",
        removed_tables=(),
        source_artifact_digest=projection_inputs[0].source_binding.snapshot_digest.value,
        repository_base_digest=_SNAPSHOT_DIGEST,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=bindings,
    )

    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=projection_inputs,
    )
    package = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    package_manifest = validate_repository_import_package(package)
    assert package_manifest.canonicalization_manifest_digest == frozen.manifest.manifest_digest
    replay_sql = _replay_sql_from_package(package)
    assert "4000000000" in replay_sql
    assert "4000000001" in replay_sql


def _replay_sql_from_package(payload: bytes) -> str:
    _, replay_sql = unpack_repository_import_entries(payload)
    return replay_sql.decode("utf-8")


def test_rebuild_always_publish_is_deterministic_for_same_inputs() -> None:
    adapter = SubmitImportPublicationAdapter()
    first_store = InMemoryArtifactStore()
    second_store = InMemoryArtifactStore()
    build_input = _build_input(store=first_store)
    second_build_input = _build_input(store=second_store)
    first = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=first_store,
        projection_inputs=_projection_inputs(),
    )
    second = adapter.build_and_publish_from_inputs(
        build_input=second_build_input,
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
        build_input=_build_input(store=store),
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
    projection_inputs = (
        ProjectionTableInput(
            canonical_table="b1_n1_iec104_syx_list",
            reader=reader,
            source_binding=binding,
        ),
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
        projection_inputs=projection_inputs,
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
    projection_inputs = (
        ProjectionTableInput(
            canonical_table="net_cfg",
            reader=reader,
            source_binding=binding,
        ),
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
        projection_inputs=projection_inputs,
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
    projection_inputs = (
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
    )
    published = adapter.build_and_publish_from_inputs(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
        projection_inputs=projection_inputs,
    )
    assert published.checkpoint.backend_import_artifact_ref.artifact_id.startswith("r4-package-")


def test_checkpoint_reuse_read_back_preserves_package_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
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
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
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
        build_input=_build_input(store=store),
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
        table_name=table.descriptor.table_name,
        artifact_id=table.artifact.manifest_ref.artifact_id,
        media_type=table.artifact.manifest_ref.media_type,
        size_bytes=table.artifact.manifest_ref.size_bytes,
        raw_sha256=table.artifact.manifest_ref.raw_sha256.value,
    )
    projection_inputs = _open_projection_inputs((binding,), store=store)
    build_input = _build_input(
        store=store,
        snapshot_tables=(binding,),
        projection_inputs=projection_inputs,
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
        _build_input(store=store),
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
        _build_input(store=store),
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
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
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


@pytest.mark.parametrize(
    "binding_change",
    (
        "closure_ref",
        "closure_digest",
        "manifest_ref",
        "manifest_digest",
        "parent_commit",
        "removed_tables",
    ),
)
def test_reuse_rejects_changed_frozen_prepare_bindings(binding_change: str) -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    if binding_change == "closure_ref":
        changed = replace(
            build_input,
            canonical_table_set_closure_ref=replace(
                build_input.canonical_table_set_closure_ref,
                artifact_id="other-canonical-closure",
            ),
        )
    elif binding_change == "closure_digest":
        changed_digest = "sha256:" + "7" * 64
        changed = replace(
            build_input,
            canonical_table_set_closure_ref=replace(
                build_input.canonical_table_set_closure_ref,
                raw_sha256=DigestRef(changed_digest),
            ),
            canonical_table_set_closure_digest=changed_digest,
        )
    elif binding_change == "manifest_ref":
        changed = replace(
            build_input,
            canonicalization_manifest_ref=replace(
                build_input.canonicalization_manifest_ref,
                artifact_id="other-preview-manifest",
            ),
        )
    elif binding_change == "manifest_digest":
        changed = replace(build_input, canonicalization_manifest_digest="sha256:" + "6" * 64)
    elif binding_change == "parent_commit":
        changed = replace(build_input, expected_parent_commit_id="other-parent")
    else:
        changed = replace(build_input, removed_tables=("removed_table",))
    with pytest.raises(PrepareCheckpointPayloadBindingError):
        reuse_prepare_import_checkpoint(
            build_input=changed,
            checkpoint=published.checkpoint,
            publication=adapter,
            store=store,
        )
