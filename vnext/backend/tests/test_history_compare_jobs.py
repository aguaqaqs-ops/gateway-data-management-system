"""History compare job pipeline tests."""

from __future__ import annotations

from tests.support.artifact_layout import open_test_store

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
import gateway_backend.application.history.compare_jobs as compare_jobs

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history.contracts import (
    HistoryCompareDiagnosticCode,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_HANDLER,
    HISTORY_COMPARE_MATERIALIZE_HANDLER,
    HISTORY_COMPARE_PUBLISH_HANDLER,
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
    _sides_from_materialize_checkpoint,
    history_compare_assemble_state_from_checkpoint,
    history_compare_step_id,
)
from gateway_backend.capabilities.comparison import (
    OrderedRecordKind,
    ComparisonTableStatus,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.history_compare import get_compare_result
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus, StepStatus
from gateway_backend.operations.worker import ExecutorAcknowledgment
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.history_compare_job_harness import (
    ORDERED_SYX_TABLE,
    REPOSITORY_ID,
    HistoryCompareJobHarness,
    build_history_compare_harness,
    claim_next_step,
    history_compare_net_cfg_provider,
    history_compare_ordered_provider,
    history_compare_provider,
    insert_history_compare_operation,
    ordered_syx_catalog_table,
    run_claimed_handler,
    run_full_history_compare_job,
    run_through_step,
)
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryCatalogTable,
    RepositoryColumn,
)
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    RepositoryRows,
    catalog_table,
    int_id_column,
    make_catalog,
    text_column,
)
from gateway_backend.operations.contracts import BusinessReference

from tests.support.history_compare_reference import (
    compare_bound_snapshots,
    compare_bound_snapshots_and_ordered_kinds,
    materialize_bound_snapshot,
    local_comparison_digest,
)
from tests.support.history_zero_write_tables import capture_business_table_state

F1_POLICY_BINDING_CASES = (
    (
        "move_only",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((2, 1, "b"), (1, 2, "a"))},
        (OrderedRecordKind.ROW_MOVED,),
        0,
    ),
    (
        "pseudo_blank",
        {ORDERED_SYX_TABLE: ((1, 1, "a"),)},
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (4_000_000_000, 2, "blank"))},
        (),
        0,
    ),
    (
        "keyed_ignored_column",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((1, 2, "a"), (2, 1, "b"))},
        (OrderedRecordKind.ROW_MOVED,),
        0,
    ),
)

RULESET_MISMATCH_STEPS = (
    ("materialize_inputs", HISTORY_COMPARE_MATERIALIZE_HANDLER, ()),
    (
        "assemble_comparison",
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        (HISTORY_COMPARE_MATERIALIZE_HANDLER,),
    ),
    (
        "publish_result",
        HISTORY_COMPARE_PUBLISH_HANDLER,
        (HISTORY_COMPARE_MATERIALIZE_HANDLER, HISTORY_COMPARE_ASSEMBLE_HANDLER),
    ),
)

pytestmark = pytest.mark.unit



def _reader_names(provider: FakeRepositoryTableAccessProvider) -> tuple[str, ...]:
    return tuple(reader.catalog_table().table_name for session in provider.sessions for reader in session.table_readers)


def _history_assemble_state(
    harness: HistoryCompareJobHarness,
    job_state: object,
) -> dict[str, object]:
    assert isinstance(job_state, dict)
    _state_ref, assemble_state = history_compare_assemble_state_from_checkpoint(
        job_state,
        harness.deps.artifact_store,
    )
    return assemble_state


def _history_snapshot_bundle_data(
    harness: HistoryCompareJobHarness,
) -> tuple[
    dict[tuple[str, str, str], list[dict[str, object]]],
    tuple[dict[str, object], ...],
]:
    from gateway_backend.artifacts.serialize import artifact_ref_from_dict
    from gateway_backend.capabilities.bundle_assembly import BUNDLE_MANIFEST_MEDIA_TYPE
    from gateway_backend.capabilities.snapshot_materialization._parquet import read_parquet_table

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _history_assemble_state(harness, envelope.job_state)
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    bundle_manifest_refs = [
        artifact_ref_from_dict(cast(dict[str, object], item))
        for item in required_refs
        if isinstance(item, dict)
        and artifact_ref_from_dict(cast(dict[str, object], item)).media_type
        == BUNDLE_MANIFEST_MEDIA_TYPE
    ]
    assert len(bundle_manifest_refs) == 1
    manifest = json.loads(harness.artifact_store.locate(bundle_manifest_refs[0]).decode("utf-8"))
    assert isinstance(manifest, dict)
    raw_entries = manifest.get("closure_entries")
    assert isinstance(raw_entries, list)
    snapshot_entries = tuple(
        cast(dict[str, object], entry)
        for entry in raw_entries
        if isinstance(entry, dict) and entry.get("kind") == "SNAPSHOT_TABLE"
    )
    rows_by_binding: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for entry in snapshot_entries:
        artifact_ref_raw = entry.get("artifact_ref")
        table_bindings_raw = entry.get("table_bindings")
        assert isinstance(artifact_ref_raw, dict)
        assert isinstance(table_bindings_raw, list)
        row_data = cast(
            list[dict[str, object]],
            read_parquet_table(
                harness.artifact_store.locate(
                    artifact_ref_from_dict(cast(dict[str, object], artifact_ref_raw))
                )
            ).to_pylist(),
        )
        for binding_raw in table_bindings_raw:
            assert isinstance(binding_raw, dict)
            key = (
                str(binding_raw["pair_id"]),
                str(binding_raw["side"]),
                str(binding_raw["table_name"]),
            )
            assert key not in rows_by_binding
            rows_by_binding[key] = row_data
    return rows_by_binding, snapshot_entries


def test_materialize_deduplicates_identical_commits(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.business_baseline_commit_id),
            ("bn-b", BASELINE_HEAD.business_baseline_commit_id),
        ),
    )
    insert_history_compare_operation(harness)
    before_opens = harness.total_open_count()
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    # Metadata/catalog authority is read once; canonical rows are deferred.
    assert harness.total_open_count() - before_opens == 1

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert materialize_step.status is StepStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    assert assemble_step.status is StepStatus.PENDING
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = _sides_from_materialize_checkpoint(envelope.job_state, harness.artifact_store, repository_id=REPOSITORY_ID)
    assert set(sides) == {BASELINE_HEAD.business_baseline_commit_id}
    assert set(envelope.job_state) == {"materialized_sides_ref"}


def test_history_materialization_preserves_complete_metadata_without_reading_rows(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path)
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    assert all(not _reader_names(provider) for provider in harness.providers.values())
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        step = uow.operations.get_step(history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE))
    assert step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, step.checkpoint_ref)
    sides = _sides_from_materialize_checkpoint(envelope.job_state, harness.artifact_store, repository_id=REPOSITORY_ID)
    assert set(sides) == set(harness.providers)
    for side in sides.values():
        assert side.table_set is not None
        assert tuple(table.descriptor.table_name for table in side.table_set.tables) == ("t",)
        assert all(table.reader is None and table.artifact is None for table in side.table_set.tables)


