"""History compare accept validation and node resolution."""

from __future__ import annotations

import logging

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.history.compare_bindings import (
    compute_accept_binding_fingerprint,
    deterministic_history_compare_ids,
)
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HISTORY_COMPARE_MAX_NODES,
    HISTORY_COMPARE_MIN_NODES,
    HISTORY_COMPARE_VIEW_KIND,
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryCompareNodeBinding,
    HistoryCompareValidationResult,
    HistoryNodeRef,
)
from gateway_backend.application.history.errors import (
    HistoryCompareAcceptanceUnavailable,
    HistoryCompareAliasLimit,
    HistoryComparePreflightFailure,
    HistoryCompareRequestExpired,
    HistoryCompareScopeLimit,
    HistoryIntegrityFailure,
    HistoryCompareBindingConflict,
    HistoryCompareIdempotencyConflict,
    HistoryCompareJobNotRegistered,
    HistoryCompareNodeNotFound,
    HistoryRequestValidation,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    history_compare_step_id,
)
from gateway_backend.application.history.compare_registry import assert_compare_registry_ready
from gateway_backend.application.history.ports import (
    HistoryComparePort,
    HistoryControlTransaction,
    HistoryControlUnitOfWorkFactory,
)
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeNotFound
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.operations.store import OperationQueueFull
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptanceResult:
    operation_id: str
    status: OperationStatus
    replay: bool


def accept_history_compare(
    *,
    command: HistoryCompareAcceptCommand,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    comparison_ruleset_digest: str,
    now: datetime,
    result_retention_seconds: int = 86_400,
    history_scope_active_limit: int = 2,
    operation_queue_limit: int = 32,
    preflight: Callable[[OperationRecord, HistoryCompareAcceptanceRecord], AbstractContextManager[frozenset[str]]] | None = None,
    resolve_current_identity: Callable[[], IdentityContext] | None = None,
) -> HistoryCompareAcceptanceResult:
    try:
        assert_compare_registry_ready(job_registry)
    except ValueError as exc:
        raise HistoryCompareJobNotRegistered from exc

    rejected: set[str] = set()
    verified_id: str | None = None
    verified_refs: frozenset[str] = frozenset()
    with ExitStack() as borrowed:
        for _ in range(8):
            outcome = _accept_history_compare_once(
                command=command, unit_of_work_factory=unit_of_work_factory,
                comparison_ruleset_digest=comparison_ruleset_digest, now=now,
                result_retention_seconds=result_retention_seconds,
                history_scope_active_limit=history_scope_active_limit,
                operation_queue_limit=operation_queue_limit,
                resolve_current_identity=resolve_current_identity,
                rejected=rejected, verified_id=verified_id, verified_refs=verified_refs,
            )
            if isinstance(outcome, HistoryCompareAcceptanceResult):
                return outcome
            candidate, operation, same_key = outcome
            if preflight is None:
                raise HistoryCompareAcceptanceUnavailable
            try:
                verified_refs = borrowed.enter_context(preflight(operation, candidate))
                verified_id = operation.operation_id
            except HistoryComparePreflightFailure:
                if same_key:
                    raise
                logging.getLogger(__name__).warning(
                    "history result preflight rejected candidate operation_id=%s", operation.operation_id
                )
                rejected.add(operation.operation_id)
                verified_id = None
                verified_refs = frozenset()
        raise HistoryCompareAcceptanceUnavailable


