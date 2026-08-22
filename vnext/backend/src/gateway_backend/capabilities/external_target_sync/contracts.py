"""Public contracts owned by the External Target Sync capability.

Owner: External Target Sync capability
Authority: docs/backend-vnext/refactoring/formal/contracts/external-target-sync-and-recovery.md
Downstream consumers may import this module only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.mutation_planning.contracts import (
    ChangeSetClosure,
    MutationTargetKind,
    RendererCapabilityDeclaration,
)

EXTERNAL_TARGET_SYNC_CONTRACT_VERSION = "backend-vnext/external-target-sync/v1"
REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION = (
    "backend-vnext/external-target-reference-checkpoint/v1"
)

_CHECKPOINT_DOCUMENT_KEYS = frozenset(
    {
        "applied_change_set_digest",
        "change_set_digest",
        "checkpoint_contract_version",
        "ledger_digest",
        "phase",
        "target_id",
        "transaction_id",
    }
)
_REGISTRATION_DOCUMENT_KEYS = frozenset(
    {
        "applied_change_set_digest",
        "canonical_projection_digest",
        "generation",
        "repository_base_digest",
        "target_dialect",
        "target_id",
    }
)


class ExternalApplyPhase(StrEnum):
    PREPARE = "PREPARE"
    APPLYING = "APPLYING"
    VERIFYING = "VERIFYING"


class ExternalApplyStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class ExternalSyncOutcome(StrEnum):
    EXTERNAL_SYNC_SUCCEEDED = "EXTERNAL_SYNC_SUCCEEDED"
    EXTERNAL_SYNC_APPLIED_UNVERIFIED = "EXTERNAL_SYNC_APPLIED_UNVERIFIED"
    EXTERNAL_SYNC_PENDING = "EXTERNAL_SYNC_PENDING"
    EXTERNAL_SYNC_FAILED = "EXTERNAL_SYNC_FAILED"


class ExternalApplyFailureCode(StrEnum):
    FAILED = "FAILED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    READBACK_MISMATCH = "READBACK_MISMATCH"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    TARGET_CAPABILITY_UNSUPPORTED = "TARGET_CAPABILITY_UNSUPPORTED"
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"


@dataclass(frozen=True, slots=True)
class TargetRegistration:
    target_id: str
    target_dialect: MutationTargetKind
    canonical_projection_digest: DigestRef
    repository_base_digest: DigestRef
    applied_change_set_digest: DigestRef | None
    generation: int

    def __post_init__(self) -> None:
        if type(self.target_id) is not str or self.target_id == "":
            raise ValueError("target_id must be a non-empty string")
        if type(self.target_dialect) is not MutationTargetKind:
            raise ValueError("target_dialect must be MutationTargetKind")
        for label in ("canonical_projection_digest", "repository_base_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if self.applied_change_set_digest is not None and type(self.applied_change_set_digest) is not DigestRef:
            raise ValueError("applied_change_set_digest must be DigestRef or None")
        if type(self.generation) is not int or isinstance(self.generation, bool) or self.generation < 0:
            raise ValueError("generation must be a non-negative int")

    def to_document(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "applied_change_set_digest": None
            if self.applied_change_set_digest is None
            else self.applied_change_set_digest.value,
            "canonical_projection_digest": self.canonical_projection_digest.value,
            "generation": self.generation,
            "repository_base_digest": self.repository_base_digest.value,
            "target_dialect": self.target_dialect.value,
            "target_id": self.target_id,
        }
        return payload


@dataclass(frozen=True, slots=True)
class ExternalApplyInput:
    change_set_closure: ChangeSetClosure
    change_set_digest: DigestRef
    target_registration: TargetRegistration
    expected_repository_base_digest: DigestRef
    renderer_capability: RendererCapabilityDeclaration
    contract_version: str = EXTERNAL_TARGET_SYNC_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.change_set_closure) is not ChangeSetClosure:
            raise ValueError("change_set_closure must be ChangeSetClosure")
        if type(self.change_set_digest) is not DigestRef:
            raise ValueError("change_set_digest must be DigestRef")
        if type(self.target_registration) is not TargetRegistration:
            raise ValueError("target_registration must be TargetRegistration")
        if type(self.expected_repository_base_digest) is not DigestRef:
            raise ValueError("expected_repository_base_digest must be DigestRef")
        if type(self.renderer_capability) is not RendererCapabilityDeclaration:
            raise ValueError("renderer_capability must be RendererCapabilityDeclaration")
        if self.contract_version != EXTERNAL_TARGET_SYNC_CONTRACT_VERSION:
            raise ValueError("unsupported external target sync contract version")
        if self.change_set_digest != self.change_set_closure.manifest.change_set_digest:
            raise ValueError("change_set_digest must match closure manifest")
        if (
            self.expected_repository_base_digest
            != self.target_registration.repository_base_digest
        ):
            raise ValueError("expected_repository_base_digest must match target registration")


@dataclass(frozen=True, slots=True)
class ExternalApplyResult:
    phase: ExternalApplyPhase
    status: ExternalApplyStatus
    outcome: ExternalSyncOutcome
    change_set_digest: DigestRef
    failure_code: ExternalApplyFailureCode | None = None
    applied_change_set_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if type(self.phase) is not ExternalApplyPhase:
            raise ValueError("phase must be ExternalApplyPhase")
        if type(self.status) is not ExternalApplyStatus:
            raise ValueError("status must be ExternalApplyStatus")
        if type(self.outcome) is not ExternalSyncOutcome:
            raise ValueError("outcome must be ExternalSyncOutcome")
        if type(self.change_set_digest) is not DigestRef:
            raise ValueError("change_set_digest must be DigestRef")
        if self.failure_code is not None and type(self.failure_code) is not ExternalApplyFailureCode:
            raise ValueError("failure_code must be ExternalApplyFailureCode or None")
        if self.applied_change_set_digest is not None and type(self.applied_change_set_digest) is not DigestRef:
            raise ValueError("applied_change_set_digest must be DigestRef or None")
        if self.status is ExternalApplyStatus.SUCCEEDED:
            if self.failure_code is not None:
                raise ValueError("SUCCEEDED apply must not carry failure_code")
            if self.applied_change_set_digest is None:
                raise ValueError("SUCCEEDED apply requires applied_change_set_digest")
            if self.outcome not in {
                ExternalSyncOutcome.EXTERNAL_SYNC_SUCCEEDED,
                ExternalSyncOutcome.EXTERNAL_SYNC_APPLIED_UNVERIFIED,
            }:
                raise ValueError("SUCCEEDED apply requires a success outcome")
            return
        if self.status is ExternalApplyStatus.UNKNOWN_OUTCOME:
            if self.outcome is not ExternalSyncOutcome.EXTERNAL_SYNC_PENDING:
                raise ValueError("UNKNOWN_OUTCOME apply must remain pending")
            return
        if self.failure_code is None:
            raise ValueError("FAILED apply requires failure_code")
        if self.outcome is not ExternalSyncOutcome.EXTERNAL_SYNC_FAILED:
            raise ValueError("FAILED apply must use EXTERNAL_SYNC_FAILED outcome")


@dataclass(frozen=True, slots=True)
class ReferenceExecutorCheckpoint:
    """Test-only reference executor fixture shape; not durable production state."""

    checkpoint_contract_version: str
    target_id: str
    phase: ExternalApplyPhase
    change_set_digest: DigestRef
    applied_change_set_digest: DigestRef | None
    ledger_digest: DigestRef
    transaction_id: str

    def __post_init__(self) -> None:
        if self.checkpoint_contract_version != REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION:
            raise ValueError("unsupported reference executor checkpoint contract version")
        if type(self.target_id) is not str or self.target_id == "":
            raise ValueError("target_id must be a non-empty string")
        if type(self.phase) is not ExternalApplyPhase:
            raise ValueError("phase must be ExternalApplyPhase")
        if type(self.change_set_digest) is not DigestRef:
            raise ValueError("change_set_digest must be DigestRef")
        if self.applied_change_set_digest is not None and type(self.applied_change_set_digest) is not DigestRef:
            raise ValueError("applied_change_set_digest must be DigestRef or None")
        if type(self.ledger_digest) is not DigestRef:
            raise ValueError("ledger_digest must be DigestRef")
        if type(self.transaction_id) is not str or self.transaction_id == "":
            raise ValueError("transaction_id must be a non-empty string")

    def to_document(self) -> dict[str, object]:
        return {
            "applied_change_set_digest": None
            if self.applied_change_set_digest is None
            else self.applied_change_set_digest.value,
            "change_set_digest": self.change_set_digest.value,
            "checkpoint_contract_version": self.checkpoint_contract_version,
            "ledger_digest": self.ledger_digest.value,
            "phase": self.phase.value,
            "target_id": self.target_id,
            "transaction_id": self.transaction_id,
        }


def reference_executor_checkpoint_from_document(
    document: Mapping[str, object],
) -> ReferenceExecutorCheckpoint:
    if type(document) is not dict:
        raise ValueError("reference executor checkpoint document must be a dict")
    _reject_unknown_keys(document, _CHECKPOINT_DOCUMENT_KEYS, "reference executor checkpoint")
    applied_payload = document.get("applied_change_set_digest")
    applied_digest = None if applied_payload is None else DigestRef(_require_string(applied_payload))
    return ReferenceExecutorCheckpoint(
        checkpoint_contract_version=_require_string(document.get("checkpoint_contract_version")),
        target_id=_require_string(document.get("target_id")),
        phase=ExternalApplyPhase(_require_string(document.get("phase"))),
        change_set_digest=DigestRef(_require_string(document.get("change_set_digest"))),
        applied_change_set_digest=applied_digest,
        ledger_digest=DigestRef(_require_string(document.get("ledger_digest"))),
        transaction_id=_require_string(document.get("transaction_id")),
    )


def target_registration_from_document(document: Mapping[str, object]) -> TargetRegistration:
    if type(document) is not dict:
        raise ValueError("target registration document must be a dict")
    _reject_unknown_keys(document, _REGISTRATION_DOCUMENT_KEYS, "target registration")
    applied_payload = document.get("applied_change_set_digest")
    applied_digest = None if applied_payload is None else DigestRef(_require_string(applied_payload))
    return TargetRegistration(
        target_id=_require_string(document.get("target_id")),
        target_dialect=MutationTargetKind(_require_string(document.get("target_dialect"))),
        canonical_projection_digest=DigestRef(
            _require_string(document.get("canonical_projection_digest"))
        ),
        repository_base_digest=DigestRef(_require_string(document.get("repository_base_digest"))),
        applied_change_set_digest=applied_digest,
        generation=_require_int(document.get("generation")),
    )


def compute_reference_executor_checkpoint_digest(
    checkpoint: ReferenceExecutorCheckpoint,
) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(checkpoint.to_document()))


def _require_string(value: object) -> str:
    if type(value) is not str or value == "":
        raise ValueError("expected non-empty string")
    return value


def _require_int(value: object) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise ValueError("expected int")
    return value


def _reject_unknown_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")
