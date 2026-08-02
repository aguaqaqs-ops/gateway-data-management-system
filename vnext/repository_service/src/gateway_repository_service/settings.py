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
    mysql_connector_version: str = "9.7.0"

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

    @field_validator("output_tail_bytes", "output_capture_bytes", "record_batch_rows")
    @classmethod
    def _bounds_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("bounds must be positive")
        return value

    @property
    def author(self) -> str:
        return f"{self.author_name} <{self.author_email}>"