def _accept_history_compare_once(
    *, command: HistoryCompareAcceptCommand, unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    comparison_ruleset_digest: str, now: datetime, result_retention_seconds: int,
    history_scope_active_limit: int, operation_queue_limit: int,
    resolve_current_identity: Callable[[], IdentityContext] | None,
    rejected: set[str], verified_id: str | None, verified_refs: frozenset[str],
) -> HistoryCompareAcceptanceResult | tuple[HistoryCompareAcceptanceRecord, OperationRecord, bool]:
    with unit_of_work_factory() as unit_of_work:
        if resolve_current_identity is not None:
            current = resolve_current_identity()
            if (current.actor_id != command.context.actor_id
                    or current.gateway_device_external_key != command.context.gateway_device_external_key
                    or current.business_project_id != command.context.business_project_id):
                raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY)
            command = replace(command, context=current)
        validation = validate_history_compare_binding(
            command=command, unit_of_work=unit_of_work,
            comparison_ruleset_digest=comparison_ruleset_digest,
        )
        same_key = validation.replay and validation.prior_acceptance is not None
        candidates: tuple[HistoryCompareAcceptanceRecord, ...]
        if same_key and validation.prior_acceptance is not None:
            candidates = (validation.prior_acceptance,)
        else:
            candidates = unit_of_work.history_compare.find_candidates(
                gateway_device_external_key=validation.gateway_device_external_key,
                business_project_id=validation.business_project_id,
                request_fingerprint=validation.request_fingerprint,
                now=unit_of_work.transaction_now,
            )
        for candidate in candidates:
            if candidate.operation_id in rejected:
                continue
            operation = unit_of_work.operations.get_operation(candidate.operation_id)
            if (operation.job_kind != HISTORY_COMPARE_JOB_KIND
                    or operation.job_contract_version != HISTORY_COMPARE_JOB_CONTRACT_VERSION):
                if same_key:
                    raise HistoryIntegrityFailure("history operation version binding disagrees")
                rejected.add(operation.operation_id)
                continue
            if operation.status is OperationStatus.SUCCEEDED:
                if operation.completed_at is None:
                    raise HistoryCompareAcceptanceUnavailable
                expiry = operation.completed_at + timedelta(seconds=candidate.result_retention_seconds)
                if unit_of_work.transaction_now >= expiry:
                    if same_key:
                        raise HistoryCompareRequestExpired("history compare request expired; use a new key")
                    continue
                if verified_id != operation.operation_id:
                    return candidate, operation, bool(same_key)
                if not unit_of_work.history_compare.result_protection_matches(
                    operation.operation_id, verified_refs, expiry
                ):
                    if same_key:
                        raise HistoryIntegrityFailure("history result protection disagrees with its expiry")
                    rejected.add(operation.operation_id)
                    continue
            elif not same_key and operation.status not in (OperationStatus.QUEUED, OperationStatus.RUNNING):
                continue
            if not same_key:
                if unit_of_work.history_compare.count_aliases(operation.operation_id) >= 64:
                    raise HistoryCompareAliasLimit(operation.operation_id)
                unit_of_work.history_compare.save_alias(record=candidate, idempotency_key=command.idempotency_key)
            return HistoryCompareAcceptanceResult(operation.operation_id, operation.status, True)

        active_ids = unit_of_work.history_compare.active_operation_ids(
            gateway_device_external_key=validation.gateway_device_external_key,
            business_project_id=validation.business_project_id,
        )
        if len(active_ids) >= history_scope_active_limit:
            raise HistoryCompareScopeLimit(active_ids)
        if unit_of_work.count_queued_operations() >= operation_queue_limit:
            raise OperationQueueFull
        operation_id = validation.operation_id
        acceptance_id = validation.acceptance_id
        if operation_id is None or acceptance_id is None:
            raise HistoryCompareAcceptanceUnavailable

        job_payload = build_history_compare_job_payload(
            validation=validation,
            acceptance_id=acceptance_id,
            idempotency_key=command.idempotency_key,
        )
        operation = OperationRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            operation_id=operation_id,
            job_kind=HISTORY_COMPARE_JOB_KIND,
            job_contract_version=HISTORY_COMPARE_JOB_CONTRACT_VERSION,
            job_payload=job_payload,
            job_payload_ref=None,
            business_refs=(BusinessReference(kind="history_compare", value=acceptance_id),),
            artifact_refs=(),
            repository_operation_id=None,
            checkpoint_ref=None,
            ready_closure_ref=None,
            status=OperationStatus.QUEUED,
            diagnostic=None,
            cancel_requested=False,
            created_at=now,
            updated_at=now,
            completed_at=None,
            optimistic_version=0,
        )
        step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_MATERIALIZE),
            operation_id=operation_id,
            step_name=HISTORY_COMPARE_STEP_MATERIALIZE,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.history_compare.save_acceptance(
            HistoryCompareAcceptanceRecord(
                acceptance_id=acceptance_id,
                gateway_device_external_key=validation.gateway_device_external_key,
                business_project_id=validation.business_project_id,
                repository_id=validation.repository_id,
                idempotency_key=command.idempotency_key,
                request_fingerprint=validation.request_fingerprint,
                comparison_ruleset_digest=validation.comparison_ruleset_digest,
                nodes=validation.nodes,
                operation_id=operation_id,
                created_at=now,
                result_retention_seconds=result_retention_seconds,
            )
        )
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)

    return HistoryCompareAcceptanceResult(
        operation_id=operation_id, status=OperationStatus.QUEUED, replay=False,
    )


def build_history_compare_job_payload(
    *,
    validation: HistoryCompareValidationResult,
    acceptance_id: str,
    idempotency_key: str,
) -> bytes:
    payload = {
        "gateway_device_external_key": validation.gateway_device_external_key,
        "business_project_id": validation.business_project_id,
        "repository_id": validation.repository_id,
        "acceptance_id": acceptance_id,
        "idempotency_key": idempotency_key,
        "request_fingerprint": validation.request_fingerprint,
        "comparison_ruleset_digest": validation.comparison_ruleset_digest,
        "comparison_contract_version": HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        "view_kind": HISTORY_COMPARE_VIEW_KIND,
        "pair_count": max(len(validation.nodes) - 1, 1),
        "nodes": [
            {
                "ref_kind": node.ref_kind.value,
                "ref_id": node.ref_id,
                "commit_id": node.commit_id,
            }
            for node in validation.nodes
        ],
    }
    return canonicalize_json_value(payload)


