"""Harness protocol v1 runtime DTOs (not persisted wire schemas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

HARNESS_PROTOCOL_VERSION = 1

PhaseName = Literal[
    "preflight",
    "seed",
    "invoke",
    "stabilize_and_observe",
    "drive_recovery",
    "cleanup_subject",
]

SupportLevel = Literal["SUPPORTED", "UNSUPPORTED"]
PhaseOutcome = Literal["COMPLETED", "FAILED"]
CleanupStatus = Literal["CLEAN", "LEAKED", "FAILED"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str

    def to_wire(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class SupportDecision:
    support: SupportLevel
    reason_code: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "harness_protocol_version": HARNESS_PROTOCOL_VERSION,
            "support": self.support,
            "diagnostics": [item.to_wire() for item in self.diagnostics],
        }
        if self.support == "UNSUPPORTED":
            payload["reason_code"] = self.reason_code or "unsupported"
        return payload


@dataclass(frozen=True, slots=True)
class PhaseReceipt:
    phase: PhaseName
    outcome: PhaseOutcome
    stable_code: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "harness_protocol_version": HARNESS_PROTOCOL_VERSION,
            "phase": self.phase,
            "outcome": self.outcome,
            "diagnostics": [item.to_wire() for item in self.diagnostics],
        }
        if self.outcome == "FAILED":
            payload["stable_code"] = self.stable_code or "phase-failed"
        return payload


class InvocationReceipt(PhaseReceipt):
    @classmethod
    def completed(cls, *, diagnostics: tuple[Diagnostic, ...] = ()) -> InvocationReceipt:
        return cls(phase="invoke", outcome="COMPLETED", diagnostics=diagnostics)

    @classmethod
    def failed(
        cls, *, stable_code: str, diagnostics: tuple[Diagnostic, ...] = ()
    ) -> InvocationReceipt:
        return cls(
            phase="invoke",
            outcome="FAILED",
            stable_code=stable_code,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class RecoveryReceipt(PhaseReceipt):
    @classmethod
    def completed(cls, *, diagnostics: tuple[Diagnostic, ...] = ()) -> RecoveryReceipt:
        return cls(phase="drive_recovery", outcome="COMPLETED", diagnostics=diagnostics)

    @classmethod
    def failed(
        cls, *, stable_code: str, diagnostics: tuple[Diagnostic, ...] = ()
    ) -> RecoveryReceipt:
        return cls(
            phase="drive_recovery",
            outcome="FAILED",
            stable_code=stable_code,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    status: CleanupStatus
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        return {
            "harness_protocol_version": HARNESS_PROTOCOL_VERSION,
            "phase": "cleanup_subject",
            "outcome": "COMPLETED" if self.status == "CLEAN" else "FAILED",
            "cleanup_status": self.status,
            "diagnostics": [item.to_wire() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ActualObservation:
    expectation_id: str
    observation_point: str
    contract_binding: dict[str, Any]
    payload_descriptor: dict[str, Any]
    canonical_encoding_version: int
    actual_content_digest: str
    payload: dict[str, Any]
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        return {
            "harness_protocol_version": HARNESS_PROTOCOL_VERSION,
            "expectation_id": self.expectation_id,
            "observation_point": self.observation_point,
            "contract_binding": self.contract_binding,
            "payload_descriptor": self.payload_descriptor,
            "canonical_encoding_version": self.canonical_encoding_version,
            "actual_content_digest": self.actual_content_digest,
            "payload": self.payload,
            "diagnostics": [item.to_wire() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ObservationSet:
    observations: tuple[ActualObservation, ...]
    receipt: PhaseReceipt

    def to_wire(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_wire(),
            "observations": [item.to_wire() for item in self.observations],
        }


@dataclass
class ComparisonRow:
    expectation_id: str
    expected_content_digest: str
    actual_content_digest: str | None
    outcome: Literal["NOT_RUN", "MATCH", "MISMATCH"]


@dataclass
class RunState:
    harness_error: bool = False
    unsupported: bool = False
    unsupported_reason: str | None = None
    comparison_rows: list[ComparisonRow] = field(default_factory=list)
    checkpoint_results: list[dict[str, Any]] = field(default_factory=list)
    collected_observations: list[ActualObservation] = field(default_factory=list)
    fault_receipt: dict[str, Any] | None = None
    cleanup_status: CleanupStatus = "CLEAN"
    cleanup_diagnostics: list[Diagnostic] = field(default_factory=list)
    runner_diagnostics: list[Diagnostic] = field(default_factory=list)
    provision_count: int = 0
    checkpoint_gate_expectation_digests: dict[str, str] = field(default_factory=dict)
    checkpoint_gate_mismatch_ids: set[str] = field(default_factory=set)
    validated_environment_versions: list[dict[str, str]] | None = None
    subject_started: bool = False