def test_assemble_resumes_from_materialized_sides_with_runtime_ruleset(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-resume")
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _history_assemble_state(harness, envelope.job_state)
    assert assemble_state["bundle_digest"]


def test_primary_key_change_across_commits_degrades_without_failing_job(tmp_path: Path) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    value_col = text_column("value", 1)
    id_table = catalog_table("t", (int_id_column(), value_col), primary_key=("id",))
    code_col = RepositoryColumn(name="code", ordinal=0, scalar_type="INT", nullable=False)
    code_table = catalog_table("t", (code_col, value_col), primary_key=("code",))
    rows = {"t": ((1, "a"),)}

    def _provider(commit_id: str, table: RepositoryCatalogTable) -> FakeRepositoryTableAccessProvider:
        catalog = make_catalog(
            (table,),
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            base_catalog=catalog,
            rows=rows,
            declared_rows=rows,
            current_commit=commit_id,
        )

    providers = {
        before_commit: _provider(before_commit, id_table),
        current_commit: _provider(current_commit, code_table),
    }
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers=providers,
        idempotency_key="history-compare-pk-change",
    )
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    assert "table_policies" not in envelope.job_state
    facts = compare_bound_snapshots(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
    assert facts.tables[0].status is ComparisonTableStatus.DEGRADED


def test_materialize_checkpoint_preserves_keyless_storage_facts_for_history_compare(
    tmp_path: Path,
) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-keyless-current"
    before_rows = {"t": (("same",), ("same",), ("before",))}
    current_rows = {"t": (("same",), ("same",), ("after",))}

    def _provider(
        commit_id: str,
        rows: RepositoryRows,
    ) -> FakeRepositoryTableAccessProvider:
        table = catalog_table(
            "t",
            (text_column("value", 0),),
            primary_key=(),
            row_count=len(rows["t"]),
        )
        catalog = make_catalog(
            (table,),
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            base_catalog=catalog,
            rows=rows,
            declared_rows=rows,
            current_commit=commit_id,
        )

    providers = {
        before_commit: _provider(before_commit, before_rows),
        current_commit: _provider(current_commit, current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-keyless-current", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-keyless-checkpoint",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    materialize_envelope = load_checkpoint_envelope(
        harness.artifact_store,
        materialize_step.checkpoint_ref,
    )
    sides = _sides_from_materialize_checkpoint(
        materialize_envelope.job_state,
        harness.artifact_store, repository_id=REPOSITORY_ID,
    )
    current_side = sides[current_commit]
    assert (
        current_side.storage_facts[0].storage_rule_view.canonical_key_policy.value
        == "DDL_PRIMARY_KEY_OR_KEYLESS"
    )

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    assemble_envelope = load_checkpoint_envelope(
        harness.artifact_store,
        assemble_step.checkpoint_ref,
    )
    assemble_state = _history_assemble_state(harness, assemble_envelope.job_state)
    pairs = assemble_state["pairs"]
    assert isinstance(pairs, list)
    pair = pairs[0]
    assert isinstance(pair, dict)
    assert pair["comparison_digest"] == local_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )


def test_two_node_compare_job_succeeds(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path)
    run_full_history_compare_job(harness)

    baseline_session = harness.providers[BASELINE_HEAD.business_baseline_commit_id].last_session
    current_session = harness.providers["commit-b"].last_session
    assert baseline_session is not None and current_session is not None
    # Exact commits are restored from a canonical JSON map; either identical
    # side may populate the shared canonical content first. Count real readers
    # across all sessions/commits rather than depending on metadata map order.
    all_reader_names = tuple(name for provider in harness.providers.values() for name in _reader_names(provider))
    assert all_reader_names == ("t",)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        publish_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_PUBLISH)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert publish_step.status is StepStatus.SUCCEEDED
    assert operation.ready_closure_ref is not None
    rows_by_binding, snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = "left_to_right"
    assert rows_by_binding == {
        (pair_id, "before", "t"): [{"id": "1"}],
        (pair_id, "current", "t"): [{"id": "1"}],
    }
    assert len(snapshot_entries) == 1
    assert snapshot_entries[0]["shared"] is True


def test_history_full_table_export_uses_cold_and_warm_cache_entries(tmp_path: Path) -> None:
    from gateway_backend.artifacts import ArtifactRef
    from gateway_backend.artifacts.snapshot_table_export_cache import (
        SnapshotTableArtifactCacheKey,
    )

    class ExportCache:
        def __init__(self) -> None:
            self.entries: dict[SnapshotTableArtifactCacheKey, ArtifactRef] = {}

        def lookup_many(
            self,
            keys: tuple[SnapshotTableArtifactCacheKey, ...],
        ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
            return {key: self.entries[key] for key in keys if key in self.entries}

        def store_many(
            self,
            entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...],
        ) -> None:
            self.entries.update(entries)

        def discard_if_same(self, key: SnapshotTableArtifactCacheKey, ref: ArtifactRef) -> bool:
            if self.entries.get(key) != ref:
                return False
            del self.entries[key]
            return True

    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-export-cache-current"
    table_rows: RepositoryRows = {
        "t": ((1,),),
        ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b")),
    }

    def provider(commit_id: str) -> FakeRepositoryTableAccessProvider:
        catalog = make_catalog(
            (
                catalog_table("t", (int_id_column(),), primary_key=("id",), row_count=1),
                ordered_syx_catalog_table(),
            ),
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            rows=table_rows,
            declared_rows=table_rows,
            current_commit=commit_id,
        )

    store = InMemoryArtifactStore()
    cache = ExportCache()
    cold_providers = {
        before_commit: provider(before_commit),
        current_commit: provider(current_commit),
    }
    cold = build_history_compare_harness(
        tmp_path / "cold",
        artifact_store=store,
        snapshot_export_cache=cache,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-export-cache-current", current_commit),
        ),
        custom_providers=cold_providers,
        idempotency_key="history-full-export-cache-cold",
    )
    run_full_history_compare_job(cold)

    cold_before = cold_providers[before_commit].last_session
    cold_current = cold_providers[current_commit].last_session
    assert cold_before is not None and cold_current is not None
    expected_reader_names = tuple(sorted(("t", ORDERED_SYX_TABLE)))
    cold_reader_names = _reader_names(cold_providers[before_commit])
    assert cold_reader_names == expected_reader_names
    assert cold_current.table_readers == []
    assert len(cache.entries) == 2
    cold_rows, cold_entries = _history_snapshot_bundle_data(cold)
    cold_pair_id = "left_to_right"
    assert cold_rows == {
        (cold_pair_id, "before", "t"): [{"id": "1"}],
        (cold_pair_id, "current", "t"): [{"id": "1"}],
        (cold_pair_id, "before", ORDERED_SYX_TABLE): [
            {"gid": "1", "no": "1", "value": "a"},
            {"gid": "2", "no": "2", "value": "b"},
        ],
        (cold_pair_id, "current", ORDERED_SYX_TABLE): [
            {"gid": "1", "no": "1", "value": "a"},
            {"gid": "2", "no": "2", "value": "b"},
        ],
    }
    assert len(cold_entries) == 2

    warm_providers = {
        before_commit: provider(before_commit),
        current_commit: provider(current_commit),
    }
    warm = build_history_compare_harness(
        tmp_path / "warm",
        # A later operation shares the real C index. Client Parquet is not a
        # canonical recovery source; its derived cache is independently reused.
        db_path=cold.db_path,
        artifact_store=store,
        snapshot_export_cache=cache,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-export-cache-current-warm", current_commit),
        ),
        custom_providers=warm_providers,
        idempotency_key="history-full-export-cache-warm",
    )
    run_full_history_compare_job(warm)

    assert all(
        provider_item.last_session is not None
        and provider_item.last_session.table_readers == []
        for provider_item in warm_providers.values()
    )
    warm_rows, warm_entries = _history_snapshot_bundle_data(warm)
    warm_pair_id = "left_to_right"
    assert set(warm_rows) == {
        (warm_pair_id, side, table)
        for side in ("before", "current")
        for table in ("t", ORDERED_SYX_TABLE)
    }
    assert {
        (side, table): rows
        for (_pair_id, side, table), rows in warm_rows.items()
    } == {
        (side, table): rows
        for (_pair_id, side, table), rows in cold_rows.items()
    }
    assert len(warm_entries) == 2


