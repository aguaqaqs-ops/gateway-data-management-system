"""Production canonical-row-hash subject harness."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.constants import (
    FORMAL_PROVIDER_MATRIX_PROVIDER_IDS,
)
from gateway_conformance.harness.canonical_row_hashes.integration import (
    IntegrationArtifactSession,
    compute_integration_result_value,
)
from gateway_conformance.harness.canonical_row_hashes.native_compute import (
    compute_native_result_value,
)
from gateway_conformance.harness.canonical_row_hashes.reference import (
    compute_reference_result_value,
)
from gateway_conformance.harness.canonical_row_hashes.result_payload import (
    build_row_hashes_observation,
)
from gateway_conformance.runner.runtime import HarnessRuntimeContext
from gateway_conformance.runner.types import (
    CleanupReceipt,
    InvocationReceipt,
    ObservationSet,
    PhaseReceipt,
    RecoveryReceipt,
    SupportDecision,
)

CleanupMode = Literal["CLEAN", "LEAKED", "FAILED"]


class CanonicalRowHashesSubjectHarness:
    """Formal scenario production harness (profile-dispatched)."""

    def __init__(self, *, cleanup_mode: CleanupMode = "CLEAN") -> None:
        self._cleanup_mode: CleanupMode = cleanup_mode
        self._integration_session = IntegrationArtifactSession()
        self._integration_root: Path | None = None

    def preflight(self, plan: dict[str, object]) -> SupportDecision:
        execution_key = plan.get("execution_key")
        if not isinstance(execution_key, dict):
            raise ConformanceValidationError("plan missing execution_key")
        profile = str(execution_key.get("profile", ""))
        provider_id = execution_key.get("provider_id")
        if profile in {"reference", "integration"}:
            if provider_id is not None:
                return SupportDecision(
                    support="UNSUPPORTED",
                    reason_code="reference-integration-require-null-provider",
                )
        elif profile == "provider-matrix":
            if provider_id is None:
                return SupportDecision(
                    support="UNSUPPORTED",
                    reason_code="provider-matrix-requires-provider-id",
                )
            if str(provider_id) not in FORMAL_PROVIDER_MATRIX_PROVIDER_IDS:
                return SupportDecision(
                    support="UNSUPPORTED",
                    reason_code="unknown-provider-id",
                )
        else:
            return SupportDecision(support="UNSUPPORTED", reason_code="unknown-profile")
        if profile in {"integration", "provider-matrix"} and str(provider_id) == "rust-native":
            try:
                import gateway_backend  # noqa: F401
                import gateway_compute  # noqa: F401
            except ImportError:
                return SupportDecision(
                    support="UNSUPPORTED",
                    reason_code="native-backend-unavailable",
                )
        if profile == "integration":
            try:
                import gateway_backend  # noqa: F401
            except ImportError:
                return SupportDecision(
                    support="UNSUPPORTED",
                    reason_code="integration-backend-unavailable",
                )
        return SupportDecision(support="SUPPORTED")

    def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
        _ = plan
        profile = context.profile.profile
        if profile == "integration":
            self._integration_root = self._integration_session.provision()
        return PhaseReceipt(phase="seed", outcome="COMPLETED")

    def invoke(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> InvocationReceipt:
        _ = context, plan
        return InvocationReceipt.completed()

    def stabilize_and_observe(
        self,
        context: HarnessRuntimeContext,
        plan: dict[str, object],
        *,
        observation_point: str,
    ) -> ObservationSet:
        profile = context.profile.profile
        provider_id = context.profile.provider_id
        try:
            if profile == "reference":
                value = compute_reference_result_value(context, plan)
            elif profile == "integration":
                if self._integration_root is None:
                    raise ConformanceValidationError("integration artifact root not provisioned")
                value = compute_integration_result_value(
                    context, plan, artifact_root=self._integration_root
                )
            elif profile == "provider-matrix":
                if provider_id == "python-reference":
                    value = compute_reference_result_value(context, plan)
                elif provider_id == "rust-native":
                    value = compute_native_result_value(context, plan)
                else:
                    raise ConformanceValidationError("unknown provider-matrix provider")
            else:
                raise ConformanceValidationError("unsupported profile for observation")
            obs = build_row_hashes_observation(
                plan, observation_point=observation_point, value=value
            )
        except ConformanceValidationError:
            raise
        except Exception as exc:
            raise ConformanceValidationError(str(exc)) from exc
        return ObservationSet(
            observations=(obs,),
            receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
        )

    def drive_recovery(
        self, context: HarnessRuntimeContext, plan: dict[str, object]
    ) -> RecoveryReceipt:
        _ = context, plan
        return RecoveryReceipt.completed()

    def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
        _ = context
        try:
            self._integration_session.cleanup()
            self._integration_root = None
        except Exception:
            if self._cleanup_mode == "CLEAN":
                return CleanupReceipt(status="FAILED")
        return CleanupReceipt(status=self._cleanup_mode)
