"""Provisioned scope seed rules: a repeated seed keeps the advanced Head, and a rejected batch writes nothing."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gateway_backend.infrastructure.control_db.database import (
    connect_control_db,
    initialize_and_verify_control_db,
)
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings
from tests.support.baseline_fixtures import apply_baseline_head_state, seed_provisioned_mapping_with_head
from tests.support.workspace_fixtures import make_baseline_head

pytestmark = pytest.mark.unit

BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")


def _mapping_record(
    *,
    device_key: str,
    project_id: str,
    repository_id: str,
    node_id: str,
    commit_id: str,
    head_version: int = 0,
) -> dict[str, object]:
    return {
        "gateway_device_external_key": device_key,
        "business_project_id": project_id,
        "repository_id": repository_id,
        "business_baseline_node_id": node_id,
        "business_baseline_commit_id": commit_id,
        "baseline_head_version": head_version,
        "enabled": True,
    }


# A valid first seed for a new scope. Every rejected batch below lists it first, so a partial
# write would appear as a new mapping, INITIAL node or Head row.
_NEW_SCOPE = _mapping_record(
    device_key="device-2",
    project_id="project-2",
    repository_id="repo-2",
    node_id="node-2",
    commit_id="commit-2",
)

# The first two rows fail in batch validation, before any row is written. The last two fail
# while records are applied, after _NEW_SCOPE was written in the same transaction, so they
# exercise the rollback.
REJECTED_SEED_BATCHES = (
    pytest.param(
        (
            _NEW_SCOPE,
            _mapping_record(
                device_key="device-3",
                project_id="project-3",
                repository_id="repo-1",
                node_id="node-1",
                commit_id="commit-1",
            ),
        ),
        "repository is already owned by a different scope",
        id="repository-owned-by-another-scope",
    ),
    pytest.param(
        (
            _NEW_SCOPE,
            _mapping_record(
                device_key="device-4",
                project_id="project-4",
                repository_id="repo-2",
                node_id="node-4",
                commit_id="commit-4",
            ),
        ),
        "seed batch assigns one repository to multiple scopes",
        id="repository-assigned-to-two-scopes",
    ),
    pytest.param(
        (
            _NEW_SCOPE,
            _mapping_record(
                device_key="device-2",
                project_id="project-2",
                repository_id="repo-5",
                node_id="node-5",
                commit_id="commit-5",
            ),
        ),
        "seed batch assigns one scope to multiple repositories",
        id="scope-assigned-to-two-repositories",
    ),
    pytest.param(
        (
            _NEW_SCOPE,
            _mapping_record(
                device_key="device-6",
                project_id="project-6",
                repository_id="repo-6",
                node_id="node-6",
                commit_id="commit-6",
                head_version=3,
            ),
        ),
        "first repository seed must use baseline_head_version 0",
        id="first-seed-with-nonzero-head-version",
    ),
    pytest.param(
        (
            _NEW_SCOPE,
            _mapping_record(
                device_key="device-1",
                project_id="project-1",
                repository_id="repo-1",
                node_id="node-7",
                commit_id="commit-1",
            ),
        ),
        "seed initial identity does not match stored INITIAL node",
        id="initial-identity-mismatch",
    ),
)

_SEED_STATE_QUERIES = (
    "SELECT * FROM provisioned_scope_mappings ORDER BY gateway_device_external_key, business_project_id",
    "SELECT * FROM baseline_node_records ORDER BY node_id",
    "SELECT * FROM baseline_head_records ORDER BY repository_id",
)


def _seed_state(db_path: Path) -> tuple[list[tuple[object, ...]], ...]:
    connection = connect_control_db(db_path)
    try:
        return tuple(
            [tuple(row) for row in connection.execute(query).fetchall()]
            for query in _SEED_STATE_QUERIES
        )
    finally:
        connection.close()


def test_seed_restart_does_not_regress_advanced_head(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path)
    seed_provisioned_mapping_with_head(
        db_path,
        repository_id="repo-1",
        baseline_head=BASELINE_HEAD,
    )
    advanced = make_baseline_head(version=7, commit_id=BASELINE_HEAD.business_baseline_commit_id)
    apply_baseline_head_state(db_path, repository_id="repo-1", baseline_head=advanced)

    mapping_file = tmp_path / "provisioned-mapping.json"
    mapping_file.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": "device-1",
                        "business_project_id": "project-1",
                        "repository_id": "repo-1",
                        "business_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
                        "business_baseline_commit_id": BASELINE_HEAD.business_baseline_commit_id,
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    seed_provisioned_mappings(db_path, mapping_file)

    connection = connect_control_db(db_path)
    try:
        head = get_current_head_from_connection(connection, "repo-1")
        assert head.baseline_head_version == 7
        assert head.business_baseline_commit_id == BASELINE_HEAD.business_baseline_commit_id
    finally:
        connection.close()


def test_seed_rejects_cross_scope_repository_reassignment(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path)
    seed_provisioned_mapping_with_head(
        db_path,
        device_key="device-1",
        project_id="project-1",
        repository_id="repo-1",
        baseline_head=make_baseline_head(version=0, commit_id="commit-1"),
    )

    mapping_file = tmp_path / "reassign.json"
    mapping_file.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": "device-2",
                        "business_project_id": "project-2",
                        "repository_id": "repo-1",
                        "business_baseline_node_id": "node-1",
                        "business_baseline_commit_id": "commit-1",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="already owned by a different scope"):
        seed_provisioned_mappings(db_path, mapping_file)


@pytest.mark.parametrize(("batch", "message"), REJECTED_SEED_BATCHES)
def test_rejected_seed_batch_is_refused_as_a_whole(
    tmp_path: Path,
    batch: tuple[dict[str, object], ...],
    message: str,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path)
    seed_provisioned_mapping_with_head(
        db_path,
        device_key="device-1",
        project_id="project-1",
        repository_id="repo-1",
        baseline_head=make_baseline_head(version=0, commit_id="commit-1"),
    )
    before = _seed_state(db_path)
    assert len(before[0]) == 1

    mapping_file = tmp_path / "rejected-batch.json"
    mapping_file.write_text(json.dumps({"mappings": list(batch)}), encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(message)):
        seed_provisioned_mappings(db_path, mapping_file)

    assert _seed_state(db_path) == before