def test_changed_history_table_reads_both_pair_sides(tmp_path: Path) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-changed-current"
    providers = {
        before_commit: history_compare_provider(
            commit_id=before_commit,
            declared_rows={"t": ((1,),)},
        ),
        current_commit: history_compare_provider(
            commit_id=current_commit,
            declared_rows={"t": ((2,),)},
        ),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-changed-current", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-changed-table-reads-both-sides",
    )
    run_full_history_compare_job(harness)

    for provider in providers.values():
        session = provider.last_session
        assert session is not None
        assert tuple(reader.catalog_table().table_name for reader in session.table_readers) == ("t",)


def test_history_bundle_preserves_changed_added_and_deleted_table_bindings(tmp_path: Path) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-with-added-table"
    before_tables = (
        catalog_table("t", (int_id_column(),), primary_key=("id",), row_count=1),
        catalog_table(
            "gone",
            (text_column("value", 0),),
            primary_key=(),
            row_count=1,
        ),
    )
    current_tables = (
        catalog_table("t", (int_id_column(),), primary_key=("id",), row_count=1),
        catalog_table("added", (text_column("value", 0),), primary_key=(), row_count=1),
    )
    before_rows: RepositoryRows = {"t": ((1,),), "gone": (("old",),)}
    current_rows: RepositoryRows = {"t": ((2,),), "added": (("new",),)}

    def _provider(
        commit_id: str,
        tables: tuple[RepositoryCatalogTable, ...],
        rows: RepositoryRows,
    ) -> FakeRepositoryTableAccessProvider:
        catalog = make_catalog(
            tables,
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            base_catalog=catalog,
            rows=rows,
            declared_rows=rows,
            current_commit=commit_id,
        )

    providers = {
        before_commit: _provider(before_commit, before_tables, before_rows),
        current_commit: _provider(current_commit, current_tables, current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-deleted-table", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-added-and-deleted-table-bundle",
    )
    run_full_history_compare_job(harness)

    before_session = providers[before_commit].last_session
    current_session = providers[current_commit].last_session
    assert before_session is not None and current_session is not None
    assert _reader_names(providers[before_commit]) == (
        "gone",
        "t",
    )
    assert _reader_names(providers[current_commit]) == (
        "added",
        "t",
    )
    rows_by_binding, _snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = "left_to_right"
    assert rows_by_binding == {
        (pair_id, "before", "t"): [{"id": "1"}],
        (pair_id, "current", "t"): [{"id": "2"}],
        (pair_id, "before", "gone"): [{"value": "old"}],
        (pair_id, "current", "added"): [{"value": "new"}],
    }


def test_unchanged_ordered_history_bundles_both_sides_and_preserves_facts(
    tmp_path: Path,
) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-ordered-current"
    rows: RepositoryRows = {
        ORDERED_SYX_TABLE: (
            (1, 1, "a"),
            (4_000_000_000, 2, "blank"),
            (2, 3, "b"),
        )
    }
    providers = {
        before_commit: history_compare_ordered_provider(
            commit_id=before_commit,
            rows=rows,
        ),
        current_commit: history_compare_ordered_provider(
            commit_id=current_commit,
            rows=rows,
        ),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-ordered-current", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-unchanged-ordered",
    )
    run_full_history_compare_job(harness)

    before_session = providers[before_commit].last_session
    current_session = providers[current_commit].last_session
    assert before_session is not None and current_session is not None
    assert _reader_names(providers[before_commit]) == (
        ORDERED_SYX_TABLE,
    )
    assert _reader_names(providers[current_commit]) == ()  # Scoped content hit.

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _history_assemble_state(harness, envelope.job_state)
    pairs = assemble_state["pairs"]
    assert isinstance(pairs, list)
    pair = pairs[0]
    assert isinstance(pair, dict)
    assert pair["comparison_digest"] == local_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )
    rows_by_binding, snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = "left_to_right"
    expected_rows = [
        {"gid": "1", "no": "1", "value": "a"},
        {"gid": "4000000000", "no": "2", "value": "blank"},
        {"gid": "2", "no": "3", "value": "b"},
    ]
    assert rows_by_binding == {
        (pair_id, "before", ORDERED_SYX_TABLE): expected_rows,
        (pair_id, "current", ORDERED_SYX_TABLE): expected_rows,
    }
    assert len(snapshot_entries) == 1
    assert snapshot_entries[0]["shared"] is True


def test_three_node_compare_job_uses_multi_pair_bundle(tmp_path: Path) -> None:
    import json

    from gateway_backend.artifacts.serialize import artifact_ref_from_dict
    from gateway_backend.capabilities.bundle_assembly import BUNDLE_MANIFEST_MEDIA_TYPE

    node_a = BASELINE_HEAD.business_baseline_node_id
    node_b = "bn-b"
    node_c = "bn-c"
    commit_a = BASELINE_HEAD.business_baseline_commit_id
    commit_b = "commit-b"
    commit_c = "commit-c"
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (node_a, commit_a),
            (node_b, commit_b),
            (node_c, commit_c),
        ),
        idempotency_key="history-compare-3-node",
    )
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _history_assemble_state(harness, envelope.job_state)
    pairs = assemble_state["pairs"]
    assert isinstance(pairs, list)
    assert len(pairs) == 2
    assert pairs[0]["pair_id"] == "left_to_middle"
    assert pairs[1]["pair_id"] == "middle_to_right"
    assert (pairs[0]["before_commit"], pairs[0]["current_commit"]) == (commit_a, commit_b)
    assert (pairs[1]["before_commit"], pairs[1]["current_commit"]) == (commit_b, commit_c)
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    manifest_ref = next(
        artifact_ref_from_dict(item)
        for item in required_refs
        if artifact_ref_from_dict(item).media_type == BUNDLE_MANIFEST_MEDIA_TYPE
    )
    manifest = json.loads(harness.artifact_store.locate(manifest_ref).decode("utf-8"))
    assert manifest["bundle_profile"] == "MULTI_PAIR"
    inputs = manifest["inputs"]
    assert [item["display_name"] for item in inputs] == ["node-0", "node-1", "node-2"]
    assert [item["role"] for item in inputs] == [node_a, node_b, node_c]
    rows_by_binding, snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_ids = ("left_to_middle", "middle_to_right")
    assert rows_by_binding == {
        (pair_id, side, "t"): [{"id": "1"}]
        for pair_id in pair_ids
        for side in ("before", "current")
    }
    assert len(snapshot_entries) == 1
    assert snapshot_entries[0]["shared"] is True
    table_bindings = snapshot_entries[0]["table_bindings"]
    assert isinstance(table_bindings, list)
    assert len(table_bindings) == 4


