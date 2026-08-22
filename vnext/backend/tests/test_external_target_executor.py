"""S5 external reference executor tests."""

from __future__ import annotations

from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.external_target_sync._ledger_digest import compute_ledger_digest
from gateway_backend.capabilities.external_target_sync._reference_executor import (
    ReferenceExecutorFaults,
    ReferenceExecutorState,
    apply_change_set_reference,
    export_reference_checkpoint,
    reconcile_unknown_outcome,
    restore_reference_checkpoint,
)
from gateway_backend.capabilities.external_target_sync.contracts import (
    ExternalApplyFailureCode,
    ExternalApplyResult,
    ExternalApplyStatus,
    ExternalSyncOutcome,
    reference_executor_checkpoint_from_document,
)
from gateway_backend.capabilities.mutation_planning import (
    MutationPlanStatus,
    MutationPolicy,
    plan_storage_mutation,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    ChangeSetClosure,
    RowMutationOperation,
)
from tests.support.external_target_executor import (
    apply_input_for,
    executor_state_for,
    registration_for_closure,
)
from tests.support.mutation_contracts import (
    change_set_closure,
    delete_mutation,
    digest,
    insert_mutation,
    planning_request,
    storage_key,
    table_snapshot,
    keyed_row,
)
from tests.support.mutation_renderer_fixtures import load_closure

pytestmark = pytest.mark.unit


def _apply(
    closure: ChangeSetClosure,
    state: ReferenceExecutorState,
    *,
    faults: ReferenceExecutorFaults | None = None,
) -> tuple[ExternalApplyResult, ReferenceExecutorState]:
    apply_input = apply_input_for(closure, state.registration)
    return apply_change_set_reference(apply_input, state, faults=faults)


def _seed_patch_update_ledger(
    state: ReferenceExecutorState,
    closure: ChangeSetClosure,
) -> None:
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        key_bytes_for_ordering,
        ledger_row_from_image,
    )
    from tests.support.mutation_contracts import row_image, storage_key

    key = storage_key(board="0", link_no="0")
    before_image = row_image(board="0", link_no="0", status="9")
    row = ledger_row_from_image(key, before_image)
    for mutation in closure.mutations:
        if mutation.operation is RowMutationOperation.UPDATE:
            if mutation.before_row_digest is not None:
                row = replace(row, row_digest=mutation.before_row_digest)
    state.ledger.tables["orders"] = {key_bytes_for_ordering(key): row}


def test_first_full_apply_from_planner_closure() -> None:
    closure = load_closure("valid/first-load-insert")
    state = executor_state_for(closure)
    result, state = _apply(closure, state)
    assert result.status is ExternalApplyStatus.SUCCEEDED
    assert result.outcome is ExternalSyncOutcome.EXTERNAL_SYNC_SUCCEEDED
    assert state.registration.applied_change_set_digest == closure.manifest.change_set_digest
    assert len(state.ledger.tables.get("orders", {})) == 2


def test_idempotent_retry_reuses_existing_result() -> None:
    closure = load_closure("valid/patch-single-update")
    state = executor_state_for(closure)
    _seed_patch_update_ledger(state, closure)
    first, state = _apply(closure, state)
    before_digest = compute_ledger_digest(state.ledger)
    second, state = _apply(closure, state)
    assert second.status is ExternalApplyStatus.SUCCEEDED
    assert second.applied_change_set_digest == first.applied_change_set_digest
    assert compute_ledger_digest(state.ledger) == before_digest


def test_before_image_mismatch_fails_closed_and_rolls_back() -> None:
    mutation = delete_mutation()
    bad = replace(mutation, before_row_digest=DigestRef("sha256:" + "99" * 32))
    closure = change_set_closure(mutations=(bad,))
    state = executor_state_for(closure)
    state.ledger.tables["orders"] = {}
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        ledger_row_from_image,
    )
    from tests.support.mutation_contracts import row_image

    key = storage_key()
    image = row_image()
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        key_bytes_for_ordering,
    )

    state.ledger.tables["orders"][key_bytes_for_ordering(key)] = ledger_row_from_image(key, image)
    before_digest = compute_ledger_digest(state.ledger)
    result, state = _apply(closure, state)
    assert result.status is ExternalApplyStatus.FAILED
    assert result.failure_code is ExternalApplyFailureCode.DRIFT_DETECTED
    assert compute_ledger_digest(state.ledger) == before_digest


def test_insert_conflict_drifts_and_rolls_back() -> None:
    closure = change_set_closure(mutations=(insert_mutation(board="1", link_no="2"),))
    state = executor_state_for(closure)
    key = storage_key()
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        key_bytes_for_ordering,
        ledger_row_from_image,
    )
    from tests.support.mutation_contracts import row_image

    state.ledger.tables["orders"] = {
        key_bytes_for_ordering(key): ledger_row_from_image(key, row_image())
    }
    before_digest = compute_ledger_digest(state.ledger)
    result, state = _apply(closure, state)
    assert result.failure_code is ExternalApplyFailureCode.DRIFT_DETECTED
    assert compute_ledger_digest(state.ledger) == before_digest


