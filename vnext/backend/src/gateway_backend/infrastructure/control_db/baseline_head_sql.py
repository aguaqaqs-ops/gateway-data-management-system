"""Connection-scoped baseline head reads without control DB UoW imports."""

from __future__ import annotations

import sqlite3

from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import BaselineHead


def get_current_head_from_connection(
    connection: sqlite3.Connection,
    repository_id: str,
) -> BaselineHead:
    row = connection.execute(
        """
        SELECT head.node_id, node.commit_id, head.optimistic_version
        FROM baseline_head_records AS head
        INNER JOIN baseline_node_records AS node ON node.node_id = head.node_id
        WHERE head.repository_id = ?
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        raise KeyError(repository_id)
    return BaselineHead(
        business_baseline_node_id=row["node_id"],
        business_baseline_commit_id=row["commit_id"],
        baseline_head_version=row["optimistic_version"],
    )


def assert_initial_scope_matches(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
) -> None:
    """Reject scope resolution when INITIAL node scope does not match the caller."""

    row = connection.execute(
        """
        SELECT gateway_device_external_key, business_project_id
        FROM baseline_node_records
        WHERE repository_id = ? AND kind = 'INITIAL'
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        raise ScopeResolutionError("baseline initial node is missing")
    if (
        row["gateway_device_external_key"] != gateway_device_external_key
        or row["business_project_id"] != business_project_id
    ):
        raise ScopeResolutionError("baseline initial scope does not match provisioned mapping")


__all__ = ["assert_initial_scope_matches", "get_current_head_from_connection"]
