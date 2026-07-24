"""Test-only fake subject harness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from gateway_conformance.owner.validate import compute_owner_content_digest
from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.runtime import HarnessRuntimeContext
from gateway_conformance.runner.types import (
    ActualObservation,
    CleanupReceipt,
    InvocationReceipt,
    ObservationSet,
    PhaseReceipt,
    RecoveryReceipt,
    SupportDecision,
)

PhaseBehavior = Literal["ok", "fail", "unsupported"]


@dataclass(slots=True, weakref_slot=True)
class FakeSubjectHarness:
    """Configurable harness for contract tests."""

    preflight_behavior: PhaseBehavior = "ok"
    seed_behavior: PhaseBehavior = "ok"
    invoke_behavior: PhaseBehavior = "ok"
    observe_behavior: PhaseBehavior = "ok"
    recovery_behavior: PhaseBehavior = "ok"
    cleanup_status: Literal["CLEAN", "LEAKED", "FAILED"] = "CLEAN"
    observation_mode: Literal["match", "mismatch", "missing", "duplicate", "unexpected"] = "match"
    phase_log: list[str] = field(default_factory=list)
    side_effect_counts: dict[str, int] = field(default_factory=dict)
    custom_observations: dict[str, list[ActualObservation]] | None = None
    fail_stable_code: str = "fake-failed"
    on_phase: Callable[[str], None] | None = None

    def _record(self, phase: str) -> None:
        self.phase_log.append(phase)
        self.side_effect_counts[phase] = self.side_effect_counts.get(phase, 0) + 1
        if self.on_phase is not None:
            self.on_phase(phase)

    def preflight(self, plan: dict[str, object]) -> SupportDecision:
        self._record("preflight")
        if self.preflight_behavior == "unsupported":
            return SupportDecision(support="UNSUPPORTED", reason_code="fake-unsupported")
        if self.preflight_behavior == "fail":
            raise ConformanceValidationError("fake preflight infrastructure failure")
        return SupportDecision(support="SUPPORTED")

    def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
        self._record("seed")
        if self.seed_behavior == "fail":
            return PhaseReceipt(phase="seed", outcome="FAILED", stable_code=self.fail_stable_code)
        return PhaseReceipt(phase="seed", outcome="COMPLETED")

    def invoke(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> InvocationReceipt:
        self._record("invoke")
        if self.invoke_behavior == "fail":
            return InvocationReceipt.failed(stable_code=self.fail_stable_code)
        if "fault" in plan and context.fault is not None:
            context.fault.consume()
        return InvocationReceipt.completed()

    def _build_observation(
        self,
        request: dict[str, Any],
        *,
        observation_point: str,
        value: Any,
    ) -> ActualObservation:
        binding = dict(request["contract_binding"])
        descriptor = dict(request["payload_descriptor"])
        digest = compute_owner_content_digest(
            value,
            owner=str(binding["owner"]),
            contract_id=str(binding["contract_id"]),
            semantic_version=str(binding["semantic_version"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=int(descriptor["schema_version"]),
        )
        return ActualObservation(
            expectation_id=str(request["expectation_id"]),
            observation_point=observation_point,
            contract_binding=binding,
            payload_descriptor=descriptor,
            canonical_encoding_version=1,
            actual_content_digest=digest,
            payload={"storage": "inline", "value": value},
        )

    def _default_value_for_request(self, request: dict[str, Any], plan: dict[str, object]) -> Any:
        kind = str(request["kind"])
        if kind == "structured":
            return {"status": "ok"}
        if kind == "recovery":
            return {"checkpoints": ["ok"]}
        if kind == "artifact":
            manifest_value = {"artifact": True}
            binding = request["contract_binding"]
            descriptor = request["payload_descriptor"]
            digest = compute_owner_content_digest(
                manifest_value,
                owner=str(binding["owner"]),
                contract_id=str(binding["contract_id"]),
                semantic_version=str(binding["semantic_version"]),
                schema_id=str(descriptor["schema_id"]),
                schema_version=int(descriptor["schema_version"]),
            )
            return {"content_digest": digest, "manifest": manifest_value}
        return {}

    def stabilize_and_observe(
        self,
        context: HarnessRuntimeContext,
        plan: dict[str, object],
        *,
        observation_point: str,
    ) -> ObservationSet:
        self._record(f"stabilize_and_observe:{observation_point}")
        if self.observe_behavior == "fail":
            return ObservationSet(
                observations=(),
                receipt=PhaseReceipt(
                    phase="stabilize_and_observe",
                    outcome="FAILED",
                    stable_code=self.fail_stable_code,
                ),
            )
        requests = cast(list[dict[str, Any]], plan["observation_requests"])
        if self.custom_observations and observation_point in self.custom_observations:
            custom = tuple(self.custom_observations[observation_point])
            return ObservationSet(
                observations=custom,
                receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
            )
        observations: tuple[ActualObservation, ...]
        if self.observation_mode == "missing":
            observations = ()
        elif self.observation_mode == "duplicate":
            req = dict(requests[0])
            value = self._default_value_for_request(req, plan)
            obs = self._build_observation(req, observation_point=observation_point, value=value)
            observations = (obs, obs)
        elif self.observation_mode == "unexpected":
            req = dict(requests[0])
            value = self._default_value_for_request(req, plan)
            obs = self._build_observation(req, observation_point=observation_point, value=value)
            extra = self._build_observation(
                {
                    **req,
                    "expectation_id": "unexpected-extra",
                },
                observation_point=observation_point,
                value=value,
            )
            observations = (obs, extra)
        else:
            built: list[ActualObservation] = []
            for raw in requests:
                req = dict(raw)
                value = self._default_value_for_request(req, plan)
                if self.observation_mode == "mismatch" and str(req["kind"]) == "structured":
                    value = {"status": "bad"}
                obs = self._build_observation(req, observation_point=observation_point, value=value)
                if self.observation_mode == "mismatch" and observation_point == "after-failure":
                    obs = self._build_observation(
                        req, observation_point=observation_point, value={"checkpoints": ["bad"]}
                    )
                built.append(obs)
            observations = tuple(built)
        return ObservationSet(
            observations=observations,
            receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
        )

    def drive_recovery(
        self, context: HarnessRuntimeContext, plan: dict[str, object]
    ) -> RecoveryReceipt:
        self._record("drive_recovery")
        if self.recovery_behavior == "fail":
            return RecoveryReceipt.failed(stable_code=self.fail_stable_code)
        return RecoveryReceipt.completed()

    def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
        self._record("cleanup_subject")
        return CleanupReceipt(status=self.cleanup_status)