def test_repository_row_count_mismatch_fails_history_compare(tmp_path: Path) -> None:
    commit_id = BASELINE_HEAD.business_baseline_commit_id
    provider = history_compare_provider(
        commit_id=commit_id,
        row_count=2,
        declared_rows={"t": ((1,), (2,))},
    )
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: provider,
            "commit-b": history_compare_provider(commit_id="commit-b"),
        },
        idempotency_key="history-compare-row-count-mismatch",
    )
    # Freeze valid two-row authority, then truncate every actual runtime row
    # stream. Metadata-only opens do not consume this fault or read any row.
    provider.declared_rows = {"t": ((1,),)}
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert operation.status is OperationStatus.FAILED
    assert assemble_step.status is StepStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == "REPOSITORY_ROW_COUNT_MISMATCH"


def test_ruleset_mismatch_publishes_stable_failed_code(tmp_path: Path) -> None:
    import json

    from gateway_shared_kernel.jcs import canonicalize_json_value

    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-ruleset")
    payload = json.loads(harness.job_payload)
    payload["comparison_ruleset_digest"] = "sha256:old-ruleset"
    object.__setattr__(harness, "job_payload", canonicalize_json_value(payload))
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value


@pytest.mark.parametrize(
    ("step_name", "handler_identity", "prior_handlers"),
    RULESET_MISMATCH_STEPS,
    ids=("materialize", "assemble", "publish"),
)
def test_history_compare_rejects_runtime_ruleset_change_before_each_step(
    tmp_path: Path,
    step_name: str,
    handler_identity: str,
    prior_handlers: tuple[str, ...],
) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key=f"ruleset-drift-{step_name}")
    insert_history_compare_operation(harness)
    for prior_handler in prior_handlers:
        run_through_step(harness, prior_handler)

    with patch(
        "gateway_backend.application.history.compare_jobs.comparison_rule_set",
        return_value=SimpleNamespace(ruleset_digest=DigestRef("sha256:" + "cd" * 32)),
    ):
        run_through_step(harness, handler_identity)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        failed_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, step_name)
        )
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value
    assert failed_step.status is StepStatus.FAILED


def test_publish_pins_assemble_checkpoint_and_clears_step_checkpoints(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-durable")
    run_full_history_compare_job(harness)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
        publish_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_PUBLISH)
        )
        assert assemble_step.checkpoint_ref is not None
        assemble_ref = assemble_step.checkpoint_ref
        protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        )
        step_protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step.step_id,
        )
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=assemble_step.step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=publish_step.step_id,
        ) == frozenset()
    assert step_protected == frozenset()
    assert assemble_ref.artifact_id in protected
    cast(InMemoryArtifactStore, harness.artifact_store)._artifacts.pop(assemble_ref.artifact_id, None)  # noqa: SLF001

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(harness.operation_id)
    assert acceptance is not None
    with pytest.raises(ApiError) as exc_info:
        get_compare_result(
            operation=operation,
            acceptance=acceptance,
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                harness.db_path,
                read_only=read_only,
            ),
            artifact_store=harness.artifact_store,
        )
    assert exc_info.value.code == "ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize(
    ("case_id", "before_rows", "current_rows", "expected_kinds", "expected_modified"),
    F1_POLICY_BINDING_CASES,
)
def test_f1_policy_binding_integration_cases(
    tmp_path: Path,
    case_id: str,
    before_rows: dict[str, tuple[tuple[object, ...], ...]],
    current_rows: dict[str, tuple[tuple[object, ...], ...]],
    expected_kinds: tuple[OrderedRecordKind, ...],
    expected_modified: int,
) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    providers = {
        before_commit: history_compare_ordered_provider(commit_id=before_commit, rows=before_rows),
        current_commit: history_compare_ordered_provider(commit_id=current_commit, rows=current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-b", current_commit),
        ),
        custom_providers=providers,
        idempotency_key=f"history-compare-f1-{case_id}",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    assert "table_policies" not in envelope.job_state

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    local_digest = local_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )
    facts, kinds = compare_bound_snapshots_and_ordered_kinds(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
    assert kinds == expected_kinds
    modified_count = sum(table.row_modified_count for table in facts.tables)
    assert modified_count == expected_modified

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    assemble_envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _history_assemble_state(harness, assemble_envelope.job_state)
    pairs = assemble_state["pairs"]
    assert isinstance(pairs, list)
    pair = pairs[0]
    assert isinstance(pair, dict)
    assert pair["comparison_digest"] == local_digest


def test_history_compares_canonical_net_cfg_without_dropped_column(tmp_path: Path) -> None:
    table_name = "net_cfg"
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-b"
    before_rows = {table_name: (("b1", 1, "a"),)}
    current_rows = {table_name: (("b1", 1, "a"),)}
    providers = {
        before_commit: history_compare_net_cfg_provider(commit_id=before_commit, rows=before_rows),
        current_commit: history_compare_net_cfg_provider(commit_id=current_commit, rows=current_rows),
    }
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-netcfg-b", current_commit),
        ),
        custom_providers=providers,
        idempotency_key="history-compare-f1-netcfg",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    assert "table_policies" not in envelope.job_state

    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    facts, kinds = compare_bound_snapshots_and_ordered_kinds(
        materialize_bound_snapshot(
            providers[before_commit],
            commit_id=before_commit,
            artifact_store=harness.artifact_store,
        ),
        materialize_bound_snapshot(
            providers[current_commit],
            commit_id=current_commit,
            artifact_store=harness.artifact_store,
        ),
    )
    assert kinds == ()
    modified_count = sum(table.row_modified_count for table in facts.tables)
    assert modified_count == 0
    assert facts.tables[0].status is ComparisonTableStatus.UNCHANGED


def test_job_payload_within_budget_without_table_policies(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path)
    payload = json.loads(harness.job_payload)
    assert len(harness.job_payload) <= 64 * 1024
    assert "table_policies" not in payload


