from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Runtime settings owned by the backend process."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_BACKEND_")

    artifact_root: Path = Path("runtime-data/artifacts")
