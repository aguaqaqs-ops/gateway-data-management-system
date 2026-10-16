"""Application recovery contract and R5 policy boundary tests for P4-R5-S1a/S1b."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application import (
    RecoveryCapability,
    RecoveryDecision,
    RecoveryDecisionDisposition,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
)
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationDiagnostic,
    OperationStatus,
    StepStatus,
)
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.recovery import (
    DIAGNOSTIC_LEASE_EXPIRED,
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_STARTED,
    DIAGNOSTIC_RECOVERY_AUTHORIZED,
    DIAGNOSTIC_RETRY_SCHEDULED,
    MAX_RECOVERY_SESSIONS,
    OperatorRecoveryCommand,
    RECONCILE_SESSION_BUDGET_SECONDS,
    RECOVERY_BACKOFF_CAP_SECONDS,
    RECOVERY_BACKOFF_SECONDS,
    RECOVERY_DIAGNOSTIC_CODES,
    ExternalEffectPhase,
    HandlerExecutionFailure,
    HandlerFailureKind,
    RecoveryCapabilityValue,
    RecoveryPolicyDecision,
    RecoveryPolicyDecisionDisposition,
    RecoveryPolicyOutcomeDisposition,
    RecoveryTransitionIntent,
    apply_recovery_backoff_jitter,
    classify_cancel,
    classify_expired_lease,
    classify_handler_failure,
    classify_startup,
    compute_retry_not_before,
    reconcile_budget_exhausted,
    recovery_backoff_base_seconds,
    recovery_sessions_exhausted,
    recovery_sessions_remaining,
    build_recovery_routed_executor,
    transition_for_decision,
    transition_for_outcome,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
RETRY_NOT_BEFORE = BASE_TIME + timedelta(seconds=2)

EXPECTED_DECISION_DISPOSITIONS = frozenset(
    {
        "NO_ACTION",
        "MOVE_TO_RETRY_WAIT",
        "CLAIM_FOR_RECONCILE",
        "MARK_MANUAL_RECOVERY",
        "BLOCK_STARTUP_RETRYABLE",
        "BLOCK_STARTUP_FATAL",
    }
)

EXPECTED_OUTCOME_DISPOSITIONS = frozenset(
    {
        "PUBLISHED",
        "RETRYABLE_FAILURE",
        "PERMANENT_FAILURE",
        "RECONCILE_PENDING",
        "MANUAL_RECOVERY",
        "CANCELLED",
    }
)

EXPECTED_RECOVERY_CAPABILITIES = frozenset(
    {
        "PURE_RECOMPUTE",
        "EXTERNAL_EFFECT",
        "NON_RETRYABLE",
    }
)

VALID_CODE = "r5.retry_scheduled"
VALID_REASON = "retry scheduled after lease expiry"
MANUAL_DIAGNOSTIC = OperationDiagnostic(code="MANUAL", message="manual recovery required")
_MAX_DIAGNOSTIC_MESSAGE_BYTES = 4 * 1024


def _operation_record() -> OperationRecord:
    return OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="op-0001",
        job_kind="synthetic.pure-compute",
        job_contract_version="backend-vnext/synthetic/pure-compute/v1",
        job_payload=canonicalize_json_value({"seed": "alpha"}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.RUNNING,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )


def _step_record() -> StepRecord:
    return StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-0001",
        operation_id="op-0001",
        step_name="compute",
        status=StepStatus.RUNNING,
        attempt_count=1,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id="worker-0001",
        lease_token="lease-token-0001",
        lease_expires_at=BASE_TIME + timedelta(seconds=30),
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        started_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )


def test_recovery_capability_values_exact() -> None:
    assert {item.value for item in RecoveryCapability} == EXPECTED_RECOVERY_CAPABILITIES


def test_recovery_decision_disposition_values_exact() -> None:
    assert {item.value for item in RecoveryDecisionDisposition} == EXPECTED_DECISION_DISPOSITIONS


def test_recovery_outcome_disposition_values_exact() -> None:
    assert {item.value for item in RecoveryOutcomeDisposition} == EXPECTED_OUTCOME_DISPOSITIONS


def test_recovery_decision_is_frozen_bounded_record() -> None:
    decision = RecoveryDecision(
        disposition=RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT,
        diagnostic_code=VALID_CODE,
        retry_not_before=RETRY_NOT_BEFORE,
        reason=VALID_REASON,
    )
    assert dataclasses.is_dataclass(decision)
    assert decision.disposition is RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT
    assert decision.retry_not_before == RETRY_NOT_BEFORE


def test_recovery_outcome_is_frozen_bounded_record() -> None:
    outcome = RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.PUBLISHED,
        diagnostic_code=None,
        reason=None,
    )
    assert dataclasses.is_dataclass(outcome)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED


MALFORMED_DECISION_FIELDS: tuple[tuple[dict[str, Any], str], ...] = (
    (
        {
            "disposition": "MOVE_TO_RETRY_WAIT",
            "diagnostic_code": VALID_CODE,
            "retry_not_before": RETRY_NOT_BEFORE,
            "reason": VALID_REASON,
        },
        "disposition must be RecoveryDecisionDisposition",
    ),
    (
        {
            "disposition": RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT,
            "diagnostic_code": "R5.RETRY",
            "retry_not_before": RETRY_NOT_BEFORE,
            "reason": VALID_REASON,
        },
        "diagnostic_code must match bounded namespaced pattern",
    ),
    (
        {
            "disposition": RecoveryDecisionDisposition.NO_ACTION,
            "diagnostic_code": VALID_CODE,
            "retry_not_before": RETRY_NOT_BEFORE,
            "reason": VALID_REASON,
        },
        "retry_not_before must be null unless disposition is MOVE_TO_RETRY_WAIT",
    ),
    (
        {
            "disposition": RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT,
            "diagnostic_code": VALID_CODE,
            "retry_not_before": None,
            "reason": VALID_REASON,
        },
        "retry_not_before is required for MOVE_TO_RETRY_WAIT",
    ),
    (
        {
            "disposition": RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT,
            "diagnostic_code": VALID_CODE,
            "retry_not_before": RETRY_NOT_BEFORE.replace(tzinfo=None),
            "reason": VALID_REASON,
        },
        "retry_not_before must be timezone-aware UTC",
    ),
    (
        {
            "disposition": RecoveryDecisionDisposition.NO_ACTION,
            "diagnostic_code": VALID_CODE,
            "retry_not_before": None,
            "reason": "",
        },
        "reason exceeds bounded diagnostic size",
    ),
)

MALFORMED_OUTCOME_FIELDS: tuple[tuple[dict[str, Any], str], ...] = (
    (
        {
            "disposition": "PUBLISHED",
            "diagnostic_code": None,
            "reason": None,
        },
        "disposition must be RecoveryOutcomeDisposition",
    ),
    (
        {
            "disposition": RecoveryOutcomeDisposition.RETRYABLE_FAILURE,
            "diagnostic_code": "BAD_CODE",
            "reason": VALID_REASON,
        },
        "diagnostic_code must match bounded namespaced pattern",
    ),
)


@pytest.mark.parametrize(("fields", "message"), MALFORMED_DECISION_FIELDS)
def test_recovery_decision_rejects_malformed_fields(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RecoveryDecision(**fields)


@pytest.mark.parametrize(("fields", "message"), MALFORMED_OUTCOME_FIELDS)
def test_recovery_outcome_rejects_malformed_fields(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RecoveryOutcome(**fields)


def test_recovery_port_accepts_structural_implementation() -> None:
    class _StubRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            del operation, step, control, lease_session
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.PUBLISHED,
                diagnostic_code=None,
                reason=None,
            )

    port: RecoveryPort = _StubRecoveryPort()
    assert isinstance(port, RecoveryPort)
    outcome = port.recover(
        _operation_record(),
        _step_record(),
        ExecutionControl(),
        _noop_lease_session(),
    )
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED


def test_recovery_decision_fields_exclude_payload_artifact_and_callables() -> None:
    decision = RecoveryDecision(
        disposition=RecoveryDecisionDisposition.CLAIM_FOR_RECONCILE,
        diagnostic_code=VALID_CODE,
        retry_not_before=None,
        reason=VALID_REASON,
    )
    for field in dataclasses.fields(decision):
        field_type = field.type
        assert "Artifact" not in str(field_type)
        assert "Callable" not in str(field_type)
        assert "bytes" not in str(field_type)


def _noop_lease_session() -> LeaseSession:
    class _Session:
        def refresh_control(self) -> None:
            return None

        def heartbeat(self) -> StepRecord:
            return _step_record()

        def publish_checkpoint(self, builder) -> object:  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def publish_successor(self, builder) -> object:  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def publish_operation(self, builder) -> object:  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def acknowledge_safe_handoff(self, generation) -> ExecutorAcknowledgment:  # type: ignore[no-untyped-def]
            raise AssertionError("not used")

        def completion_acknowledgment(self) -> ExecutorAcknowledgment | None:
            return None

    return cast(LeaseSession, _Session())


def _deterministic_jitter(lower: float, _upper: float) -> float:
    return lower


# --- S1b policy constants and budgets ---


def test_recovery_policy_constants_frozen() -> None:
    assert MAX_RECOVERY_SESSIONS == 3
    assert RECOVERY_BACKOFF_SECONDS == (1.0, 2.0, 4.0)
    assert RECOVERY_BACKOFF_CAP_SECONDS == 10.0
    assert RECONCILE_SESSION_BUDGET_SECONDS == 60.0


def test_recovery_diagnostic_codes_exact() -> None:
    assert RECOVERY_DIAGNOSTIC_CODES == frozenset(
        {
            DIAGNOSTIC_LEASE_EXPIRED,
            DIAGNOSTIC_RETRY_SCHEDULED,
            DIAGNOSTIC_RECONCILE_STARTED,
            "r5.reconcile_timeout",
            DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            DIAGNOSTIC_RECOVERY_AUTHORIZED,
        }
    )


BACKOFF_BASE_CASES: tuple[tuple[int, float], ...] = (
    (1, 1.0),
    (2, 2.0),
    (3, 4.0),
    (4, 4.0),
    (10, 4.0),
)


@pytest.mark.parametrize(("session_index", "expected_base"), BACKOFF_BASE_CASES)
def test_recovery_backoff_base_seconds(session_index: int, expected_base: float) -> None:
    assert recovery_backoff_base_seconds(session_index) == expected_base


def test_compute_retry_not_before_uses_bounded_jitter() -> None:
    retry_not_before = compute_retry_not_before(
        BASE_TIME,
        2,
        jitter=_deterministic_jitter,
    )
    assert retry_not_before == BASE_TIME + timedelta(seconds=2.0)


def test_apply_recovery_backoff_jitter_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="jitter result must remain within the bounded backoff"):
        apply_recovery_backoff_jitter(
            1.0,
            10.0,
            jitter=lambda _lower, _upper: 0.5,
        )


SESSION_BUDGET_CASES: tuple[tuple[int, int, bool], ...] = (
    (1, 2, False),
    (2, 1, False),
    (3, 0, True),
    (4, 0, True),
)


@pytest.mark.parametrize(
    ("attempt_count", "remaining", "exhausted"),
    SESSION_BUDGET_CASES,
)
def test_recovery_session_budget(
    attempt_count: int,
    remaining: int,
    exhausted: bool,
) -> None:
    assert recovery_sessions_remaining(attempt_count) == remaining
    assert recovery_sessions_exhausted(attempt_count) is exhausted


RECONCILE_BUDGET_CASES: tuple[tuple[float, bool], ...] = (
    (0.0, False),
    (59.9, False),
    (60.0, True),
    (120.0, True),
)


@pytest.mark.parametrize(("elapsed", "exhausted"), RECONCILE_BUDGET_CASES)
def test_reconcile_budget_exhausted(elapsed: float, exhausted: bool) -> None:
    assert reconcile_budget_exhausted(elapsed) is exhausted


def _policy_decision_to_application(decision: RecoveryPolicyDecision) -> RecoveryDecision:
    return RecoveryDecision(
        disposition=RecoveryDecisionDisposition(decision.disposition.value),
        diagnostic_code=decision.diagnostic_code,
        retry_not_before=decision.retry_not_before,
        reason=decision.reason,
    )


def test_recovery_policy_decision_structural_parity_with_application() -> None:
    decision = RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT,
        diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
        retry_not_before=RETRY_NOT_BEFORE,
        reason=VALID_REASON,
    )
    application_decision = _policy_decision_to_application(decision)
    assert application_decision.disposition is RecoveryDecisionDisposition.MOVE_TO_RETRY_WAIT


class _RecoveryReleaseSession:
    def __init__(self) -> None:
        self.intent: RecoveryTransitionIntent | None = None
        self.diagnostic: OperationDiagnostic | None = None

    def completion_acknowledgment(self) -> ExecutorAcknowledgment | None:
        return None

    def publish_recovery_release(
        self,
        intent: RecoveryTransitionIntent,
        *,
        diagnostic: OperationDiagnostic,
    ) -> ExecutorAcknowledgment:
        self.intent = intent
        self.diagnostic = diagnostic
        return ExecutorAcknowledgment.SAFE_HANDOFF


REPOSITORY_READ_FAILURE_CASES = (
    ("temporary_error_then_success", True, 1, StepStatus.RETRY_WAIT, None),
    ("temporary_error_budget_exhausted", True, 3, StepStatus.FAILED, OperationStatus.FAILED),
)


@pytest.mark.parametrize(
    ("scenario", "retryable", "attempt_count", "expected_step", "expected_operation"),
    REPOSITORY_READ_FAILURE_CASES,
)
def test_pure_recompute_repository_read_failure_uses_bounded_terminal_diagnostics(
    scenario: str,
    retryable: bool,
    attempt_count: int,
    expected_step: StepStatus,
    expected_operation: OperationStatus | None,
) -> None:
    operation = _operation_record()
    step = dataclasses.replace(_step_record(), attempt_count=attempt_count)
    calls = 0

    def handler(
        _operation: OperationRecord,
        _step: StepRecord,
        _control: ExecutionControl,
        _session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HandlerExecutionFailure(
                retryable=retryable,
                diagnostic_code="repository.service_not_ready",
                reason="repository catalog read failed (SERVICE_NOT_READY: service is not ready)",
            )
        return ExecutorAcknowledgment.PUBLISHED

    execute = build_recovery_routed_executor(
        cast(ClaimedExecutor, handler),
        None,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        jitter=_deterministic_jitter,
        now_factory=lambda: BASE_TIME,
    )
    first_session = _RecoveryReleaseSession()
    first_ack = execute(
        operation,
        step,
        ExecutionControl(),
        cast(LeaseSession, first_session),
    )
    assert first_ack is ExecutorAcknowledgment.SAFE_HANDOFF
    assert first_session.intent is not None
    assert first_session.intent.step_target is expected_step
    assert first_session.intent.operation_target is expected_operation
    assert first_session.diagnostic is not None
    if expected_step is StepStatus.RETRY_WAIT:
        assert first_session.diagnostic.code == DIAGNOSTIC_RETRY_SCHEDULED.upper()
    else:
        assert first_session.diagnostic.code == "REPOSITORY.SERVICE_NOT_READY"
    assert "UNCLASSIFIED" not in first_session.diagnostic.code
    assert "SERVICE_NOT_READY" in first_session.diagnostic.message

    if scenario == "temporary_error_then_success":
        second_session = _RecoveryReleaseSession()
        second_ack = execute(
            operation,
            dataclasses.replace(step, attempt_count=2),
            ExecutionControl(),
            cast(LeaseSession, second_session),
        )
        assert second_ack is ExecutorAcknowledgment.PUBLISHED
        assert second_session.intent is None
        assert calls == 2


def test_unexpected_pure_recompute_handler_exception_fails_operation_without_exiting_worker() -> None:
    def handler(
        _operation: OperationRecord,
        _step: StepRecord,
        _control: ExecutionControl,
        _session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        raise RuntimeError("internal handler detail")

    execute = build_recovery_routed_executor(
        cast(ClaimedExecutor, handler),
        None,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        jitter=_deterministic_jitter,
        now_factory=lambda: BASE_TIME,
    )
    session = _RecoveryReleaseSession()

    acknowledgment = execute(
        _operation_record(),
        _step_record(),
        ExecutionControl(),
        cast(LeaseSession, session),
    )

    assert acknowledgment is ExecutorAcknowledgment.SAFE_HANDOFF
    assert session.intent is not None
    assert session.intent.step_target is StepStatus.FAILED
    assert session.intent.operation_target is OperationStatus.FAILED
    assert session.diagnostic is not None
    assert session.diagnostic.code == "OPERATION.PURE_RECOMPUTE_FAILED"
    assert session.diagnostic.message == "pure-recompute handler raised RuntimeError"


EXPIRED_LEASE_MATRIX: tuple[
    tuple[str, RecoveryCapabilityValue, int, RecoveryPolicyDecisionDisposition],
    ...,
] = (
    ("pure_retry", RecoveryCapabilityValue.PURE_RECOMPUTE, 1, RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT),
    ("external_reconcile", RecoveryCapabilityValue.EXTERNAL_EFFECT, 1, RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE),
    ("non_retryable_manual", RecoveryCapabilityValue.NON_RETRYABLE, 1, RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY),
    ("budget_exhausted", RecoveryCapabilityValue.PURE_RECOMPUTE, 3, RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY),
)


@pytest.mark.parametrize(
    ("name", "capability", "attempt_count", "expected_disposition"),
    EXPIRED_LEASE_MATRIX,
)
def test_classify_expired_lease_matrix(
    name: str,
    capability: RecoveryCapabilityValue,
    attempt_count: int,
    expected_disposition: RecoveryPolicyDecisionDisposition,
) -> None:
    del name
    decision = classify_expired_lease(
        capability=capability,
        attempt_count=attempt_count,
        now=BASE_TIME,
        jitter=_deterministic_jitter,
    )
    assert decision.disposition is expected_disposition
    _policy_decision_to_application(decision)


STARTUP_MATRIX: tuple[
    tuple[
        str,
        OperationStatus,
        StepStatus,
        RecoveryCapabilityValue,
        bool,
        int,
        RecoveryPolicyDecisionDisposition,
    ],
    ...,
] = (
    (
        "manual_no_action",
        OperationStatus.MANUAL_RECOVERY_REQUIRED,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        True,
        1,
        RecoveryPolicyDecisionDisposition.NO_ACTION,
    ),
    (
        "active_lease_no_action",
        OperationStatus.RUNNING,
        StepStatus.RUNNING,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        False,
        1,
        RecoveryPolicyDecisionDisposition.NO_ACTION,
    ),
    (
        "pure_expired_retryable",
        OperationStatus.RUNNING,
        StepStatus.RUNNING,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        True,
        1,
        RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_RETRYABLE,
    ),
    (
        "external_expired_reconcile",
        OperationStatus.RUNNING,
        StepStatus.RUNNING,
        RecoveryCapabilityValue.EXTERNAL_EFFECT,
        True,
        1,
        RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE,
    ),
    (
        "non_retryable_fatal",
        OperationStatus.RUNNING,
        StepStatus.RUNNING,
        RecoveryCapabilityValue.NON_RETRYABLE,
        True,
        1,
        RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL,
    ),
    (
        "budget_exhausted_fatal",
        OperationStatus.RUNNING,
        StepStatus.RUNNING,
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        True,
        3,
        RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL,
    ),
)


@pytest.mark.parametrize(
    (
        "name",
        "operation_status",
        "step_status",
        "capability",
        "lease_expired",
        "attempt_count",
        "expected_disposition",
    ),
    STARTUP_MATRIX,
)
def test_classify_startup_matrix(
    name: str,
    operation_status: OperationStatus,
    step_status: StepStatus,
    capability: RecoveryCapabilityValue,
    lease_expired: bool,
    attempt_count: int,
    expected_disposition: RecoveryPolicyDecisionDisposition,
) -> None:
    del name
    operation = _operation_record()
    if operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED:
        operation = dataclasses.replace(
            operation,
            status=operation_status,
            diagnostic=MANUAL_DIAGNOSTIC,
        )
    else:
        operation = dataclasses.replace(operation, status=operation_status)
    step = _step_record()
    if step_status is StepStatus.MANUAL_RECOVERY_REQUIRED:
        step = dataclasses.replace(
            step,
            status=step_status,
            attempt_count=attempt_count,
            diagnostic=MANUAL_DIAGNOSTIC,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
        )
    else:
        step = dataclasses.replace(step, status=step_status, attempt_count=attempt_count)
    decision = classify_startup(
        operation=operation,
        step=step,
        capability=capability,
        lease_expired=lease_expired,
        now=BASE_TIME,
        jitter=_deterministic_jitter,
    )
    assert decision.disposition is expected_disposition
    _policy_decision_to_application(decision)


HANDLER_FAILURE_MATRIX: tuple[
    tuple[
        str,
        RecoveryCapabilityValue,
        HandlerFailureKind,
        ExternalEffectPhase | None,
        bool,
        RecoveryPolicyOutcomeDisposition,
    ],
    ...,
] = (
    (
        "pure_retryable",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        HandlerFailureKind.RETRYABLE,
        None,
        False,
        RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE,
    ),
    (
        "pure_permanent",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        HandlerFailureKind.PERMANENT,
        None,
        False,
        RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE,
    ),
    (
        "unreadable_checkpoint",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        HandlerFailureKind.CHECKPOINT_UNREADABLE,
        None,
        False,
        RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
    ),
    (
        "unclassified_fail_closed",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        HandlerFailureKind.UNCLASSIFIED,
        None,
        False,
        RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
    ),
    (
        "external_pre_request_retry",
        RecoveryCapabilityValue.EXTERNAL_EFFECT,
        HandlerFailureKind.RETRYABLE,
        ExternalEffectPhase.REQUEST_NOT_ACCEPTED,
        False,
        RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE,
    ),
    (
        "external_unknown_reconcile",
        RecoveryCapabilityValue.EXTERNAL_EFFECT,
        HandlerFailureKind.RECONCILE,
        ExternalEffectPhase.REQUEST_ACCEPTED_OR_UNKNOWN,
        False,
        RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING,
    ),
    (
        "non_retryable_permanent",
        RecoveryCapabilityValue.NON_RETRYABLE,
        HandlerFailureKind.PERMANENT,
        None,
        False,
        RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE,
    ),
    (
        "non_retryable_ambiguous_manual",
        RecoveryCapabilityValue.NON_RETRYABLE,
        HandlerFailureKind.PERMANENT,
        None,
        True,
        RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY,
    ),
)


@pytest.mark.parametrize(
    ("name", "capability", "failure_kind", "effect_phase", "ambiguous", "expected"),
    HANDLER_FAILURE_MATRIX,
)
def test_classify_handler_failure_matrix(
    name: str,
    capability: RecoveryCapabilityValue,
    failure_kind: HandlerFailureKind,
    effect_phase: ExternalEffectPhase | None,
    ambiguous: bool,
    expected: RecoveryPolicyOutcomeDisposition,
) -> None:
    del name
    outcome = classify_handler_failure(
        capability=capability,
        failure_kind=failure_kind,
        effect_phase=effect_phase,
        evidence_ambiguous=ambiguous,
    )
    assert outcome is expected


CANCEL_MATRIX: tuple[tuple[bool, bool, RecoveryPolicyOutcomeDisposition | None], ...] = (
    (False, False, None),
    (True, False, RecoveryPolicyOutcomeDisposition.CANCELLED),
    (True, True, RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING),
)


@pytest.mark.parametrize(
    ("cancel_requested", "effect_boundary_crossed", "expected"),
    CANCEL_MATRIX,
)
def test_classify_cancel_matrix(
    cancel_requested: bool,
    effect_boundary_crossed: bool,
    expected: RecoveryPolicyOutcomeDisposition | None,
) -> None:
    assert (
        classify_cancel(
            cancel_requested=cancel_requested,
            effect_boundary_crossed=effect_boundary_crossed,
        )
        is expected
    )


DECISION_TRANSITION_MATRIX: tuple[
    tuple[RecoveryPolicyDecisionDisposition, StepStatus | None, OperationStatus | None, bool],
    ...,
] = (
    (RecoveryPolicyDecisionDisposition.NO_ACTION, None, None, False),
    (RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT, StepStatus.RETRY_WAIT, None, False),
    (RecoveryPolicyDecisionDisposition.CLAIM_FOR_RECONCILE, StepStatus.RETRY_WAIT, None, False),
    (RecoveryPolicyDecisionDisposition.MARK_MANUAL_RECOVERY, StepStatus.MANUAL_RECOVERY_REQUIRED, OperationStatus.MANUAL_RECOVERY_REQUIRED, True),
    (RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_RETRYABLE, StepStatus.RETRY_WAIT, None, False),
    (RecoveryPolicyDecisionDisposition.BLOCK_STARTUP_FATAL, StepStatus.MANUAL_RECOVERY_REQUIRED, OperationStatus.MANUAL_RECOVERY_REQUIRED, True),
)


@pytest.mark.parametrize(
    ("disposition", "step_target", "operation_target", "retain_occupancy"),
    DECISION_TRANSITION_MATRIX,
)
def test_transition_for_decision_matrix(
    disposition: RecoveryPolicyDecisionDisposition,
    step_target: StepStatus | None,
    operation_target: OperationStatus | None,
    retain_occupancy: bool,
) -> None:
    retry_not_before = RETRY_NOT_BEFORE if disposition is RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT else None
    decision = RecoveryPolicyDecision(
        disposition=disposition,
        diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
        retry_not_before=retry_not_before,
        reason=VALID_REASON,
    )
    intent = transition_for_decision(
        decision,
        attempt_count=1,
        now=BASE_TIME,
        jitter=_deterministic_jitter,
    )
    assert intent.step_target is step_target
    assert intent.operation_target is operation_target
    assert intent.retain_occupancy is retain_occupancy
    if step_target is StepStatus.RETRY_WAIT:
        assert intent.set_retry_not_before is not None


OUTCOME_TRANSITION_MATRIX: tuple[
    tuple[
        str,
        RecoveryPolicyOutcomeDisposition,
        int,
        float,
        bool,
        bool,
        StepStatus | None,
        OperationStatus | None,
        bool,
    ],
    ...,
] = (
    ("published", RecoveryPolicyOutcomeDisposition.PUBLISHED, 1, 0.0, False, False, StepStatus.SUCCEEDED, OperationStatus.SUCCEEDED, False),
    ("retryable_with_budget", RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE, 1, 0.0, False, False, StepStatus.RETRY_WAIT, None, False),
    ("retryable_exhausted", RecoveryPolicyOutcomeDisposition.RETRYABLE_FAILURE, 3, 0.0, False, False, StepStatus.FAILED, OperationStatus.FAILED, False),
    ("reconcile_pending", RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING, 1, 10.0, False, False, StepStatus.RETRY_WAIT, None, False),
    (
        "reconcile_pending_session_exhausted",
        RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING,
        3,
        10.0,
        False,
        False,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
        OperationStatus.MANUAL_RECOVERY_REQUIRED,
        True,
    ),
    ("reconcile_timeout_manual", RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING, 1, 60.0, False, False, StepStatus.MANUAL_RECOVERY_REQUIRED, OperationStatus.MANUAL_RECOVERY_REQUIRED, True),
    ("permanent_failure", RecoveryPolicyOutcomeDisposition.PERMANENT_FAILURE, 1, 0.0, False, False, StepStatus.FAILED, OperationStatus.FAILED, False),
    ("manual_recovery", RecoveryPolicyOutcomeDisposition.MANUAL_RECOVERY, 1, 0.0, False, False, StepStatus.MANUAL_RECOVERY_REQUIRED, OperationStatus.MANUAL_RECOVERY_REQUIRED, True),
    ("cancel_before_boundary", RecoveryPolicyOutcomeDisposition.CANCELLED, 1, 0.0, False, False, StepStatus.CANCELLED, OperationStatus.CANCELLED, False),
    ("cancel_after_boundary_reconcile", RecoveryPolicyOutcomeDisposition.CANCELLED, 1, 0.0, True, True, StepStatus.RETRY_WAIT, None, False),
)


@pytest.mark.parametrize(
    (
        "name",
        "outcome",
        "attempt_count",
        "reconcile_elapsed",
        "effect_boundary_crossed",
        "cancel_requested",
        "step_target",
        "operation_target",
        "retain_occupancy",
    ),
    OUTCOME_TRANSITION_MATRIX,
)
def test_transition_for_outcome_matrix(
    name: str,
    outcome: RecoveryPolicyOutcomeDisposition,
    attempt_count: int,
    reconcile_elapsed: float,
    effect_boundary_crossed: bool,
    cancel_requested: bool,
    step_target: StepStatus | None,
    operation_target: OperationStatus | None,
    retain_occupancy: bool,
) -> None:
    del name
    intent = transition_for_outcome(
        outcome,
        capability=RecoveryCapabilityValue.PURE_RECOMPUTE,
        attempt_count=attempt_count,
        reconcile_elapsed_seconds=reconcile_elapsed,
        effect_boundary_crossed=effect_boundary_crossed,
        cancel_requested=cancel_requested,
        now=BASE_TIME,
        jitter=_deterministic_jitter,
    )
    assert intent.step_target is step_target
    assert intent.operation_target is operation_target
    assert intent.retain_occupancy is retain_occupancy


def test_recovery_capability_value_matches_application() -> None:
    assert {item.value for item in RecoveryCapabilityValue} == EXPECTED_RECOVERY_CAPABILITIES


def test_recovery_policy_decision_disposition_matches_application() -> None:
    assert {item.value for item in RecoveryPolicyDecisionDisposition} == EXPECTED_DECISION_DISPOSITIONS


def test_recovery_policy_outcome_disposition_matches_application() -> None:
    assert {item.value for item in RecoveryPolicyOutcomeDisposition} == EXPECTED_OUTCOME_DISPOSITIONS


# --- S2c operator recovery command port ---


EXPECTED_OPERATOR_RECOVERY_COMMANDS = frozenset(
    {
        "RESUME_RECONCILE",
        "RETRY_FROM_CHECKPOINT",
        "ABORT_CONFIRMED_FAILURE",
    }
)


def test_operator_recovery_command_enum_closure() -> None:
    from gateway_backend.operations.recovery import OperatorRecoveryCommand

    assert {item.value for item in OperatorRecoveryCommand} == EXPECTED_OPERATOR_RECOVERY_COMMANDS


OPERATOR_COMMAND_CAPABILITY_MATRIX: tuple[
    tuple[
        str,
        OperatorRecoveryCommand,
        RecoveryCapabilityValue,
        bool,
    ],
    ...,
] = (
    ("resume_external", OperatorRecoveryCommand.RESUME_RECONCILE, RecoveryCapabilityValue.EXTERNAL_EFFECT, True),
    ("resume_pure", OperatorRecoveryCommand.RESUME_RECONCILE, RecoveryCapabilityValue.PURE_RECOMPUTE, False),
    ("resume_non_retryable", OperatorRecoveryCommand.RESUME_RECONCILE, RecoveryCapabilityValue.NON_RETRYABLE, False),
    ("retry_pure", OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT, RecoveryCapabilityValue.PURE_RECOMPUTE, True),
    ("retry_external", OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT, RecoveryCapabilityValue.EXTERNAL_EFFECT, False),
    ("abort_pure", OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE, RecoveryCapabilityValue.PURE_RECOMPUTE, True),
    ("abort_external", OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE, RecoveryCapabilityValue.EXTERNAL_EFFECT, True),
    ("abort_non_retryable", OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE, RecoveryCapabilityValue.NON_RETRYABLE, True),
)


@pytest.mark.parametrize(
    ("name", "command", "capability", "allowed"),
    OPERATOR_COMMAND_CAPABILITY_MATRIX,
)
def test_authorize_operator_command_capability_matrix(
    name: str,
    command: OperatorRecoveryCommand,
    capability: RecoveryCapabilityValue,
    allowed: bool,
) -> None:
    del name
    from gateway_backend.operations.recovery import authorize_operator_command

    if allowed:
        authorize_operator_command(
            command,
            capability=capability,
            operation_status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            step_status=StepStatus.MANUAL_RECOVERY_REQUIRED,
        )
        return
    with pytest.raises(ValueError, match="requires"):
        authorize_operator_command(
            command,
            capability=capability,
            operation_status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            step_status=StepStatus.MANUAL_RECOVERY_REQUIRED,
        )


OPERATOR_COMMAND_SOURCE_STATE_MATRIX: tuple[
    tuple[str, OperationStatus, StepStatus, str],
    ...,
] = (
    ("running_operation", OperationStatus.RUNNING, StepStatus.MANUAL_RECOVERY_REQUIRED, "operation"),
    ("running_step", OperationStatus.MANUAL_RECOVERY_REQUIRED, StepStatus.RUNNING, "step"),
)


@pytest.mark.parametrize(
    ("name", "operation_status", "step_status", "label"),
    OPERATOR_COMMAND_SOURCE_STATE_MATRIX,
)
def test_authorize_operator_command_rejects_non_manual_source(
    name: str,
    operation_status: OperationStatus,
    step_status: StepStatus,
    label: str,
) -> None:
    del name
    from gateway_backend.operations.recovery import authorize_operator_command

    with pytest.raises(ValueError, match=label):
        authorize_operator_command(
            OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT,
            capability=RecoveryCapabilityValue.PURE_RECOMPUTE,
            operation_status=operation_status,
            step_status=step_status,
        )


OPERATOR_TRANSITION_INTENT_MATRIX: tuple[
    tuple[
        OperatorRecoveryCommand,
        StepStatus | None,
        OperationStatus | None,
        bool,
    ],
    ...,
] = (
    (
        OperatorRecoveryCommand.RESUME_RECONCILE,
        StepStatus.RUNNING,
        OperationStatus.RUNNING,
        True,
    ),
    (
        OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT,
        StepStatus.RUNNING,
        OperationStatus.RUNNING,
        True,
    ),
    (
        OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
        StepStatus.FAILED,
        OperationStatus.FAILED,
        False,
    ),
)


@pytest.mark.parametrize(
    ("command", "step_target", "operation_target", "retain_occupancy"),
    OPERATOR_TRANSITION_INTENT_MATRIX,
)
def test_transition_for_operator_command_matrix(
    command: OperatorRecoveryCommand,
    step_target: StepStatus | None,
    operation_target: OperationStatus | None,
    retain_occupancy: bool,
) -> None:
    from gateway_backend.operations.recovery import transition_for_operator_command

    intent = transition_for_operator_command(command)
    assert intent.step_target is step_target
    assert intent.operation_target is operation_target
    assert intent.retain_occupancy is retain_occupancy


OPERATOR_REQUEST_VALIDATION_CASES: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "empty_reason",
        {"reason": ""},
        "reason exceeds bounded diagnostic size",
    ),
    (
        "oversized_reason",
        {"reason": "x" * (_MAX_DIAGNOSTIC_MESSAGE_BYTES + 1)},
        "reason exceeds bounded diagnostic size",
    ),
    (
        "bad_step_version",
        {"expected_step_optimistic_version": -1},
        "expected_step_optimistic_version",
    ),
)


@pytest.mark.parametrize(("name", "overrides", "match"), OPERATOR_REQUEST_VALIDATION_CASES)
def test_operator_recovery_request_validation(
    name: str,
    overrides: dict[str, object],
    match: str,
) -> None:
    del name
    from gateway_backend.operations.recovery import OperatorRecoveryRequest

    with pytest.raises(ValueError, match=match):
        if "reason" in overrides:
            OperatorRecoveryRequest(
                command=OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
                operation_id="operation-0001",
                step_id="step-0001",
                expected_operation_optimistic_version=2,
                expected_step_optimistic_version=3,
                reason=str(overrides["reason"]),
            )
        else:
            bad_version = overrides["expected_step_optimistic_version"]
            assert isinstance(bad_version, int)
            OperatorRecoveryRequest(
                command=OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
                operation_id="operation-0001",
                step_id="step-0001",
                expected_operation_optimistic_version=2,
                expected_step_optimistic_version=bad_version,
                reason=VALID_REASON,
            )


def test_authorize_operator_abort_allows_terminal_replay() -> None:
    from gateway_backend.operations.recovery import authorize_operator_command

    authorize_operator_command(
        OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
        capability=RecoveryCapabilityValue.PURE_RECOMPUTE,
        operation_status=OperationStatus.FAILED,
        step_status=StepStatus.FAILED,
    )


def test_operator_recovery_transition_intents_subset_of_allowed_transitions() -> None:
    from gateway_backend.operations.recovery import transition_for_operator_command
    from gateway_backend.operations.state import validate_operation_transition, validate_step_transition

    for command in OperatorRecoveryCommand:
        intent = transition_for_operator_command(command)
        if intent.step_target is not None:
            current_step = dataclasses.replace(
                _step_record(),
                status=intent.step_source,
                attempt_count=3,
                started_at=BASE_TIME,
                diagnostic=MANUAL_DIAGNOSTIC,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                optimistic_version=3,
            )
            candidate_step = dataclasses.replace(
                current_step,
                status=intent.step_target,
                worker_id="worker-op" if intent.step_target is StepStatus.RUNNING else None,
                lease_token="lease-op" if intent.step_target is StepStatus.RUNNING else None,
                lease_expires_at=(
                    BASE_TIME + timedelta(seconds=30)
                    if intent.step_target is StepStatus.RUNNING
                    else None
                ),
                diagnostic=MANUAL_DIAGNOSTIC if intent.step_target in {
                    StepStatus.FAILED,
                    StepStatus.MANUAL_RECOVERY_REQUIRED,
                } else None,
                completed_at=BASE_TIME if intent.step_target.is_final_terminal() else None,
                optimistic_version=current_step.optimistic_version + 1,
            )
            validate_step_transition(
                current_step,
                candidate_step,
                recovery_authorized=True,
            )
        if intent.operation_target is not None:
            current_operation = dataclasses.replace(
                _operation_record(),
                status=intent.operation_source,
                diagnostic=MANUAL_DIAGNOSTIC,
                optimistic_version=2,
            )
            candidate_operation = dataclasses.replace(
                current_operation,
                status=intent.operation_target,
                diagnostic=(
                    MANUAL_DIAGNOSTIC
                    if intent.operation_target in {
                        OperationStatus.FAILED,
                        OperationStatus.MANUAL_RECOVERY_REQUIRED,
                    }
                    else None
                ),
                completed_at=(
                    BASE_TIME if intent.operation_target.is_final_terminal() else None
                ),
                optimistic_version=current_operation.optimistic_version + 1,
            )
            validate_operation_transition(
                current_operation,
                candidate_operation,
                recovery_authorized=True,
            )