def test_accept_operation_sets_business_refs_and_protection_owner(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from gateway_backend.application.history.contracts import (
        HistoryCompareAcceptCommand,
        HistoryNodeRef,
        HistoryNodeRefKind,
        PERMISSION_READ_PROJECT_HISTORY,
    )
    from gateway_backend.application.history.compare_jobs import history_compare_job_definitions
    from gateway_backend.application.job_definitions import JobDefinitionRegistry
    from gateway_backend.http.dependencies import OpenAdmissionGate
    from gateway_backend.http.orchestration.history_compare import accept_compare_operation
    from tests.support.workspace_fixtures import make_identity

    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-business-refs")
    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    identity = make_identity(permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY}))
    result = accept_compare_operation(
        command=HistoryCompareAcceptCommand(
            context=identity,
            idempotency_key="history-compare-business-refs-accept",
            node_refs=(
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, BASELINE_HEAD.business_baseline_node_id),
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-b"),
            ),
        ),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(harness.db_path, read_only=read_only),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
        now=datetime(2026, 9, 24, tzinfo=UTC),
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(result.response.operation_id)
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(result.response.operation_id)
    assert acceptance is not None
    assert operation.business_refs == (
        BusinessReference(kind="history_compare", value=acceptance.acceptance_id),
    )


