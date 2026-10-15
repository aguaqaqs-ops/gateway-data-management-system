"""Pure R5 recovery policy, budgets, diagnostics and transition mapping."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    _validate_opaque_id,
)
from gateway_backend.operations.persistence import LEASE_DURATION
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from gateway_backend.operations.store import LeaseExpired, OperationStore, StaleWrite, StoreBusy
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    StartupDisposition,
    WriteUnitOfWorkFactory,
)

OPERATOR_RECOVERY_WORKER_ID = "operator-recovery"

MAX_RECOVERY_SESSIONS = 3
RECOVERY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
RECOVERY_BACKOFF_CAP_SECONDS = 10.0
RECONCILE_SESSION_BUDGET_SECONDS = 60.0

DIAGNOSTIC_LEASE_EXPIRED = "r5.lease_expired"
DIAGNOSTIC_RETRY_SCHEDULED = "r5.retry_scheduled"
DIAGNOSTIC_RECONCILE_STARTED = "r5.reconcile_started"
DIAGNOSTIC_RECONCILE_TIMEOUT = "r5.reconcile_timeout"
DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED = "r5.manual_recovery_required"
DIAGNOSTIC_RECOVERY_AUTHORIZED = "r5.recovery_authorized"

RECOVERY_DIAGNOSTIC_CODES = frozenset(
    {
        DIAGNOSTIC_LEASE_EXPIRED,
        DIAGNOSTIC_RETRY_SCHEDULED,
        DIAGNOSTIC_RECONCILE_STARTED,
        DIAGNOSTIC_RECONCILE_TIMEOUT,
        DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
        DIAGNOSTIC_RECOVERY_AUTHORIZED,
    }
)

_NAMESPACED_DIAGNOSTIC_CODE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_MAX_DIAGNOSTIC_MESSAGE_BYTES = 4 * 1024

Jitter = Callable[[float, float], float]
NowFactory = Callable[[], datetime]


class RecoveryCapabilityValue(StrEnum):
    """Mirror of application RecoveryCapability without importing application."""

    PURE_RECOMPUTE = "PURE_RECOMPUTE"
    EXTERNAL_EFFECT = "EXTERNAL_EFFECT"
    NON_RETRYABLE = "NON_RETRYABLE"


RecoveryCapabilityLookup = Callable[[str, str], RecoveryCapabilityValue]


class RecoveryPolicyDecisionDisposition(StrEnum):
    """Mirror of application RecoveryDecisionDisposition."""

    NO_ACTION = "NO_ACTION"
    MOVE_TO_RETRY_WAIT = "MOVE_TO_RETRY_WAIT"
    CLAIM_FOR_RECONCILE = "CLAIM_FOR_RECONCILE"
    MARK_MANUAL_RECOVERY = "MARK_MANUAL_RECOVERY"
    BLOCK_STARTUP_RETRYABLE = "BLOCK_STARTUP_RETRYABLE"
    BLOCK_STARTUP_FATAL = "BLOCK_STARTUP_FATAL"


class RecoveryPolicyOutcomeDisposition(StrEnum):
    """Mirror of application RecoveryOutcomeDisposition."""

    PUBLISHED = "PUBLISHED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    RECONCILE_PENDING = "RECONCILE_PENDING"
    MANUAL_RECOVERY = "MANUAL_RECOVERY"
    CANCELLED = "CANCELLED"


class HandlerFailureKind(StrEnum):
    """Bounded handler failure classification for policy routing."""

    RETRYABLE = "RETRYABLE"
    PERMANENT = "PERMANENT"
    UNCLASSIFIED = "UNCLASSIFIED"
    RECONCILE = "RECONCILE"
    CHECKPOINT_UNREADABLE = "CHECKPOINT_UNREADABLE"


class ExternalEffectPhase(StrEnum):
    """Bounded external-effect request phase for reconcile/retry routing."""

    REQUEST_NOT_ACCEPTED = "REQUEST_NOT_ACCEPTED"
    REQUEST_ACCEPTED_OR_UNKNOWN = "REQUEST_ACCEPTED_OR_UNKNOWN"


@dataclass(frozen=True, slots=True)
class RecoveryPolicyDecision:
    """Read-only bounded recovery decision produced by R5 policy."""

    disposition: RecoveryPolicyDecisionDisposition
    diagnostic_code: str
    retry_not_before: datetime | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.disposition) is not RecoveryPolicyDecisionDisposition:
            raise ValueError("disposition must be RecoveryPolicyDecisionDisposition")
        _validate_namespaced_diagnostic_code(self.diagnostic_code)
        _validate_bounded_diagnostic_message(self.reason)
        if self.disposition is RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT:
            if self.retry_not_before is None:
                raise ValueError("retry_not_before is required for MOVE_TO_RETRY_WAIT")
            _validate_utc_datetime(self.retry_not_before, "retry_not_before")
        elif self.retry_not_before is not None:
            raise ValueError("retry_not_before must be null unless disposition is MOVE_TO_RETRY_WAIT")


@dataclass(frozen=True, slots=True)
class RecoveryTransitionIntent:
    """Read-only durable transition plan; CAS application remains outside policy."""

    step_source: StepStatus
    step_target: StepStatus | None
    operation_source: OperationStatus
    operation_target: OperationStatus | None
    set_retry_not_before: datetime | None
    retain_occupancy: bool
    increment_attempt_on_claim: bool


def recovery_backoff_base_seconds(session_index: int) -> float:
    if type(session_index) is not int or session_index < 1:
        raise ValueError("session_index must be a positive integer")
    sequence_index = min(session_index, len(RECOVERY_BACKOFF_SECONDS)) - 1
    return min(RECOVERY_BACKOFF_CAP_SECONDS, RECOVERY_BACKOFF_SECONDS[sequence_index])


def apply_recovery_backoff_jitter(
    base: float,
    cap: float,
    *,
    jitter: Jitter,
) -> float:
    if base < 0 or cap < base:
        raise ValueError("backoff bounds are invalid")
    delay = jitter(base, cap)
    if isinstance(delay, bool) or not isinstance(delay, (int, float)):
        raise ValueError("jitter must return a number")
    if delay < base or delay > cap:
        raise ValueError("jitter result must remain within the bounded backoff")
    return float(delay)


def compute_retry_not_before(
    now: datetime,
    session_index: int,
    *,
    jitter: Jitter,
) -> datetime:
    _validate_utc_datetime(now, "now")
    base = recovery_backoff_base_seconds(session_index)
    delay = apply_recovery_backoff_jitter(base, RECOVERY_BACKOFF_CAP_SECONDS, jitter=jitter)
    return now + timedelta(seconds=delay)


def recovery_sessions_remaining(attempt_count: int) -> int:
    if type(attempt_count) is not int or attempt_count < 1:
        raise ValueError("attempt_count must be a positive integer")
    return max(0, MAX_RECOVERY_SESSIONS - attempt_count)


def recovery_sessions_exhausted(attempt_count: int) -> bool:
    return recovery_sessions_remaining(attempt_count) == 0


def reconcile_budget_exhausted(elapsed_seconds: float) -> bool:
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
        raise ValueError("elapsed_seconds must be a number")
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be non-negative")
    return float(elapsed_seconds) >= RECONCILE_SESSION_BUDGET_SECONDS


def _retry_wait_decision(
    now: datetime,
    attempt_count: int,
    *,
    jitter: Jitter,
    diagnostic_code: str,
    reason: str,
) -> RecoveryPolicyDecision:
    retry_not_before = compute_retry_not_before(now, attempt_count, jitter=jitter)
    return RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT,
        diagnostic_code=diagnostic_code,
        retry_not_before=retry_not_before,
        reason=reason,
    )


def _manual_recovery_decision(*, diagnostic_code: str, reason: str) -> RecoveryPolicyDecision:
    return RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY,
        diagnostic_code=diagnostic_code,
        retry_not_before=None,
        reason=reason,
    )


def classify_expired_lease(
    *,
    capability: RecoveryCapabilityValue,
    attempt_count: int,
    now: datetime,
    jitter: Jitter,
) -> RecoveryPolicyDecision:
    if capability is RecoveryCapabilityValue.NON_RETRYABLE:
        return _manual_recovery_decision(
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason="non-retryable capability after lease expiry",
        )
    if recovery_sessions_exhausted(attempt_count):
        return _manual_recovery_decision(
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason="recovery session budget exhausted after lease expiry",
        )
    if capability is RecoveryCapabilityValue.EXTERNAL_EFFECT:
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE,
            diagnostic_code=DIAGNOSTIC_RECONCILE_STARTED,
            retry_not_before=None,
            reason="schedule reconcile after lease expiry",
        )
    return _retry_wait_decision(
        now,
        attempt_count,
        jitter=jitter,
        diagnostic_code=DIAGNOSTIC_LEASE_EXPIRED,
        reason="lease expired; schedule safe retry",
    )


def classify_startup(
    *,
    operation: OperationRecord,
    step: StepRecord,
    capability: RecoveryCapabilityValue,
    lease_expired: bool,
    now: datetime,
    jitter: Jitter,
) -> RecoveryPolicyDecision:
    if (
        operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
        or step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
    ):
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.NO_ACTION,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            retry_not_before=None,
            reason="manual recovery record does not block startup readiness",
        )
    if not lease_expired:
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.NO_ACTION,
            diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
            retry_not_before=None,
            reason="active lease requires no startup recovery action",
        )
    if capability is RecoveryCapabilityValue.NON_RETRYABLE:
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            retry_not_before=None,
            reason="non-retryable capability cannot recover after lease expiry",
        )
    if recovery_sessions_exhausted(step.attempt_count):
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            retry_not_before=None,
            reason="recovery session budget exhausted at startup",
        )
    if capability is RecoveryCapabilityValue.EXTERNAL_EFFECT:
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE,
            diagnostic_code=DIAGNOSTIC_RECONCILE_STARTED,
            retry_not_before=None,
            reason="startup reconcile scheduling for external effect",
        )
    return RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_RETRYABLE,
        diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
        retry_not_before=None,
        reason="startup safe retry scheduling after lease expiry",
    )


def classify_cancel(
    *,
    cancel_requested: bool,
    effect_boundary_crossed: bool,
) -> RecoveryPolicyOutcomeDisposition | None:
    if not cancel_requested:
        return None
    if effect_boundary_crossed:
        return RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING
    return RecoveryPolicyOutcomeDisposition.CANCELLED


def classify_handler_failure(
    *,
    capability: RecoveryCapabilityValue,
    failure_kind: HandlerFailureKind,
    effect_phase: ExternalEffectPhase | None = None,
    evidence_ambiguous: bool = False,
) -> RecoveryPolicyOutcomeDisposition:
    if failure_kind is HandlerFailureKind.CHECKPOINT_UNREADABLE:
        return RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY
    if capability is RecoveryCapabilityValue.NON_RETRYABLE:
        if evidence_ambiguous:
            return RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY
        return RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE
    if failure_kind is HandlerFailureKind.PERMANENT:
        return RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE
    if failure_kind is HandlerFailureKind.UNCLASSIFIED:
        return RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY
    if capability is RecoveryCapabilityValue.EXTERNAL_EFFECT:
        if effect_phase is ExternalEffectPhase.REQUEST_NOT_ACCEPTED:
            return RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE
        if effect_phase is ExternalEffectPhase.REQUEST_ACCEPTED_OR_UNKNOWN:
            return RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING
        return RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY
    if failure_kind is HandlerFailureKind.RECONCILE:
        return RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING
    return RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE


def transition_for_decision(
    decision: RecoveryPolicyDecision,
    *,
    step_source: StepStatus = StepStatus.RUNNING,
    operation_source: OperationStatus = OperationStatus.RUNNING,
    attempt_count: int = 1,
    now: datetime | None = None,
    jitter: Jitter | None = None,
) -> RecoveryTransitionIntent:
    disposition = decision.disposition
    if disposition is RecoveryPolicyDecisionDisposition.NO_ACTION:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=None,
            operation_source=operation_source,
            operation_target=None,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if disposition is RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.RETRY_WAIT,
            operation_source=operation_source,
            operation_target=None,
            set_retry_not_before=decision.retry_not_before,
            retain_occupancy=False,
            increment_attempt_on_claim=True,
        )
    if disposition in {
        RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE,
        RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_RETRYABLE,
    }:
        retry_not_before = _schedule_retry_not_before(
            attempt_count=attempt_count,
            now=now,
            jitter=jitter,
        )
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.RETRY_WAIT,
            operation_source=operation_source,
            operation_target=None,
            set_retry_not_before=retry_not_before,
            retain_occupancy=False,
            increment_attempt_on_claim=True,
        )
    if disposition is RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.MANUAL_RECOVERY_REQUIRED,
            operation_source=operation_source,
            operation_target=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            set_retry_not_before=None,
            retain_occupancy=True,
            increment_attempt_on_claim=False,
        )
    if disposition is RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.MANUAL_RECOVERY_REQUIRED,
            operation_source=operation_source,
            operation_target=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            set_retry_not_before=None,
            retain_occupancy=True,
            increment_attempt_on_claim=False,
        )
    raise ValueError("unsupported recovery policy decision disposition")


def transition_for_outcome(
    outcome_disposition: RecoveryPolicyOutcomeDisposition,
    *,
    capability: RecoveryCapabilityValue,
    attempt_count: int,
    reconcile_elapsed_seconds: float,
    effect_boundary_crossed: bool,
    cancel_requested: bool,
    now: datetime,
    jitter: Jitter,
    evidence_ambiguous: bool = False,
    step_source: StepStatus = StepStatus.RUNNING,
    operation_source: OperationStatus = OperationStatus.RUNNING,
) -> RecoveryTransitionIntent:
    cancel_outcome = classify_cancel(
        cancel_requested=cancel_requested,
        effect_boundary_crossed=effect_boundary_crossed,
    )
    if cancel_outcome is RecoveryPolicyOutcomeDisposition.CANCELLED:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.CANCELLED,
            operation_source=operation_source,
            operation_target=OperationStatus.CANCELLED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if cancel_outcome is RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING:
        outcome_disposition = RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING

    if outcome_disposition is RecoveryPolicyOutcomeDisposition.PUBLISHED:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.SUCCEEDED,
            operation_source=operation_source,
            operation_target=OperationStatus.SUCCEEDED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if outcome_disposition is RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE:
        if recovery_sessions_exhausted(attempt_count):
            return transition_for_outcome(
                RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE,
                capability=capability,
                attempt_count=attempt_count,
                reconcile_elapsed_seconds=reconcile_elapsed_seconds,
                effect_boundary_crossed=effect_boundary_crossed,
                cancel_requested=False,
                now=now,
                jitter=jitter,
                evidence_ambiguous=evidence_ambiguous,
                step_source=step_source,
                operation_source=operation_source,
            )
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.RETRY_WAIT,
            operation_source=operation_source,
            operation_target=None,
            set_retry_not_before=compute_retry_not_before(now, attempt_count, jitter=jitter),
            retain_occupancy=False,
            increment_attempt_on_claim=True,
        )
    if outcome_disposition is RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING:
        if recovery_sessions_exhausted(attempt_count):
            return transition_for_outcome(
                RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
                capability=capability,
                attempt_count=attempt_count,
                reconcile_elapsed_seconds=reconcile_elapsed_seconds,
                effect_boundary_crossed=effect_boundary_crossed,
                cancel_requested=False,
                now=now,
                jitter=jitter,
                evidence_ambiguous=evidence_ambiguous,
                step_source=step_source,
                operation_source=operation_source,
            )
        if reconcile_budget_exhausted(reconcile_elapsed_seconds):
            return transition_for_outcome(
                RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
                capability=capability,
                attempt_count=attempt_count,
                reconcile_elapsed_seconds=reconcile_elapsed_seconds,
                effect_boundary_crossed=effect_boundary_crossed,
                cancel_requested=False,
                now=now,
                jitter=jitter,
                evidence_ambiguous=evidence_ambiguous,
                step_source=step_source,
                operation_source=operation_source,
            )
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.RETRY_WAIT,
            operation_source=operation_source,
            operation_target=None,
            set_retry_not_before=compute_retry_not_before(now, attempt_count, jitter=jitter),
            retain_occupancy=False,
            increment_attempt_on_claim=True,
        )
    if outcome_disposition is RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE:
        if capability is RecoveryCapabilityValue.NON_RETRYABLE and evidence_ambiguous:
            return transition_for_outcome(
                RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
                capability=capability,
                attempt_count=attempt_count,
                reconcile_elapsed_seconds=reconcile_elapsed_seconds,
                effect_boundary_crossed=effect_boundary_crossed,
                cancel_requested=False,
                now=now,
                jitter=jitter,
                evidence_ambiguous=evidence_ambiguous,
                step_source=step_source,
                operation_source=operation_source,
            )
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.FAILED,
            operation_source=operation_source,
            operation_target=OperationStatus.FAILED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if outcome_disposition is RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.MANUAL_RECOVERY_REQUIRED,
            operation_source=operation_source,
            operation_target=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            set_retry_not_before=None,
            retain_occupancy=True,
            increment_attempt_on_claim=False,
        )
    if outcome_disposition is RecoveryPolicyOutcomeDisposition.CANCELLED:
        if effect_boundary_crossed:
            raise ValueError("CANCELLED is forbidden after irreversible effect boundary")
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.CANCELLED,
            operation_source=operation_source,
            operation_target=OperationStatus.CANCELLED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    raise ValueError("unsupported recovery policy outcome disposition")


@dataclass(frozen=True, slots=True)
class HandlerRecoveryResult:
    """Bounded handler recovery result consumed by claim-path R5 policy."""

    disposition: RecoveryPolicyOutcomeDisposition
    diagnostic_code: str | None
    reason: str | None

    def __post_init__(self) -> None:
        if type(self.disposition) is not RecoveryPolicyOutcomeDisposition:
            raise ValueError("disposition must be RecoveryPolicyOutcomeDisposition")
        if self.diagnostic_code is not None:
            _validate_namespaced_diagnostic_code(self.diagnostic_code)
        if self.reason is not None:
            _validate_bounded_diagnostic_message(self.reason)


class HandlerExecutionFailure(Exception):
    """Classified pure-recompute handler failure routed through the R5 budget."""

    def __init__(self, *, retryable: bool, diagnostic_code: str, reason: str) -> None:
        if type(retryable) is not bool:
            raise ValueError("retryable must be bool")
        _validate_namespaced_diagnostic_code(diagnostic_code)
        encoded_reason = reason.encode("utf-8")
        if len(encoded_reason) > _MAX_DIAGNOSTIC_MESSAGE_BYTES:
            reason = encoded_reason[:_MAX_DIAGNOSTIC_MESSAGE_BYTES].decode(
                "utf-8",
                errors="ignore",
            )
        _validate_bounded_diagnostic_message(reason)
        super().__init__(reason)
        self.retryable = retryable
        self.diagnostic_code = diagnostic_code
        self.reason = reason


@runtime_checkable
class HandlerRecoveryCallback(Protocol):
    """In-process claim-path recovery callback; not HTTP, registry or R3 protocol."""

    def __call__(
        self,
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> HandlerRecoveryResult:
        """Execute bounded handler recovery for one claimed step."""


def should_route_claim_to_recovery(
    capability: RecoveryCapabilityValue,
    step: StepRecord,
) -> bool:
    if type(capability) is not RecoveryCapabilityValue:
        raise ValueError("capability must be RecoveryCapabilityValue")
    if type(step) is not StepRecord:
        raise ValueError("step must be StepRecord")
    if capability is RecoveryCapabilityValue.EXTERNAL_EFFECT:
        return step.checkpoint_ref is not None
    return False


def _recovery_decision_for_claim_outcome(
    result: HandlerRecoveryResult,
    intent: RecoveryTransitionIntent,
) -> RecoveryPolicyDecision:
    reason = result.reason or "handler recovery outcome"
    if intent.step_target is StepStatus.RETRY_WAIT:
        if intent.set_retry_not_before is None:
            raise ValueError("RETRY_WAIT intent requires retry_not_before")
        return RecoveryPolicyDecision(
            disposition=RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT,
            diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
            retry_not_before=intent.set_retry_not_before,
            reason=reason,
        )
    diagnostic_code = result.diagnostic_code or DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED
    return RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY,
        diagnostic_code=diagnostic_code,
        retry_not_before=None,
        reason=reason,
    )


def finalize_handler_recovery(
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    result: HandlerRecoveryResult,
    *,
    capability: RecoveryCapabilityValue,
    jitter: Jitter,
    now_factory: NowFactory,
) -> ExecutorAcknowledgment:
    committed = lease_session.completion_acknowledgment()
    if committed is not None:
        return committed
    if result.disposition is RecoveryPolicyOutcomeDisposition.PUBLISHED:
        raise ValueError("recovery returned PUBLISHED without committing session fact")

    now = now_factory()
    intent = transition_for_outcome(
        result.disposition,
        capability=capability,
        attempt_count=step.attempt_count,
        reconcile_elapsed_seconds=0.0,
        effect_boundary_crossed=False,
        cancel_requested=False,
        now=now,
        jitter=jitter,
    )
    decision = _recovery_decision_for_claim_outcome(result, intent)
    diagnostic = policy_diagnostic_to_operation_diagnostic(decision)
    acknowledgment = lease_session.publish_recovery_release(intent, diagnostic=diagnostic)
    if type(acknowledgment) is not ExecutorAcknowledgment:
        raise ValueError("publish_recovery_release must return ExecutorAcknowledgment")
    return acknowledgment


def build_recovery_routed_executor(
    handler: ClaimedExecutor,
    recovery: HandlerRecoveryCallback | None,
    capability: RecoveryCapabilityValue,
    *,
    jitter: Jitter,
    now_factory: NowFactory,
) -> ClaimedExecutor:
    if not callable(handler):
        raise ValueError("handler must be callable")
    if recovery is not None and not callable(recovery):
        raise ValueError("recovery must be callable when provided")
    if type(capability) is not RecoveryCapabilityValue:
        raise ValueError("capability must be RecoveryCapabilityValue")
    if not callable(jitter):
        raise ValueError("jitter must be callable")
    if not callable(now_factory):
        raise ValueError("now_factory must be callable")

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        if recovery is not None and should_route_claim_to_recovery(capability, step):
            result = recovery(operation, step, control, lease_session)
            if type(result) is not HandlerRecoveryResult:
                raise ValueError("recovery must return HandlerRecoveryResult")
            return finalize_handler_recovery(
                operation,
                step,
                lease_session,
                result,
                capability=capability,
                jitter=jitter,
                now_factory=now_factory,
            )
        try:
            acknowledgment = handler(operation, step, control, lease_session)
            if type(acknowledgment) is not ExecutorAcknowledgment:
                raise ValueError("handler must return ExecutorAcknowledgment")
        except (LeaseExpired, StaleWrite, StoreBusy):
            raise
        except HandlerExecutionFailure as exc:
            if capability is not RecoveryCapabilityValue.PURE_RECOMPUTE:
                raise
            result = HandlerRecoveryResult(
                disposition=(
                    RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE
                    if exc.retryable
                    else RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE
                ),
                diagnostic_code=exc.diagnostic_code,
                reason=exc.reason,
            )
            return finalize_handler_recovery(
                operation,
                step,
                lease_session,
                result,
                capability=capability,
                jitter=jitter,
                now_factory=now_factory,
            )
        except Exception as exc:
            if capability is not RecoveryCapabilityValue.PURE_RECOMPUTE:
                raise
            # Pure recompute has no external effect to reconcile. Fail this operation
            # with a bounded diagnostic and keep the worker available for later work.
            reason = f"pure-recompute handler raised {type(exc).__name__}"
            result = HandlerRecoveryResult(
                disposition=RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE,
                diagnostic_code="operation.pure_recompute_failed",
                reason=reason,
            )
            return finalize_handler_recovery(
                operation,
                step,
                lease_session,
                result,
                capability=capability,
                jitter=jitter,
                now_factory=now_factory,
            )
        return acknowledgment

    return execute


def step_lease_expired(step: StepRecord, transaction_now: datetime) -> bool:
    if step.status is not StepStatus.RUNNING:
        return False
    _validate_utc_datetime(transaction_now, "transaction_now")
    if step.lease_expires_at is None:
        return True
    return step.lease_expires_at <= transaction_now


def policy_diagnostic_to_operation_diagnostic(decision: RecoveryPolicyDecision) -> OperationDiagnostic:
    return OperationDiagnostic(
        code=decision.diagnostic_code.upper(),
        message=decision.reason,
    )


def startup_disposition_after_recovery(
    decision: RecoveryPolicyDecision,
    *,
    retry_not_before: datetime | None,
    transaction_now: datetime,
) -> StartupDisposition:
    disposition = decision.disposition
    if disposition in {
        RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL,
        RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY,
    }:
        return StartupDisposition.FATAL_BLOCK
    if disposition is RecoveryPolicyDecisionDisposition.NO_ACTION:
        return StartupDisposition.READY
    if retry_not_before is not None and retry_not_before > transaction_now:
        return StartupDisposition.RETRYABLE_BLOCK
    return StartupDisposition.READY


def _validate_startup_recovery_intent(intent: RecoveryTransitionIntent) -> None:
    if intent.step_source is not StepStatus.RUNNING:
        raise ValueError("startup recovery only supports RUNNING step sources")
    if intent.step_target not in {
        StepStatus.RETRY_WAIT,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
    }:
        raise ValueError("startup recovery only supports RETRY_WAIT or MANUAL targets")


def build_recovery_candidates(
    operation: OperationRecord,
    step: StepRecord,
    intent: RecoveryTransitionIntent,
    *,
    decision: RecoveryPolicyDecision,
    transaction_now: datetime,
) -> tuple[StepRecord, OperationRecord | None]:
    _validate_startup_recovery_intent(intent)
    _validate_utc_datetime(transaction_now, "transaction_now")
    diagnostic = policy_diagnostic_to_operation_diagnostic(decision)
    step_target = intent.step_target
    if step_target is None:
        raise ValueError("startup recovery requires a step target")

    step_candidate = dataclasses.replace(
        step,
        status=step_target,
        diagnostic=diagnostic,
        retry_not_before=intent.set_retry_not_before,
        updated_at=transaction_now,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        optimistic_version=step.optimistic_version + 1,
    )
    if step_target is StepStatus.MANUAL_RECOVERY_REQUIRED:
        if intent.operation_target is not OperationStatus.MANUAL_RECOVERY_REQUIRED:
            raise ValueError("manual recovery requires operation transition")
        operation_candidate = dataclasses.replace(
            operation,
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return step_candidate, operation_candidate
    return step_candidate, None


def apply_recovery_transition(
    store: OperationStore,
    operation: OperationRecord,
    step: StepRecord,
    intent: RecoveryTransitionIntent,
    *,
    decision: RecoveryPolicyDecision,
) -> TransitionDisposition:
    transaction_now = store.transaction_now
    step_candidate, operation_candidate = build_recovery_candidates(
        operation,
        step,
        intent,
        decision=decision,
        transaction_now=transaction_now,
    )
    step_precondition = WritePrecondition(
        expected_optimistic_version=step.optimistic_version,
        worker_id=step.worker_id,
        lease_token=step.lease_token,
    )
    step_disposition = store.compare_and_set_step(
        step_candidate,
        step_precondition,
        require_live_lease=False,
    )
    if operation_candidate is not None:
        operation_precondition = WritePrecondition(
            expected_optimistic_version=operation.optimistic_version,
            worker_id=None,
            lease_token=None,
        )
        store.compare_and_set_operation(
            operation_candidate,
            operation_precondition,
        )
    return step_disposition


@dataclass(frozen=True, slots=True)
class StartupRecovery:
    """Apply bounded startup recovery decisions through guarded R2 CAS writes."""

    write_uow_factory: WriteUnitOfWorkFactory
    capability_lookup: RecoveryCapabilityLookup
    jitter: Jitter
    now_factory: NowFactory

    def recover_pair(
        self,
        operation: OperationRecord,
        step: StepRecord,
    ) -> StartupDisposition:
        if step.status is StepStatus.RETRY_WAIT:
            return StartupDisposition.READY
        if step.status is not StepStatus.RUNNING:
            return StartupDisposition.READY

        now = self.now_factory()
        if not step_lease_expired(step, now):
            capability = self._capability_lookup(operation.job_kind, step.step_name)
            if capability is RecoveryCapabilityValue.PURE_RECOMPUTE:
                # A restarted worker must not become idle-ready while the old pure
                # computation still owns a live lease. Startup retries are bounded by
                # the worker's existing startup budget and eventually revisit expiry.
                return StartupDisposition.RETRYABLE_BLOCK
            return StartupDisposition.READY

        try:
            with self.write_uow_factory() as unit_of_work:
                store = unit_of_work.operations
                transaction_now = store.transaction_now
                fresh_operation = store.get_operation(operation.operation_id)
                fresh_step = store.get_step(step.step_id)
                if fresh_step.status is StepStatus.RETRY_WAIT:
                    return StartupDisposition.READY
                if fresh_step.status is not StepStatus.RUNNING:
                    return StartupDisposition.READY
                if not step_lease_expired(fresh_step, transaction_now):
                    return StartupDisposition.READY

                capability = self._capability_lookup(
                    fresh_operation.job_kind,
                    fresh_step.step_name,
                )
                decision = classify_startup(
                    operation=fresh_operation,
                    step=fresh_step,
                    capability=capability,
                    lease_expired=True,
                    now=transaction_now,
                    jitter=self.jitter,
                )
                if decision.disposition is RecoveryPolicyDecisionDisposition.NO_ACTION:
                    return StartupDisposition.READY

                intent = transition_for_decision(
                    decision,
                    step_source=fresh_step.status,
                    operation_source=fresh_operation.status,
                    attempt_count=fresh_step.attempt_count,
                    now=transaction_now,
                    jitter=self.jitter,
                )
                apply_recovery_transition(
                    store,
                    fresh_operation,
                    fresh_step,
                    intent,
                    decision=decision,
                )
                retry_not_before = intent.set_retry_not_before
        except (StaleWrite, StoreBusy):
            return StartupDisposition.RETRYABLE_BLOCK

        return startup_disposition_after_recovery(
            decision,
            retry_not_before=retry_not_before,
            transaction_now=transaction_now,
        )

    def _capability_lookup(self, job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        capability = self.capability_lookup(job_kind, step_name)
        if type(capability) is not RecoveryCapabilityValue:
            raise ValueError("capability_lookup must return RecoveryCapabilityValue")
        return capability


class OperatorRecoveryCommand(StrEnum):
    """Bounded internal operator recovery commands; HTTP wiring is P5-owned."""

    RESUME_RECONCILE = "RESUME_RECONCILE"
    RETRY_FROM_CHECKPOINT = "RETRY_FROM_CHECKPOINT"
    ABORT_CONFIRMED_FAILURE = "ABORT_CONFIRMED_FAILURE"


@dataclass(frozen=True, slots=True)
class OperatorRecoveryRequest:
    """Authorized operator recovery command with optimistic-version fencing."""

    command: OperatorRecoveryCommand
    operation_id: str
    step_id: str
    expected_operation_optimistic_version: int
    expected_step_optimistic_version: int
    reason: str

    def __post_init__(self) -> None:
        if type(self.command) is not OperatorRecoveryCommand:
            raise ValueError("command must be OperatorRecoveryCommand")
        _validate_opaque_id(self.operation_id, "operation_id")
        _validate_opaque_id(self.step_id, "step_id")
        _validate_ijson_version(
            self.expected_operation_optimistic_version,
            "expected_operation_optimistic_version",
        )
        _validate_ijson_version(
            self.expected_step_optimistic_version,
            "expected_step_optimistic_version",
        )
        _validate_bounded_diagnostic_message(self.reason)


def authorize_operator_command(
    command: OperatorRecoveryCommand,
    *,
    capability: RecoveryCapabilityValue,
    operation_status: OperationStatus,
    step_status: StepStatus,
) -> None:
    if command is OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
        if (
            operation_status is OperationStatus.FAILED
            and step_status is StepStatus.FAILED
        ):
            return
    if operation_status is not OperationStatus.MANUAL_RECOVERY_REQUIRED:
        raise ValueError("operator recovery requires MANUAL_RECOVERY_REQUIRED operation")
    if step_status is not StepStatus.MANUAL_RECOVERY_REQUIRED:
        raise ValueError("operator recovery requires MANUAL_RECOVERY_REQUIRED step")
    if command is OperatorRecoveryCommand.RESUME_RECONCILE:
        if capability is not RecoveryCapabilityValue.EXTERNAL_EFFECT:
            raise ValueError("RESUME_RECONCILE requires EXTERNAL_EFFECT capability")
        return
    if command is OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT:
        if capability is not RecoveryCapabilityValue.PURE_RECOMPUTE:
            raise ValueError("RETRY_FROM_CHECKPOINT requires PURE_RECOMPUTE capability")
        return
    if command is OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
        return
    raise ValueError("unsupported operator recovery command")


def transition_for_operator_command(
    command: OperatorRecoveryCommand,
    *,
    step_source: StepStatus = StepStatus.MANUAL_RECOVERY_REQUIRED,
    operation_source: OperationStatus = OperationStatus.MANUAL_RECOVERY_REQUIRED,
) -> RecoveryTransitionIntent:
    if step_source is StepStatus.FAILED and operation_source is OperationStatus.FAILED:
        if command is not OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
            raise ValueError("terminal replay only supports ABORT_CONFIRMED_FAILURE")
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.FAILED,
            operation_source=operation_source,
            operation_target=OperationStatus.FAILED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if step_source is not StepStatus.MANUAL_RECOVERY_REQUIRED:
        raise ValueError("operator recovery only supports MANUAL_RECOVERY_REQUIRED step source")
    if operation_source is not OperationStatus.MANUAL_RECOVERY_REQUIRED:
        raise ValueError(
            "operator recovery only supports MANUAL_RECOVERY_REQUIRED operation source"
        )
    if command is OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.FAILED,
            operation_source=operation_source,
            operation_target=OperationStatus.FAILED,
            set_retry_not_before=None,
            retain_occupancy=False,
            increment_attempt_on_claim=False,
        )
    if command in {
        OperatorRecoveryCommand.RESUME_RECONCILE,
        OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT,
    }:
        return RecoveryTransitionIntent(
            step_source=step_source,
            step_target=StepStatus.RUNNING,
            operation_source=operation_source,
            operation_target=OperationStatus.RUNNING,
            set_retry_not_before=None,
            retain_occupancy=True,
            increment_attempt_on_claim=False,
        )
    raise ValueError("unsupported operator recovery command")


def _operator_diagnostic(diagnostic_code: str, reason: str) -> OperationDiagnostic:
    _validate_namespaced_diagnostic_code(diagnostic_code)
    _validate_bounded_diagnostic_message(reason)
    return OperationDiagnostic(code=diagnostic_code.upper(), message=reason)


def _operator_lease_token(step_id: str) -> str:
    token = f"operator-{step_id}"
    _validate_opaque_id(token, "lease_token")
    return token


def build_operator_recovery_candidates(
    operation: OperationRecord,
    step: StepRecord,
    intent: RecoveryTransitionIntent,
    *,
    command: OperatorRecoveryCommand,
    reason: str,
    transaction_now: datetime,
) -> tuple[StepRecord, OperationRecord | None]:
    _validate_utc_datetime(transaction_now, "transaction_now")
    _validate_bounded_diagnostic_message(reason)
    step_target = intent.step_target
    if step_target is None:
        raise ValueError("operator recovery requires a step target")

    if step_target is StepStatus.FAILED:
        diagnostic = _operator_diagnostic(DIAGNOSTIC_RECOVERY_AUTHORIZED, reason)
        step_candidate = dataclasses.replace(
            step,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
            retry_not_before=None,
            updated_at=transaction_now,
            completed_at=transaction_now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=step.optimistic_version + 1,
        )
        if intent.operation_target is not OperationStatus.FAILED:
            raise ValueError("abort requires operation FAILED transition")
        operation_candidate = dataclasses.replace(
            operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return step_candidate, operation_candidate

    if step_target is not StepStatus.RUNNING:
        raise ValueError("operator recovery only supports RUNNING or FAILED targets")
    if intent.operation_target is not OperationStatus.RUNNING:
        raise ValueError("resume/retry requires operation RUNNING transition")

    lease_token = _operator_lease_token(step.step_id)
    lease_expires_at = transaction_now + LEASE_DURATION
    if lease_expires_at <= transaction_now:
        raise ValueError("lease_expires_at must be later than updated_at for RUNNING step")

    step_candidate = dataclasses.replace(
        step,
        status=StepStatus.RUNNING,
        diagnostic=None,
        retry_not_before=None,
        updated_at=transaction_now,
        worker_id=OPERATOR_RECOVERY_WORKER_ID,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        completed_at=None,
        optimistic_version=step.optimistic_version + 1,
    )
    operation_candidate = dataclasses.replace(
        operation,
        status=OperationStatus.RUNNING,
        diagnostic=None,
        updated_at=transaction_now,
        completed_at=None,
        optimistic_version=operation.optimistic_version + 1,
    )
    return step_candidate, operation_candidate


def apply_operator_recovery_transition(
    store: OperationStore,
    operation: OperationRecord,
    step: StepRecord,
    intent: RecoveryTransitionIntent,
    *,
    command: OperatorRecoveryCommand,
    reason: str,
    expected_step_optimistic_version: int,
    expected_operation_optimistic_version: int,
) -> TransitionDisposition:
    transaction_now = store.transaction_now
    if (
        command is OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE
        and step.status is StepStatus.FAILED
        and operation.status is OperationStatus.FAILED
    ):
        step_precondition = WritePrecondition(
            expected_optimistic_version=expected_step_optimistic_version,
            worker_id=None,
            lease_token=None,
        )
        step_disposition = store.compare_and_set_step(
            step,
            step_precondition,
            recovery_authorized=True,
        )
        operation_precondition = WritePrecondition(
            expected_optimistic_version=expected_operation_optimistic_version,
            worker_id=None,
            lease_token=None,
        )
        store.compare_and_set_operation(
            operation,
            operation_precondition,
            recovery_authorized=True,
        )
        return step_disposition

    step_candidate, operation_candidate = build_operator_recovery_candidates(
        operation,
        step,
        intent,
        command=command,
        reason=reason,
        transaction_now=transaction_now,
    )
    step_precondition = WritePrecondition(
        expected_optimistic_version=expected_step_optimistic_version,
        worker_id=None,
        lease_token=None,
    )
    step_disposition = store.compare_and_set_step(
        step_candidate,
        step_precondition,
        recovery_authorized=True,
    )
    if operation_candidate is not None:
        operation_precondition = WritePrecondition(
            expected_optimistic_version=expected_operation_optimistic_version,
            worker_id=None,
            lease_token=None,
        )
        store.compare_and_set_operation(
            operation_candidate,
            operation_precondition,
            recovery_authorized=True,
        )
    return step_disposition


@dataclass(frozen=True, slots=True)
class AuthorizedOperatorRecovery:
    """Apply bounded authorized operator recovery commands through guarded R2 CAS."""

    write_uow_factory: WriteUnitOfWorkFactory
    capability_lookup: RecoveryCapabilityLookup

    def execute(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        with self.write_uow_factory() as unit_of_work:
            store = unit_of_work.operations
            fresh_operation = store.get_operation(request.operation_id)
            fresh_step = store.get_step(request.step_id)
            if fresh_step.operation_id != fresh_operation.operation_id:
                raise ValueError("step does not belong to the requested operation")
            if fresh_step.step_id != request.step_id:
                raise ValueError("step_id mismatch")

            capability = self._capability_lookup(
                fresh_operation.job_kind,
                fresh_step.step_name,
            )
            authorize_operator_command(
                request.command,
                capability=capability,
                operation_status=fresh_operation.status,
                step_status=fresh_step.status,
            )
            intent = transition_for_operator_command(
                request.command,
                step_source=fresh_step.status,
                operation_source=fresh_operation.status,
            )
            return apply_operator_recovery_transition(
                store,
                fresh_operation,
                fresh_step,
                intent,
                command=request.command,
                reason=request.reason,
                expected_step_optimistic_version=request.expected_step_optimistic_version,
                expected_operation_optimistic_version=request.expected_operation_optimistic_version,
            )

    def _capability_lookup(self, job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        capability = self.capability_lookup(job_kind, step_name)
        if type(capability) is not RecoveryCapabilityValue:
            raise ValueError("capability_lookup must return RecoveryCapabilityValue")
        return capability


def build_authorized_operator_recovery(
    *,
    write_uow_factory: WriteUnitOfWorkFactory,
    capability_lookup: RecoveryCapabilityLookup,
) -> AuthorizedOperatorRecovery:
    if not callable(write_uow_factory):
        raise ValueError("write_uow_factory must be callable")
    if not callable(capability_lookup):
        raise ValueError("capability_lookup must be callable")
    return AuthorizedOperatorRecovery(
        write_uow_factory=write_uow_factory,
        capability_lookup=capability_lookup,
    )


def _validate_ijson_version(value: object, label: str) -> None:
    if type(value) is not int or isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative I-JSON safe integer")
    if value < 0 or value > (2**53) - 1:
        raise ValueError(f"{label} must be a non-negative I-JSON safe integer")


def build_startup_recovery(
    *,
    write_uow_factory: WriteUnitOfWorkFactory,
    capability_lookup: RecoveryCapabilityLookup,
    jitter: Jitter,
    now_factory: NowFactory | None = None,
) -> StartupRecovery:
    if not callable(write_uow_factory):
        raise ValueError("write_uow_factory must be callable")
    if not callable(capability_lookup):
        raise ValueError("capability_lookup must be callable")
    if not callable(jitter):
        raise ValueError("jitter must be callable")
    effective_now = now_factory if now_factory is not None else (lambda: datetime.now(UTC))
    if not callable(effective_now):
        raise ValueError("now_factory must be callable")
    return StartupRecovery(
        write_uow_factory=write_uow_factory,
        capability_lookup=capability_lookup,
        jitter=jitter,
        now_factory=effective_now,
    )


def _schedule_retry_not_before(
    *,
    attempt_count: int,
    now: datetime | None,
    jitter: Jitter | None,
) -> datetime:
    if now is None or jitter is None:
        raise ValueError("now and jitter are required to schedule RETRY_WAIT")
    return compute_retry_not_before(now, attempt_count, jitter=jitter)


def _validate_namespaced_diagnostic_code(value: str) -> None:
    if type(value) is not str:
        raise ValueError("diagnostic_code must be a string")
    if not _NAMESPACED_DIAGNOSTIC_CODE_RE.fullmatch(value):
        raise ValueError("diagnostic_code must match bounded namespaced pattern")


def _validate_bounded_diagnostic_message(value: str) -> None:
    if type(value) is not str:
        raise ValueError("reason must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DIAGNOSTIC_MESSAGE_BYTES:
        raise ValueError("reason exceeds bounded diagnostic size")


def _validate_utc_datetime(value: datetime, label: str) -> None:
    if type(value) is not datetime:
        raise ValueError(f"{label} must be a datetime")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be timezone-aware UTC")


__all__ = [
    "AuthorizedOperatorRecovery",
    "DIAGNOSTIC_LEASE_EXPIRED",
    "DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED",
    "DIAGNOSTIC_RECONCILE_STARTED",
    "DIAGNOSTIC_RECONCILE_TIMEOUT",
    "DIAGNOSTIC_RECOVERY_AUTHORIZED",
    "DIAGNOSTIC_RETRY_SCHEDULED",
    "ExternalEffectPhase",
    "HandlerFailureKind",
    "HandlerRecoveryCallback",
    "HandlerRecoveryResult",
    "HandlerExecutionFailure",
    "Jitter",
    "MAX_RECOVERY_SESSIONS",
    "NowFactory",
    "OPERATOR_RECOVERY_WORKER_ID",
    "OperatorRecoveryCommand",
    "OperatorRecoveryRequest",
    "RECONCILE_SESSION_BUDGET_SECONDS",
    "RECOVERY_BACKOFF_CAP_SECONDS",
    "RECOVERY_BACKOFF_SECONDS",
    "RECOVERY_DIAGNOSTIC_CODES",
    "RecoveryCapabilityLookup",
    "RecoveryCapabilityValue",
    "RecoveryPolicyDecision",
    "RecoveryPolicyDecisionDisposition",
    "RecoveryPolicyOutcomeDisposition",
    "RecoveryTransitionIntent",
    "StartupRecovery",
    "apply_operator_recovery_transition",
    "apply_recovery_backoff_jitter",
    "apply_recovery_transition",
    "authorize_operator_command",
    "build_authorized_operator_recovery",
    "build_operator_recovery_candidates",
    "build_recovery_candidates",
    "build_recovery_routed_executor",
    "build_startup_recovery",
    "classify_cancel",
    "classify_expired_lease",
    "classify_handler_failure",
    "classify_startup",
    "compute_retry_not_before",
    "finalize_handler_recovery",
    "policy_diagnostic_to_operation_diagnostic",
    "reconcile_budget_exhausted",
    "recovery_backoff_base_seconds",
    "recovery_sessions_exhausted",
    "recovery_sessions_remaining",
    "should_route_claim_to_recovery",
    "startup_disposition_after_recovery",
    "step_lease_expired",
    "transition_for_decision",
    "transition_for_operator_command",
    "transition_for_outcome",
]
