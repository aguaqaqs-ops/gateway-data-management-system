"""Browser owner shutdown: actual owner fixtures, no Docker, Dolt or timing budget."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.support import compose_gate_harness as harness
from tests.support import frontend_processing_groups as frontend
from tests.support import processing_groups_harness as groups

pytestmark = pytest.mark.unit
CALLER_OUTCOMES = ((0, False, False, True), (7, False, False, False), (143, False, True, False), (0, True, False, False))


def fixture_stack(root: Path, monkeypatch: pytest.MonkeyPatch) -> groups.ProcessingGroupsStack:
    root.mkdir()
    stack = groups.ProcessingGroupsStack.__new__(groups.ProcessingGroupsStack)
    stack.owner = "test-browser-owner"
    stack.runtime_roots = {}
    stack.envs = {}
    stack.entry_project = "test-browser-entry"
    stack.entry = cast(Any, SimpleNamespace(compose=lambda *args: subprocess.CompletedProcess(args, 0)))
    monkeypatch.setattr(stack, "release", lambda: None)
    original_run = groups.run
    def run(*args: str) -> str:
        if args[0] == "docker":
            return ""
        return original_run(*args)
    monkeypatch.setattr(groups, "run", run)
    monkeypatch.setattr(harness, "release_compose_gate_lock", lambda: None)
    for name in ("group-a", "group-b"):
        directory = root / name
        directory.mkdir()
        # Same on-disk owner record the fixture verifies, including real dev/ino.
        info = directory.stat()
        (directory / ".gateway-runtime-fixture-owner.json").write_text(json.dumps({"schema_version": 1,
            "owner": stack.owner, "device": info.st_dev, "inode": info.st_ino, "directory": str(directory.absolute())}))
        (directory / "diagnostic.db").write_bytes(b"retain this diagnostic state")
        (directory / "session").mkdir()
        (directory / "session/session.json").write_text('{"sessions":[{"token":"test-only-credential"}]}')
        for token_file in ("internal.token", "repository.token"):
            (directory / token_file).write_text("test-only-credential")
        stack.runtime_roots[name] = directory
    return stack


def prepare_control(root: Path, control: Path, status: object) -> None:
    control.mkdir()
    frontend.write(control / "groups-run-status.json", status)
    frontend.write(control / "groups-ready.json", {"synthetic": {"token": "test-only-credential"}, "hot": {"token": "test-only-credential"}})
    frontend.write(root / "incoming-0.json", {"token": "test-only-credential"})


def assert_sanitized(root: Path, control: Path) -> None:
    assert not list(root.glob("incoming-*.json*"))
    ready = json.loads((control / "groups-ready.json").read_text())
    assert all("token" not in ready[identity] for identity in ("synthetic", "hot"))
    for group in ("group-a", "group-b"):
        assert (root / group / "diagnostic.db").read_bytes() == b"retain this diagnostic state"
        assert json.loads((root / group / "session/session.json").read_text()) == {"sessions": []}
        for token_file in ("internal.token", "repository.token"):
            assert (root / group / token_file).read_text() == ""


@pytest.mark.parametrize("main_exit,cleanup_failed,interrupted,success", CALLER_OUTCOMES)
def test_browser_outcome_keeps_actual_roots_until_all_success_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, main_exit: int, cleanup_failed: bool, interrupted: bool, success: bool,
) -> None:
    root, control = tmp_path / "groups", tmp_path / "control"
    stack = fixture_stack(root, monkeypatch)
    prepare_control(root, control, dict(main_exit_code=main_exit, cleanup_failed=cleanup_failed, interrupted=interrupted))
    frontend.finish_stack(stack, root, control)
    assert_sanitized(root, control)
    if success:
        frontend.cleanup_retained(root, control)
        assert not any(directory.exists() for directory in stack.runtime_roots.values())
    else:
        with pytest.raises(ValueError, match="confirmed successful"):
            frontend.cleanup_retained(root, control)
        assert all(directory.exists() for directory in stack.runtime_roots.values())


@pytest.mark.parametrize("fault", ["missing status", "malformed status", "helper exception", "close exception", "credential exception"])
def test_shutdown_faults_preserve_original_error_scrub_independently_and_never_claim_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    root, control = tmp_path / "groups", tmp_path / "control"
    stack = fixture_stack(root, monkeypatch)
    prepare_control(root, control, dict(main_exit_code=0, cleanup_failed=False, interrupted=False))
    primary = RuntimeError("original browser helper failure") if fault == "helper exception" else None
    close_error = RuntimeError("original close failure")
    if fault == "missing status":
        (control / "groups-run-status.json").unlink()
    if fault == "malformed status":
        (control / "groups-run-status.json").write_text('{"main_exit_code":false}')
    if fault in ("close exception", "credential exception"):
        def down(*args: str) -> subprocess.CompletedProcess[str]:
            raise close_error
        monkeypatch.setattr(stack.entry, "compose", down)
    if fault == "credential exception":
        original_unlink = Path.unlink
        def unlink(path: Path, missing_ok: bool = False) -> None:
            if path.name == "incoming-0.json":
                raise PermissionError("injected credential removal failure")
            original_unlink(path, missing_ok=missing_ok)
        monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(BaseExceptionGroup) as caught:
        frontend.finish_stack(stack, root, control, primary_error=primary)
    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [leaf for child in error.exceptions for leaf in leaves(child)]
        return [error]
    errors = leaves(caught.value)
    if primary:
        assert primary in errors
    if fault in ("close exception", "credential exception"):
        assert close_error in errors
    if fault == "credential exception":
        assert any(isinstance(error, PermissionError) for error in errors)
        # Failure is reported, but independent ready/runtime credential revocation still ran.
        original_unlink(root / "incoming-0.json")
    assert_sanitized(root, control)
    assert not (control / "groups-stopped.json").exists()
    assert all(directory.exists() for directory in stack.runtime_roots.values())


def test_bad_owner_never_deletes_either_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, control = tmp_path / "groups", tmp_path / "control"
    stack = fixture_stack(root, monkeypatch)
    prepare_control(root, control, dict(main_exit_code=0, cleanup_failed=False, interrupted=False))
    frontend.finish_stack(stack, root, control)
    (root / "group-b/.gateway-runtime-fixture-owner.json").write_text("{}")
    with pytest.raises(AssertionError, match="another owner"):
        frontend.cleanup_retained(root, control)
    assert all(directory.exists() for directory in stack.runtime_roots.values())


def test_changed_runtime_owner_is_not_written_but_ready_still_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, control = tmp_path / "groups", tmp_path / "control"
    stack = fixture_stack(root, monkeypatch)
    prepare_control(root, control, dict(main_exit_code=0, cleanup_failed=False, interrupted=False))
    foreign = root / "group-b"
    (foreign / ".gateway-runtime-fixture-owner.json").write_text("{}")
    original_credentials = {name: (foreign / name).read_bytes() for name in ("session/session.json", "internal.token", "repository.token")}
    with pytest.raises(BaseExceptionGroup):
        frontend.finish_stack(stack, root, control)
    assert all((foreign / name).read_bytes() == value for name, value in original_credentials.items())
    assert not (root / "incoming-0.json").exists()
    ready = json.loads((control / "groups-ready.json").read_text())
    assert all("token" not in ready[identity] for identity in ("synthetic", "hot"))
    assert not (control / "groups-stopped.json").exists()


@pytest.mark.parametrize("temporary_cleanup_failures", [0, 1, -1], ids=["publisher-removes-temp", "independent-scrub-removes-temp", "temp-removal-error-reported"])
def test_first_ready_publication_failure_retains_roots_and_sanitizes_exact_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, temporary_cleanup_failures: int,
) -> None:
    root, control = tmp_path / "groups", tmp_path / "control"
    stack = fixture_stack(root, monkeypatch)
    control.mkdir()
    frontend.write(control / "groups-run-status.json", dict(main_exit_code=0, cleanup_failed=False, interrupted=False))
    frontend.write(root / "incoming-0.json", {"token": "test-only-credential"})
    ready = control / "groups-ready.json"
    temporary = control / "groups-ready.json.tmp"
    replace_error = OSError("injected first ready replace failure")
    unlink_error = PermissionError("injected exact ready temporary removal failure")
    original_replace, original_unlink = Path.replace, Path.unlink
    observed_temporary = False
    unlink_attempts = 0

    def replace(path: Path, target: str | Path) -> Path:
        nonlocal observed_temporary
        if path == temporary and not observed_temporary:
            assert target == ready and not ready.exists()
            document = json.loads(temporary.read_text())
            assert all("token" in document[name] for name in ("synthetic", "hot"))
            observed_temporary = True
            raise replace_error
        return original_replace(path, target)

    def unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal unlink_attempts
        if path == temporary:
            unlink_attempts += 1
            if temporary_cleanup_failures == -1 or unlink_attempts <= temporary_cleanup_failures:
                raise unlink_error
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises((OSError, ExceptionGroup)) as publication:
        frontend.write(ready, {"synthetic": {"token": "test-only-credential"}, "hot": {"token": "test-only-credential"}})
    assert observed_temporary and not ready.exists()
    assert temporary.exists() is (temporary_cleanup_failures != 0)
    with pytest.raises(BaseExceptionGroup) as shutdown:
        frontend.finish_stack(stack, root, control, primary_error=publication.value)
    assert shutdown.value.subgroup(lambda error: error is replace_error) is not None
    if temporary_cleanup_failures:
        assert shutdown.value.subgroup(lambda error: error is unlink_error) is not None
    assert not ready.exists()
    assert temporary.exists() is (temporary_cleanup_failures == -1)
    assert not (control / "groups-stopped.json").exists()
    assert not (root / "incoming-0.json").exists()
    assert all((directory / "diagnostic.db").is_file() for directory in stack.runtime_roots.values())
    assert all((directory / name).read_text() == "" for directory in stack.runtime_roots.values() for name in ("internal.token", "repository.token"))
    assert all(json.loads((directory / "session/session.json").read_text()) == {"sessions": []} for directory in stack.runtime_roots.values())
    # Only the exact credential document may be removed; other evidence remains.
    print("first_ready_replace_failure=" + json.dumps(dict(temporary_observed_before_replace=observed_temporary,
        ready_absent=True, temporary_absent=not temporary.exists(), temporary_removal_error_reported=bool(temporary_cleanup_failures),
        original_replace_error_preserved=True, stopped_absent=True, diagnostic_roots_retained=True)))
    if temporary_cleanup_failures == -1:
        # Test teardown only: remove its synthetic credential after proving that
        # the real cleanup reported failure. Do not leave probe secrets in evidence.
        original_unlink(temporary)