def test_publish_job_does_not_mutate_business_tables(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-zero-write")
    before = capture_business_table_state(harness.db_path)
    run_full_history_compare_job(harness)
    after = capture_business_table_state(harness.db_path)
    assert before == after


def test_cancel_before_materialize_leaves_operation_cancelled(tmp_path: Path) -> None:
    harness = build_history_compare_harness(tmp_path, idempotency_key="history-compare-cancel-before")
    insert_history_compare_operation(harness)
    session, control, operation, step = claim_next_step(harness)
    control.request_cancel()
    run_claimed_handler(
        harness,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
    assert persisted.status is OperationStatus.CANCELLED
    assert persisted.ready_closure_ref is None
    # Checkpoint never published on this path; empty protection means no spurious pin only.
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=step.step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        ) == frozenset()


def test_cancel_at_assemble_entry_releases_materialize_checkpoint_protection(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        idempotency_key="history-compare-cancel-assemble-entry",
    )
    insert_history_compare_operation(harness)
    materialize_step_id = history_compare_step_id(
        harness.operation_id,
        HISTORY_COMPARE_STEP_MATERIALIZE,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(materialize_step_id)
        assert materialize_step.checkpoint_ref is not None
        protected = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step_id,
        )
        assert protected != frozenset()

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == HISTORY_COMPARE_STEP_ASSEMBLE
    control.request_cancel()
    run_claimed_handler(
        harness,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
        assert persisted.status is OperationStatus.CANCELLED
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-checkpoint",
            owner_id=materialize_step_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="history-compare-operation",
            owner_id=harness.operation_id,
        ) == frozenset()


def test_cancel_during_history_assembly_loop_leaves_operation_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.business_baseline_commit_id),
            ("bn-b", "commit-b"),
            ("bn-c", "commit-b"),
        ),
        idempotency_key="history-compare-cancel-assembly-loop",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    original = compare_jobs._run_pair_pipeline
    calls = 0

    def run_pair_then_cancel(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            kwargs["control"].request_cancel()
        return result

    monkeypatch.setattr(compare_jobs, "_run_pair_pipeline", run_pair_then_cancel)
    session, control, operation, step = claim_next_step(harness)
    acknowledgment = run_claimed_handler(
        harness,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(harness.operation_id)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert calls == 1
    assert persisted.status is OperationStatus.CANCELLED


HISTORY_CACHE_NODE_CASES = (
    ("direct", ("a", "b"), 1),
    ("three", ("a", "b", "c"), 2),
    ("reverse", ("b", "a"), 1),
    ("same", ("a", "a"), 0),
    ("bad-payload", ("a", "b"), 1),
)


@pytest.mark.parametrize(("case", "order", "expected_calls"), HISTORY_CACHE_NODE_CASES)
def test_new_history_operation_reuses_complete_table_work_and_exports(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
    case: str, order: tuple[str, ...], expected_calls: int,
) -> None:
    from dataclasses import replace
    from gateway_backend.application.history.compare_jobs import history_compare_composition_bundle
    from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache
    from gateway_backend.infrastructure.control_db.snapshot_export_cache import ControlDbSnapshotTableExportCache

    commits = {"a": BASELINE_HEAD.business_baseline_commit_id, "b": "commit-cache-b", "c": "commit-cache-c"}
    values = {"a": 1, "b": 2, "c": 3}
    store = open_test_store(tmp_path / "cache-artifacts")
    previous: HistoryCompareJobHarness | None = None
    observed: list[dict[str, object]] = []
    for run in ("cold", "warm"):
        providers = {commits[label]: history_compare_provider(commit_id=commits[label],
            declared_rows={"t": ((values[label],),)}) for label in set(order)}
        node_specs = tuple((
            BASELINE_HEAD.business_baseline_node_id if label == "a" else f"bn-cache-{case}-{run}-{index}",
            commits[label],
        ) for index, label in enumerate(order))
        harness = build_history_compare_harness(tmp_path / run,
            db_path=None if previous is None else previous.db_path,
            artifact_store=store, node_specs=node_specs, custom_providers=providers,
            idempotency_key=f"history-cache-{case}-{run}")
        def transaction() -> ControlDbUnitOfWork:
            return ControlDbUnitOfWork(harness.db_path)
        cache = ControlDbComputationCache(transaction, store)
        deps = replace(harness.deps, computation_cache=cache,
            snapshot_export_cache=ControlDbSnapshotTableExportCache(transaction))
        _, handlers, _, bound_deps = history_compare_composition_bundle(deps)
        harness.deps = bound_deps
        harness.handlers = dict(handlers)
        harness.publication_uow_factory = bound_deps.control_transaction_factory
        caplog.clear()
        with caplog.at_level("INFO", logger="gateway_backend.application.pair_pipeline"):
            run_full_history_compare_job(harness)
        pair_metrics = [json.loads(record.message.split("s3_pair_metrics ", 1)[1])
            for record in caplog.records if record.message.startswith("s3_pair_metrics ")]
        assert len(pair_metrics) == len(order) - 1
        calls = sum(item["comparison"]["native_calls"] for item in pair_metrics)
        assert calls == (expected_calls if run == "cold" or case == "bad-payload" else 0)
        if run == "warm":
            assert all(not _reader_names(provider) for provider in providers.values())
            assert sum(item["comparison"]["cache_hits"] for item in pair_metrics) == (0 if case == "bad-payload" else expected_calls)
        rows, _ = _history_snapshot_bundle_data(harness)
        for index in range(len(order) - 1):
            pair_id = ("left_to_right" if len(order) == 2 else ("left_to_middle", "middle_to_right")[index])
            assert rows[pair_id, "before", "t"] == [{"id": str(values[order[index]])}]
            assert rows[pair_id, "current", "t"] == [{"id": str(values[order[index + 1]])}]
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
            operation = uow.operations.get_operation(harness.operation_id)
            assert operation.status is OperationStatus.SUCCEEDED
            assert uow.connection.execute("SELECT COUNT(*) FROM artifact_protection_intents WHERE intent='active-computation-cache'").fetchone()[0] == 0
        observed.append({"rows": {(key[0].split("-p")[-1], key[1], key[2]): value
            for key, value in rows.items()}})
        if run == "cold" and case == "bad-payload":
            _replace_comparison_cache_with_bad_neutral_payload(cache, store, harness)
        previous = harness
    assert observed[0] == observed[1]


def _replace_comparison_cache_with_bad_neutral_payload(cache: Any, store: Any, harness: HistoryCompareJobHarness) -> None:
    from gateway_backend.artifacts.computation_cache import (
        CacheOperationOwner, ComputationCacheEntry, ComputationCacheKey, ComputationCacheKind,
        encode_cache_manifest,
    )
    from gateway_backend.artifacts.types import ArtifactRef
    from gateway_backend.capabilities.table_access import current_kernel_context

    context = current_kernel_context()
    assert context is not None
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        task_digest = uow.connection.execute("SELECT task_digest FROM computation_cache_entries WHERE kind='comparison'").fetchone()[0]
    owner = CacheOperationOwner("history-compare-operation", "bad-cache-fixture")
    lease = cache.lookup_and_pin(ComputationCacheKey(REPOSITORY_ID, ComputationCacheKind.COMPARISON, DigestRef(task_digest)),
        owner=owner, checkpoint=context.checkpoint, reserve=context.memory.reserve)
    assert lease is not None
    payload = dict(lease.payload)
    payload["table_fact_jcs"] = "{}"
    raw = encode_cache_manifest(lease.entry.key, format=lease.entry.format,
        member_refs=lease.entry.member_refs, payload=payload)
    manifest = ArtifactRef("a1:durable:2660848574a60e9b959e57fdc37250f4f60f6647323da2526f2dfb92e1fc4e74", "application/json", len(raw), raw_blob_digest(raw))
    entry = ComputationCacheEntry(lease.entry.key, lease.entry.format, manifest, lease.entry.member_refs)
    blobs = ((manifest, raw), *((ref, store.locate(ref)) for ref in entry.member_refs))
    lease.close()
    assert cache.store(entry, blobs, owner=owner, checkpoint=context.checkpoint, reserve=context.memory.reserve)
    cache.release_operation_pins(owner)


def test_history_failed_export_closes_both_new_canonical_consumers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.capabilities.snapshot_materialization import ensure_committed_tables
    from gateway_backend.capabilities.table_access import TableAccessError
    from gateway_backend.capabilities.table_access.contracts import ParserDiagnosticCode
    from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableSet

    harness = build_history_compare_harness(tmp_path)
    payload = compare_jobs.decode_history_compare_payload(json.loads(harness.job_payload))
    sides = compare_jobs._materialize_distinct_commits(payload, harness.deps)
    rules = compare_jobs._assert_runtime_ruleset(payload)
    captured: list[SnapshotTableSet] = []
    original = ensure_committed_tables
    def ensure(table_set: SnapshotTableSet, **kwargs: Any) -> SnapshotTableSet:
        result = original(table_set, **kwargs)
        captured.append(result)
        return result
    def denied_export(*args: Any, **kwargs: Any) -> Any:
        raise MemoryError("required export budget")
    monkeypatch.setattr(compare_jobs, "ensure_committed_tables", ensure)
    monkeypatch.setattr(compare_jobs, "export_snapshot_table_parquet", denied_export)
    with pytest.raises(MemoryError, match="required export budget"):
        compare_jobs._ensure_history_demands_once(payload, harness.deps, sides,
            [("failed-admission-pair", payload.nodes[0], payload.nodes[1])], rules, None)
    assert len(captured) == 1
    table, = captured[0].tables
    assert table.reader is not None and table.batch_reader is not None
    with pytest.raises(TableAccessError) as closed:
        table.reader.reopen()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED
    with pytest.raises(ValueError, match="closed"):
        table.batch_reader.schema()
    assert all(table.reader is None and table.batch_reader is None
        for bound in sides.values() if bound.table_set is not None for table in bound.table_set.tables)


def test_full_preview_to_history_reuses_only_the_pairs_actually_computed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    from gateway_backend.application.pair_pipeline import run_history_pair_pipeline
    from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata
    from gateway_backend.application import preview_jobs
    from gateway_backend.application.canonical_metadata.ports import CommitCanonicalMetadata, CommitCanonicalScope
    from gateway_backend.application.workspace.preview import build_preview_job_payload
    from gateway_backend.artifacts.computation_cache import ComputationCacheKind
    from gateway_backend.artifacts.serialize import artifact_ref_from_dict
    from gateway_backend.capabilities.comparison import open_records_closure
    from gateway_backend.capabilities.risk_evaluation import PersistentRiskCandidates
    from gateway_backend.capabilities.risk_evaluation.contracts import RISK_ANNOTATION_MEDIA_TYPE
    from gateway_backend.capabilities.storage_projection import canonicalization_manifest_from_bytes
    from gateway_backend.domain.workspace.models import InputCompleteness
    from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache
    from gateway_backend.infrastructure.control_db.snapshot_export_cache import ControlDbSnapshotTableExportCache
    from tests.support.canonical_metadata import CatalogCommitCanonicalMetadataPort
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
    from tests.support import preview_job_harness as preview_support

    preview = preview_support.build_preview_harness(tmp_path / "preview", input_completeness=InputCompleteness.FULL)
    seed_provisioned_mapping_with_head(preview.db_path, baseline_head=BASELINE_HEAD)
    def transaction() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(preview.db_path)
    cache = ControlDbComputationCache(transaction, open_test_store(tmp_path / "computation-cache"))
    exports = ControlDbSnapshotTableExportCache(transaction)
    risk_lookups: list[bool] = []
    risk_stores: list[bool] = []
    original_lookup = PersistentRiskCandidates.lookup
    original_store = cache.store
    def observed_lookup(candidate: PersistentRiskCandidates, key: str) -> tuple[object, ...] | None:
        result = original_lookup(candidate, key)
        risk_lookups.append(result is not None)
        return result
    def observed_store(entry: Any, blobs: Any, **kwargs: Any) -> bool:
        result = original_store(entry, blobs, **kwargs)
        if entry.key.kind is ComputationCacheKind.RISK:
            risk_stores.append(result)
        return result
    monkeypatch.setattr(PersistentRiskCandidates, "lookup", observed_lookup)
    monkeypatch.setattr(cache, "store", observed_store)
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY COMMENT 'column-{value}') COMMENT='table-{value}'; INSERT INTO t VALUES ({value});"
    initial = preview_support.store_source_package(preview.artifact_store, sql.format(value=2).encode(), artifact_id="a1:durable:5adad6374935ac1f2c031bb667178cd95a1b658a4c4276477d515ba2d687e8be")
    modified = preview_support.store_source_package(preview.artifact_store, sql.format(value=3).encode(), artifact_id="a1:durable:661b6c2cafc55581541967e4871f60d18dc73d892270c5ecebb12ce7215e89bb")
    preview.upload_revision = preview_support.build_upload_revision(input_completeness=InputCompleteness.FULL,
        initial_binding=initial, modified_binding=modified, generation=preview.upload_revision.generation)
    preview.job_payload = build_preview_job_payload(workspace_id=preview.upload_revision.workspace_id,
        upload_revision=preview.upload_revision, repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version, idempotency_key="h1-preview-full",
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest())
    _, handlers, _ = preview_jobs.preview_composition_bundle(replace(preview.deps,
        computation_cache=cache, snapshot_export_cache=exports))
    preview.handlers = dict(handlers)
    producer = "op-preview-history-producer"
    preview_support.insert_preview_operation(preview, producer)
    for handler in (preview_jobs.PREVIEW_MATERIALIZE_HANDLER, preview_jobs.PREVIEW_ASSEMBLE_HANDLER, preview_jobs.PREVIEW_PUBLISH_HANDLER):
        lease, control, operation, step = preview_support.claim_next_step(preview)
        preview_support.run_claimed_handler(preview, handler, lease, control, operation, step)
    with transaction() as uow:
        step = uow.operations.get_step(preview_support.step_id_for(producer, "materialize_inputs"))
    assert step.checkpoint_ref is not None
    checkpoint = load_checkpoint_envelope(preview.artifact_store, step.checkpoint_ref)
    inputs = preview_jobs._materialized_preview_inputs_from_checkpoint(checkpoint.job_state,
        preview.artifact_store, repository_id=REPOSITORY_ID, dependencies=preview.deps)
    canonical = inputs.canonical
    assert canonical.initial_canonicalization_manifest_ref is not None
    manifests = {
        "a": preview_support._canonical_baseline_data()[2],
        "b": canonicalization_manifest_from_bytes(preview.artifact_store.locate(canonical.initial_canonicalization_manifest_ref)),
        "c": canonicalization_manifest_from_bytes(preview.artifact_store.locate(canonical.canonicalization_manifest_ref)),
    }
    commits = {"a": BASELINE_HEAD.business_baseline_commit_id, "b": "commit-h1-initial", "c": "commit-h1-modified"}
    side_names = {"a": "BASELINE", "b": "INITIAL", "c": "MODIFIED"}
    values = {"a": 1, "b": 2, "c": 3}
    metadata = CatalogCommitCanonicalMetadataPort({(REPOSITORY_ID, commits[label]): CommitCanonicalMetadata(
        REPOSITORY_ID, commits[label], CommitCanonicalScope("device-1", "project-1"), False,
        manifests[label], inputs.sides[side_names[label]].snapshot.snapshot_digest,
    ) for label in commits})
    seen_presentations: list[tuple[PresentationMetadata, PresentationMetadata]] = []
    def capture_presentations(**kwargs: Any) -> Any:
        seen_presentations.append((kwargs["before_presentation"], kwargs["current_presentation"]))
        return run_history_pair_pipeline(**kwargs)
    monkeypatch.setattr(compare_jobs, "run_history_pair_pipeline", capture_presentations)
    seen_content: dict[str, tuple[str, ...]] = {}
    seen_producers: dict[str, str] = {}
    for name, before_label, current_label, expected_native in (
        ("h1", "b", "c", 0), ("full-first", "a", "c", 1), ("full-warm", "a", "c", 0),
    ):
        providers = {commits[label]: FakeRepositoryTableAccessProvider(catalog=make_catalog(
            preview.baseline_provider.catalog.tables, repository_id=REPOSITORY_ID, ref=commits[label], commit=commits[label]),
            rows={"t": ((values[label],),)}, declared_rows={"t": ((values[label],),)}, current_commit=commits[label])
            for label in (before_label, current_label)}
        nodes = tuple((BASELINE_HEAD.business_baseline_node_id if label == "a" else f"bn-{name}-{index}", commits[label])
            for index, label in enumerate((before_label, current_label)))
        history = build_history_compare_harness(tmp_path / name, db_path=preview.db_path,
            artifact_store=preview.artifact_store, custom_providers=providers, node_specs=nodes,
            idempotency_key="history-new-operation-" + name, computation_cache=cache,
            snapshot_export_cache=exports, commit_metadata_port=metadata)
        caplog.clear()
        risk_lookups.clear()
        risk_stores.clear()
        with caplog.at_level("INFO", logger="gateway_backend.application.pair_pipeline"):
            run_full_history_compare_job(history)
        metrics = [json.loads(record.message.split("s3_pair_metrics ", 1)[1]) for record in caplog.records
            if record.message.startswith("s3_pair_metrics ")]
        assert len(metrics) == 1 and metrics[0]["comparison_kernel_calls"] == expected_native
        before_presentation, current_presentation = seen_presentations[-1]
        assert before_presentation == manifests[before_label].presentation
        assert current_presentation == manifests[current_label].presentation
        assert next(t.comment for t in current_presentation.tables if t.table_name == "t") == "table-3"
        assert next(t.comment for t in before_presentation.tables if t.table_name == "t") == ("table-2" if before_label == "b" else None)
        assert risk_lookups == [name != "full-first"]
        assert risk_stores == ([True] if name == "full-first" else [])
        rows, _ = _history_snapshot_bundle_data(history)
        pair_id = "left_to_right"
        assert rows[pair_id, "before", "t"] == [{"id": str(values[before_label])}]
        assert rows[pair_id, "current", "t"] == [{"id": str(values[current_label])}]
        with transaction() as uow:
            current_uses = set(uow.connection.execute(
                "SELECT kind, task_digest, manifest_artifact_id FROM computation_cache_uses WHERE producer_operation_id=?",
                (history.operation_id,)))
            assert {row[0] for row in current_uses} == {"comparison", "risk"}
            source_producer = producer if name == "h1" else seen_producers.get("full-first") if name == "full-warm" else None
            if source_producer is not None:
                source_uses = set(uow.connection.execute(
                    "SELECT kind, task_digest, manifest_artifact_id FROM computation_cache_uses WHERE producer_operation_id=?",
                    (source_producer,)))
                assert {row[0] for row in current_uses & source_uses} == {"comparison", "risk"}
            assemble = uow.operations.get_step(history_compare_step_id(history.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE))
        assert assemble.checkpoint_ref is not None
        state = _history_assemble_state(history, load_checkpoint_envelope(history.artifact_store, assemble.checkpoint_ref).job_state)
        current_pair = cast(list[dict[str, Any]], state["pairs"])[0]
        annotations: list[dict[str, Any]] = []
        for document in cast(list[dict[str, object]], state["required_refs"]):
            ref = artifact_ref_from_dict(document)
            if ref.media_type == RISK_ANNOTATION_MEDIA_TYPE:
                annotation_document = json.loads(history.artifact_store.locate(ref))
                assert annotation_document["table_name"] == "t"
                annotations = annotation_document["annotations"]
                break
        assert annotations
        assert [item["annotation_id"] for item in annotations] == [f"t:{index:08d}" for index in range(len(annotations))]
        assert all(item["target"]["table_name"] == "t" for item in annotations)
        closures = []
        for document in cast(list[dict[str, object]], state["required_refs"]):
            ref = artifact_ref_from_dict(document)
            if ref.media_type == "application/json":
                raw = json.loads(history.artifact_store.locate(ref))
                if isinstance(raw, dict) and "closure_contract_version" in raw and "facts_core_digest" in raw:
                    closures.append(open_records_closure(history.artifact_store, ref))
                    break
        assert len(closures) == 1
        assert closures[0].comparison_digest.value == current_pair["comparison_digest"]
        assert sum(entry.record_count for entry in closures[0].records) == 2
        content = tuple(entry.records_content_digest.value for entry in closures[0].records)
        if name == "full-warm":
            assert content == seen_content["full-first"]
            assert all(not _reader_names(provider) for provider in providers.values())
        seen_content[name] = content
        seen_producers[name] = history.operation_id


AUTHORITY_RESTORE_FAILURES = (
    ("open_timeout", "repository.repository_ref_open_timeout"),
    ("catalog_error", "REPOSITORY_CATALOG_LOAD_FAILED"),
)


@pytest.mark.parametrize(("fault", "expected_code"), AUTHORITY_RESTORE_FAILURES)
def test_history_fresh_authority_keeps_original_provider_failure_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, expected_code: str,
) -> None:
    from gateway_backend.operations.recovery import HandlerExecutionFailure

    harness = build_history_compare_harness(tmp_path)
    insert_history_compare_operation(harness)
    materialized = run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    assert materialized.status is StepStatus.SUCCEEDED
    provider = harness.providers[BASELINE_HEAD.business_baseline_commit_id]
    monkeypatch.setattr(provider, fault, True)
    if fault == "open_timeout":
        with pytest.raises(HandlerExecutionFailure) as failure:
            run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
        assert failure.value.retryable is True
        assert failure.value.diagnostic_code == expected_code
    else:
        assembled = run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
        assert assembled.status is StepStatus.FAILED
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
            operation = uow.operations.get_operation(harness.operation_id)
        assert operation.status is OperationStatus.FAILED
        assert operation.diagnostic is not None and operation.diagnostic.code == expected_code
    assert all(not _reader_names(source) for source in harness.providers.values())


