from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from gateway_backend.application.workspace.upload_limits import (
    FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    FIXED_UPLOAD_MAX_ENTRIES,
    FIXED_UPLOAD_MAX_EXPANDED_BYTES,
    FIXED_UPLOAD_MAX_PATH_BYTES,
    FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS,
)

_MIB = 1024 * 1024

FIXED_HTTP_NEW_WORK_LIMIT = 32
FIXED_CLEANUP_UNPINNED_TTL_SECONDS = 86_400
FIXED_CLEANUP_SWEEP_BATCH_SIZE = 32
FIXED_CLEANUP_RETRY_BACKOFF_SECONDS = 1.0
FIXED_REPOSITORY_TIMEOUT_SECONDS = 30.0

_WORKER_FIXED_BUDGETS = {
    "lease_duration_seconds": 30.0,
    "heartbeat_interval_seconds": 10.0,
    "idle_claim_poll_seconds": 1.0,
    "transient_backoff_initial_seconds": 1.0,
    "transient_backoff_max_seconds": 10.0,
    "startup_retry_budget_seconds": 60.0,
    "graceful_drain_timeout_seconds": 180.0,
    "max_in_flight": 1,
    "claim_limit": 1,
}


def require_absolute_path(value: Path, *, field_name: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{field_name} must be absolute")
    return value


def require_http_url(value: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError("repository_base_url must be an absolute http or https URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc == "":
        raise ValueError("repository_base_url must be an absolute http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("repository_base_url must not embed credentials")
    return value


def _reject_changed_fixed_values(instance: object, expected: dict[str, object]) -> None:
    for field_name, expected_value in expected.items():
        if getattr(instance, field_name) != expected_value:
            raise ValueError(f"{field_name} is fixed by the runtime contract")


class BackendSettings(BaseSettings):
    """Runtime settings owned by the backend HTTP process."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_BACKEND_", frozen=True)

    control_db_path: Path
    artifact_root: Path
    repository_base_url: str
    repository_bearer_token_file: Path = Field(repr=False)
    internal_bearer_token_file: Path = Field(repr=False)
    repository_timeout_seconds: float = FIXED_REPOSITORY_TIMEOUT_SECONDS
    session_file: Path
    provisioned_mapping_file: Path
    upload_max_compressed_bytes: int = FIXED_UPLOAD_MAX_COMPRESSED_BYTES
    upload_max_expanded_bytes: int = FIXED_UPLOAD_MAX_EXPANDED_BYTES
    upload_max_entries: int = FIXED_UPLOAD_MAX_ENTRIES
    upload_max_path_bytes: int = FIXED_UPLOAD_MAX_PATH_BYTES
    upload_stream_timeout_seconds: float = FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS
    http_new_work_limit: int = FIXED_HTTP_NEW_WORK_LIMIT
    cleanup_unpinned_ttl_seconds: int = FIXED_CLEANUP_UNPINNED_TTL_SECONDS
    cleanup_sweep_batch_size: int = FIXED_CLEANUP_SWEEP_BATCH_SIZE
    cleanup_retry_backoff_seconds: float = FIXED_CLEANUP_RETRY_BACKOFF_SECONDS

    @field_validator("control_db_path")
    @classmethod
    def _require_absolute_control_db_path(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="control_db_path")

    @field_validator("artifact_root")
    @classmethod
    def _require_absolute_artifact_root(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="artifact_root")

    @field_validator("repository_base_url")
    @classmethod
    def _require_http_repository_base_url(cls, value: str) -> str:
        return require_http_url(value)

    @field_validator("repository_bearer_token_file")
    @classmethod
    def _require_absolute_token_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="repository_bearer_token_file")

    @field_validator("internal_bearer_token_file")
    @classmethod
    def _require_absolute_internal_bearer_token_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="internal_bearer_token_file")

    @field_validator("session_file")
    @classmethod
    def _require_absolute_session_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="session_file")

    @field_validator("provisioned_mapping_file")
    @classmethod
    def _require_absolute_mapping_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="provisioned_mapping_file")

    @model_validator(mode="after")
    def _validate_fixed_http_budgets(self) -> Self:
        _reject_changed_fixed_values(
            self,
            {
                "repository_timeout_seconds": FIXED_REPOSITORY_TIMEOUT_SECONDS,
                "upload_max_compressed_bytes": FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
                "upload_max_expanded_bytes": FIXED_UPLOAD_MAX_EXPANDED_BYTES,
                "upload_max_entries": FIXED_UPLOAD_MAX_ENTRIES,
                "upload_max_path_bytes": FIXED_UPLOAD_MAX_PATH_BYTES,
                "upload_stream_timeout_seconds": FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS,
                "http_new_work_limit": FIXED_HTTP_NEW_WORK_LIMIT,
                "cleanup_unpinned_ttl_seconds": FIXED_CLEANUP_UNPINNED_TTL_SECONDS,
                "cleanup_sweep_batch_size": FIXED_CLEANUP_SWEEP_BATCH_SIZE,
                "cleanup_retry_backoff_seconds": FIXED_CLEANUP_RETRY_BACKOFF_SECONDS,
            },
        )
        return self

    def __repr__(self) -> str:
        return "BackendSettings(redacted)"


class OperationWorkerSettings(BaseSettings):
    """Settings owned exclusively by the process-local operation worker.

    The worker is intentionally configured independently from ``BackendSettings``.  Its
    budgets are part of the R3 lifecycle contract, so they are exposed for diagnostics and
    dependency injection but cannot be changed through environment configuration.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GATEWAY_BACKEND_OPERATION_WORKER_",
        frozen=True,
    )

    control_db_path: Path
    artifact_root: Path
    repository_base_url: str
    repository_bearer_token_file: Path = Field(repr=False)
    repository_timeout_seconds: float = FIXED_REPOSITORY_TIMEOUT_SECONDS
    provisioned_mapping_file: Path
    lease_duration_seconds: float = 30.0
    heartbeat_interval_seconds: float = 10.0
    idle_claim_poll_seconds: float = 1.0
    transient_backoff_initial_seconds: float = 1.0
    transient_backoff_max_seconds: float = 10.0
    startup_retry_budget_seconds: float = 60.0
    graceful_drain_timeout_seconds: float = 180.0
    max_in_flight: int = 1
    claim_limit: int = 1

    @field_validator("control_db_path")
    @classmethod
    def _require_absolute_control_db_path(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="control_db_path")

    @field_validator("artifact_root")
    @classmethod
    def _require_absolute_artifact_root(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="artifact_root")

    @field_validator("repository_base_url")
    @classmethod
    def _require_http_repository_base_url(cls, value: str) -> str:
        return require_http_url(value)

    @field_validator("repository_bearer_token_file")
    @classmethod
    def _require_absolute_token_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="repository_bearer_token_file")

    @field_validator("provisioned_mapping_file")
    @classmethod
    def _require_absolute_worker_mapping_file(cls, value: Path) -> Path:
        return require_absolute_path(value, field_name="provisioned_mapping_file")

    @model_validator(mode="after")
    def _validate_fixed_budgets(self) -> Self:
        _reject_changed_fixed_values(
            self,
            {
                **_WORKER_FIXED_BUDGETS,
                "repository_timeout_seconds": FIXED_REPOSITORY_TIMEOUT_SECONDS,
            },
        )
        if self.heartbeat_interval_seconds > self.lease_duration_seconds / 3:
            raise ValueError("heartbeat_interval_seconds must be at most lease duration / 3")
        return self

    def __repr__(self) -> str:
        return "OperationWorkerSettings(redacted)"


__all__ = [
    "BackendSettings",
    "FIXED_CLEANUP_RETRY_BACKOFF_SECONDS",
    "FIXED_CLEANUP_SWEEP_BATCH_SIZE",
    "FIXED_CLEANUP_UNPINNED_TTL_SECONDS",
    "FIXED_HTTP_NEW_WORK_LIMIT",
    "FIXED_REPOSITORY_TIMEOUT_SECONDS",
    "FIXED_UPLOAD_MAX_COMPRESSED_BYTES",
    "FIXED_UPLOAD_MAX_ENTRIES",
    "FIXED_UPLOAD_MAX_EXPANDED_BYTES",
    "FIXED_UPLOAD_MAX_PATH_BYTES",
    "FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS",
    "OperationWorkerSettings",
    "require_absolute_path",
    "require_http_url",
]
