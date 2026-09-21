"""Baseline authority helpers for control DB tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings

_SEED_TIME = datetime(2024, 1, 1, tzinfo=UTC)


def seed_provisioned_mapping_with_head(
    db_path: Path,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    baseline_head: BaselineHead,
    enabled: bool = True,
    mapping_file: Path | None = None,
) -> None:
    """Seed mapping initial identity and apply the requested current BaselineHead state."""

    mapping_path = mapping_file or (db_path.parent / "provisioned-mapping.json")
    mapping_path.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": device_key,
                        "business_project_id": project_id,
                        "repository_id": repository_id,
                        "business_baseline_node_id": baseline_head.business_baseline_node_id,
                        "business_baseline_commit_id": baseline_head.business_baseline_commit_id,
                        "baseline_head_version": 0,
                        "enabled": enabled,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    seed_provisioned_mappings(db_path, mapping_path)
    apply_baseline_head_state(
        db_path,
        repository_id=repository_id,
        baseline_head=baseline_head,
        device_key=device_key,
        project_id=project_id,
    )


def apply_baseline_head_state(
    db_path: Path,
    *,
    repository_id: str,
    baseline_head: BaselineHead,
    device_key: str = "device-1",
    project_id: str = "project-1",
) -> None:
    """Update baseline authority rows to match one adapter BaselineHead DTO."""

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        connection = unit_of_work.connection
        head_row = connection.execute(
            """
            SELECT node_id, optimistic_version
            FROM baseline_head_records
            WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()
        if head_row is None:
            initial_head = initial_identity_from_head(baseline_head)
            created_at_us = _datetime_to_epoch_us(_SEED_TIME)
            bootstrap_node_id = (
                initial_head.business_baseline_node_id
                if repository_id == "repo-1"
                else f"{repository_id}:{initial_head.business_baseline_node_id}"
            )
            connection.execute(
                """
                INSERT INTO baseline_node_records (
                    node_id, repository_id, gateway_device_external_key, business_project_id,
                    commit_id, kind, parent_node_id, source_submission_id, created_at_us
                ) VALUES (?, ?, ?, ?, ?, 'INITIAL', NULL, NULL, ?)
                """,
                (
                    bootstrap_node_id,
                    repository_id,
                    device_key,
                    project_id,
                    initial_head.business_baseline_commit_id,
                    created_at_us,
                ),
            )
            connection.execute(
                """
                INSERT INTO baseline_head_records (repository_id, node_id, optimistic_version)
                VALUES (?, ?, ?)
                """,
                (
                    repository_id,
                    bootstrap_node_id,
                    initial_head.baseline_head_version,
                ),
            )
            head_row = connection.execute(
                """
                SELECT node_id, optimistic_version
                FROM baseline_head_records
                WHERE repository_id = ?
                """,
                (repository_id,),
            ).fetchone()
            if head_row is None:
                raise ValueError("baseline head bootstrap failed")
        current_node_id = head_row["node_id"]
        if baseline_head.business_baseline_node_id != current_node_id:
            parent_row = connection.execute(
                """
                SELECT node_id
                FROM baseline_node_records
                WHERE repository_id = ? AND kind = 'INITIAL'
                """,
                (repository_id,),
            ).fetchone()
            if parent_row is None:
                raise ValueError("baseline initial node is missing")
            created_at_us = _datetime_to_epoch_us(_SEED_TIME)
            connection.execute(
                """
                INSERT INTO baseline_node_records (
                    node_id, repository_id, gateway_device_external_key, business_project_id,
                    commit_id, kind, parent_node_id, source_submission_id, created_at_us
                ) VALUES (?, ?, ?, ?, ?, 'ARCHIVED_SUBMISSION', ?, 'submission-test', ?)
                """,
                (
                    baseline_head.business_baseline_node_id,
                    repository_id,
                    device_key,
                    project_id,
                    baseline_head.business_baseline_commit_id,
                    parent_row["node_id"],
                    created_at_us,
                ),
            )
            connection.execute(
                """
                UPDATE baseline_head_records
                SET node_id = ?, optimistic_version = ?
                WHERE repository_id = ?
                """,
                (
                    baseline_head.business_baseline_node_id,
                    baseline_head.baseline_head_version,
                    repository_id,
                ),
            )
            return
        connection.execute(
            """
            UPDATE baseline_node_records
            SET commit_id = ?
            WHERE node_id = ?
            """,
            (baseline_head.business_baseline_commit_id, current_node_id),
        )
        connection.execute(
            """
            UPDATE baseline_head_records
            SET optimistic_version = ?
            WHERE repository_id = ?
            """,
            (baseline_head.baseline_head_version, repository_id),
        )


def upsert_provisioned_mapping_row(
    db_path: Path,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    baseline_head: BaselineHead | None = None,
    enabled: bool = True,
) -> None:
    """Update mapping scope fields and optionally drift baseline authority."""

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
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
            (device_key, project_id, repository_id, 1 if enabled else 0),
        )
    if baseline_head is not None:
        apply_baseline_head_state(
            db_path,
            repository_id=repository_id,
            baseline_head=baseline_head,
            device_key=device_key,
            project_id=project_id,
        )


def initial_identity_from_head(baseline_head: BaselineHead) -> BaselineHead:
    """Return the seed-file initial identity for one adapter BaselineHead."""

    return replace(baseline_head, baseline_head_version=0)


def _datetime_to_epoch_us(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
