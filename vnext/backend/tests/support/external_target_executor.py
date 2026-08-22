"""Helpers for external reference executor tests."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.external_target_sync.contracts import (
    EXTERNAL_TARGET_SYNC_CONTRACT_VERSION,
    ExternalApplyInput,
    TargetRegistration,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    ChangeSetClosure,
    MutationTargetKind,
)
from gateway_backend.capabilities.external_target_sync._reference_executor import (
    ReferenceExecutorState,
    empty_executor_state,
)
from tests.support.mutation_contracts import renderer_capability


def registration_for_closure(
    closure: ChangeSetClosure,
    *,
    target_id: str = "target-a",
    applied_change_set_digest: DigestRef | None = None,
    generation: int = 0,
) -> TargetRegistration:
    binding = closure.manifest.storage_projection_digest
    return TargetRegistration(
        target_id=target_id,
        target_dialect=MutationTargetKind.EXTERNAL_REFERENCE,
        canonical_projection_digest=binding.after_storage_projection_digest,
        repository_base_digest=closure.manifest.base_repository_ref_digest,
        applied_change_set_digest=applied_change_set_digest,
        generation=generation,
    )


def apply_input_for(
    closure: ChangeSetClosure,
    registration: TargetRegistration,
) -> ExternalApplyInput:
    return ExternalApplyInput(
        change_set_closure=closure,
        change_set_digest=closure.manifest.change_set_digest,
        target_registration=registration,
        expected_repository_base_digest=registration.repository_base_digest,
        renderer_capability=renderer_capability(target_kind=MutationTargetKind.EXTERNAL_REFERENCE),
        contract_version=EXTERNAL_TARGET_SYNC_CONTRACT_VERSION,
    )


def executor_state_for(
    closure: ChangeSetClosure,
    *,
    target_id: str = "target-a",
    applied_change_set_digest: DigestRef | None = None,
    generation: int = 0,
) -> ReferenceExecutorState:
    registration = registration_for_closure(
        closure,
        target_id=target_id,
        applied_change_set_digest=applied_change_set_digest,
        generation=generation,
    )
    return empty_executor_state(registration)
