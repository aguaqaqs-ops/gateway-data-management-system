"""Configured-root absence, nested mounts and metadata file ownership boundaries."""
from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from gateway_repository_service import artifact_layout
from gateway_repository_service.control_db import ControlStore
from gateway_repository_service.layout import DurableLayout, LayoutError
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.storage_roots import RepositoryRoots
from support.lifecycle_harness import prepare_test_roots
from support.storage_layout import write_storage_layout


@pytest.mark.parametrize("missing", ["repository", "artifacts", "metadata", "scratch"])
def test_production_missing_root_fails_before_database_open_and_creates_no_replacement(
    tmp_path: Path, missing: str,
) -> None:
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "roots"))
    target = getattr(roots, missing)
    target.rmdir()
    token = tmp_path / "token"
    token.write_text("test-token")
    settings = RepositoryServiceSettings(profile="production", bearer_token_file=token, roots=roots)
    with patch.object(ControlStore, "open") as opened:
        with pytest.raises(ServiceStartupError, match="configured RS root is unavailable"):
            ServiceRuntime.start(settings)
        opened.assert_not_called()
    assert not target.exists()
    assert all(not list(root.iterdir()) for root in roots.paths() if root != target)
    assert not settings.control_db_path.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_control_database_or_journal_symlink_is_rejected_before_open(
    tmp_path: Path, suffix: str,
) -> None:
    layout = DurableLayout.create_for_probe(tmp_path / "roots")
    settings = RepositoryServiceSettings(profile="test", bearer_token="token", roots=layout.roots)
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"outside-metadata")
    target = Path(f"{settings.control_db_path}{suffix}")
    target.symlink_to(sentinel)
    with patch.object(ControlStore, "open") as opened:
        with pytest.raises(ServiceStartupError, match="control database metadata path"):
            ServiceRuntime.start(settings)
        opened.assert_not_called()
    assert sentinel.read_bytes() == b"outside-metadata"
    assert target.is_symlink()
    assert not settings.control_db_path.exists() if suffix else settings.control_db_path.is_symlink()


@pytest.mark.integration
@pytest.mark.serial
def test_nested_mount_is_rejected_before_creation_or_permission_changes(tmp_path: Path) -> None:
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "roots"))
    nested = roots.repository / ".staging"
    nested.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep"
    sentinel.write_bytes(b"unchanged")
    before = outside.stat()
    layout_file = write_storage_layout(roots)
    subprocess.run(["mount", "--bind", str(outside), str(nested)], check=True, capture_output=True)
    try:
        with (
            patch("os.mkdir", side_effect=AssertionError("directory creation before validation")) as mkdir,
            patch.object(artifact_layout, "_fchown_chmod",
                side_effect=AssertionError("permission mutation before validation")) as permissions,
        ):
            with pytest.raises(LayoutError, match="unavailable or redirected"):
                DurableLayout.create_service(roots)
            assert artifact_layout.main(["--storage-layout-file", str(layout_file),
                "--gateway-user", pwd.getpwuid(os.getuid()).pw_name]) == 1
            mkdir.assert_not_called()
            permissions.assert_not_called()
        assert list(outside.iterdir()) == [sentinel]
        assert sentinel.read_bytes() == b"unchanged"
        after = outside.stat()
        assert (after.st_uid, after.st_gid, after.st_mode) == (before.st_uid, before.st_gid, before.st_mode)
    finally:
        subprocess.run(["umount", str(nested)], check=True, capture_output=True)
