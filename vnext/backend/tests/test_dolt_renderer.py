"""S4 deterministic repository replay SQL renderer tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.mutation_planning import (
    MutationFailureCode,
    MutationPlanStatus,
    MutationPolicy,
    plan_storage_mutation,
)
from gateway_backend.capabilities.mutation_planning._dolt_renderer import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
    render_change_set_replay,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    MAX_REPLAY_SQL_BYTES,
    CanonicalStorageKey,
    ChangeSetClosure,
    ChangeSetMutation,
    MutationTargetKind,
    PersistedRowImage,
    RendererCapabilityDeclaration,
    RowMutationOperation,
)
from tests.support.mutation_contracts import (
    change_set_closure,
    delete_mutation,
    insert_mutation,
    planning_request,
    renderer_capability,
    keyed_row,
    table_snapshot,
    table_summary,
)
from tests.support.mutation_renderer_fixtures import (
    load_closure,
    load_expected_sql,
)
from gateway_backend.capabilities.mutation_planning.contracts import TableMutationKind

pytestmark = pytest.mark.unit

R7_RENDERER_GOLDEN_CASES: tuple[tuple[str, str], ...] = (
    ("patch-single-update", "valid/patch-single-update"),
    ("first-load-insert", "valid/first-load-insert"),
    ("rebuild-replace-rows", "valid/rebuild-replace-rows"),
    ("destructive-delete", "valid/destructive-delete"),
    ("multi-table-patch", "valid/multi-table-patch"),
    ("mixed-scalars", "valid/mixed-scalars"),
)


@pytest.mark.parametrize(("case_id", "relative_dir"), R7_RENDERER_GOLDEN_CASES)
def test_renderer_golden_cases(case_id: str, relative_dir: str) -> None:
    closure = load_closure(relative_dir)
    expected = load_expected_sql(relative_dir)
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY", case_id
    assert outcome.sql_bytes == expected
    assert outcome.sql_digest == raw_blob_digest(expected)


def test_renderer_is_deterministic_for_golden_closure() -> None:
    closure = load_closure("valid/patch-single-update")
    first = render_change_set_replay(closure)
    second = render_change_set_replay(closure)
    assert first == second
    assert first.sql_bytes is not None
    assert first.sql_digest == raw_blob_digest(first.sql_bytes)


def test_planner_ready_closure_renders_successfully() -> None:
    result = plan_storage_mutation(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(table_snapshot(rows=(keyed_row(),)),),
            after_tables=(table_snapshot(rows=(keyed_row(status="1"),)),),
        )
    )
    assert result.status is MutationPlanStatus.READY
    assert result.change_set_closure is not None
    outcome = render_change_set_replay(result.change_set_closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert outcome.sql_bytes.endswith(b"\n")


def test_multi_table_sql_statement_order_matches_mutations() -> None:
    closure = load_closure("valid/multi-table-patch")
    outcome = render_change_set_replay(closure)
    assert outcome.sql_bytes is not None
    statements = [line for line in outcome.sql_bytes.decode("utf-8").splitlines() if line]
    assert len(statements) == len(closure.mutations)
    for statement, mutation in zip(statements, closure.mutations, strict=True):
        assert mutation.canonical_table in statement
        assert statement.endswith(";")


def test_source_literal_anomaly_fixture_fails_closed() -> None:
    closure = load_closure("capability-failures/source-literal-anomaly")
    outcome = render_change_set_replay(closure)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED
    assert outcome.sql_bytes is None


def test_wrong_renderer_capability_digest_fails_closed() -> None:
    closure = change_set_closure(mutations=(delete_mutation(),))
    wrong_capability = RendererCapabilityDeclaration(
        target_kind=MutationTargetKind.CANONICAL_REPOSITORY_REPLAY,
        capability_version=REPOSITORY_REPLAY_RENDERER_CAPABILITY.capability_version,
        capability_digest=DigestRef("sha256:" + "99" * 32),
        capability_contract_version=REPOSITORY_REPLAY_RENDERER_CAPABILITY.capability_contract_version,
    )
    patched_manifest = replace(
        closure.manifest,
        renderer_capability=wrong_capability,
        target_identity=wrong_capability,
    )
    patched = ChangeSetClosure(manifest=patched_manifest, mutations=closure.mutations)
    outcome = render_change_set_replay(patched)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED


def test_external_reference_renderer_capability_fails_closed() -> None:
    closure = change_set_closure(mutations=(delete_mutation(),))
    external = renderer_capability(target_kind=MutationTargetKind.EXTERNAL_REFERENCE)
    patched_manifest = replace(
        closure.manifest,
        renderer_capability=external,
        target_identity=external,
    )
    patched = ChangeSetClosure(manifest=patched_manifest, mutations=closure.mutations)
    outcome = render_change_set_replay(patched)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED


def test_replay_size_cap_rejects_without_partial_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gateway_backend.capabilities.mutation_planning._dolt_renderer.MAX_REPLAY_SQL_BYTES",
        64,
    )
    mutations = tuple(insert_mutation(board=str(i), link_no=str(i + 1)) for i in range(8))
    closure = change_set_closure(
        summaries=(table_summary(operation=TableMutationKind.REBUILD_TABLE),),
        mutations=mutations,
    )
    outcome = render_change_set_replay(closure)
    assert outcome.status == "FAILED"
    assert outcome.failure_code is MutationFailureCode.RESOURCE_EXCEEDED
    assert outcome.sql_bytes is None


def test_replay_size_cap_boundary_accepts_under_limit() -> None:
    # One INSERT line is far below MAX_REPLAY_SQL_BYTES.
    closure = change_set_closure(mutations=(insert_mutation(),))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert len(outcome.sql_bytes) < MAX_REPLAY_SQL_BYTES


def test_update_excludes_key_columns_from_set_clause() -> None:
    closure = load_closure("valid/patch-single-update")
    outcome = render_change_set_replay(closure)
    assert outcome.sql_bytes is not None
    text = outcome.sql_bytes.decode("utf-8")
    assert "SET `status`=" in text
    assert "SET `board`=" not in text
    assert "SET `link_no`=" not in text


def test_string_escape_in_sql_literal() -> None:
    image = PersistedRowImage(
        columns=(
            ("board", {"kind": "string", "text": "a'b\\n"}),
            ("link_no", {"kind": "signed-integer", "decimal": "1"}),
            ("status", {"kind": "signed-integer", "decimal": "9"}),
        )
    )
    mutation = ChangeSetMutation(
        canonical_table="orders",
        operation=RowMutationOperation.INSERT,
        canonical_storage_key=CanonicalStorageKey(
            columns=(
                ("board", {"kind": "string", "text": "a'b\\n"}),
                ("link_no", {"kind": "signed-integer", "decimal": "1"}),
            )
        ),
        after_image=image,
    )
    closure = change_set_closure(mutations=(mutation,))
    outcome = render_change_set_replay(closure)
    assert outcome.status == "READY"
    assert outcome.sql_bytes is not None
    assert b"a\\'b\\\\n" in outcome.sql_bytes
