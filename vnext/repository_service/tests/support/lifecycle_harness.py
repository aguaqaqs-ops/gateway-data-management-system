"""Shared lifecycle test settings for repository service integration tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from gateway_repository_service.settings import RepositoryServiceSettings


def dolt_available(dolt_binary: Path | None = None) -> bool:
    candidate = dolt_binary or Path("/usr/local/bin/dolt")
    if candidate.is_file():
        return True
    return shutil.which("dolt") is not None


def lifecycle_settings(
    tmp_path: Path,
    *,
    profile: str = "test",
    bearer_token: str | None = "test-bearer-token",
    bearer_token_file: Path | None = None,
    dolt_binary: Path | None = None,
    dolt_version: str = "2.1.11",
    min_free_disk_bytes: int | None = None,
) -> RepositoryServiceSettings:
    data_root = tmp_path / "data-root"
    kwargs: dict[str, object] = {
        "profile": profile,
        "data_root": data_root,
        "bearer_token": bearer_token,
        "bearer_token_file": bearer_token_file,
        "dolt_binary": dolt_binary or Path("/usr/local/bin/dolt"),
        "dolt_version": dolt_version,
    }
    if min_free_disk_bytes is not None:
        kwargs["min_free_disk_bytes"] = min_free_disk_bytes
    return RepositoryServiceSettings(**kwargs)  # type: ignore[arg-type]
