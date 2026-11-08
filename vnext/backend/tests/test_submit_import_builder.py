"""Submit import builder publication and checkpoint reuse tests."""

from __future__ import annotations

from tests.support.native_projection import project_storage, project_canonical_fixture

from dataclasses import replace
from contextlib import contextmanager
from collections.abc import Iterator
from types import SimpleNamespace

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
    ArtifactSourceBinding,
    MaterializationStage,
    MaterializationPolicy,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    Snapshot,
    SnapshotMaterializationStatus,
    SnapshotSourceContext,
    SnapshotTable,
    SnapshotTableSet,
    SourceKind,
    RepositoryColumn,
)
from gateway_backend.application.canonical_metadata.table_access import build_committed_table_access
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    derive_removed_tables,
    resolve_canonical_snapshot_bindings,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.application.submission.errors import PrepareCheckpointPayloadBindingError, SubmitImportPublicationError
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
    open_canonicalization_manifest,
    project_canonical_arrow_table_set,
)
from gateway_backend.capabilities.snapshot_materialization import materialize_canonical_snapshot, open_snapshot_table_artifact
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext, SourceRow
from gateway_backend.capabilities.snapshot_materialization.contracts import GID_PSEUDO_MIN
from gateway_backend.capabilities.storage_projection.package import (
    unpack_repository_import_entries,
    validate_repository_import_package,
)
from gateway_backend.capabilities.table_access.contracts import PARSER_VERSION
from gateway_backend.capabilities.table_rules import TABLE_RULESET_VERSION
from gateway_backend.capabilities.table_rules import (
    TableRulesetSnapshot,
    table_ruleset_document,
    table_ruleset_from_document,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.infrastructure.repository_write.import_publication import (
    SubmitImportPublicationAdapter,
)
from tests.support.snapshot_materialization import materialize_arrow_sql as materialize_sql, snapshot_table_as_arrow
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
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider, catalog_table, make_catalog,
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


def _open_projection_inputs(
    bindings: tuple[SnapshotTableBinding, ...], *, store: InMemoryArtifactStore,
    repository_id: str,
) -> tuple[ProjectionTableInput, ...]:
    """Test setup for projecting already published canonical artifacts."""
    inputs: list[ProjectionTableInput] = []
    for binding in bindings:
        ref = ArtifactRef(binding.artifact_id, binding.media_type, binding.size_bytes,
                          DigestRef(binding.raw_sha256))
        table = open_snapshot_table_artifact(store, ref, repository_id=repository_id,
                                             canonical_required=True)
        assert table.reader is not None and table.artifact is not None
        reader = table.reader.reopen()
        table.reader.close()
        if table.batch_reader is not None:
            table.batch_reader.close()
        inputs.append(ProjectionTableInput(
            canonical_table=binding.table_name, reader=reader,
            source_binding=ArtifactSourceBinding(
                snapshot_digest=table.artifact.manifest.snapshot_digest,
                descriptor=table.descriptor, repository_id=repository_id,
            ), artifact=table.artifact, canonicalized_input=True,
        ))
    return tuple(inputs)


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
    if store is not None and snapshot_tables is None:
        return _frozen_build_input(store, projection_inputs or _projection_inputs())
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
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
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
        repository_id="test-repository",
        parent_manifest=None,
        parent_manifest_digest=None,
        parent_is_initial=True,
        removed_tables=(),
        source_artifact_digest=projection.manifest.source_artifact_digest.value,
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


def _frozen_build_input(
    store: InMemoryArtifactStore,
    raw_inputs: tuple[ProjectionTableInput, ...],
    *,
    ruleset: TableRulesetSnapshot | None = None,
) -> PrepareImportBuildInput:
    if ruleset is None:
        ruleset = migrated_table_ruleset_snapshot()
    source_digest = raw_inputs[0].source_binding.snapshot_digest
    source_context = SnapshotSourceContext(
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        sql_source_digest=source_digest,
    )
    source_snapshot = Snapshot(
        snapshot_id="submit-import-source",
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        parser_version=PARSER_VERSION,
        table_ruleset_version=TABLE_RULESET_VERSION,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        snapshot_materialization_contract_version=SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        materialization_stage=MaterializationStage.FINAL,
        snapshot_digest=source_digest,
        raw_state_digest=source_digest,
        created_at="2025-01-01T00:00:00Z",
        source_context=source_context,
    )
    source_tables = tuple(
        snapshot_table_as_arrow(SnapshotTable(
            descriptor=item.source_binding.descriptor,
            reader=item.reader.reopen(),
            artifact=item.artifact,
        ))
        for item in raw_inputs
    )
    table_set = SnapshotTableSet(
        snapshot_id=source_snapshot.snapshot_id,
        snapshot_digest=source_digest,
        table_ruleset_version=TABLE_RULESET_VERSION,
        tables=source_tables,
    )
    frozen = project_canonical_arrow_table_set(table_set, ruleset)
    for table in source_tables:
        if table.reader is not None:
            table.reader.close()
    assert frozen.status is ProjectionStatus.COMPLETE
    assert frozen.manifest is not None
    assert frozen.manifest.manifest_digest is not None
    try:
        canonical = materialize_canonical_snapshot(
            source_snapshot,
            frozen.tables,
            artifact_store=store,
            context=ParserInvocationContext(NeverCancel()), repository_id="test-repository",
        )
    finally:
        for table in frozen.tables:
            if table.reader is not None:
                table.reader.close()
    assert canonical.status is SnapshotMaterializationStatus.COMPLETE
    assert canonical.snapshot is not None
    assert canonical.table_set is not None

    manifest_payload = durable_manifest_bytes(frozen.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="fixture-canonicalization-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_payload),
        raw_sha256=raw_blob_digest(manifest_payload),
    )
    store.put(manifest_payload, manifest_ref)
    canonical_tables = tuple(
        table for table in canonical.table_set.tables if table.artifact is not None
    )
    closure_payload = canonicalize_json_value(
        {
            "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
            "tables": [
                {
                    "table_name": table.descriptor.table_name,
                    "manifest_ref": artifact_ref_to_dict(table.artifact.manifest_ref),
                }
                for table in canonical_tables
                if table.artifact is not None
            ],
        }
    )
    closure_ref = ArtifactRef(
        artifact_id="fixture-canonical-table-closure",
        media_type="application/jcs",
        size_bytes=len(closure_payload),
        raw_sha256=raw_blob_digest(closure_payload),
    )
    store.put(closure_payload, closure_ref)
    bindings = tuple(
        SnapshotTableBinding(
            table_name=table.descriptor.table_name,
            artifact_id=table.artifact.manifest_ref.artifact_id,
            media_type=table.artifact.manifest_ref.media_type,
            size_bytes=table.artifact.manifest_ref.size_bytes,
            raw_sha256=table.artifact.manifest_ref.raw_sha256.value,
        )
        for table in canonical_tables
        if table.artifact is not None
    )
    return PrepareImportBuildInput(
        submit_attempt_id="sa-import-frozen-fixture",
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=frozen.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-commit-1",
        repository_id="test-repository",
        parent_manifest=None,
        parent_manifest_digest=None,
        parent_is_initial=True,
        removed_tables=(),
        source_artifact_digest=canonical.snapshot.snapshot_digest.value,
        snapshot_tables=bindings,
    )


def _keyed_parent_submit(
    *, fault: str | None = None, ruleset: TableRulesetSnapshot | None = None,
) -> tuple[SubmitImportPublicationAdapter, PrepareImportBuildInput, InMemoryArtifactStore]:
    """Use the real canonical IPC and committed-table owners around a fake Repository source."""
    before_rows = tuple(
        as_row(int_cell(index), varchar_cell(f"value-{index}")) for index in range(100)
    )
    after_rows = tuple(
        as_row(int_cell(index), varchar_cell("new-value" if index == 42 else f"value-{index}"))
        for index in range(100)
    )

    def raw_input(rows: tuple[SourceRow, ...]) -> tuple[ProjectionTableInput, ...]:
        reader, binding = table_input(
            "a_widget", columns=(int_column("id"), varchar_column("value")),
            primary_key_columns=("id",), rows=rows,
        )
        return (ProjectionTableInput("a_widget", reader, binding),)

    before_store = InMemoryArtifactStore()
    before_input = _frozen_build_input(before_store, raw_input(before_rows), ruleset=ruleset)
    parent_manifest = open_canonicalization_manifest(
        before_store, before_input.canonicalization_manifest_ref,
    )
    assert parent_manifest.manifest_digest is not None
    parent_table = open_snapshot_table_artifact(
        before_store,
        ArtifactRef(
            before_input.snapshot_tables[0].artifact_id,
            before_input.snapshot_tables[0].media_type,
            before_input.snapshot_tables[0].size_bytes,
            DigestRef(before_input.snapshot_tables[0].raw_sha256),
        ),
        repository_id="test-repository", canonical_required=True,
    )
    descriptor = parent_table.descriptor
    assert parent_table.reader is not None
    parent_table.reader.close()
    if parent_table.batch_reader is not None:
        parent_table.batch_reader.close()
    columns = tuple(
        RepositoryColumn(
            name=column.name, ordinal=index, scalar_type=column.scalar_type,
            nullable=column.nullable,
        )
        for index, column in enumerate(descriptor.columns)
    )
    catalog = make_catalog(
        (catalog_table("a_widget", columns, primary_key=("id",),
                       row_count=99 if fault == "count" else 100),),
        repository_id="test-repository", ref="parent-commit-1", commit="parent-commit-1",
    )
    source_rows = tuple(
        (index, "wrong-value" if fault == "content" and index == 42 else f"value-{index}")
        for index in range(100)
    )
    provider = FakeRepositoryTableAccessProvider(
        catalog=catalog, rows={"a_widget": source_rows},
        current_commit="other-commit" if fault == "commit" else "parent-commit-1",
    )

    class Index:
        def __init__(self) -> None:
            self.refs: dict[object, ArtifactRef] = {}

        def lookup(self, key: object) -> ArtifactRef | None:
            return self.refs.get(key)

        def register(self, key: object, ref: ArtifactRef) -> None:
            self.refs[key] = ref

        def bind_commit(self, *, repository_id: str, commit_id: str,
                        refs: tuple[ArtifactRef, ...]) -> None:
            del repository_id, commit_id, refs

    index = Index()

    @contextmanager
    def uow() -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(canonical_tables=index)

    committed = build_committed_table_access(
        store=InMemoryArtifactStore(), unit_of_work_factory=uow,
        repository_provider_factory=lambda _repo, _commit: provider,
        repository_id="test-repository",
    )
    after_store = InMemoryArtifactStore()
    after_input = _frozen_build_input(after_store, raw_input(after_rows), ruleset=ruleset)
    build_input = replace(
        after_input, parent_is_initial=False, parent_manifest=parent_manifest,
        parent_manifest_digest=parent_manifest.manifest_digest.value,
    )
    adapter = SubmitImportPublicationAdapter(
        repository_provider_factory=lambda _repo, _commit: provider,
        committed_table_factory=lambda _store, _repo: committed,
    )
    return adapter, build_input, after_store


def test_submit_patch_uses_frozen_parent_after_ruleset_activation() -> None:
    active_ruleset = migrated_table_ruleset_snapshot()
    frozen_document = table_ruleset_document(active_ruleset)
    rules = frozen_document["rules"]
    assert type(rules) is list
    fallback_rule = rules[-1]
    assert type(fallback_rule) is dict
    assert fallback_rule["selector"] == {"kind": "FALLBACK", "value": "*"}
    fallback_rule["compare_excluded_columns"] = ["value"]
    frozen_ruleset = table_ruleset_from_document(frozen_document)
    adapter, build_input, store = _keyed_parent_submit(ruleset=frozen_ruleset)
    assert build_input.parent_manifest is not None
    assert frozen_ruleset.ruleset_digest == build_input.parent_manifest.ruleset_digest
    assert frozen_ruleset.ruleset_digest != active_ruleset.ruleset_digest
    assert build_input.parent_manifest.tables[0].canonical_key_columns == ("id",)
    published = adapter.build_and_publish(build_input=build_input, store=store)
    sql = _replay_sql_from_package(adapter.read_back_package(checkpoint=published.checkpoint, store=store))
    assert "UPDATE `a_widget` SET" in sql
    assert "new-value" in sql
    assert "DROP TABLE" not in sql


@pytest.mark.parametrize("fault", ("commit", "count", "content"))
def test_submit_rejects_parent_commit_or_rows_outside_frozen_binding(fault: str) -> None:
    adapter, build_input, store = _keyed_parent_submit(fault=fault)
    with pytest.raises(SubmitImportPublicationError):
        adapter.build_and_publish(build_input=build_input, store=store)


def test_empty_canonical_closure_resolves_without_table_artifacts() -> None:
    store = InMemoryArtifactStore()
    materialized = materialize_sql(
        "SET FOREIGN_KEY_CHECKS=0;",
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=store,
    )
    assert materialized.status is SnapshotMaterializationStatus.COMPLETE
    assert materialized.table_set is not None
    assert materialized.table_set.tables == ()
    projection = project_canonical_fixture(
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
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=store,
    )
    assert materialized.status is SnapshotMaterializationStatus.COMPLETE
    assert materialized.table_set is not None
    canonical = project_canonical_fixture(
        materialized.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert canonical.manifest is not None
    assert canonical.manifest.manifest_digest is not None
    parent_projection = _project_inputs(_projection_inputs())
    assert parent_projection.manifest is not None
    assert parent_projection.manifest.manifest_digest is not None
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
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-empty-removal",
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=canonical.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-with-old-table",
        repository_id="test-repository",
        parent_manifest=parent_projection.manifest,
        parent_manifest_digest=parent_projection.manifest.manifest_digest.value,
        parent_is_initial=False,
        removed_tables=("net_cfg",),
        source_artifact_digest=canonical.manifest.source_artifact_digest.value,
        snapshot_tables=(),
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(build_input=build_input, store=store)
    package = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(package)
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE" not in replay_sql
    assert published.checkpoint.removed_tables == ("net_cfg",)


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
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=store,
    )
    assert source.status is SnapshotMaterializationStatus.COMPLETE
    assert source.snapshot is not None
    assert source.table_set is not None
    frozen = project_canonical_arrow_table_set(
        source.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert frozen.status is ProjectionStatus.COMPLETE
    assert frozen.manifest is not None
    assert frozen.manifest.manifest_digest is not None
    assert "no" in {column.name for column in frozen.manifest.tables[0].dropped_columns}
    assert "no" not in {column.name for column in frozen.tables[0].descriptor.columns}

    canonical_snapshot = materialize_canonical_snapshot(
        source.snapshot,
        frozen.tables,
        artifact_store=store,
        context=ParserInvocationContext(NeverCancel()), repository_id="test-repository",
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
    canonical_inputs = _open_projection_inputs(bindings, store=store, repository_id="test-repository")
    manifest_payload = durable_manifest_bytes(frozen.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="frozen-com_cfg-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_payload),
        raw_sha256=raw_blob_digest(manifest_payload),
    )
    store.put(manifest_payload, manifest_ref)
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-frozen-dropped-column",
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
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
        repository_id="test-repository",
        parent_manifest=None,
        parent_manifest_digest=None,
        parent_is_initial=True,
        removed_tables=(),
        source_artifact_digest=canonical_inputs[0].source_binding.snapshot_digest.value,
        snapshot_tables=bindings,
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=store,
    )
    assert source.status is SnapshotMaterializationStatus.COMPLETE
    assert source.snapshot is not None
    assert source.table_set is not None
    frozen = project_canonical_arrow_table_set(
        source.table_set,
        migrated_table_ruleset_snapshot(),
    )
    assert frozen.status is ProjectionStatus.COMPLETE
    assert frozen.manifest is not None
    assert frozen.manifest.manifest_digest is not None
    assert frozen.manifest.tables[0].gid_pseudo_count == 2

    canonical_snapshot = materialize_canonical_snapshot(
        source.snapshot,
        frozen.tables,
        artifact_store=store,
        context=ParserInvocationContext(NeverCancel()), repository_id="test-repository",
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
    projection_inputs = _open_projection_inputs(bindings, store=store, repository_id="test-repository")
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
    build_input = PrepareImportBuildInput(
        submit_attempt_id="sa-ordered-pseudo-replay",
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256.value,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=frozen.manifest.manifest_digest.value,
        expected_parent_commit_id="parent-ordered",
        repository_id="test-repository",
        parent_manifest=None,
        parent_manifest_digest=None,
        parent_is_initial=True,
        removed_tables=(),
        source_artifact_digest=projection_inputs[0].source_binding.snapshot_digest.value,
        snapshot_tables=bindings,
    )

    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
    first = adapter.build_and_publish(
        build_input=build_input,
        store=first_store,
    )
    second = adapter.build_and_publish(
        build_input=second_build_input,
        store=second_store,
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
    published = adapter.build_and_publish(
        build_input=_build_input(store=store),
        store=store,
    )
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE `net_cfg`" in replay_sql
    assert "INSERT INTO `net_cfg`" in replay_sql
    assert "VALUES ('eth0', 1)" in replay_sql


def test_submit_places_every_rebuilt_schema_before_table_rows() -> None:
    store = InMemoryArtifactStore()
    second_reader, second_binding = table_input(
        "a_widget", columns=(int_column("id"), varchar_column("value")),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1), varchar_cell("first")),),
    )
    raw_inputs = _projection_inputs() + (
        ProjectionTableInput(
            canonical_table="a_widget", reader=second_reader,
            source_binding=second_binding,
        ),
    )
    build_input = _frozen_build_input(store, raw_inputs)
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(build_input=build_input, store=store)
    sql = _replay_sql_from_package(adapter.read_back_package(checkpoint=published.checkpoint, store=store))
    assert sql.index("DROP TABLE IF EXISTS `a_widget`") < sql.index("CREATE TABLE `a_widget`")
    assert sql.index("CREATE TABLE `a_widget`") < sql.index("DROP TABLE IF EXISTS `net_cfg`")
    assert sql.index("CREATE TABLE `net_cfg`") < sql.index("INSERT INTO `a_widget`")
    assert sql.index("INSERT INTO `a_widget`") < sql.index("INSERT INTO `net_cfg`")


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
    published = adapter.build_and_publish(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
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
    published = adapter.build_and_publish(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
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
    published = adapter.build_and_publish(
        build_input=_build_input(store=store, projection_inputs=projection_inputs),
        store=store,
    )
    assert published.checkpoint.backend_import_artifact_ref.artifact_id.startswith("r4-package-")


def test_checkpoint_reuse_read_back_preserves_package_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
    )
    orphan_count = len(store._artifacts)
    second = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
    published = adapter.build_and_publish(
        build_input=_build_input(store=store),
        store=store,
    )
    artifact_ids = set(store._artifacts)
    assert published.checkpoint.canonicalization_manifest_ref.artifact_id in artifact_ids
    assert published.checkpoint.backend_import_artifact_ref.artifact_id in artifact_ids
    assert not any(artifact_id.startswith("change-set-closure-") for artifact_id in artifact_ids)


def test_build_and_publish_from_pinned_canonical_ipc_artifact_succeeds() -> None:
    store = InMemoryArtifactStore()
    sql = (
        "CREATE TABLE `unknown_widget` (`id` INT NOT NULL PRIMARY KEY, `flags` SET('x','y') NOT NULL);"
        "INSERT INTO `unknown_widget` VALUES (1, 'x');"
    )
    source = materialize_sql(
        sql,
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=store,
    )
    assert source.snapshot is not None and source.table_set is not None
    projected = project_canonical_arrow_table_set(source.table_set, migrated_table_ruleset_snapshot())
    result = materialize_canonical_snapshot(source.snapshot, projected.tables, artifact_store=store,
        context=ParserInvocationContext(NeverCancel()), repository_id="test-repository")
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
    projection_inputs = _open_projection_inputs((binding,), store=store, repository_id="test-repository")
    build_input = _build_input(
        store=store,
        projection_inputs=projection_inputs,
    )
    adapter = SubmitImportPublicationAdapter()
    published = adapter.build_and_publish(build_input=build_input, store=store)
    assert published.replay is False
    payload = adapter.read_back_package(checkpoint=published.checkpoint, store=store)
    replay_sql = _replay_sql_from_package(payload)
    assert "INSERT INTO `unknown_widget`" in replay_sql


def test_prepare_rejects_parent_manifest_with_corrupt_content() -> None:
    store = InMemoryArtifactStore()
    initial = _build_input(store=store)
    parent = open_canonicalization_manifest(store, initial.canonicalization_manifest_ref)
    assert parent.manifest_digest is not None
    build_input = replace(
        initial, parent_is_initial=False,
        parent_manifest=replace(parent, source_artifact_digest=digest_ref("bb")),
        parent_manifest_digest=parent.manifest_digest.value,
    )
    with pytest.raises(SubmitImportPublicationError, match="parent manifest"):
        SubmitImportPublicationAdapter().build_and_publish(build_input=build_input, store=store)


def test_reuse_rejects_mismatched_semantic_manifest_digest() -> None:
    adapter = SubmitImportPublicationAdapter()
    store = InMemoryArtifactStore()
    build_input = _build_input(store=store)
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
    published = adapter.build_and_publish(
        build_input=build_input,
        store=store,
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
