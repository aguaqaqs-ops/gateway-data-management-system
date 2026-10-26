"""Mutation Planning public contract tests. Does not plan rows or render SQL."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities import mutation_planning as mutation_planning_public
from gateway_backend.capabilities.mutation_planning import (
    CANONICAL_ENCODING_VERSION,
    CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
    CHANGE_SET_MANIFEST_CONTRACT_VERSION,
    MAX_CHANGE_SET_JSON_BYTES,
    MAX_PATCH_CHANGE_RATIO,
    MAX_PATCH_CHANGED_ROWS,
    MAX_REPLAY_SQL_BYTES,
    MUTATION_CONTRACT_VERSION,
    THRESHOLD_POLICY_VERSION,
    ChangeSetArtifact,
    MutationFailureCode,
    MutationPlanningResult,
    MutationPlanStatus,
    MutationPolicy,
    TableMutationKind,
    RowMutationOperation,
    StorageMutationPlan,
    change_set_closure_from_document,
    change_set_manifest_from_document,
    compute_mutation_plan_identity_digest,
    mutation_plan_identity_payload,
    validate_canonical_cell_value,
    validate_change_set_ordering,
)
from gateway_backend.capabilities.mutation_planning import contracts as mutation_contracts
from tests.support.mutation_contracts import (
    change_set_artifact,
    change_set_closure,
    change_set_manifest,
    delete_mutation,
    insert_mutation,
    planning_input,
    row_image,
    storage_key,
    table_summary,
)

pytestmark = pytest.mark.unit

_OWNER = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "gateway_backend"
    / "capabilities"
    / "mutation_planning"
)
_MIB = 1024 * 1024
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "host_path",
        "sql_text",
        "replay_sql",
        "checkpoint",
        "parser_invocation_context",
    }
)

MALFORMED_CELL_VALUE_SHAPES: tuple[tuple[object, str], ...] = (
    ({"kind": "boolean", "value": "yes"}, "value"),
    ({"kind": "signed-integer"}, "decimal"),
    ({"kind": "unsupported"}, "unsupported"),
    ({"kind": "null", "extra": True}, "unknown fields"),
)

MALFORMED_MANIFEST_SHAPES: tuple[tuple[dict[str, object], str], ...] = (
    (
        {
            "artifact_contract_version": CHANGE_SET_ARTIFACT_CONTRACT_VERSION,
            "base_repository_ref_digest": "sha256:" + "00" * 32,
            "canonical_encoding_version": CANONICAL_ENCODING_VERSION,
            "change_set_digest": "sha256:" + "11" * 32,
            "manifest_contract_version": CHANGE_SET_MANIFEST_CONTRACT_VERSION,
            "mutation_contract_version": MUTATION_CONTRACT_VERSION,
            "mutation_policy": MutationPolicy.REBUILD_ALWAYS.value,
            "renderer_capability": {},
            "source_identity_digest": "sha256:" + "22" * 32,
            "storage_projection_digest": {},
            "table_ruleset_digest": "sha256:" + "33" * 32,
            "table_summaries": [],
            "target_identity": {},
            "threshold_policy": {},
            "unexpected": True,
        },
        "unknown fields",
    ),
)


def test_versions_and_budgets_match_s0() -> None:
    assert MUTATION_CONTRACT_VERSION == "backend-vnext/storage-mutation/v1"
    assert CHANGE_SET_ARTIFACT_CONTRACT_VERSION == "backend-vnext/change-set-artifact/v1"
    assert CHANGE_SET_MANIFEST_CONTRACT_VERSION == "backend-vnext/change-set-manifest/v1"
    assert THRESHOLD_POLICY_VERSION == "backend-vnext/mutation-threshold/v1"
    assert CANONICAL_ENCODING_VERSION == 1
    assert MAX_PATCH_CHANGED_ROWS == 1_000
    assert MAX_PATCH_CHANGE_RATIO == "0.01"
    assert MAX_CHANGE_SET_JSON_BYTES == 16 * _MIB
    assert MAX_REPLAY_SQL_BYTES == 200 * _MIB


def test_public_types_have_no_forbidden_fields() -> None:
    for name in dir(mutation_contracts):
        candidate = getattr(mutation_contracts, name)
        if not is_dataclass(candidate):
            continue
        names = {item.name for item in fields(candidate)}
        assert names.isdisjoint(FORBIDDEN_FIELD_NAMES), name


def test_plan_identity_is_stable_and_sensitive_to_input_changes() -> None:
    base = planning_input()
    digest = compute_mutation_plan_identity_digest(base)
    assert digest == compute_mutation_plan_identity_digest(base)
    changed = replace(
        base,
        mutation_policy=MutationPolicy.ADAPTIVE_PATCH,
    )
    assert compute_mutation_plan_identity_digest(changed) != digest
    payload = mutation_plan_identity_payload(base)
    assert payload["mutation_policy"] == MutationPolicy.REBUILD_ALWAYS.value
    assert "table_summaries" not in payload


def test_change_set_ordering_enforces_table_phase_and_key_order() -> None:
    ordered = (delete_mutation(board="1"), insert_mutation(board="3"))
    validate_change_set_ordering(ordered)
    with pytest.raises(ValueError, match="canonical table order"):
        validate_change_set_ordering((insert_mutation(table="z"), delete_mutation(table="a")))
    with pytest.raises(ValueError, match="DELETE -> UPDATE -> INSERT"):
        validate_change_set_ordering((insert_mutation(), delete_mutation()))


def test_manifest_and_closure_round_trip() -> None:
    summaries = (table_summary(),)
    mutations = (delete_mutation(),)
    artifact = change_set_artifact(summaries=summaries, mutations=mutations)
    manifest_document = artifact.manifest.to_document()
    restored_manifest = change_set_manifest_from_document(manifest_document)
    assert restored_manifest == artifact.manifest
    closure = change_set_closure(summaries=summaries, mutations=mutations)
    closure_document = {
        "manifest": closure.manifest.to_document(),
        "mutations": [item.to_document() for item in closure.mutations],
    }
    restored_closure = change_set_closure_from_document(closure_document)
    assert restored_closure.manifest == closure.manifest
    assert restored_closure.mutations == closure.mutations
    assert restored_closure.closure_digest == closure.closure_digest


def test_closure_rejects_non_object_cell_columns() -> None:
    closure = change_set_closure(summaries=(table_summary(),), mutations=(delete_mutation(),))
    document = {
        "manifest": closure.manifest.to_document(),
        "mutations": [{**delete_mutation().to_document(), "canonical_storage_key": [None]}],
    }
    with pytest.raises(ValueError, match="cell column must be an object"):
        change_set_closure_from_document(document)


@pytest.mark.parametrize(("payload", "match"), MALFORMED_CELL_VALUE_SHAPES)
def test_canonical_cell_value_rejects_malformed_shapes(payload: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        validate_canonical_cell_value(payload, "cell")


@pytest.mark.parametrize(("payload", "match"), MALFORMED_MANIFEST_SHAPES)
def test_change_set_manifest_rejects_malformed_shapes(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        change_set_manifest_from_document(payload)


def test_failed_planning_result_cannot_publish_closure() -> None:
    with pytest.raises(ValueError, match="must not publish"):
        MutationPlanningResult(
            status=MutationPlanStatus.FAILED,
            failure_code=MutationFailureCode.FAILED,
            change_set_closure=change_set_closure(),
        )


def test_confirmation_required_result_cannot_publish_closure() -> None:
    request = planning_input()
    plan = StorageMutationPlan(
        mutation_plan_identity_digest=compute_mutation_plan_identity_digest(request),
        plan_status=MutationPlanStatus.CONFIRMATION_REQUIRED,
        table_summaries=(table_summary(operation=TableMutationKind.REBUILD_TABLE),),
        planning_input=request,
        requires_confirmation=True,
        confirmation_reason="destructive table drop",
        failure_code=MutationFailureCode.CONFIRMATION_REQUIRED,
    )
    with pytest.raises(ValueError, match="must not publish"):
        MutationPlanningResult(
            status=MutationPlanStatus.CONFIRMATION_REQUIRED,
            plan=plan,
            change_set_closure=change_set_closure(),
        )


def test_ready_result_requires_closure_and_matching_plan() -> None:
    request = planning_input()
    plan = StorageMutationPlan(
        mutation_plan_identity_digest=compute_mutation_plan_identity_digest(request),
        plan_status=MutationPlanStatus.READY,
        table_summaries=(table_summary(),),
        planning_input=request,
    )
    closure = change_set_closure(
        summaries=plan.table_summaries,
        mutations=(delete_mutation(),),
    )
    result = MutationPlanningResult(
        status=MutationPlanStatus.READY,
        plan=plan,
        change_set_closure=closure,
    )
    assert result.change_set_closure is not None


def test_change_set_artifact_rejects_digest_mismatch() -> None:
    manifest = change_set_manifest(mutations=(delete_mutation(),))
    with pytest.raises(ValueError, match="change_set_digest"):
        ChangeSetArtifact(
            manifest=replace(
                manifest,
                change_set_digest=DigestRef("sha256:" + "99" * 32),
            ),
            mutations=(delete_mutation(),),
        )


def test_public_package_exports_contracts_only() -> None:
    assert hasattr(mutation_planning_public, "StorageMutationPlan")
    assert hasattr(mutation_planning_public, "compute_change_set_digest")
    assert hasattr(mutation_planning_public, "plan_storage_mutation")
    assert not hasattr(mutation_planning_public, "plan_mutations")
    assert not hasattr(mutation_planning_public, "render_replay_sql")
    for source in _OWNER.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "NotImplementedError" not in text, source
        assert "host_path" not in text, source


def test_update_mutation_requires_before_digest_and_after_image() -> None:
    from gateway_backend.capabilities.mutation_planning.contracts import ChangeSetMutation

    with pytest.raises(ValueError, match="before_row_digest"):
        ChangeSetMutation(
            canonical_table="orders",
            operation=RowMutationOperation.UPDATE,
            canonical_storage_key=storage_key(),
            after_image=row_image(),
        )
    mutation = ChangeSetMutation(
        canonical_table="orders",
        operation=RowMutationOperation.UPDATE,
        canonical_storage_key=storage_key(),
        before_row_digest=raw_blob_digest(b"before"),
        after_image=row_image(),
    )
    assert mutation.operation is RowMutationOperation.UPDATE
