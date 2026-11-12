"""Deterministic optional-sidecar disappearance at the real O_PATH boundary.

These are target-semantics assertions, not expected-failure annotations. The
unfixed implementation may fail the optional-sidecar cases; preserve that result.
No SQLite connection, worker process, Docker or Dolt is used.
"""
from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from gateway_backend import runtime_preflight
from gateway_backend.deployment_config import DeploymentConfig
from tests.support.artifact_layout import write_deployment_files

pytestmark = pytest.mark.unit
SIDECARS = ("control.sqlite3-wal", "control.sqlite3-shm", "control.sqlite3-journal")
LAYERS = ("check", "guard")


def _observer(tmp_path: Path, layer: str) -> tuple[Path, Callable[[], None]]:
    if layer == "check":
        metadata = tmp_path / "metadata"
        metadata.mkdir()
        (metadata / "control.sqlite3").write_bytes(b"ordinary-main-database")
        def observe_files() -> None:
            runtime_preflight.check_database_files(metadata)
        return metadata, observe_files
    storage, resources = write_deployment_files(tmp_path / "roots")
    config = DeploymentConfig.load(storage, resources)
    metadata = Path(config.storage.roots["be-metadata"].path)
    # Ordinary placeholder: this owner checks filesystem identity, never opens
    # a business transaction or validates a SQLite database schema.
    (metadata / "control.sqlite3").write_bytes(b"ordinary-main-database")
    guard = runtime_preflight.RuntimePreflight(config, "worker", container=False)
    return metadata, guard.check


def _delete_at_path_open(monkeypatch: pytest.MonkeyPatch, target: Path, observations: list[dict[str, Any]]) -> None:
    original_open = os.open
    def delete_then_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if Path(path) == target and flags & os.O_PATH and not observations:
            observed = target.lstat()
            record: dict[str, Any] = {"file": target.name, "flags": flags,
                "observed_inode_before_unlink": observed.st_ino}
            observations.append(record)
            target.unlink()
            try:
                return original_open(path, flags, *args, **kwargs)
            except OSError as error:
                record["real_open_errno"] = error.errno
                raise
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", delete_then_open)


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("name", SIDECARS)
def test_optional_database_sidecar_disappearance_keeps_identity_check_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str, name: str,
) -> None:
    metadata, observe = _observer(tmp_path, layer)
    database = metadata / "control.sqlite3"
    before = database.stat()
    content = database.read_bytes()
    target = metadata / name
    target.write_bytes(b"optional-sidecar")
    observations: list[dict[str, Any]] = []
    _delete_at_path_open(monkeypatch, target, observations)
    result = "returned"
    try:
        # A genuine optional-file ENOENT must not make the unchanged main DB
        # unavailable. Do not swallow/xfail the pre-fix exception to make this green.
        observe()
    except Exception as error:
        result = type(error).__name__ + ": " + str(error)
        raise
    finally:
        after = database.stat()
        unchanged = (before.st_dev, before.st_ino, content) == (after.st_dev, after.st_ino, database.read_bytes())
        print(json.dumps({"layer": layer, "owner_module": runtime_preflight.__file__, "target": name, "result": result, "injection": observations,
            "main_unchanged": unchanged, "main_sha256": hashlib.sha256(content).hexdigest()}, sort_keys=True))
        assert len(observations) == 1
        assert observations[0]["real_open_errno"] == 2
        assert unchanged
        assert not target.exists()


@pytest.mark.parametrize("layer", LAYERS)
def test_observed_main_database_disappearance_still_refuses_identity_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str,
) -> None:
    metadata, observe = _observer(tmp_path, layer)
    database = metadata / "control.sqlite3"
    observations: list[dict[str, Any]] = []
    _delete_at_path_open(monkeypatch, database, observations)
    with pytest.raises((OSError, ValueError)) as caught:
        observe()
    print(json.dumps({"layer": layer, "owner_module": runtime_preflight.__file__, "target": database.name, "result": type(caught.value).__name__,
        "injection": observations, "main_absent": not database.exists()}, sort_keys=True))
    assert len(observations) == 1
    assert observations[0]["real_open_errno"] == 2
    assert not database.exists()


OWNER_CHANGE_FAULTS = (
    "main-deleted", "main-replaced", "main-symlink", "main-permission", "main-mount",
    "metadata-missing", "metadata-replaced", "metadata-symlink", "sidecar-eacces", "sidecar-eio", "sidecar-eloop",
)


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("fault", OWNER_CHANGE_FAULTS)
def test_optional_disappearance_does_not_hide_owner_changes_or_other_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: str, fault: str,
) -> None:
    import errno

    metadata, observe = _observer(tmp_path, layer)
    database = metadata / "control.sqlite3"
    target = metadata / "control.sqlite3-wal"
    target.write_bytes(b"optional-sidecar")
    replacement = tmp_path / "replacement-main"
    replacement.write_bytes(b"different-main")
    original_open, original_access = os.open, os.access
    original_bounded = runtime_preflight._bounded
    injected = False
    permission_checks: list[bool] = []
    def change_then_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        nonlocal injected
        if Path(path) == target and flags & os.O_PATH and not injected:
            injected = True
            if fault.startswith("sidecar-"):
                failure = {"sidecar-eacces": errno.EACCES, "sidecar-eio": errno.EIO, "sidecar-eloop": errno.ELOOP}[fault]
                raise OSError(failure, "injected O_PATH refusal", str(target))
            target.unlink()
            if fault == "main-deleted":
                database.unlink()
            elif fault == "main-replaced":
                os.replace(replacement, database)
            elif fault == "main-symlink":
                database.unlink()
                database.symlink_to(replacement)
            elif fault.startswith("metadata-"):
                displaced = tmp_path / "displaced-metadata"
                metadata.rename(displaced)
                if fault == "metadata-replaced":
                    metadata.mkdir()
                    # Keep the main inode identical: the directory identity must
                    # independently reject the replacement, not merely the file.
                    os.link(displaced / "control.sqlite3", database)
                elif fault == "metadata-symlink":
                    metadata.symlink_to(displaced, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)
    def deny_changed_main(path: Any, mode: int, **kwargs: Any) -> bool:
        if fault == "main-permission" and injected and str(path).startswith("/proc/self/fd/"):
            permission_checks.append(mode == os.R_OK and kwargs.get("effective_ids") is True)
            return False
        return original_access(path, mode, **kwargs)
    def changed_mount(path: Path, limit: int) -> str:
        if fault == "main-mount" and injected and path.parent == Path("/proc/self/fdinfo"):
            # Keep file and directory mutually consistent but change the mount
            # from the one that owned the previously validated main database.
            return "mnt_id: changed-owner-mount"
        return original_bounded(path, limit)
    monkeypatch.setattr(runtime_preflight, "_bounded", changed_mount)
    monkeypatch.setattr(os, "open", change_then_open)
    monkeypatch.setattr(os, "access", deny_changed_main)
    with pytest.raises((OSError, ValueError)) as caught:
        observe()
    assert injected
    if fault == "main-permission":
        assert permission_checks == [True]
    if fault == "main-replaced":
        assert not replacement.exists()
    else:
        assert replacement.read_bytes() == b"different-main"
    print(json.dumps({"layer": layer, "fault": fault, "result": type(caught.value).__name__}, sort_keys=True))
