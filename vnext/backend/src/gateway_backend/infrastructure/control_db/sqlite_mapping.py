"""Provisioned device/project → repository scope control-plane projection."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.domain.baseline.models import (
    BaselineHeadRecord,
    BaselineNode,
    BaselineNodeKind,
)
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext, ResolvedScope
from gateway_backend.infrastructure.control_db.sqlite_provisioned_scope import (
    ProvisionedScopeTransactionRead,
    resolve_provisioned_scope_from_connection,
)

class ProvisionedScopeResolution:
    """Resolve session identity against seeded provisioned mappings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def resolve(self, context: IdentityContext) -> ResolvedScope:
        from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

        with ControlDbUnitOfWork(self._db_path, read_only=True) as unit_of_work:
            return resolve_provisioned_scope_from_connection(
                unit_of_work.connection,
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )


class ProvisionedBaselineHeadRead:
    """Read BaselineHead from baseline authority tables."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def get_current_head(self, repository_id: str) -> BaselineHead:
        from gateway_backend.infrastructure.control_db.sqlite_baseline import SQLiteBaselineHeadRead

        return SQLiteBaselineHeadRead(self._db_path).get_current_head(repository_id)


def seed_provisioned_mappings(db_path: Path, mapping_file: Path) -> None:
    """Idempotently upsert provisioned mappings from a server-owned JSON file."""

    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    records = load_provisioned_mapping_file(mapping_file)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _seed_provisioned_mappings_in_transaction(unit_of_work.connection, records)


def load_provisioned_mapping_file(mapping_file: Path) -> tuple[dict[str, object], ...]:
    if not isinstance(mapping_file, Path) or not mapping_file.is_absolute():
        raise ValueError("provisioned mapping file must be absolute")
    try:
        payload = json.loads(mapping_file.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError("provisioned mapping file is unreadable") from None
    except json.JSONDecodeError as exc:
        raise ValueError("provisioned mapping file is invalid JSON") from exc
    if type(payload) is not dict:
        raise ValueError("provisioned mapping file must be a JSON object")
    raw_mappings = payload.get("mappings")
    if type(raw_mappings) is not list or not raw_mappings:
        raise ValueError("provisioned mapping file must contain mappings")
    records: list[dict[str, object]] = []
    for item in raw_mappings:
        records.append(_validate_mapping_record(item))
    return tuple(records)


def _validate_mapping_record(item: object) -> dict[str, object]:
    if type(item) is not dict:
        raise ValueError("provisioned mapping entry must be an object")
    required = (
        "gateway_device_external_key",
        "business_project_id",
        "repository_id",
        "business_baseline_node_id",
        "business_baseline_commit_id",
        "baseline_head_version",
        "enabled",
    )
    missing = [key for key in required if key not in item]
    if missing:
        raise ValueError("provisioned mapping entry is missing required fields")
    version = item["baseline_head_version"]
    enabled = item["enabled"]
    if type(version) is not int or isinstance(version, bool) or version < 0:
        raise ValueError("baseline_head_version must be a non-negative integer")
    if type(enabled) is not bool:
        raise ValueError("enabled must be a boolean")
    record = {
        key: item[key] if key not in {"baseline_head_version", "enabled"} else item[key]
        for key in required
    }
    for key in (
        "gateway_device_external_key",
        "business_project_id",
        "repository_id",
        "business_baseline_node_id",
        "business_baseline_commit_id",
    ):
        value = record[key]
        if type(value) is not str or not value:
            raise ValueError(f"{key} must be a non-empty string")
    return record


def _seed_provisioned_mappings_in_transaction(
    connection: sqlite3.Connection,
    records: tuple[dict[str, object], ...],
) -> None:
    _validate_seed_batch_reverse_scope(connection, records)
    seed_now = datetime.now(UTC)
    for record in records:
        _apply_seed_record(connection, record, seed_now=seed_now)


def _validate_seed_batch_reverse_scope(
    connection: sqlite3.Connection,
    records: tuple[dict[str, object], ...],
) -> None:
    repository_to_scope: dict[str, tuple[str, str]] = {}
    scope_to_repository: dict[tuple[str, str], str] = {}
    for record in records:
        repository_id = record["repository_id"]
        device_key = record["gateway_device_external_key"]
        project_id = record["business_project_id"]
        if (
            type(repository_id) is not str
            or type(device_key) is not str
            or type(project_id) is not str
        ):
            raise ValueError("seed record has invalid scope fields")
        scope = (device_key, project_id)
        if repository_id in repository_to_scope and repository_to_scope[repository_id] != scope:
            raise ValueError("seed batch assigns one repository to multiple scopes")
        repository_to_scope[repository_id] = scope
        if scope in scope_to_repository and scope_to_repository[scope] != repository_id:
            raise ValueError("seed batch assigns one scope to multiple repositories")
        scope_to_repository[scope] = repository_id
    for repository_id, scope in repository_to_scope.items():
        existing_rows = connection.execute(
            """
            SELECT gateway_device_external_key, business_project_id
            FROM provisioned_scope_mappings
            WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchall()
        for row in existing_rows:
            existing_scope = (row["gateway_device_external_key"], row["business_project_id"])
            if existing_scope != scope:
                raise ValueError("repository is already owned by a different scope")
        initial_row = connection.execute(
            """
            SELECT gateway_device_external_key, business_project_id
            FROM baseline_node_records
            WHERE repository_id = ? AND kind = 'INITIAL'
            """,
            (repository_id,),
        ).fetchone()
        if initial_row is not None:
            initial_scope = (
                initial_row["gateway_device_external_key"],
                initial_row["business_project_id"],
            )
            if initial_scope != scope:
                raise ValueError("repository initial scope cannot be reassigned")


