from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Raised when service settings fail closed validation."""


def _read_token_file(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsError("bearer token file is unavailable") from exc
    token = raw.strip()
    return token or None


class RepositoryServiceSettings(BaseSettings):
    """Settings owned exclusively by Repository Service."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_REPOSITORY_")

    profile: Literal["production", "development", "test"] = "production"
    bearer_token_file: Path | None = None
    bearer_token: str | None = None
    data_root: Path = Path("runtime-data/repository")
    dolt_binary: Path = Path("/usr/local/bin/dolt")
    dolt_version: str = "2.1.11"
    author_name: str = "Gateway Repository Service"
    author_email: str = "repository@gateway.invalid"
    metadata_timeout_seconds: float = 30.0
    server_start_timeout_seconds: float = 30.0
    import_timeout_seconds: float = 60.0 * 60.0
    terminate_grace_seconds: float = 2.0
    # Shorter than design §9's suggested 10s default for faster CI/serial shutdown tests;
    # production deployments may raise this via settings.
    import_shutdown_grace_seconds: float = 2.0
    output_tail_bytes: int = 16 * 1024
    output_capture_bytes: int = 256 * 1024
    record_batch_rows: int = 1024
    record_batch_row_bounds: tuple[int, ...] = (256, 1024)
    record_batch_bytes: int = 4 * 1024 * 1024
    v8_record_batch_bytes: int = 1 * 1024 * 1024
    connector_fetch_row_bound: int = 32
    max_stream_line_bytes: int = 64 * 1024 * 1024
    v8_memory_safety_ceiling_bytes: int = 8 * 1024 * 1024 * 1024
    cgroup_root: Path | None = None
    cgroup_layout: Path | None = None
    memory_sample_interval_seconds: float = 0.01
    mysql_connector_version: str = "9.7.0"
    measurement_methodology_version: str = "p2-r1-audit-corrective-v7"
    v8_measurement_methodology_version: str = "p2-r1-audit-corrective-v8"
    min_free_disk_bytes: int = 5 * 1024 * 1024 * 1024
    min_free_disk_fraction: float = 0.10
    max_upload_bytes: int = 256 * 1024 * 1024
    max_manifest_json_bytes: int = 16 * 1024 * 1024
    max_replay_sql_bytes: int = 200 * 1024 * 1024
    max_total_expanded_entry_bytes: int = 4 * 1024 * 1024 * 1024
    max_decompressed_tar_stream_bytes: int = 4 * 1024 * 1024 * 1024
    artifact_ttl_seconds: int = 24 * 60 * 60
    sqlite_busy_timeout_ms: int = 5000
    catalog_parallel_workers: int = 2
    max_import_workers: int = 4
    max_queued_imports: int = 64
    import_headroom_bytes: int = 1 * 1024**3

    @field_validator("dolt_binary")
    @classmethod
    def _dolt_binary_must_be_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("dolt_binary must be an absolute path")
        return value

    @field_validator(
        "metadata_timeout_seconds",
        "server_start_timeout_seconds",
        "import_timeout_seconds",
        "terminate_grace_seconds",
        "import_shutdown_grace_seconds",
    )
    @classmethod
    def _timeouts_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeouts must be positive")
        return value

    @field_validator(
        "output_tail_bytes",
        "output_capture_bytes",
        "record_batch_rows",
        "record_batch_bytes",
        "v8_record_batch_bytes",
        "connector_fetch_row_bound",
        "max_stream_line_bytes",
        "v8_memory_safety_ceiling_bytes",
        "min_free_disk_bytes",
        "max_upload_bytes",
        "max_manifest_json_bytes",
        "max_replay_sql_bytes",
        "max_total_expanded_entry_bytes",
        "max_decompressed_tar_stream_bytes",
        "artifact_ttl_seconds",
        "sqlite_busy_timeout_ms",
        "catalog_parallel_workers",
        "max_import_workers",
        "max_queued_imports",
    )
    @classmethod
    def _bounds_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("bounds must be positive")
        return value

    @field_validator("import_headroom_bytes")
    @classmethod
    def _import_headroom_must_be_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("import_headroom_bytes must be non-negative")
        return value

    @field_validator("catalog_parallel_workers")
    @classmethod
    def _catalog_parallel_workers_must_be_bounded(cls, value: int) -> int:
        if not 1 <= value <= 4:
            raise ValueError("catalog_parallel_workers must be between 1 and 4")
        return value

    @field_validator("record_batch_row_bounds")
    @classmethod
    def _row_bounds_must_be_positive(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or any(item <= 0 for item in value):
            raise ValueError("record_batch_row_bounds must contain positive values")
        return value

    @field_validator("memory_sample_interval_seconds")
    @classmethod
    def _sampling_interval_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("memory_sample_interval_seconds must be positive")
        return value

    @field_validator("min_free_disk_fraction")
    @classmethod
    def _disk_fraction_must_be_valid(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("min_free_disk_fraction must be in (0, 1]")
        return value

    @field_validator("cgroup_root")
    @classmethod
    def _cgroup_root_must_be_absolute(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("cgroup_root must be absolute")
        return value

    @field_validator("cgroup_layout")
    @classmethod
    def _cgroup_layout_must_be_absolute(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("cgroup_layout must be absolute")
        return value

    @property
    def author(self) -> str:
        return f"{self.author_name} <{self.author_email}>"

    @property
    def control_db_path(self) -> Path:
        return self.data_root / "service-state" / "repository-service.sqlite3"

    def resolve_bearer_token(self) -> str:
        if self.profile == "production":
            if self.bearer_token_file is None:
                raise SettingsError("production bearer token file is required")
            token = _read_token_file(self.bearer_token_file)
            if token is None:
                raise SettingsError("production bearer token file is missing or empty")
            return token

        if self.bearer_token_file is not None:
            token = _read_token_file(self.bearer_token_file)
            if token is not None:
                return token
        if self.bearer_token is not None and self.bearer_token.strip():
            return self.bearer_token.strip()
        raise SettingsError("development or test bearer token is required")

    def redacted_dump(self) -> dict[str, Any]:
        data = self.model_dump()
        if data.get("bearer_token"):
            data["bearer_token"] = "<redacted>"
        return data

    def __repr__(self) -> str:
        return f"RepositoryServiceSettings({self.redacted_dump()})"

    def __str__(self) -> str:
        return self.__repr__()