def test_history_pipeline_failure_keeps_its_original_runtime_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_history_compare_harness(tmp_path)
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    def failed_pipeline(**kwargs: Any) -> Any:
        raise compare_jobs.HistoryCompareJobError("risk evaluation failed")
    monkeypatch.setattr(compare_jobs, "_assemble_comparison", failed_pipeline)
    with pytest.raises(compare_jobs.HistoryCompareJobError, match="risk evaluation failed"):
        run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        operation = uow.operations.get_operation(harness.operation_id)
    assert operation.status is OperationStatus.RUNNING
    assert operation.diagnostic is None


@pytest.mark.parametrize("field_name", ["ready_closure_artifact_id", "bundle_artifact_id"])
@pytest.mark.parametrize("artifact_id", ["old-closure", "a1:unknown:" + "a" * 64,
    "00000000-0000-4000-8000-000000000001"])
def test_history_assemble_checkpoint_rejects_unsupported_bare_refs(field_name: str, artifact_id: str) -> None:
    from gateway_backend.application.history.compare_jobs import _history_compare_ready_ref
    from gateway_backend.application.payloads import CheckpointDecodeError
    ready_id = "a1:durable:" + "0" * 64
    state: dict[str, object] = {"ready_closure_artifact_id": ready_id,
        "bundle_artifact_id": "a1:export:" + "1" * 64,
        "ready_closure_ref": {"artifact_id": ready_id, "media_type": "application/jcs",
            "size_bytes": 0, "raw_sha256": "sha256:" + "0" * 64}}
    state[field_name] = artifact_id
    with pytest.raises(CheckpointDecodeError, match="invalid artifact bindings"):
        _history_compare_ready_ref(state)