def _apply_seed_record(
    connection: sqlite3.Connection,
    record: dict[str, object],
    *,
    seed_now: datetime,
) -> None:
    repository_id = record["repository_id"]
    gateway_device_external_key = record["gateway_device_external_key"]
    business_project_id = record["business_project_id"]
    initial_node_id = record["business_baseline_node_id"]
    initial_commit_id = record["business_baseline_commit_id"]
    initial_version = record["baseline_head_version"]
    enabled = 1 if record["enabled"] else 0
    if (
        type(repository_id) is not str
        or type(gateway_device_external_key) is not str
        or type(business_project_id) is not str
        or type(initial_node_id) is not str
        or type(initial_commit_id) is not str
        or type(initial_version) is not int
    ):
        raise ValueError("seed record has invalid field types")
    initial_node = connection.execute(
        """
        SELECT node_id, commit_id, gateway_device_external_key, business_project_id
        FROM baseline_node_records
        WHERE repository_id = ? AND kind = 'INITIAL'
        """,
        (repository_id,),
    ).fetchone()
    if initial_node is None:
        if initial_version != 0:
            raise ValueError("first repository seed must use baseline_head_version 0")
        node = BaselineNode(
            node_id=initial_node_id,
            repository_id=repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            commit_id=initial_commit_id,
            kind=BaselineNodeKind.INITIAL,
            parent_node_id=None,
            source_submission_id=None,
            created_at=seed_now,
        )
        head = BaselineHeadRecord(
            repository_id=repository_id,
            node_id=initial_node_id,
            optimistic_version=0,
        )
        created_at_us = _datetime_to_epoch_us(seed_now)
        connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, 'INITIAL', NULL, NULL, ?)
            """,
            (
                node.node_id,
                node.repository_id,
                node.gateway_device_external_key,
                node.business_project_id,
                node.commit_id,
                created_at_us,
            ),
        )
        connection.execute(
            """
            INSERT INTO baseline_head_records (repository_id, node_id, optimistic_version)
            VALUES (?, ?, ?)
            """,
            (head.repository_id, head.node_id, head.optimistic_version),
        )
    else:
        if (
            initial_node["node_id"] != initial_node_id
            or initial_node["commit_id"] != initial_commit_id
            or initial_node["gateway_device_external_key"] != gateway_device_external_key
            or initial_node["business_project_id"] != business_project_id
        ):
            raise ValueError("seed initial identity does not match stored INITIAL node")
    connection.execute(
        """
        INSERT INTO provisioned_scope_mappings (
            gateway_device_external_key,
            business_project_id,
            repository_id,
            enabled
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(gateway_device_external_key, business_project_id) DO UPDATE SET
            repository_id = excluded.repository_id,
            enabled = excluded.enabled
        """,
        (gateway_device_external_key, business_project_id, repository_id, enabled),
    )


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("datetime must be aware UTC")
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


__all__ = [
    "ProvisionedBaselineHeadRead",
    "ProvisionedScopeResolution",
    "ProvisionedScopeTransactionRead",
    "load_provisioned_mapping_file",
    "resolve_provisioned_scope_from_connection",
    "seed_provisioned_mappings",
]
