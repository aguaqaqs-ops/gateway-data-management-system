"""Scope-bound paginated History operation discovery."""
from __future__ import annotations

import base64
import binascii
import hashlib

from gateway_shared_kernel.jcs import canonicalize_json_value
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, ValidationError

from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeNotFound
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.http.dependencies import HistoryHttpDependencies
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.history_compare import _public_operation_status
from gateway_backend.http.schemas.history import (
    HistoryCompareListItemResponse, HistoryCompareListResponse, HistoryNodeRefResponse,
)
from gateway_backend.operations import OperationStatus


class _Cursor(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    scope_hash: str
    created_at: datetime
    operation_id: str


def list_compare_operations(
    *, context: IdentityContext, deps: HistoryHttpDependencies, limit: int, cursor: str | None,
) -> HistoryCompareListResponse:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    try:
        with deps.unit_of_work_factory(read_only=True) as uow:
            try:
                scope = uow.resolve_provisioned_scope(
                    gateway_device_external_key=context.gateway_device_external_key,
                    business_project_id=context.business_project_id,
                )
            except ScopeNotFound as exc:
                raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
            scope_hash = hashlib.sha256(canonicalize_json_value([
                context.gateway_device_external_key, context.business_project_id, scope.repository_id,
            ])).hexdigest()
            after = None
            if cursor is not None:
                try:
                    raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
                    decoded = _Cursor.model_validate_json(raw, strict=True)
                    if (decoded.scope_hash != scope_hash
                            or decoded.created_at.tzinfo is None or not decoded.operation_id):
                        raise ValueError("cursor scope or ordering is invalid")
                    after = (decoded.created_at, decoded.operation_id)
                except (UnicodeError, binascii.Error, ValueError, ValidationError) as exc:
                    raise ApiError(code="REQUEST_VALIDATION_FAILED", message="invalid cursor", status_code=422) from exc
            records = uow.history_compare.list_acceptances(
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id, repository_id=scope.repository_id,
                now=uow.transaction_now, after=after, limit=limit + 1,
            )
            items: list[HistoryCompareListItemResponse] = []
            for acceptance in records[:limit]:
                operation = uow.operations.get_operation(acceptance.operation_id)
                expires = (operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds)
                           if operation.status is OperationStatus.SUCCEEDED and operation.completed_at is not None
                           else None)
                items.append(HistoryCompareListItemResponse(
                    operation_id=operation.operation_id,
                    nodes=[HistoryNodeRefResponse(ref_kind=node.ref_kind.value, ref_id=node.ref_id)
                           for node in acceptance.nodes],
                    status=_public_operation_status(operation.status), accepted_at=acceptance.created_at,
                    completed_at=operation.completed_at, result_expires_at=expires,
                ))
            next_cursor = None
            if len(records) > limit:
                last = records[limit - 1]
                payload = _Cursor(scope_hash=scope_hash, created_at=last.created_at, operation_id=last.operation_id)
                next_cursor = base64.urlsafe_b64encode(payload.model_dump_json().encode()).decode("ascii")
            return HistoryCompareListResponse(items=items, next_cursor=next_cursor)
    except (PermissionDenied, ApiError):
        raise