def test_repository_base_drift_rejected_at_prepare() -> None:
    closure = load_closure("valid/first-load-insert")
    state = executor_state_for(closure)
    state.registration = replace(
        state.registration,
        repository_base_digest=digest("ff"),
    )
    result, _ = _apply(closure, state)
    assert result.failure_code is ExternalApplyFailureCode.DRIFT_DETECTED


def test_projection_drift_rejected_at_prepare() -> None:
    closure = load_closure("valid/first-load-insert")
    state = executor_state_for(closure)
    state.registration = replace(
        state.registration,
        canonical_projection_digest=digest("ff"),
    )
    result, _ = _apply(closure, state)
    assert result.failure_code is ExternalApplyFailureCode.DRIFT_DETECTED


def test_unknown_outcome_reconcile_then_retry_succeeds() -> None:
    closure = load_closure("valid/patch-single-update")
    state = executor_state_for(closure)
    _seed_patch_update_ledger(state, closure)
    unknown, state = _apply(
        closure,
        state,
        faults=ReferenceExecutorFaults(force_unknown_outcome=True),
    )
    assert unknown.status is ExternalApplyStatus.UNKNOWN_OUTCOME
    checkpoint = export_reference_checkpoint(state)
    blind, state = _apply(closure, state)
    assert blind.status is ExternalApplyStatus.FAILED
    reconciled, state = reconcile_unknown_outcome(state, checkpoint)
    assert reconciled.outcome is ExternalSyncOutcome.EXTERNAL_SYNC_PENDING
    success, state = _apply(closure, state)
    assert success.status is ExternalApplyStatus.SUCCEEDED


def test_idempotency_conflict_when_pending_unknown_digest_differs() -> None:
    closure_a = load_closure("valid/patch-single-update")
    closure_b = load_closure("valid/first-load-insert")
    state = executor_state_for(closure_a)
    _seed_patch_update_ledger(state, closure_a)
    _, state = _apply(
        closure_a,
        state,
        faults=ReferenceExecutorFaults(force_unknown_outcome=True),
    )
    result, _ = _apply(closure_b, state)
    assert result.failure_code is ExternalApplyFailureCode.IDEMPOTENCY_CONFLICT


def test_checkpoint_round_trip_document() -> None:
    closure = load_closure("valid/patch-single-update")
    state = executor_state_for(closure)
    _seed_patch_update_ledger(state, closure)
    _, state = _apply(
        closure,
        state,
        faults=ReferenceExecutorFaults(force_unknown_outcome=True),
    )
    checkpoint = export_reference_checkpoint(state)
    document = checkpoint.to_document()
    restored = reference_executor_checkpoint_from_document(document)
    assert restored == checkpoint
    registration = registration_for_closure(closure)
    taken_over = restore_reference_checkpoint(restored, registration)
    assert taken_over.pending_change_set_digest == closure.manifest.change_set_digest
    assert taken_over.transaction_id == checkpoint.transaction_id


def test_planner_integration_smoke() -> None:
    before_row = keyed_row()
    after_row = keyed_row(status="1")
    result = plan_storage_mutation(
        planning_request(
            policy=MutationPolicy.ADAPTIVE_PATCH,
            before_tables=(table_snapshot(rows=(before_row,)),),
            after_tables=(table_snapshot(rows=(after_row,)),),
        )
    )
    assert result.status is MutationPlanStatus.READY
    assert result.change_set_closure is not None
    closure = result.change_set_closure
    state = executor_state_for(closure)
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        key_bytes_for_ordering,
        ledger_row_from_image,
    )

    key = before_row.key
    state.ledger.tables["orders"] = {
        key_bytes_for_ordering(key): ledger_row_from_image(key, before_row.image)
    }
    for mutation in closure.mutations:
        if mutation.before_row_digest is not None:
            key_bytes = key_bytes_for_ordering(mutation.canonical_storage_key)
            if key_bytes in state.ledger.tables.get("orders", {}):
                row = state.ledger.tables["orders"][key_bytes]
                state.ledger.tables["orders"][key_bytes] = replace(
                    row,
                    row_digest=mutation.before_row_digest,
                )
    apply_result, state = _apply(closure, state)
    assert apply_result.status is ExternalApplyStatus.SUCCEEDED


def test_readback_mismatch_rolls_back() -> None:
    closure = load_closure("valid/patch-single-update")
    state = executor_state_for(closure)
    _seed_patch_update_ledger(state, closure)
    result, state = _apply(
        closure,
        state,
        faults=ReferenceExecutorFaults(force_readback_mismatch=True),
    )
    assert result.failure_code is ExternalApplyFailureCode.READBACK_MISMATCH
    assert state.registration.applied_change_set_digest is None


def test_update_mutation_applies_after_image() -> None:
    closure = load_closure("valid/patch-single-update")
    state = executor_state_for(closure)
    _seed_patch_update_ledger(state, closure)
    result, state = _apply(closure, state)
    assert result.status is ExternalApplyStatus.SUCCEEDED
    from gateway_backend.capabilities.external_target_sync._ledger_digest import (
        key_bytes_for_ordering,
    )
    from tests.support.mutation_contracts import storage_key

    key = storage_key(board="0", link_no="0")
    row = state.ledger.tables["orders"][key_bytes_for_ordering(key)]
    assert row.image.columns[-1][1]["decimal"] == "1"
