from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Runtime settings owned by the backend process."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_BACKEND_")

    artifact_root: Path = Path("runtime-data/artifacts")


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
        if not value.is_absolute():
            raise ValueError("control_db_path must be absolute")
        return value

    @model_validator(mode="after")
    def _validate_fixed_budgets(self) -> "OperationWorkerSettings":
        fixed_values = {
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
        for field_name, expected in fixed_values.items():
            if getattr(self, field_name) != expected:
                raise ValueError(f"{field_name} is fixed by the operation-worker contract")
        if self.heartbeat_interval_seconds > self.lease_duration_seconds / 3:
            raise ValueError("heartbeat_interval_seconds must be at most lease duration / 3")
        return self


__all__ = ["BackendSettings", "OperationWorkerSettings"]
