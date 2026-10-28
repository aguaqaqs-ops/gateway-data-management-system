"""History compare job pipeline tests."""

from __future__ import annotations

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
    HistoryCompareNodeBinding,
    HistoryNodeRefKind,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_HANDLER,
    HISTORY_COMPARE_MATERIALIZE_HANDLER,
    HISTORY_COMPARE_PUBLISH_HANDLER,
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
    HistoryCompareJobPayload,
    _history_requested_tables,
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
    CanonicalBinding,
    CanonicalTableIdentity,
    RepositoryCatalogTable,
    RepositoryColumn,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    OrderedPolicy,
    StorageRuleView,
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

from tests.support.history_compare_oracle import (
    compare_bound_snapshots,
    materialize_bound_snapshot,
    oracle_comparison_digest,
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
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (None, 2, "blank"))},
        (),
        0,
    ),
    (
        "keyed_ignored_column",
        {ORDERED_SYX_TABLE: ((1, 1, "a"), (2, 2, "b"))},
        {ORDERED_SYX_TABLE: ((1, 99, "a"), (2, 2, "b"))},
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
    sides = _sides_from_materialize_checkpoint(envelope.job_state, harness.artifact_store)
    assert set(sides) == {BASELINE_HEAD.business_baseline_commit_id}
    assert set(envelope.job_state) == {"materialized_sides_ref"}


def test_history_materialization_selects_changed_commit_tables() -> None:
    def binding(
        tables: tuple[tuple[str, bytes, bytes, bool], ...],
    ) -> CanonicalBinding:
        views: list[StorageRuleView] = []
        identities: list[CanonicalTableIdentity] = []
        for name, schema_bytes, content_bytes, ordered in tables:
            views.append(
                StorageRuleView(
                    canonical_table=name,
                    canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
                    ordered_policy=OrderedPolicy.GID_NO_V1 if ordered else OrderedPolicy.NONE,
                    structural_columns=("no",) if ordered else (),
                    retained_columns=("gid", "no") if ordered else (),
                )
            )
            schema_digest = raw_blob_digest(schema_bytes)
            identities.append(
                CanonicalTableIdentity(
                    canonical_table=name,
                    row_count=1,
                    source_schema_digest=schema_digest,
                    canonical_schema_digest=schema_digest,
                    raw_content_digest=raw_blob_digest(content_bytes),
                )
            )
        return CanonicalBinding(
            storage_projection_version="storage-projection/v3",
            ruleset_id="history-test-rules",
            ruleset_version="v4",
            ruleset_digest=raw_blob_digest(b"history-test-ruleset"),
            tables=tuple(sorted(views, key=lambda item: item.canonical_table.encode("utf-8"))),
            table_identities=tuple(
                sorted(identities, key=lambda item: item.canonical_table.encode("utf-8"))
            ),
        )

    before = binding(
        (
            ("unchanged", b"schema", b"same", False),
            ("changed_content", b"schema", b"before", False),
            ("changed_schema", b"schema-before", b"same", False),
            ("removed", b"schema", b"removed", False),
            ("ordered", b"ordered-schema", b"same", True),
        )
    )
    current = binding(
        (
            ("unchanged", b"schema", b"same", False),
            ("changed_content", b"schema", b"current", False),
            ("changed_schema", b"schema-current", b"same", False),
            ("added", b"schema", b"added", False),
            ("ordered", b"ordered-schema", b"same", True),
        )
    )
    payload = HistoryCompareJobPayload(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id=REPOSITORY_ID,
        acceptance_id="acceptance-1",
        idempotency_key="history-materialize-selection",
        request_fingerprint="fingerprint-1",
        comparison_ruleset_digest="sha256:" + "a" * 64,
        comparison_contract_version="backend-vnext/comparison/v3",
        view_kind="HISTORY",
        pair_count=1,
        nodes=(
            HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, "node-a", "commit-a"),
            HistoryCompareNodeBinding(HistoryNodeRefKind.SUBMISSION, "node-b", "commit-b"),
        ),
    )

    assert _history_requested_tables(payload, {"commit-a": before, "commit-b": current}) == {
        "commit-a": ("changed_content", "changed_schema", "removed"),
        "commit-b": ("added", "changed_content", "changed_schema", "ordered"),
    }

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
        harness.artifact_store,
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
    assert pair["comparison_digest"] == oracle_comparison_digest(
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
    baseline_reader_names = tuple(
        reader.catalog_table().table_name for reader in baseline_session.table_readers
    )
    assert baseline_reader_names == ("t",)
    current_reader_names = tuple(
        reader.catalog_table().table_name for reader in current_session.table_readers
    )
    assert current_reader_names == ("t",)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        publish_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_PUBLISH)
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert publish_step.status is StepStatus.SUCCEEDED
    assert operation.ready_closure_ref is not None
    rows_by_binding, snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = f"{harness.operation_id}-p0"
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

        def discard_many(self, keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> None:
            for key in keys:
                self.entries.pop(key, None)

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
    cold_reader_names = tuple(
        reader.catalog_table().table_name for reader in cold_before.table_readers
    )
    assert cold_reader_names == expected_reader_names
    assert cold_current.table_readers == []
    assert len(cache.entries) == 2
    cold_rows, cold_entries = _history_snapshot_bundle_data(cold)
    cold_pair_id = f"{cold.operation_id}-p0"
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
        artifact_store=store,
        snapshot_export_cache=cache,
        node_specs=(
            (BASELINE_HEAD.business_baseline_node_id, before_commit),
            ("bn-export-cache-current", current_commit),
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
    warm_pair_id = f"{warm.operation_id}-p0"
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
    assert tuple(reader.catalog_table().table_name for reader in before_session.table_readers) == (
        "gone",
        "t",
    )
    assert tuple(reader.catalog_table().table_name for reader in current_session.table_readers) == (
        "added",
        "t",
    )
    rows_by_binding, _snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = f"{harness.operation_id}-p0"
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
    assert tuple(reader.catalog_table().table_name for reader in before_session.table_readers) == (
        ORDERED_SYX_TABLE,
    )
    assert tuple(reader.catalog_table().table_name for reader in current_session.table_readers) == (
        ORDERED_SYX_TABLE,
    )

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
    assert pair["comparison_digest"] == oracle_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )
    rows_by_binding, snapshot_entries = _history_snapshot_bundle_data(harness)
    pair_id = f"{harness.operation_id}-p0"
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
    assert pairs[0]["pair_id"] == f"{harness.operation_id}-p0"
    assert pairs[1]["pair_id"] == f"{harness.operation_id}-p1"
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
    pair_ids = (f"{harness.operation_id}-p0", f"{harness.operation_id}-p1")
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
        declared_rows={"t": ((1,),)},
    )
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: provider,
            "commit-b": history_compare_provider(commit_id="commit-b"),
        },
        idempotency_key="history-compare-row-count-mismatch",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        materialize_step = unit_of_work.operations.get_step(
            history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
    assert operation.status is OperationStatus.FAILED
    assert materialize_step.status is StepStatus.FAILED
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

    oracle_digest = oracle_comparison_digest(
        before_provider=providers[before_commit],
        current_provider=providers[current_commit],
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=harness.artifact_store,
    )
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
    kinds: list[OrderedRecordKind] = []
    for table in facts.tables:
        extension = table.ordered_extension
        if extension is not None:
            kinds.extend(record.record_kind for record in extension.records)
    assert kinds == list(expected_kinds)
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
    assert pair["comparison_digest"] == oracle_digest


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
    kinds: list[OrderedRecordKind] = []
    for table in facts.tables:
        extension = table.ordered_extension
        if extension is not None:
            kinds.extend(record.record_kind for record in extension.records)
    assert kinds == []
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
