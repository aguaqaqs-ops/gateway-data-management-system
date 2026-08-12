from pathlib import Path
import logging

import pytest

from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION
from gateway_repository_service.runtime import ServiceRuntime
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
    assert settings.max_manifest_json_bytes == 16 * 1024 * 1024
    assert settings.max_replay_sql_bytes == 200 * 1024 * 1024
    assert settings.max_total_expanded_entry_bytes == 4 * 1024 * 1024 * 1024
    assert settings.max_decompressed_tar_stream_bytes == 4 * 1024 * 1024 * 1024
    assert settings.artifact_ttl_seconds == 24 * 60 * 60
    assert settings.artifact_cleanup_interval_seconds == 300
    assert settings.max_concurrent_uploads == 8
    assert settings.max_import_workers == 4
    assert settings.max_queued_imports == 64
    assert settings.max_concurrent_row_streams == 8
    assert settings.full_scan_timeout_seconds == 3600
    assert settings.min_free_disk_bytes == 5 * 1024 * 1024 * 1024
    assert settings.min_free_disk_fraction == 0.10
    assert settings.import_headroom_bytes == 1 * 1024**3


@pytest.mark.parametrize(
    "field",
    [
        "max_import_workers",
        "max_queued_imports",
        "artifact_cleanup_interval_seconds",
        "max_concurrent_uploads",
        "max_concurrent_row_streams",
        "full_scan_timeout_seconds",
    ],
)
def test_max_import_workers_rejects_zero(tmp_path: Path, field: str) -> None:
    kwargs: dict[str, int] = {field: 0}
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    [
        "artifact_cleanup_interval_seconds",
        "max_concurrent_uploads",
        "max_concurrent_row_streams",
        "full_scan_timeout_seconds",
    ],
)
def test_operational_bounds_reject_negative(tmp_path: Path, field: str) -> None:
    kwargs: dict[str, int] = {field: -1}
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", **kwargs)  # type: ignore[arg-type]


def test_control_db_user_version_is_not_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_REPOSITORY_CONTROL_DB_USER_VERSION", "1")
    settings = RepositoryServiceSettings(data_root=tmp_path / "root", profile="test", bearer_token="token")
    assert not hasattr(settings, "control_db_user_version")
    assert CONTROL_DB_USER_VERSION == 9


@pytest.mark.parametrize(
    "field",
    [
        "max_upload_bytes",
        "max_manifest_json_bytes",
        "max_replay_sql_bytes",
        "max_total_expanded_entry_bytes",
        "max_decompressed_tar_stream_bytes",
        "artifact_ttl_seconds",
        "import_headroom_bytes",
    ],
)
def test_positive_bounds_reject_zero(tmp_path: Path, field: str) -> None:
    kwargs: dict[str, int] = {field: 0}
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", **kwargs)  # type: ignore[arg-type]


def test_import_headroom_bytes_rejects_non_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", import_headroom_bytes=-1)
    with pytest.raises(ValueError):
        RepositoryServiceSettings(data_root=tmp_path / "root", import_headroom_bytes=0)


def test_import_queue_settings_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_REPOSITORY_MAX_QUEUED_IMPORTS", "32")
    monkeypatch.setenv("GATEWAY_REPOSITORY_IMPORT_HEADROOM_BYTES", "2048")
    settings = RepositoryServiceSettings(data_root=tmp_path / "root")
    assert settings.max_queued_imports == 32
    assert settings.import_headroom_bytes == 2048


def test_operational_admission_settings_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_CLEANUP_INTERVAL_SECONDS", "120")
    monkeypatch.setenv("GATEWAY_REPOSITORY_MAX_CONCURRENT_UPLOADS", "3")
    monkeypatch.setenv("GATEWAY_REPOSITORY_MAX_CONCURRENT_ROW_STREAMS", "2")
    monkeypatch.setenv("GATEWAY_REPOSITORY_FULL_SCAN_TIMEOUT_SECONDS", "900")
    settings = RepositoryServiceSettings(data_root=tmp_path / "root")
    assert settings.artifact_cleanup_interval_seconds == 120
    assert settings.max_concurrent_uploads == 3
    assert settings.max_concurrent_row_streams == 2
    assert settings.full_scan_timeout_seconds == 900


@pytest.mark.integration
def test_runtime_uses_code_control_db_user_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_REPOSITORY_CONTROL_DB_USER_VERSION", "1")
    settings = RepositoryServiceSettings(
        data_root=tmp_path / "root",
        profile="test",
        bearer_token="token",
        dolt_binary=Path("/usr/local/bin/dolt"),
    )
    runtime = ServiceRuntime.start(settings)
    try:
        version = runtime.control_store.connection.execute("PRAGMA user_version").fetchone()
        assert int(version[0]) == CONTROL_DB_USER_VERSION
    finally:
        runtime.shutdown()