@pytest.mark.parametrize('damaged_side', ('same-commit-later-table', 'later-commit'))
def test_history_repairs_damaged_exact_commit_before_retaining_batch_readers(
    tmp_path: Path, damaged_side: str,
) -> None:
    import pyarrow as pa
    from gateway_backend.artifacts.serialize import artifact_ref_from_json

    left = BASELINE_HEAD.business_baseline_commit_id
    right = 'commit-repair-right'
    local = open_test_store(tmp_path / 'repair-artifacts')
    def providers() -> dict[str, FakeRepositoryTableAccessProvider]:
        result = {}
        for commit, value in ((left, 1), (right, 2)):
            catalog = make_catalog((catalog_table('a', (int_id_column(),), row_count=1),
                catalog_table('z', (int_id_column(),), row_count=1)),
                repository_id=REPOSITORY_ID, ref=commit, commit=commit)
            rows = {'a': ((value,),), 'z': ((value + 10,),)}
            result[commit] = FakeRepositoryTableAccessProvider(catalog=catalog,
                rows=rows, declared_rows=rows, current_commit=commit)
        return result
    cold = build_history_compare_harness(tmp_path / 'cold', artifact_store=local,
        node_specs=((BASELINE_HEAD.business_baseline_node_id, left), ('bn-repair-right', right)),
        custom_providers=providers(), idempotency_key='repair-cold')
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, NeverCancel, kernel_execution_scope,
    )
    with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(8 * 1024**3), NeverCancel(), 1), new_operation=True):
        run_full_history_compare_job(cold)
    with local.cleanup_session("a1:canonical:" + "0" * 64) as acquired:
        assert acquired  # The completed cold operation has released every mapping.
    target_commit, target_value = (left, 11) if damaged_side == 'same-commit-later-table' else (right, 2)
    with ControlDbUnitOfWork(cold.db_path, read_only=True) as uow:
        ids = [row[0] for row in uow.connection.execute(
            'SELECT artifact_id FROM canonical_commit_tables WHERE repository_id=? AND commit_id=?',
            (REPOSITORY_ID, target_commit))]
    assert len(ids) == 2
    damaged_ref = None
    for artifact_id in ids:
        path = local.payload_path(artifact_id)
        with pa.memory_map(str(path), 'r') as mapped:
            value = pa.ipc.open_file(mapped).read_all().column(0)[0].as_py()
        if value == target_value:
            damaged_ref = artifact_ref_from_json((local.object_directory(artifact_id) / 'ref.jcs').read_bytes())
            break
    assert damaged_ref is not None
    original = local.payload_path(damaged_ref.artifact_id).read_bytes()
    local.payload_path(damaged_ref.artifact_id).write_bytes(b'corrupt')
    warm = build_history_compare_harness(tmp_path / 'warm', db_path=cold.db_path, artifact_store=local,
        node_specs=((BASELINE_HEAD.business_baseline_node_id, left), ('bn-repair-warm-right', right)),
        custom_providers=providers(), idempotency_key='repair-warm')
    with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(8 * 1024**3), NeverCancel(), 1), new_operation=True):
        run_full_history_compare_job(warm)
    assert local.locate(damaged_ref) == original
    cold_rows, _ = _history_snapshot_bundle_data(cold)
    warm_rows, _ = _history_snapshot_bundle_data(warm)
    assert {(side, table): rows for (_pair, side, table), rows in cold_rows.items()} == {
        (side, table): rows for (_pair, side, table), rows in warm_rows.items()}
    with ControlDbUnitOfWork(warm.db_path, read_only=True) as uow:
        assert uow.operations.get_operation(warm.operation_id).status is OperationStatus.SUCCEEDED
