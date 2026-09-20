"""Shared runtime settings constructors for backend tests."""

from __future__ import annotations

import json
from pathlib import Path

from gateway_backend.settings import BackendSettings, OperationWorkerSettings

TEST_REPOSITORY_BASE_URL = "http://127.0.0.1:9"
TEST_REPOSITORY_TOKEN = "test-repository-token"
TEST_INTERNAL_BEARER_TOKEN = "test-internal-bearer"
TEST_SESSION_TOKEN = "test-session-token"
TEST_MAPPING_REPOSITORY_ID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
TEST_MAPPING_COMMIT_ID = "commit-base"
TEST_DEVICE_KEY = "device-1"
TEST_PROJECT_ID = "project-1"


def default_session_document() -> dict[str, object]:
    return {
        "sessions": [
            {
                "token": TEST_SESSION_TOKEN,
                "actor_id": "actor-1",
                "gateway_device_external_key": TEST_DEVICE_KEY,
                "business_project_id": TEST_PROJECT_ID,
                "permissions": [
                    "workspace_read",
                    "upload_submit_workspace",
                    "preview_workspace",
                    "review_submission",
                ],
            }
        ]
    }


def default_mapping_document() -> dict[str, object]:
    return {
        "mappings": [
            {
                "gateway_device_external_key": TEST_DEVICE_KEY,
                "business_project_id": TEST_PROJECT_ID,
                "repository_id": TEST_MAPPING_REPOSITORY_ID,
                "business_baseline_node_id": "node-1",
                "business_baseline_commit_id": TEST_MAPPING_COMMIT_ID,
                "baseline_head_version": 3,
                "enabled": True,
            }
        ]
    }


def write_session_file(path: Path, document: dict[str, object] | None = None) -> Path:
    path.write_text(json.dumps(document or default_session_document()), encoding="utf-8")
    return path


def write_mapping_file(path: Path, document: dict[str, object] | None = None) -> Path:
    path.write_text(json.dumps(document or default_mapping_document()), encoding="utf-8")
    return path


def make_operation_worker_settings(
    tmp_path: Path,
    *,
    control_db_path: Path | None = None,
    **overrides: object,
) -> OperationWorkerSettings:
    db_path = control_db_path if control_db_path is not None else tmp_path / "control.sqlite3"
    artifact_root = overrides.pop("artifact_root", db_path.parent / "artifacts")
    token_file = overrides.pop(
        "repository_bearer_token_file",
        db_path.parent / "repository-bearer-token",
    )
    repository_base_url = overrides.pop("repository_base_url", TEST_REPOSITORY_BASE_URL)
    mapping_file = overrides.pop(
        "provisioned_mapping_file",
        db_path.parent / "provisioned-mapping.json",
    )
    return OperationWorkerSettings(
        control_db_path=db_path,
        artifact_root=artifact_root,  # type: ignore[arg-type]
        repository_base_url=repository_base_url,  # type: ignore[arg-type]
        repository_bearer_token_file=token_file,  # type: ignore[arg-type]
        provisioned_mapping_file=mapping_file,  # type: ignore[arg-type]
        **overrides,  # type: ignore[arg-type]
    )


def make_backend_settings(
    tmp_path: Path,
    *,
    control_db_path: Path | None = None,
    **overrides: object,
) -> BackendSettings:
    db_path = control_db_path if control_db_path is not None else tmp_path / "control.sqlite3"
    artifact_root = overrides.pop("artifact_root", tmp_path / "artifacts")
    token_file = overrides.pop(
        "repository_bearer_token_file",
        tmp_path / "repository-bearer-token",
    )
    repository_base_url = overrides.pop("repository_base_url", TEST_REPOSITORY_BASE_URL)
    session_file = overrides.pop("session_file", tmp_path / "session.json")
    internal_bearer_file = overrides.pop(
        "internal_bearer_token_file",
        tmp_path / "internal-bearer-token",
    )
    mapping_file = overrides.pop("provisioned_mapping_file", tmp_path / "provisioned-mapping.json")
    return BackendSettings(
        control_db_path=db_path,
        artifact_root=artifact_root,  # type: ignore[arg-type]
        repository_base_url=repository_base_url,  # type: ignore[arg-type]
        repository_bearer_token_file=token_file,  # type: ignore[arg-type]
        internal_bearer_token_file=internal_bearer_file,  # type: ignore[arg-type]
        session_file=session_file,  # type: ignore[arg-type]
        provisioned_mapping_file=mapping_file,  # type: ignore[arg-type]
        **overrides,  # type: ignore[arg-type]
    )


def prepare_backend_runtime_paths(tmp_path: Path) -> None:
    """Create the directories and identity files required for production startup."""

    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    token_file = tmp_path / "repository-bearer-token"
    if not token_file.exists():
        token_file.write_text(TEST_REPOSITORY_TOKEN + "\n", encoding="utf-8")
    internal_bearer_file = tmp_path / "internal-bearer-token"
    if not internal_bearer_file.exists():
        internal_bearer_file.write_text(TEST_INTERNAL_BEARER_TOKEN + "\n", encoding="utf-8")
    write_session_file(tmp_path / "session.json")
    write_mapping_file(tmp_path / "provisioned-mapping.json")
