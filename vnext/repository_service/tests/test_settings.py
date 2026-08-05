from pathlib import Path
import logging

import pytest

from gateway_repository_service.settings import RepositoryServiceSettings, SettingsError


def test_repository_data_root_is_local_to_service() -> None:
    assert RepositoryServiceSettings().data_root.name == "repository"


def test_default_profile_is_production(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(data_root=tmp_path / "root")
    assert settings.profile == "production"


def test_env_token_without_explicit_profile_requires_production_file(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(
        data_root=tmp_path / "root",
        bearer_token="env-only-token",
    )
    with pytest.raises(SettingsError, match="production bearer token file is required"):
        settings.resolve_bearer_token()


def test_control_db_path_is_under_service_state(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(data_root=tmp_path / "root")
    assert settings.control_db_path == tmp_path / "root" / "service-state" / "repository-service.sqlite3"


def test_test_profile_requires_bearer_token(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(data_root=tmp_path / "root", profile="test")
    with pytest.raises(SettingsError):
        settings.resolve_bearer_token()


def test_settings_str_redacts_bearer_token_for_logging(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = RepositoryServiceSettings(
        data_root=tmp_path / "root",
        profile="test",
        bearer_token="logging-secret-token",
    )
    logger = logging.getLogger("test.settings.redaction")
    with caplog.at_level(logging.INFO):
        logger.info("%s", settings)
    assert "logging-secret-token" not in caplog.text
    assert "<redacted>" in caplog.text
