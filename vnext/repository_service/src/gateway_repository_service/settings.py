from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RepositoryServiceSettings(BaseSettings):
    """Settings owned exclusively by Repository Service."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_REPOSITORY_")

    data_root: Path = Path("runtime-data/repository")
    dolt_binary: Path = Path("/usr/local/bin/dolt")
    dolt_version: str = "2.1.11"
    author_name: str = "Gateway Repository Service"
    author_email: str = "repository@gateway.invalid"
    metadata_timeout_seconds: float = 30.0
    server_start_timeout_seconds: float = 30.0
    import_timeout_seconds: float = 60.0 * 60.0
    terminate_grace_seconds: float = 2.0
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
    )
    @classmethod
    def _bounds_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("bounds must be positive")
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
