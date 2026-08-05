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


def test_default_upload_and_ttl_settings() -> None:
    settings = RepositoryServiceSettings()
    assert settings.max_upload_bytes == 256 * 1024 * 1024
    assert settings.artifact_ttl_seconds == 24 * 60 * 60
    assert settings.control_db_user_version == 2


@pytest.mark.parametrize("field", ["max_upload_bytes", "artifact_ttl_seconds", "control_db_user_version"])
def test_positive_bounds_reject_zero(tmp_path: Path, field: str) -> None:
    kwargs: dict[str, int] = {field: 0}
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", **kwargs)  # type: ignore[arg-type]
