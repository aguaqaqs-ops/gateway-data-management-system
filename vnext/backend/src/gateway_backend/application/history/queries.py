"""History bounded read queries."""

from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime, timedelta

from gateway_shared_kernel.jcs import canonicalize_json_value
from pydantic import BaseModel, ConfigDict, ValidationError

from gateway_backend.application.history.contracts import (
    DEFAULT_HISTORY_PAGE_LIMIT,
    MAX_HISTORY_PAGE_LIMIT,
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryCompareListItem,
    HistoryCompareListPage,
    HistoryNodeRef,
    HistoryTreeProjection,
)
from gateway_backend.application.history.errors import (
    HistoryIntegrityFailure,
    HistoryRequestValidation,
)
from gateway_backend.application.history.ports import (
    HistoryControlUnitOfWorkFactory,
    HistorySnapshotLoaderPort,
)
from gateway_backend.application.history.projection import _decode_cursor, project_history_page
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeNotFound
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.operations import OperationStatus


class _Cursor(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    scope_hash: str
    created_at: datetime
    operation_id: str


def get_project_history(
    *,
    context: IdentityContext,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    snapshot_loader: HistorySnapshotLoaderPort,
    limit: int | None = None,
    cursor: str | None = None,
) -> HistoryTreeProjection:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    resolved_limit = DEFAULT_HISTORY_PAGE_LIMIT if limit is None else limit
    if (
        type(resolved_limit) is not int
        or resolved_limit < 1
        or resolved_limit > MAX_HISTORY_PAGE_LIMIT
    ):
        raise HistoryRequestValidation("limit must be an integer between 1 and 500")
    cursor_order_key = _decode_cursor(cursor)
    try:
        with unit_of_work_factory(read_only=True) as unit_of_work:
            fresh_scope = unit_of_work.resolve_provisioned_scope(
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )
            page = snapshot_loader.load_page_in_transaction(
                unit_of_work,
                repository_id=fresh_scope.repository_id,
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
                limit=resolved_limit,
                after_order_key=cursor_order_key,
            )
    except ScopeNotFound as exc:
        raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
    except ValueError as exc:
        raise HistoryIntegrityFailure("history fact rows are inconsistent") from exc
    return project_history_page(page=page)


def list_compare_operations(
    *,
    context: IdentityContext,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    limit: int,
    cursor: str | None,
) -> HistoryCompareListPage:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    if type(limit) is not int or limit < 1 or limit > 100:
        raise HistoryRequestValidation("limit must be an integer between 1 and 100")
    with unit_of_work_factory(read_only=True) as uow:
        try:
            scope = uow.resolve_provisioned_scope(
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )
        except ScopeNotFound as exc:
            raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
        scope_hash = hashlib.sha256(
            canonicalize_json_value(
                [
                    context.gateway_device_external_key,
                    context.business_project_id,
                    scope.repository_id,
                ]
            )
        ).hexdigest()
        after = None
        if cursor is not None:
            try:
                raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
                decoded = _Cursor.model_validate_json(raw, strict=True)
                if (
                    decoded.scope_hash != scope_hash
                    or decoded.created_at.tzinfo is None
                    or not decoded.operation_id
                ):
                    raise ValueError("cursor scope or ordering is invalid")
                after = (decoded.created_at, decoded.operation_id)
            except (UnicodeError, binascii.Error, ValueError, ValidationError) as exc:
                raise HistoryRequestValidation("invalid cursor") from exc
        records = uow.history_compare.list_acceptances(
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
            repository_id=scope.repository_id,
            now=uow.transaction_now,
            after=after,
            limit=limit + 1,
        )
        items: list[HistoryCompareListItem] = []
        for acceptance in records[:limit]:
            operation = uow.operations.get_operation(acceptance.operation_id)
            expires = (
                operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds)
                if operation.status is OperationStatus.SUCCEEDED
                and operation.completed_at is not None
                else None
            )
            items.append(
                HistoryCompareListItem(
                    operation_id=operation.operation_id,
                    nodes=tuple(
                        HistoryNodeRef(ref_kind=node.ref_kind, ref_id=node.ref_id)
                        for node in acceptance.nodes
                    ),
                    status=operation.status,
                    accepted_at=acceptance.created_at,
                    completed_at=operation.completed_at,
                    result_expires_at=expires,
                )
            )
        next_cursor = None
        if len(records) > limit:
            last = records[limit - 1]
            payload = _Cursor(
                scope_hash=scope_hash,
                created_at=last.created_at,
                operation_id=last.operation_id,
            )
            next_cursor = base64.urlsafe_b64encode(payload.model_dump_json().encode()).decode(
                "ascii"
            )
        return HistoryCompareListPage(items=tuple(items), next_cursor=next_cursor)
