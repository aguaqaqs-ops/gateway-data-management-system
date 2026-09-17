"""Fail-closed backend and worker settings for 5A runtime."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway_backend.capabilities.source_package_staging.contracts import RESOURCE_BUDGETS
from gateway_backend.settings import (
    FIXED_CLEANUP_UNPINNED_TTL_SECONDS,
    FIXED_HTTP_NEW_WORK_LIMIT,
    FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    FIXED_UPLOAD_MAX_ENTRIES,
    FIXED_UPLOAD_MAX_EXPANDED_BYTES,
    FIXED_UPLOAD_MAX_PATH_BYTES,
    OperationWorkerSettings,
    _WORKER_FIXED_BUDGETS,
    require_http_url,
)
from tests.support.runtime_settings import (
    TEST_INTERNAL_BEARER_TOKEN,
    TEST_REPOSITORY_TOKEN,
    make_backend_settings,
    make_operation_worker_settings,
)

pytestmark = pytest.mark.unit


def test_backend_settings_require_absolute_paths_and_http_url(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        make_backend_settings(tmp_path, control_db_path=Path("relative.sqlite3"))
    with pytest.raises(ValidationError, match="absolute"):
        make_backend_settings(tmp_path, artifact_root=Path("artifacts"))
    with pytest.raises(ValidationError, match="http"):
        make_backend_settings(tmp_path, repository_base_url="not-a-url")
    with pytest.raises(ValidationError, match="credentials"):
        make_backend_settings(tmp_path, repository_base_url="http://user:secret@127.0.0.1:9")


def test_backend_settings_freeze_upload_admission_and_cleanup_budgets(tmp_path: Path) -> None:
    settings = make_backend_settings(tmp_path)
    assert settings.upload_max_compressed_bytes == RESOURCE_BUDGETS.max_source_package_compressed_bytes
    assert settings.upload_max_expanded_bytes == RESOURCE_BUDGETS.max_source_package_expanded_bytes
    assert settings.upload_max_entries == RESOURCE_BUDGETS.max_source_package_entries
    assert settings.upload_max_path_bytes == RESOURCE_BUDGETS.max_normalized_path_bytes
    assert settings.upload_max_compressed_bytes == FIXED_UPLOAD_MAX_COMPRESSED_BYTES
    assert settings.upload_max_expanded_bytes == FIXED_UPLOAD_MAX_EXPANDED_BYTES
    assert settings.upload_max_entries == FIXED_UPLOAD_MAX_ENTRIES
    assert settings.upload_max_path_bytes == FIXED_UPLOAD_MAX_PATH_BYTES
    assert settings.http_new_work_limit == FIXED_HTTP_NEW_WORK_LIMIT
    assert settings.cleanup_unpinned_ttl_seconds == FIXED_CLEANUP_UNPINNED_TTL_SECONDS
    with pytest.raises(ValidationError, match="fixed"):
        make_backend_settings(tmp_path, http_new_work_limit=1)
    with pytest.raises(ValidationError, match="fixed"):
        make_backend_settings(tmp_path, upload_max_compressed_bytes=1)


def test_settings_repr_and_validation_errors_omit_token_and_paths(tmp_path: Path) -> None:
    token_file = tmp_path / "repository-bearer-token"
    token_file.write_text(TEST_REPOSITORY_TOKEN, encoding="utf-8")
    internal_bearer_file = tmp_path / "internal-bearer-token"
    internal_bearer_file.write_text(TEST_INTERNAL_BEARER_TOKEN, encoding="utf-8")
    settings = make_backend_settings(
        tmp_path,
        repository_bearer_token_file=token_file,
        internal_bearer_token_file=internal_bearer_file,
    )
    rendered = repr(settings)
    assert rendered == "BackendSettings(redacted)"
    assert TEST_REPOSITORY_TOKEN not in rendered
    assert str(tmp_path) not in rendered
    with pytest.raises(ValueError, match="credentials") as exc_info:
        require_http_url("http://user:super-secret@example.invalid")
    assert "super-secret" not in str(exc_info.value)


def test_backend_settings_require_internal_bearer_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        make_backend_settings(tmp_path, internal_bearer_token_file=Path("relative-token"))


def test_worker_settings_freeze_lifecycle_budgets(tmp_path: Path) -> None:
    settings = make_operation_worker_settings(tmp_path)
    assert settings.graceful_drain_timeout_seconds == _WORKER_FIXED_BUDGETS["graceful_drain_timeout_seconds"]
    assert settings.max_in_flight == _WORKER_FIXED_BUDGETS["max_in_flight"]
    assert settings.claim_limit == _WORKER_FIXED_BUDGETS["claim_limit"]
    with pytest.raises(ValidationError, match="fixed"):
        make_operation_worker_settings(tmp_path, graceful_drain_timeout_seconds=1.0)


def test_worker_settings_require_artifact_root_and_repository_read(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        OperationWorkerSettings(control_db_path=tmp_path / "control.sqlite3")  # type: ignore[call-arg]
    settings = make_operation_worker_settings(tmp_path)
    assert settings.artifact_root.is_absolute()
    assert settings.repository_base_url.startswith("http")
    assert repr(settings) == "OperationWorkerSettings(redacted)"
