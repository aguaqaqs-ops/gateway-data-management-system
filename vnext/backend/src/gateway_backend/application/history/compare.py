"""History compare accept validation and node resolution."""

from __future__ import annotations

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
    HistoryCompareNodeBinding,
    HistoryCompareValidationResult,
    HistoryNodeRef,
)
from gateway_backend.application.history.errors import (
    HistoryCompareBindingConflict,
    HistoryCompareIdempotencyConflict,
    HistoryCompareNodeNotFound,
    HistoryIntegrityUnresolved,
    HistoryRequestValidation,
)
from typing import cast

from gateway_backend.application.history.ports import HistoryComparePort
from gateway_backend.application.submission.ports import WorkspaceControlTransaction
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeResolutionError
from gateway_backend.domain.workspace.policies import assert_permission


def resolve_compare_nodes(
    unit_of_work: WorkspaceControlTransaction,
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
    unit_of_work: WorkspaceControlTransaction,
    table_ruleset_version: str,
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
    except ScopeResolutionError as exc:
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
        table_ruleset_version=table_ruleset_version,
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind=HISTORY_COMPARE_VIEW_KIND,
    )

    if prior is not None:
        if prior.request_fingerprint != request_fingerprint:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        if prior.table_ruleset_version != table_ruleset_version:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        if prior.nodes != resolved_nodes:
            raise HistoryCompareIdempotencyConflict(idempotency_key=command.idempotency_key)
        return HistoryCompareValidationResult(
            repository_id=fresh_scope.repository_id,
            gateway_device_external_key=command.context.gateway_device_external_key,
            business_project_id=command.context.business_project_id,
            nodes=resolved_nodes,
            request_fingerprint=request_fingerprint,
            table_ruleset_version=table_ruleset_version,
            replay=True,
            prior_acceptance=prior,
            operation_id=prior.operation_id,
            acceptance_id=prior.acceptance_id,
        )

    for node in resolved_nodes:
        if compare_port.has_pending_integrity_for_commit(
            repository_id=fresh_scope.repository_id,
            commit_id=node.commit_id,
        ):
            raise HistoryIntegrityUnresolved

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
        table_ruleset_version=table_ruleset_version,
        replay=False,
        prior_acceptance=None,
        operation_id=operation_id,
        acceptance_id=acceptance_id,
    )


def _compare_port(unit_of_work: WorkspaceControlTransaction) -> HistoryComparePort:
    history_compare = getattr(unit_of_work, "history_compare", None)
    if history_compare is None:
        raise RuntimeError("history_compare port is not bound on the control transaction")
    return cast(HistoryComparePort, history_compare)
