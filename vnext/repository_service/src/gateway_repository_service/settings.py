from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RepositoryServiceSettings(BaseSettings):
    """Settings owned exclusively by Repository Service."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GATEWAY_REPOSITORY_")

    data_root: Path = Path("runtime-data/repository")