def resolve_compare_nodes(
    unit_of_work: HistoryControlTransaction,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    node_refs: tuple[HistoryNodeRef, ...],
) -> tuple[HistoryCompareNodeBinding, ...]:
    compare_port = _compare_port(unit_of_work)
    resolved: list[HistoryCompareNodeBinding] = []
    for node_ref in node_refs:
        commit_id = compare_port.resolve_node_ref(
            repository_id=repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            ref_kind=node_ref.ref_kind.value,
            ref_id=node_ref.ref_id,
        )
        if commit_id is None:
            raise HistoryCompareNodeNotFound
        resolved.append(
            HistoryCompareNodeBinding(
                ref_kind=node_ref.ref_kind,
                ref_id=node_ref.ref_id,
                commit_id=commit_id,
            )
        )
    return tuple(resolved)


def validate_history_compare_binding(
    *,
    command: HistoryCompareAcceptCommand,
    unit_of_work: HistoryControlTransaction,
    comparison_ruleset_digest: str,
) -> HistoryCompareValidationResult:
    assert_permission(command.context, PERMISSION_READ_PROJECT_HISTORY)
    if (
        len(command.node_refs) < HISTORY_COMPARE_MIN_NODES
        or len(command.node_refs) > HISTORY_COMPARE_MAX_NODES
    ):
        raise HistoryRequestValidation("nodes must contain 2 or 3 entries")
    try:
        fresh_scope = unit_of_work.resolve_provisioned_scope(
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
        )
    except ScopeNotFound as exc:
        raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc

    compare_port = _compare_port(unit_of_work)
    prior = compare_port.find_acceptance_by_idempotency(
        gateway_device_external_key=command.context.gateway_device_external_key,
        business_project_id=command.context.business_project_id,
        idempotency_key=command.idempotency_key,
    )
    if prior is not None:
        if prior.gateway_device_external_key != command.context.gateway_device_external_key:
            raise HistoryCompareBindingConflict("scope device does not match durable acceptance")
        if prior.business_project_id != command.context.business_project_id:
            raise HistoryCompareBindingConflict("scope project does not match durable acceptance")
        if prior.repository_id != fresh_scope.repository_id:
            raise HistoryCompareBindingConflict("repository mapping does not match durable acceptance")

    resolved_nodes = resolve_compare_nodes(
        unit_of_work,
        repository_id=fresh_scope.repository_id,
        gateway_device_external_key=command.context.gateway_device_external_key,
        business_project_id=command.context.business_project_id,
        node_refs=command.node_refs,
    )
    request_fingerprint = compute_accept_binding_fingerprint(
        gateway_device_external_key=command.context.gateway_device_external_key,
        business_project_id=command.context.business_project_id,
        repository_id=fresh_scope.repository_id,
        nodes=resolved_nodes,
        comparison_ruleset_digest=comparison_ruleset_digest,
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind=HISTORY_COMPARE_VIEW_KIND,
    )

    if prior is not None:
        if prior.request_fingerprint != request_fingerprint:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        if prior.comparison_ruleset_digest != comparison_ruleset_digest:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        if prior.nodes != resolved_nodes:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        return HistoryCompareValidationResult(
            repository_id=fresh_scope.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            nodes=resolved_nodes,
            request_fingerprint=request_fingerprint,
            comparison_ruleset_digest=comparison_ruleset_digest,
            replay=True,
            prior_acceptance=prior,
            operation_id=prior.operation_id,
            acceptance_id=prior.acceptance_id,
        )

    operation_id, acceptance_id = deterministic_history_compare_ids(
        gateway_device_external_key=command.context.gateway_device_external_key,
        business_project_id=command.context.business_project_id,
        idempotency_key=command.idempotency_key,
    )
    return HistoryCompareValidationResult(
        repository_id=fresh_scope.repository_id,
        gateway_device_external_key=command.context.gateway_device_external_key,
        business_project_id=command.context.business_project_id,
        nodes=resolved_nodes,
        request_fingerprint=request_fingerprint,
        comparison_ruleset_digest=comparison_ruleset_digest,
        replay=False,
        prior_acceptance=None,
        operation_id=operation_id,
        acceptance_id=acceptance_id,
    )


def _compare_port(unit_of_work: HistoryControlTransaction) -> HistoryComparePort:
    return unit_of_work.history_compare
