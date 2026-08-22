"""External Target Sync public contract tests. Does not execute target writes."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.external_target_sync import (
    EXTERNAL_TARGET_SYNC_CONTRACT_VERSION,
    REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
    ExternalApplyFailureCode,
    ExternalApplyInput,
    ExternalApplyPhase,
    ExternalApplyResult,
    ExternalApplyStatus,
    ExternalSyncOutcome,
    ReferenceExecutorCheckpoint,
    TargetRegistration,
    compute_reference_executor_checkpoint_digest,
    reference_executor_checkpoint_from_document,
    target_registration_from_document,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    CHANGE_SET_MANIFEST_CONTRACT_VERSION,
    MutationTargetKind,
)
from tests.support.mutation_contracts import (
    change_set_closure,
    digest,
    planning_input,
    renderer_capability,
)

pytestmark = pytest.mark.unit

MALFORMED_REGISTRATION_SHAPES: tuple[tuple[dict[str, object], str], ...] = (
    (
        {
            "applied_change_set_digest": None,
            "canonical_projection_digest": digest("aa").value,
            "generation": 0,
            "repository_base_digest": digest("bb").value,
            "target_dialect": MutationTargetKind.EXTERNAL_REFERENCE.value,
            "target_id": "target-a",
            "unexpected": True,
        },
        "unknown fields",
    ),
)

MALFORMED_CHECKPOINT_SHAPES: tuple[tuple[dict[str, object], str], ...] = (
    (
        {
            "applied_change_set_digest": None,
            "change_set_digest": digest("cc").value,
            "checkpoint_contract_version": REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
            "ledger_digest": digest("dd").value,
            "phase": ExternalApplyPhase.PREPARE.value,
            "target_id": "target-a",
            "transaction_id": "txn-1",
            "checkpoint": True,
        },
        "unknown fields",
    ),
)


def _registration(*, applied: DigestRef | None = None) -> TargetRegistration:
    return TargetRegistration(
        target_id="target-a",
        target_dialect=MutationTargetKind.EXTERNAL_REFERENCE,
        canonical_projection_digest=digest("aa"),
        repository_base_digest=digest("bb"),
        applied_change_set_digest=applied,
        generation=0,
    )


def test_apply_lifecycle_enums_match_contract() -> None:
    assert ExternalApplyPhase.PREPARE.value == "PREPARE"
    assert ExternalApplyPhase.APPLYING.value == "APPLYING"
    assert ExternalApplyPhase.VERIFYING.value == "VERIFYING"
    assert ExternalApplyStatus.UNKNOWN_OUTCOME.value == "UNKNOWN_OUTCOME"
    assert ExternalSyncOutcome.EXTERNAL_SYNC_SUCCEEDED.value == "EXTERNAL_SYNC_SUCCEEDED"
    assert ExternalSyncOutcome.EXTERNAL_SYNC_APPLIED_UNVERIFIED.value == (
        "EXTERNAL_SYNC_APPLIED_UNVERIFIED"
    )


def test_external_apply_input_binds_public_change_set_only() -> None:
    closure = change_set_closure(mutations=())
    registration = _registration()
    request = ExternalApplyInput(
        change_set_closure=closure,
        change_set_digest=closure.manifest.change_set_digest,
        target_registration=registration,
        expected_repository_base_digest=registration.repository_base_digest,
        renderer_capability=renderer_capability(target_kind=MutationTargetKind.EXTERNAL_REFERENCE),
        contract_version=EXTERNAL_TARGET_SYNC_CONTRACT_VERSION,
    )
    assert request.change_set_closure.manifest.manifest_contract_version == (
        CHANGE_SET_MANIFEST_CONTRACT_VERSION
    )
    with pytest.raises(ValueError, match="expected_repository_base_digest"):
        ExternalApplyInput(
            change_set_closure=closure,
            change_set_digest=closure.manifest.change_set_digest,
            target_registration=registration,
            expected_repository_base_digest=digest("ff"),
            renderer_capability=renderer_capability(target_kind=MutationTargetKind.EXTERNAL_REFERENCE),
        )


def test_apply_result_distinguishes_verified_and_unverified_success() -> None:
    change_set = digest("cc")
    verified = ExternalApplyResult(
        phase=ExternalApplyPhase.VERIFYING,
        status=ExternalApplyStatus.SUCCEEDED,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_SUCCEEDED,
        change_set_digest=change_set,
        applied_change_set_digest=change_set,
    )
    unverified = ExternalApplyResult(
        phase=ExternalApplyPhase.VERIFYING,
        status=ExternalApplyStatus.SUCCEEDED,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_APPLIED_UNVERIFIED,
        change_set_digest=change_set,
        applied_change_set_digest=change_set,
    )
    assert verified.outcome is not unverified.outcome


def test_reference_executor_checkpoint_round_trip_and_digest() -> None:
    checkpoint = ReferenceExecutorCheckpoint(
        checkpoint_contract_version=REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
        target_id="target-a",
        phase=ExternalApplyPhase.APPLYING,
        change_set_digest=digest("cc"),
        applied_change_set_digest=None,
        ledger_digest=digest("dd"),
        transaction_id="txn-1",
    )
    document = checkpoint.to_document()
    restored = reference_executor_checkpoint_from_document(document)
    assert restored == checkpoint
    assert compute_reference_executor_checkpoint_digest(restored) == (
        compute_reference_executor_checkpoint_digest(checkpoint)
    )
    assert "checkpoint" not in restored.to_document()


def test_checkpoint_shape_is_not_part_of_change_set_manifest_keys() -> None:
    from gateway_backend.capabilities.mutation_planning.contracts import _MANIFEST_DOCUMENT_KEYS

    assert "checkpoint" not in _MANIFEST_DOCUMENT_KEYS
    assert "transaction_id" not in _MANIFEST_DOCUMENT_KEYS


@pytest.mark.parametrize(("payload", "match"), MALFORMED_REGISTRATION_SHAPES)
def test_target_registration_rejects_malformed_shapes(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        target_registration_from_document(payload)


@pytest.mark.parametrize(("payload", "match"), MALFORMED_CHECKPOINT_SHAPES)
def test_reference_executor_checkpoint_rejects_malformed_shapes(
    payload: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        reference_executor_checkpoint_from_document(payload)


def test_failed_apply_requires_failure_code() -> None:
    with pytest.raises(ValueError, match="failure_code"):
        ExternalApplyResult(
            phase=ExternalApplyPhase.VERIFYING,
            status=ExternalApplyStatus.FAILED,
            outcome=ExternalSyncOutcome.EXTERNAL_SYNC_FAILED,
            change_set_digest=digest("cc"),
        )


def test_unknown_outcome_remains_pending() -> None:
    result = ExternalApplyResult(
        phase=ExternalApplyPhase.APPLYING,
        status=ExternalApplyStatus.UNKNOWN_OUTCOME,
        outcome=ExternalSyncOutcome.EXTERNAL_SYNC_PENDING,
        change_set_digest=digest("cc"),
        failure_code=ExternalApplyFailureCode.FAILED,
    )
    assert result.outcome is ExternalSyncOutcome.EXTERNAL_SYNC_PENDING


def test_registration_round_trip() -> None:
    registration = _registration(applied=digest("ee"))
    document = registration.to_document()
    restored = target_registration_from_document(document)
    assert restored == registration
    assert planning_input().mutation_policy.value == "REBUILD_ALWAYS"
