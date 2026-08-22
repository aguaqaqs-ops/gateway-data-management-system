"""In-memory fault-injectable reference external target executor."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.external_target_sync._ledger_digest import (
    ReferenceTargetLedger,
    compute_ledger_digest,
    key_bytes_for_ordering,
    ledger_row_from_image,
)
from gateway_backend.capabilities.external_target_sync.contracts import (
    ExternalApplyFailureCode,
    ExternalApplyInput,
    ExternalApplyPhase,
    ExternalApplyResult,
    ExternalApplyStatus,
    ExternalSyncOutcome,
    ReferenceExecutorCheckpoint,
    REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
    TargetRegistration,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    ChangeSetClosure,
    ChangeSetMutation,
    MutationTargetKind,
    RowMutationOperation,
)


@dataclass(frozen=True, slots=True)
class ReferenceExecutorFaults:
    crash_after_phase: ExternalApplyPhase | None = None
    fail_on_mutation_index: int | None = None
    force_readback_mismatch: bool = False
    force_unknown_outcome: bool = False


@dataclass
class ReferenceExecutorState:
    registration: TargetRegistration
    ledger: ReferenceTargetLedger
    phase: ExternalApplyPhase = ExternalApplyPhase.PREPARE
    transaction_id: str | None = None
    pending_change_set_digest: DigestRef | None = None
    ledger_snapshot: ReferenceTargetLedger | None = None
    snapshot_ledger_digest: DigestRef | None = None


def empty_executor_state(registration: TargetRegistration) -> ReferenceExecutorState:
    ledger = ReferenceTargetLedger(
        target_id=registration.target_id,
        tables={},
        applied_change_set_digest=registration.applied_change_set_digest,
        generation=registration.generation,
    )
    return ReferenceExecutorState(registration=registration, ledger=ledger)


def apply_change_set_reference(
    apply_input: ExternalApplyInput,
    state: ReferenceExecutorState,
    *,
    faults: ReferenceExecutorFaults | None = None,
) -> tuple[ExternalApplyResult, ReferenceExecutorState]:
    faults = faults or ReferenceExecutorFaults()
    closure = apply_input.change_set_closure
    change_set_digest = apply_input.change_set_digest

    prepare_failure = _validate_prepare(apply_input, state)
    if prepare_failure is not None:
        return prepare_failure, state

    if state.registration.applied_change_set_digest == change_set_digest:
        return _success_result(change_set_digest, ExternalApplyPhase.VERIFYING), state

    if state.pending_change_set_digest is not None:
        if state.pending_change_set_digest != change_set_digest:
            return _failed_result(
                change_set_digest,
                ExternalApplyFailureCode.IDEMPOTENCY_CONFLICT,
                ExternalApplyPhase.PREPARE,
            ), state
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.FAILED,
            state.phase,
        ), state

    state.phase = ExternalApplyPhase.PREPARE
    state.ledger_snapshot = state.ledger.copy()
    state.snapshot_ledger_digest = compute_ledger_digest(state.ledger_snapshot)
    state.pending_change_set_digest = change_set_digest
    state.transaction_id = _transaction_id(
        state.registration.target_id,
        change_set_digest,
    )
    state.phase = ExternalApplyPhase.APPLYING

    if faults.crash_after_phase is ExternalApplyPhase.PREPARE:
        return _unknown_result(change_set_digest, ExternalApplyPhase.APPLYING), state

    try:
        for index, mutation in enumerate(closure.mutations):
            if faults.fail_on_mutation_index == index:
                raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
            _apply_mutation(state.ledger, mutation)
    except _ApplyFailure as exc:
        _rollback_state(state)
        return _failed_result(
            change_set_digest,
            exc.code,
            ExternalApplyPhase.APPLYING,
        ), state

    if faults.crash_after_phase is ExternalApplyPhase.APPLYING or faults.force_unknown_outcome:
        return _unknown_result(change_set_digest, ExternalApplyPhase.APPLYING), state

    state.phase = ExternalApplyPhase.VERIFYING
    if faults.crash_after_phase is ExternalApplyPhase.VERIFYING:
        return _unknown_result(change_set_digest, ExternalApplyPhase.VERIFYING), state

    expected = _simulate_mutations(state.ledger_snapshot, closure.mutations)
    if faults.force_readback_mismatch or not _ledger_rows_equal(state.ledger, expected):
        _rollback_state(state)
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.READBACK_MISMATCH,
            ExternalApplyPhase.VERIFYING,
        ), state

    state.registration = TargetRegistration(
        target_id=state.registration.target_id,
        target_dialect=state.registration.target_dialect,
        canonical_projection_digest=state.registration.canonical_projection_digest,
        repository_base_digest=state.registration.repository_base_digest,
        applied_change_set_digest=change_set_digest,
        generation=state.registration.generation + 1,
    )
    state.ledger.applied_change_set_digest = change_set_digest
    state.ledger.generation = state.registration.generation
    state.pending_change_set_digest = None
    state.transaction_id = None
    state.ledger_snapshot = None
    state.snapshot_ledger_digest = None
    state.phase = ExternalApplyPhase.VERIFYING
    return _success_result(change_set_digest, ExternalApplyPhase.VERIFYING), state


def reconcile_unknown_outcome(
    state: ReferenceExecutorState,
    checkpoint: ReferenceExecutorCheckpoint,
) -> tuple[ExternalApplyResult, ReferenceExecutorState]:
    if checkpoint.target_id != state.registration.target_id:
        return _failed_result(
            checkpoint.change_set_digest,
            ExternalApplyFailureCode.FAILED,
            checkpoint.phase,
        ), state
    if checkpoint.change_set_digest != state.pending_change_set_digest:
        return _failed_result(
            checkpoint.change_set_digest,
            ExternalApplyFailureCode.FAILED,
            checkpoint.phase,
        ), state

    if state.ledger_snapshot is not None:
        state.ledger = state.ledger_snapshot.copy()

    state.pending_change_set_digest = None
    state.transaction_id = None
    state.ledger_snapshot = None
    state.snapshot_ledger_digest = None
    state.phase = ExternalApplyPhase.PREPARE

    return ExternalApplyResult(
        phase=ExternalApplyPhase.PREPARE,
        status=ExternalApplyStatus.UNKNOWN_OUTCOME,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_PENDING,
        change_set_digest=checkpoint.change_set_digest,
        failure_code=ExternalApplyFailureCode.FAILED,
    ), state


def export_reference_checkpoint(state: ReferenceExecutorState) -> ReferenceExecutorCheckpoint:
    if state.pending_change_set_digest is None or state.transaction_id is None:
        raise ValueError("checkpoint export requires an active reference transaction")
    return ReferenceExecutorCheckpoint(
        checkpoint_contract_version=REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
        target_id=state.registration.target_id,
        phase=state.phase,
        change_set_digest=state.pending_change_set_digest,
        applied_change_set_digest=state.registration.applied_change_set_digest,
        ledger_digest=compute_ledger_digest(state.ledger),
        transaction_id=state.transaction_id,
    )


def restore_reference_checkpoint(
    checkpoint: ReferenceExecutorCheckpoint,
    registration: TargetRegistration,
) -> ReferenceExecutorState:
    if checkpoint.target_id != registration.target_id:
        raise ValueError("checkpoint target_id must match registration")
    ledger = ReferenceTargetLedger(
        target_id=registration.target_id,
        tables={},
        applied_change_set_digest=registration.applied_change_set_digest,
        generation=registration.generation,
    )
    return ReferenceExecutorState(
        registration=registration,
        ledger=ledger,
        phase=checkpoint.phase,
        transaction_id=checkpoint.transaction_id,
        pending_change_set_digest=checkpoint.change_set_digest,
        ledger_snapshot=None,
        snapshot_ledger_digest=None,
    )


class _ApplyFailure(Exception):
    def __init__(self, code: ExternalApplyFailureCode) -> None:
        self.code = code


def _validate_prepare(
    apply_input: ExternalApplyInput,
    state: ReferenceExecutorState,
) -> ExternalApplyResult | None:
    closure = apply_input.change_set_closure
    registration = state.registration
    change_set_digest = apply_input.change_set_digest

    if apply_input.renderer_capability.target_kind is not MutationTargetKind.EXTERNAL_REFERENCE:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.TARGET_CAPABILITY_UNSUPPORTED,
            ExternalApplyPhase.PREPARE,
        )
    if change_set_digest != closure.manifest.change_set_digest:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.FAILED,
            ExternalApplyPhase.PREPARE,
        )
    if apply_input.expected_repository_base_digest != registration.repository_base_digest:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.DRIFT_DETECTED,
            ExternalApplyPhase.PREPARE,
        )
    if registration.repository_base_digest != closure.manifest.base_repository_ref_digest:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.DRIFT_DETECTED,
            ExternalApplyPhase.PREPARE,
        )
    binding = closure.manifest.storage_projection_digest
    if registration.canonical_projection_digest != binding.after_storage_projection_digest:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.DRIFT_DETECTED,
            ExternalApplyPhase.PREPARE,
        )
    if state.ledger.target_id != registration.target_id:
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.FAILED,
            ExternalApplyPhase.PREPARE,
        )
    if _closure_has_anomaly_cells(closure):
        return _failed_result(
            change_set_digest,
            ExternalApplyFailureCode.TARGET_CAPABILITY_UNSUPPORTED,
            ExternalApplyPhase.PREPARE,
        )
    return None


def _closure_has_anomaly_cells(closure: ChangeSetClosure) -> bool:
    for mutation in closure.mutations:
        for _, cell in mutation.canonical_storage_key.columns:
            if cell.get("kind") == "source-literal-anomaly":
                return True
        if mutation.after_image is not None:
            for _, cell in mutation.after_image.columns:
                if cell.get("kind") == "source-literal-anomaly":
                    return True
    return False


def _apply_mutation(ledger: ReferenceTargetLedger, mutation: ChangeSetMutation) -> None:
    table = mutation.canonical_table
    key_bytes = key_bytes_for_ordering(mutation.canonical_storage_key)
    table_rows = ledger.tables.setdefault(table, {})
    if mutation.operation is RowMutationOperation.DELETE:
        if mutation.before_row_digest is None:
            raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
        row = table_rows.get(key_bytes)
        if row is None or row.row_digest != mutation.before_row_digest:
            raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
        del table_rows[key_bytes]
        return
    if mutation.operation is RowMutationOperation.UPDATE:
        if mutation.before_row_digest is None or mutation.after_image is None:
            raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
        row = table_rows.get(key_bytes)
        if row is None or row.row_digest != mutation.before_row_digest:
            raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
        table_rows[key_bytes] = ledger_row_from_image(
            mutation.canonical_storage_key,
            mutation.after_image,
        )
        return
    if mutation.after_image is None:
        raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
    if key_bytes in table_rows:
        raise _ApplyFailure(ExternalApplyFailureCode.DRIFT_DETECTED)
    table_rows[key_bytes] = ledger_row_from_image(
        mutation.canonical_storage_key,
        mutation.after_image,
    )


def _simulate_mutations(
    ledger: ReferenceTargetLedger,
    mutations: tuple[ChangeSetMutation, ...],
) -> ReferenceTargetLedger:
    simulated = ledger.copy()
    for mutation in mutations:
        _apply_mutation(simulated, mutation)
    return simulated


def _ledger_rows_equal(left: ReferenceTargetLedger, right: ReferenceTargetLedger) -> bool:
    if set(left.tables) != set(right.tables):
        return False
    for table_name in left.tables:
        left_rows = left.tables[table_name]
        right_rows = right.tables[table_name]
        if set(left_rows) != set(right_rows):
            return False
        for key_bytes, left_row in left_rows.items():
            right_row = right_rows[key_bytes]
            if left_row.row_digest != right_row.row_digest:
                return False
    return True


def _rollback_state(state: ReferenceExecutorState) -> None:
    if state.ledger_snapshot is not None:
        state.ledger = state.ledger_snapshot.copy()
    state.pending_change_set_digest = None
    state.transaction_id = None
    state.ledger_snapshot = None
    state.snapshot_ledger_digest = None
    state.phase = ExternalApplyPhase.PREPARE


def _transaction_id(target_id: str, change_set_digest: DigestRef) -> str:
    digest = raw_blob_digest(f"{target_id}:{change_set_digest.value}".encode())
    return digest.value.removeprefix("sha256:")[:32]


def _success_result(change_set_digest: DigestRef, phase: ExternalApplyPhase) -> ExternalApplyResult:
    return ExternalApplyResult(
        phase=phase,
        status=ExternalApplyStatus.SUCCEEDED,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_SUCCEEDED,
        change_set_digest=change_set_digest,
        applied_change_set_digest=change_set_digest,
    )


def _failed_result(
    change_set_digest: DigestRef,
    failure_code: ExternalApplyFailureCode,
    phase: ExternalApplyPhase,
) -> ExternalApplyResult:
    return ExternalApplyResult(
        phase=phase,
        status=ExternalApplyStatus.FAILED,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_FAILED,
        change_set_digest=change_set_digest,
        failure_code=failure_code,
    )


def _unknown_result(change_set_digest: DigestRef, phase: ExternalApplyPhase) -> ExternalApplyResult:
    return ExternalApplyResult(
        phase=phase,
        status=ExternalApplyStatus.UNKNOWN_OUTCOME,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_PENDING,
        change_set_digest=change_set_digest,
        failure_code=ExternalApplyFailureCode.FAILED,
    )
