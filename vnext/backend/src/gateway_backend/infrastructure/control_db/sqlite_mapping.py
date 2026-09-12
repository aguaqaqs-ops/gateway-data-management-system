"""Provisioned device/project → repository/BaselineHead control-plane projection."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import cast

from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext, ResolvedScope
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork


class ProvisionedScopeResolution:
    """Resolve session identity against seeded provisioned mappings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def resolve(self, context: IdentityContext) -> ResolvedScope:
        with ControlDbUnitOfWork(self._db_path, read_only=True) as unit_of_work:
            mapping = _load_active_mapping(
                unit_of_work.connection,
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )
        if mapping is None:
            raise ScopeResolutionError("provisioned mapping is missing")
        if mapping["enabled"] != 1:
            raise ScopeResolutionError("provisioned mapping is disabled")
        return ResolvedScope(
            repository_id=mapping["repository_id"],
            baseline_head=BaselineHead(
                business_baseline_node_id=mapping["business_baseline_node_id"],
                business_baseline_commit_id=mapping["business_baseline_commit_id"],
                baseline_head_version=mapping["baseline_head_version"],
            ),
        )


class ProvisionedBaselineHeadRead:
    """Read BaselineHead from the provisioned mapping projection."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def get_current_head(self, repository_id: str) -> BaselineHead:
        with ControlDbUnitOfWork(self._db_path, read_only=True) as unit_of_work:
            row = unit_of_work.connection.execute(
                """
                SELECT business_baseline_node_id, business_baseline_commit_id, baseline_head_version
                FROM provisioned_scope_mappings
                WHERE repository_id = ? AND enabled = 1
                LIMIT 1
                """,
                (repository_id,),
            ).fetchone()
        if row is None:
            raise KeyError(repository_id)
        return BaselineHead(
            business_baseline_node_id=row["business_baseline_node_id"],
            business_baseline_commit_id=row["business_baseline_commit_id"],
            baseline_head_version=row["baseline_head_version"],
        )


def seed_provisioned_mappings(db_path: Path, mapping_file: Path) -> None:
    """Idempotently upsert provisioned mappings from a server-owned JSON file."""

    records = load_provisioned_mapping_file(mapping_file)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        for record in records:
            unit_of_work.connection.execute(
                """
                INSERT INTO provisioned_scope_mappings (
                    gateway_device_external_key,
                    business_project_id,
                    repository_id,
                    business_baseline_node_id,
                    business_baseline_commit_id,
                    baseline_head_version,
                    enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(gateway_device_external_key, business_project_id) DO UPDATE SET
                    repository_id = excluded.repository_id,
                    business_baseline_node_id = excluded.business_baseline_node_id,
                    business_baseline_commit_id = excluded.business_baseline_commit_id,
                    baseline_head_version = excluded.baseline_head_version,
                    enabled = excluded.enabled
                """,
                (
                    record["gateway_device_external_key"],
                    record["business_project_id"],
                    record["repository_id"],
                    record["business_baseline_node_id"],
                    record["business_baseline_commit_id"],
                    record["baseline_head_version"],
                    1 if record["enabled"] else 0,
                ),
            )


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
            SELECT repository_id, business_baseline_node_id, business_baseline_commit_id,
                   baseline_head_version, enabled
            FROM provisioned_scope_mappings
            WHERE gateway_device_external_key = ? AND business_project_id = ?
            """,
            (gateway_device_external_key, business_project_id),
        ).fetchone(),
    )


__all__ = [
    "ProvisionedBaselineHeadRead",
    "ProvisionedScopeResolution",
    "load_provisioned_mapping_file",
    "seed_provisioned_mappings",
]
