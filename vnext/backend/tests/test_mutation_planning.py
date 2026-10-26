"""S2 mutation planner, eligibility and ChangeSet closure tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, cast

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.mutation_planning import (
    MutationExecutionContext,
    MutationFailureCode,
    MutationPlanStatus,
    MutationPolicy,
    TableMutationKind,
    change_set_closure_document,
    plan_storage_mutation,
    validate_published_change_set_closure,
)
from gateway_backend.capabilities.mutation_planning import _artifacts as mutation_artifacts
from gateway_backend.capabilities.mutation_planning._planner import _patch_eligible
from gateway_backend.capabilities.mutation_planning._digest import key_bytes_for_ordering
from gateway_backend.capabilities.mutation_planning.contracts import (
    ChangeSetArtifact,
    CanonicalStorageKey,
    MutationKeyedRow,
    MutationPlanningRequest,
    MutationPlanningResult,
    MutationThresholdPolicy,
    MutationTableSnapshot,
    PersistedRowImage,
    RowMutationOperation,
)
from gateway_backend.capabilities.mutation_planning._digest import row_digest_from_image
from gateway_backend.capabilities.mutation_planning._repository_replay_renderer import (
    render_change_set_replay,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    OrderedPolicy,
    StorageRuleView,
)
from tests.support.mutation_contracts import (
    digest,
    keyed_row,
    manifest,
    manifest_table,
    planning_request,
    projection_binding,
    row_image,
    storage_key,
    storage_view,
    table_snapshot,
)

pytestmark = pytest.mark.unit

_FORBIDDEN_CLOSURE_KEYS = frozenset({"sql_text", "replay_sql", "checkpoint"})


@dataclass(frozen=True, slots=True)
class _CancelProbe:
    cancelled: bool = False

    def is_set(self) -> bool:
        return self.cancelled


def _plan(
    request: MutationPlanningRequest,
    *,
    store: InMemoryArtifactStore | None = None,
) -> MutationPlanningResult:
    return plan_storage_mutation(request, artifact_store=store)


def _rows(count: int, *, status_for: set[int] | None = None) -> tuple[MutationKeyedRow, ...]:
    status_for = status_for or set()
    rows = [
        keyed_row(board=str(index), link_no="0", status="1" if index in status_for else "9")
        for index in range(count)
    ]
    return tuple(sorted(rows, key=lambda row: key_bytes_for_ordering(row.key)))


def _snapshot_with_rows(
    *,
    table: str = "orders",
    before_count: int,
    after_count: int,
    changed_after: set[int] | None = None,
    schema_digest_before: DigestRef | None = None,
    schema_digest_after: DigestRef | None = None,
) -> tuple[MutationTableSnapshot, MutationTableSnapshot]:
    before = table_snapshot(
        table=table,
        rows=_rows(before_count),
        schema_digest=schema_digest_before,
    )
    after_rows = _rows(after_count, status_for=changed_after or set())
    after = table_snapshot(
        table=table,
        rows=after_rows,
        schema_digest=schema_digest_after,
        content_digest=raw_blob_digest(f"after:{after_count}:{changed_after}".encode()),
    )
    if before_count == after_count and not changed_after:
        after = replace(
            after,
            manifest_table=replace(
                after.manifest_table,
                content_digest=before.manifest_table.content_digest,
            ),
        )
    return before, after


R7_MUTATION_BASELINE_CASES: tuple[tuple[str, object], ...] = (
    ("dual_empty_noop", {"before": (), "after": (), "expect": MutationPlanStatus.NOOP}),
    (
        "first_load_rebuild",
        {
            "before": (),
            "after": (table_snapshot(rows=(keyed_row(),)),),
            "expect": MutationPlanStatus.READY,
            "operation": TableMutationKind.REBUILD_TABLE,
        },
    ),
    (
        "unchanged_noop",
        {
            "before": (table_snapshot(rows=(keyed_row(),)),),
            "after": (table_snapshot(rows=(keyed_row(),)),),
            "expect": MutationPlanStatus.NOOP,
        },
    ),
)

R7_REBUILD_PATCH_NOOP_CASES: tuple[tuple[str, object], ...] = (
    (
        "rebuild_always_single_update",
        {
            "policy": MutationPolicy.REBUILD_ALWAYS,
            "changed": {0},
            "operation": TableMutationKind.REBUILD_TABLE,
        },
    ),
    (
        "adaptive_patch_single_update",
        {
            "policy": MutationPolicy.ADAPTIVE_PATCH,
            "before_count": 100,
            "after_count": 100,
            "changed": {0},
            "operation": TableMutationKind.PATCH_DML,
        },
    ),
    (
        "table_noop_in_mixed_plan",
        {
            "policy": MutationPolicy.ADAPTIVE_PATCH,
            "before_count": 100,
            "after_count": 100,
            "changed": {0},
            "extra_unchanged_table": "inventory",
            "operations": {
                "orders": TableMutationKind.PATCH_DML,
                "inventory": TableMutationKind.NOOP,
            },
        },
    ),
)

R7_SCHEMA_KEY_PROJECTION_CHANGE_CASES: tuple[tuple[str, object], ...] = (
    (
        "schema_digest_change",
        {
            "schema_before": digest("aa"),
            "schema_after": digest("bb"),
            "operation": TableMutationKind.REBUILD_TABLE,
        },
    ),
    (
        "key_columns_change",
        {
            "key_before": ("board", "link_no"),
            "key_after": ("board",),
            "operation": TableMutationKind.REBUILD_TABLE,
        },
    ),
)

R7_DESTRUCTIVE_CONFIRMATION_CASES: tuple[tuple[str, object], ...] = (
    (
        "without_confirmation",
        {
            "granted": False,
            "expect": MutationPlanStatus.CONFIRMATION_REQUIRED,
            "publishes": False,
        },
    ),
    (
        "with_confirmation",
        {
            "granted": True,
            "expect": MutationPlanStatus.READY,
            "publishes": True,
        },
    ),
)

THRESHOLD_BOUNDARY_CASES: tuple[tuple[str, object], ...] = (
    (
        "ratio_at_boundary_patch",
        {
            "row_count": 100,
            "changed_row_count": 1,
            "eligible": True,
        },
    ),
    (
        "ratio_over_boundary_rebuild",
        {
            "row_count": 100,
            "changed_row_count": 2,
            "eligible": False,
        },
    ),
    (
        "count_at_boundary_patch",
        {
            "row_count": 100_000,
            "changed_row_count": 1000,
            "eligible": True,
        },
    ),
    (
        "count_over_boundary_rebuild",
        {
            "row_count": 100_100,
            "changed_row_count": 1001,
            "eligible": False,
        },
    ),
)


@pytest.mark.parametrize(("case_id", "case"), R7_MUTATION_BASELINE_CASES)
def test_mutation_baseline_cases(case_id: str, case: dict[str, object]) -> None:
    request = planning_request(
        before_tables=case["before"],  # type: ignore[arg-type]
        after_tables=case["after"],  # type: ignore[arg-type]
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is case["expect"]
    if result.status is MutationPlanStatus.NOOP:
        assert result.change_set_closure is None
        assert result.published_closure is None
        return
    assert result.plan is not None
    summary = result.plan.table_summaries[0]
    assert summary.operation is case["operation"]


@pytest.mark.parametrize(("case_id", "case"), R7_REBUILD_PATCH_NOOP_CASES)
def test_rebuild_patch_noop_cases(case_id: str, case: dict[str, Any]) -> None:
    before_count = int(case.get("before_count", 2))
    after_count = int(case.get("after_count", 2))
    before, after = _snapshot_with_rows(
        before_count=before_count,
        after_count=after_count,
        changed_after=cast(set[int], case["changed"]),
    )
    before_tables: tuple[MutationTableSnapshot, ...] = (before,)
    after_tables: tuple[MutationTableSnapshot, ...] = (after,)
    if case.get("extra_unchanged_table"):
        table = str(case["extra_unchanged_table"])
        row = keyed_row(board="9", link_no="9")
        before_tables = (table_snapshot(table=table, rows=(row,)), before)
        after_tables = (table_snapshot(table=table, rows=(row,)), after)
    request = planning_request(
        policy=cast(MutationPolicy, case["policy"]),
        before_tables=before_tables,
        after_tables=after_tables,
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.READY
    assert result.plan is not None
    by_table = {item.canonical_table: item.operation for item in result.plan.table_summaries}
    expected_ops = case.get("operations") or {before.manifest_table.name: case["operation"]}
    for table, operation in cast(dict[str, TableMutationKind], expected_ops).items():
        assert by_table[table] is operation


@pytest.mark.parametrize(("case_id", "case"), R7_SCHEMA_KEY_PROJECTION_CHANGE_CASES)
def test_schema_key_projection_change_cases(case_id: str, case: dict[str, object]) -> None:
    before = table_snapshot(rows=(keyed_row(),), schema_digest=case.get("schema_before"))  # type: ignore[arg-type]
    after_manifest = manifest_table(
        schema_digest=case.get("schema_after"),  # type: ignore[arg-type]
        row_count=1,
    )
    if case.get("key_after"):
        after_manifest = replace(
            after_manifest,
            canonical_key_columns=case["key_after"],  # type: ignore[arg-type]
        )
    if case.get("key_before"):
        before = replace(
            before,
            manifest_table=replace(
                before.manifest_table,
                canonical_key_columns=case["key_before"],  # type: ignore[arg-type]
            ),
        )
    after = replace(
        table_snapshot(rows=(keyed_row(),)),
        manifest_table=after_manifest,
    )
    request = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=(before,),
        after_tables=(after,),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.READY
    assert result.plan is not None
    assert result.plan.table_summaries[0].operation is case["operation"]


@pytest.mark.parametrize(("case_id", "case"), R7_DESTRUCTIVE_CONFIRMATION_CASES)
def test_destructive_confirmation_cases(case_id: str, case: dict[str, object]) -> None:
    before = table_snapshot(rows=(keyed_row(),))
    request = planning_request(
        before_tables=(before,),
        after_tables=(),
        destructive_confirmation_granted=bool(case["granted"]),
    )
    store = InMemoryArtifactStore()
    before_refs = set(store._artifacts)
    result = _plan(request, store=store)
    assert result.status is case["expect"]
    if not case["publishes"]:
        assert result.change_set_closure is None
        assert result.published_closure is None
        assert result.failure_code is MutationFailureCode.CONFIRMATION_REQUIRED
        assert set(store._artifacts) == before_refs
        return
    assert result.change_set_closure is not None
    assert result.published_closure is not None
    validate_published_change_set_closure(
        store,
        result.published_closure,
        expected_closure=result.change_set_closure,
    )


@pytest.mark.parametrize(("case_id", "case"), THRESHOLD_BOUNDARY_CASES)
def test_threshold_boundary_cases(case_id: str, case: dict[str, Any]) -> None:
    before = table_snapshot(rows=(keyed_row(),))
    after = table_snapshot(rows=(keyed_row(board="9"),))
    eligible = _patch_eligible(
        before,
        after,
        changed_row_count=int(case["changed_row_count"]),
        before_row_count=int(case["row_count"]),
        after_row_count=int(case["row_count"]),
        threshold=MutationThresholdPolicy(),
    )
    assert eligible is case["eligible"]


def test_submit_count_examples_match_hand_computed_net_changes() -> None:
    before, after = _snapshot_with_rows(before_count=1000, after_count=1002)
    inserted = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(after,),
        ),
        store=InMemoryArtifactStore(),
    )
    assert inserted.plan is not None and inserted.change_set_closure is not None
    inserted_summary = inserted.plan.table_summaries[0]
    assert inserted_summary.operation is TableMutationKind.PATCH_DML
    assert inserted_summary.changed_row_count == 2
    assert [item.operation for item in inserted.change_set_closure.mutations] == [
        RowMutationOperation.INSERT,
        RowMutationOperation.INSERT,
    ]

    before_rows = _rows(1000)
    after_rows = list(before_rows)
    after_rows[0] = keyed_row(board="1000", link_no="0")
    after_key_change = table_snapshot(
        rows=tuple(sorted(after_rows, key=lambda row: key_bytes_for_ordering(row.key))),
        content_digest=raw_blob_digest(b"key-change"),
    )
    key_changed = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(table_snapshot(rows=before_rows),),
            after_tables=(after_key_change,),
        ),
        store=InMemoryArtifactStore(),
    )
    assert key_changed.plan is not None and key_changed.change_set_closure is not None
    key_change_summary = key_changed.plan.table_summaries[0]
    assert key_change_summary.operation is TableMutationKind.PATCH_DML
    assert key_change_summary.changed_row_count == 2
    assert sorted(item.operation for item in key_changed.change_set_closure.mutations) == [
        RowMutationOperation.DELETE,
        RowMutationOperation.INSERT,
    ]

    before, after = _snapshot_with_rows(
        before_count=100,
        after_count=100,
        changed_after=set(range(6)),
    )
    rebuilt = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(after,),
        ),
        store=InMemoryArtifactStore(),
    )
    assert rebuilt.plan is not None
    rebuild_summary = rebuilt.plan.table_summaries[0]
    assert rebuild_summary.operation is TableMutationKind.REBUILD_TABLE
    assert rebuild_summary.changed_row_count == 6
    assert rebuild_summary.after_row_count == 100


def test_submit_table_level_counts_for_added_and_deleted_tables() -> None:
    added = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(),
            after_tables=(table_snapshot(table="added", rows=_rows(7)),),
        ),
        store=InMemoryArtifactStore(),
    )
    assert added.plan is not None
    added_summary = added.plan.table_summaries[0]
    assert added_summary.canonical_table == "added"
    assert added_summary.operation is TableMutationKind.REBUILD_TABLE
    assert added_summary.changed_row_count == 7
    assert added_summary.after_row_count == 7

    deleted = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(table_snapshot(table="deleted", rows=_rows(10)),),
            after_tables=(),
            destructive_confirmation_granted=True,
        ),
        store=InMemoryArtifactStore(),
    )
    assert deleted.plan is not None
    deleted_summary = deleted.plan.table_summaries[0]
    assert deleted_summary.canonical_table == "deleted"
    assert deleted_summary.operation is TableMutationKind.REBUILD_TABLE
    assert deleted_summary.changed_row_count == 10
    assert deleted_summary.after_row_count == 0


def test_gid_no_v1_table_is_patchable_within_the_frozen_threshold() -> None:
    retained = ("gid", "no", "value")
    view = StorageRuleView(
        canonical_table="t",
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.GID_NO_V1,
        retained_columns=retained,
        canonical_key_columns=("gid",),
        structural_columns=("no",),
        dropped_columns=(),
    )
    manifest_table_value = manifest_table(table="t", row_count=100)
    manifest_table_value = replace(
        manifest_table_value,
        ordered_policy=OrderedPolicy.GID_NO_V1,
        retained_columns=retained,
        structural_columns=("no",),
        canonical_key_columns=("gid",),
    )

    def rows(changed: set[int]) -> tuple[MutationKeyedRow, ...]:
        result: list[MutationKeyedRow] = []
        for index in range(1, 101):
            gid = {"kind": "unsigned-integer", "decimal": str(index)}
            image = PersistedRowImage(
                columns=(
                    ("gid", gid),
                    ("no", {"kind": "signed-integer", "decimal": str(index)}),
                    (
                        "value",
                        {"kind": "string", "text": "changed" if index - 1 in changed else "stable"},
                    ),
                )
            )
            result.append(
                MutationKeyedRow(
                    key=CanonicalStorageKey(columns=(("gid", gid),)),
                    image=image,
                    row_digest=row_digest_from_image(image, retained_columns=retained),
                )
            )
        result.sort(key=lambda row: key_bytes_for_ordering(row.key))
        return tuple(result)

    before_rows = rows(set())
    for changed, expected in (
        ({0}, TableMutationKind.PATCH_DML),
        ({0, 1}, TableMutationKind.REBUILD_TABLE),
    ):
        after_rows = rows(changed)
        before = MutationTableSnapshot(
            manifest_table=replace(manifest_table_value, canonical_row_count=100),
            storage_view=view,
            rows=before_rows,
        )
        after = MutationTableSnapshot(
            manifest_table=replace(
                manifest_table_value,
                canonical_row_count=100,
                content_digest=raw_blob_digest(f"ordered:{changed}".encode()),
            ),
            storage_view=view,
            rows=after_rows,
        )
        request = planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(after,),
        )
        result = _plan(request, store=InMemoryArtifactStore())
        assert result.status is MutationPlanStatus.READY
        assert result.plan is not None
        assert result.plan.table_summaries[0].operation is expected


def test_change_set_identity_is_stable_and_order_independent() -> None:
    before_a, after_a = _snapshot_with_rows(before_count=3, after_count=3, changed_after={1})
    before_b, after_b = _snapshot_with_rows(before_count=3, after_count=3, changed_after={1})
    request_a = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=(before_a,),
        after_tables=(after_a,),
    )
    request_b = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=(before_b,),
        after_tables=(after_b,),
    )
    first = _plan(request_a)
    second = _plan(request_b)
    assert first.plan is not None and second.plan is not None
    assert (
        first.plan.mutation_plan_identity_digest
        == second.plan.mutation_plan_identity_digest
    )
    assert first.change_set_closure is not None and second.change_set_closure is not None
    assert (
        first.change_set_closure.closure_digest
        == second.change_set_closure.closure_digest
    )

    before_tables = (
        table_snapshot(table="alpha", rows=_rows(2)),
        table_snapshot(table="beta", rows=_rows(20)),
    )
    after_tables = (
        table_snapshot(table="alpha", rows=_rows(2)),
        table_snapshot(
            table="beta",
            rows=_rows(20, status_for={0}),
            content_digest=raw_blob_digest(b"beta-changed"),
        ),
    )
    request_ordered = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=before_tables,
        after_tables=after_tables,
    )
    ordered_first = _plan(request_ordered)
    ordered_second = _plan(request_ordered)
    assert ordered_first.change_set_closure is not None
    assert ordered_second.change_set_closure is not None
    assert (
        ordered_first.change_set_closure.closure_digest
        == ordered_second.change_set_closure.closure_digest
    )
    assert ordered_first.plan is not None
    table_names = [item.canonical_table for item in ordered_first.plan.table_summaries]
    assert table_names == sorted(table_names)


def test_ready_closure_document_has_no_sql_or_checkpoint_fields() -> None:
    before, after = _snapshot_with_rows(before_count=100, after_count=100, changed_after={0})
    result = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(after,),
        ),
        store=InMemoryArtifactStore(),
    )
    assert result.change_set_closure is not None
    artifact = ChangeSetArtifact(
        manifest=result.change_set_closure.manifest,
        mutations=result.change_set_closure.mutations,
    )
    document = change_set_closure_document(artifact)
    payload = json.loads(canonicalize_json_value(document).decode())
    assert _FORBIDDEN_CLOSURE_KEYS.isdisjoint(_collect_keys(payload))
    update_ops = [
        item
        for item in result.change_set_closure.mutations
        if item.operation is RowMutationOperation.UPDATE
    ]
    assert len(update_ops) == 1
    assert update_ops[0].before_row_digest is not None
    assert update_ops[0].after_image is not None


def test_source_literal_anomaly_fails_closed_without_closure() -> None:
    anomaly_image = row_image(status="9")
    anomaly_image = replace(
        anomaly_image,
        columns=(
            ("board", {"kind": "signed-integer", "decimal": "1"}),
            ("link_no", {"kind": "signed-integer", "decimal": "2"}),
            ("status", {"kind": "source-literal-anomaly", "envelope": {"raw": "x"}}),
        ),
    )
    before_row = MutationKeyedRow(
        key=storage_key(),
        image=anomaly_image,
        row_digest=raw_blob_digest(b"anomaly-before"),
    )
    after_row = keyed_row(status="1")
    request = planning_request(
        before_tables=(table_snapshot(rows=(before_row,)),),
        after_tables=(table_snapshot(rows=(after_row,)),),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.FAILED
    assert result.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED
    assert result.change_set_closure is None


def test_source_literal_anomaly_in_key_fails_closed_without_closure() -> None:
    anomaly_key = CanonicalStorageKey(
        columns=(("board", {"kind": "source-literal-anomaly", "envelope": {"raw": "x"}}),)
    )
    before_row = MutationKeyedRow(
        key=anomaly_key,
        image=row_image(),
        row_digest=raw_blob_digest(b"anomaly-key-before"),
    )
    request = planning_request(
        before_tables=(table_snapshot(rows=(before_row,)),),
        after_tables=(),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.FAILED
    assert result.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED
    assert result.change_set_closure is None


def test_mixed_plan_closure_manifest_keeps_noop_table_summary() -> None:
    before, after = _snapshot_with_rows(before_count=20, after_count=20, changed_after={0})
    unchanged = table_snapshot(table="inventory", rows=(keyed_row(board="9", link_no="9"),))
    result = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(unchanged, before),
            after_tables=(unchanged, after),
        )
    )
    assert result.change_set_closure is not None
    assert [item.canonical_table for item in result.change_set_closure.manifest.table_summaries] == [
        "inventory",
        "orders",
    ]
    assert {item.canonical_table for item in result.change_set_closure.mutations} == {"orders"}


def test_cancellation_fails_closed() -> None:
    before, after = _snapshot_with_rows(before_count=1, after_count=1, changed_after={0})
    probe = _CancelProbe(cancelled=True)
    request = planning_request(
        before_tables=(before,),
        after_tables=(after,),
    )
    request = replace(
        request,
        planning_input=replace(
            request.planning_input,
            context=MutationExecutionContext(cancel_requested=probe),
        ),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.FAILED
    assert result.failure_code is MutationFailureCode.FAILED


def test_byte_cap_returns_resource_exceeded_without_new_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    before, after = _snapshot_with_rows(before_count=5, after_count=5, changed_after=set(range(5)))
    request = planning_request(
        policy=MutationPolicy.REBUILD_ALWAYS,
        before_tables=(before,),
        after_tables=(after,),
    )
    store = InMemoryArtifactStore()
    before_refs = set(store._artifacts)
    monkeypatch.setattr(mutation_artifacts, "MAX_CHANGE_SET_JSON_BYTES", 1)
    result = _plan(request, store=store)
    assert result.status is MutationPlanStatus.FAILED
    assert result.failure_code is MutationFailureCode.RESOURCE_EXCEEDED
    assert set(store._artifacts) == before_refs


def test_empty_before_non_empty_after_never_patch_dml() -> None:
    request = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=(),
        after_tables=(table_snapshot(rows=(keyed_row(),)),),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.READY
    assert result.plan is not None
    assert result.plan.table_summaries[0].operation is TableMutationKind.REBUILD_TABLE


def test_non_keyed_table_with_row_changes_rebuilds() -> None:
    view = storage_view()
    view = replace(view, canonical_key_policy=CanonicalKeyPolicy.NONE, canonical_key_columns=())
    before = replace(table_snapshot(rows=(keyed_row(),)), storage_view=view)
    after = replace(
        table_snapshot(rows=(keyed_row(status="1"),)),
        storage_view=view,
        manifest_table=replace(
            table_snapshot(rows=(keyed_row(status="1"),)).manifest_table,
            canonical_key_policy=CanonicalKeyPolicy.NONE,
            canonical_key_columns=(),
        ),
    )
    before_manifest = manifest(tables=(before.manifest_table,))
    after_manifest = manifest(tables=(after.manifest_table,))
    binding = projection_binding(
        before_manifest=before_manifest.manifest_digest,
        after_manifest=after_manifest.manifest_digest,
    )
    request = planning_request(
        policy=MutationPolicy.ADAPTIVE_PATCH,
        before_tables=(before,),
        after_tables=(after,),
    )
    request = replace(
        request,
        before_manifest=before_manifest,
        after_manifest=after_manifest,
        planning_input=replace(request.planning_input, projection_binding=binding),
    )
    result = _plan(request, store=InMemoryArtifactStore())
    assert result.status is MutationPlanStatus.READY
    assert result.plan is not None
    assert result.plan.table_summaries[0].operation is TableMutationKind.REBUILD_TABLE


def test_keyless_multiset_changes_rebuild_and_identical_multisets_are_noop() -> None:
    before = _keyless_snapshot(_keyless_rows("9", "9", "1"))
    same = _keyless_snapshot(_keyless_rows("1", "9", "9"))
    changed = _keyless_snapshot(_keyless_rows("0", "9", "9"))

    unchanged_result = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(same,),
        )
    )
    assert unchanged_result.status is MutationPlanStatus.NOOP

    changed_result = _plan(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(before,),
            after_tables=(changed,),
        )
    )
    assert changed_result.status is MutationPlanStatus.READY
    assert changed_result.plan is not None
    assert changed_result.plan.table_summaries[0].operation is TableMutationKind.REBUILD_TABLE
    assert changed_result.plan.table_summaries[0].changed_row_count == 2
    assert changed_result.change_set_closure is not None
    rendered = render_change_set_replay(changed_result.change_set_closure)
    assert rendered.status == "READY"
    assert rendered.sql_bytes is not None
    assert rendered.sql_bytes.count(b"DELETE FROM `orders`;") == 1
    assert rendered.sql_bytes.count(b"INSERT INTO `orders`") == 1
    assert rendered.sql_bytes.count(b"), (") == 2
    assert rendered.sql_bytes.count(b", 9)") == 2
    assert rendered.sql_bytes.count(b", 0)") == 1


def _keyless_rows(*statuses: str) -> tuple[MutationKeyedRow, ...]:
    rows = tuple(
        replace(keyed_row(status=status), key=CanonicalStorageKey(columns=()))
        for status in statuses
    )
    return tuple(sorted(rows, key=lambda row: row.row_digest.value))


def _keyless_snapshot(rows: tuple[MutationKeyedRow, ...]) -> MutationTableSnapshot:
    base = table_snapshot(rows=())
    view = replace(
        base.storage_view,
        canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
        canonical_key_columns=(),
    )
    manifest_row = replace(
        base.manifest_table,
        source_row_count=len(rows),
        canonical_row_count=len(rows),
        canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
        canonical_key_columns=(),
    )
    return MutationTableSnapshot(
        manifest_table=manifest_row,
        storage_view=view,
        rows=rows,
    )


def _collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for item in value.values():
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys
