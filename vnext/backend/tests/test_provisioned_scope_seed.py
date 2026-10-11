"""Provisioned scope seed rules: a repeated seed keeps the advanced Head, and a repository cannot move to another scope."""

from __future__ import annotations

import json
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
