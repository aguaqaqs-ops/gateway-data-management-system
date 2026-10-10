"""Connection-scoped provisioned scope resolution without UoW imports."""

from __future__ import annotations

import sqlite3
from typing import cast

from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import ResolvedScope
from gateway_backend.infrastructure.control_db.baseline_head_sql import (
    assert_initial_scope_matches,
    get_current_head_from_connection,
)


def _load_active_mapping(
    connection: sqlite3.Connection,
    *,
    gateway_device_external_key: str,
    business_project_id: str,
) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            """
            SELECT repository_id, enabled
            FROM provisioned_scope_mappings
            WHERE gateway_device_external_key = ? AND business_project_id = ?
            """,
            (gateway_device_external_key, business_project_id),
        ).fetchone(),
    )


def resolve_provisioned_scope_from_connection(
    connection: sqlite3.Connection,
    *,
    gateway_device_external_key: str,
    business_project_id: str,
) -> ResolvedScope:
    """Read one provisioned scope from the current SQLite connection."""

    mapping = _load_active_mapping(
        connection,
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
    )
    if mapping is None:
        raise ScopeResolutionError("provisioned mapping is missing")
    if mapping["enabled"] != 1:
        raise ScopeResolutionError("provisioned mapping is disabled")
    repository_id = mapping["repository_id"]
    assert_initial_scope_matches(
        connection,
        repository_id=repository_id,
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
    )
    return ResolvedScope(
        repository_id=repository_id,
        baseline_head=get_current_head_from_connection(connection, repository_id),
    )


class ProvisionedScopeTransactionRead:
    """Same-transaction provisioned scope reader for Submit T1."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def resolve_provisioned_scope(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> ResolvedScope:
        return resolve_provisioned_scope_from_connection(
            self._connection,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
        )
