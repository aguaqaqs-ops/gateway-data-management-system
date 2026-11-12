"""Failure-only observations must not prevent the fixed-worker test's cleanup."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
from threading import Event

import pytest

from tests import test_fixed_workers_compose_e2e as journey
from tests.support import compose_gate_harness as harness

pytestmark = pytest.mark.unit
FINALIZER_FAULTS = ("diagnostics", "executor release", "polling resume", "project cleanup")


@pytest.mark.parametrize("primary_failure", [True, False])
@pytest.mark.parametrize("fault", FINALIZER_FAULTS)
def test_fixed_worker_finalizer_attempts_all_cleanup_and_preserves_primary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primary_failure: bool, fault: str,
) -> None:
    calls: list[str] = []
    cleanup_context: list[BaseException | None] = []
    primary = AssertionError("original worker invariant failure")
    secondary = RuntimeError("injected " + fault)
    barriers = [tmp_path / "worker-1", tmp_path / "worker-2"]
    resumed = Event()
    def record(phase: str) -> None:
        calls.append(phase)
        if phase == "project cleanup":
            cleanup_context.append(sys.exception())
        if phase == fault:
            raise secondary
    def collect() -> None:
        record("diagnostics")
    def release(path: Path, _value: str) -> None:
        calls.append(path.name)
        # Only the first release fails; the second must still be attempted.
        if fault == "executor release" and path == barriers[0].with_suffix(".release"):
            raise secondary
    monkeypatch.setattr(journey, "write_container_readable_text", release)
    # Preserve the real set method: the injected method must not call itself.
    real_set = Event.set
    def injected_resume() -> None:
        real_set(resumed)
        record("polling resume")
    monkeypatch.setattr(resumed, "set", injected_resume)
    with pytest.raises(AssertionError if primary_failure else RuntimeError) as caught:
        try:
            if primary_failure:
                raise primary
        finally:
            journey._finalize_worker_probe(collect, barriers, resumed,
                lambda: record("project cleanup"))
    assert caught.value is (primary if primary_failure else secondary)
    assert calls == ["diagnostics", "worker-1.release", "worker-2.release", "polling resume", "project cleanup"]
    assert resumed.is_set()
    assert cleanup_context == [primary if primary_failure else secondary if fault != "project cleanup" else None]
    if primary_failure:
        assert primary.__notes__ == [f"fixed-worker {fault} failed: RuntimeError: injected {fault}"]


@pytest.mark.parametrize("primary_failure", [True, False])
def test_fixed_worker_finalizer_keeps_all_errors_when_multiple_cleanup_actions_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primary_failure: bool,
) -> None:
    calls: list[str] = []
    primary = AssertionError("original worker invariant failure")
    def fail(phase: str) -> None:
        calls.append(phase)
        raise RuntimeError(phase)
    monkeypatch.setattr(journey, "write_container_readable_text", lambda path, _value: fail(path.name))
    resumed = Event()
    monkeypatch.setattr(resumed, "set", lambda: fail("resume"))
    with pytest.raises(AssertionError if primary_failure else RuntimeError) as caught:
        try:
            if primary_failure:
                raise primary
        finally:
            journey._finalize_worker_probe(lambda: fail("collector"), [tmp_path / "worker-1", tmp_path / "worker-2"],
                resumed, lambda: fail("cleanup"))
    assert calls == ["collector", "worker-1.release", "worker-2.release", "resume", "cleanup"]
    if primary_failure:
        assert caught.value is primary
    else:
        assert str(caught.value) == "collector"
    notes = caught.value.__notes__
    expected = [("executor release", "worker-1.release"), ("executor release", "worker-2.release"),
        ("polling resume", "resume"), ("project cleanup", "cleanup")]
    if primary_failure:
        expected.insert(0, ("diagnostics", "collector"))
    assert notes == [f"fixed-worker {phase} failed: RuntimeError: {message}" for phase, message in expected]


@pytest.mark.parametrize("fault", ["diagnostics", "executor release", "polling resume", None])
def test_fixed_worker_finalizer_passes_failure_context_to_existing_root_retention_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None,
) -> None:
    project = "unit-fixed-worker-retention"
    env = {"COMPOSE_PROJECT_NAME": project}
    cleanup_commands: list[list[str]] = []
    def command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--cleanup" in args:
            cleanup_commands.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(harness, "_teardown_compose_project_resources", lambda _: None)
    monkeypatch.setattr(harness, "release_compose_gate_lock", lambda: None)
    monkeypatch.setattr(subprocess, "run", command)
    monkeypatch.setitem(harness._runtime_fixtures, project, (tmp_path, "test-owner"))
    def fail_at(phase: str) -> None:
        if phase == fault:
            raise RuntimeError("injected " + phase)
    monkeypatch.setattr(journey, "write_container_readable_text", lambda _path, _text: fail_at("executor release"))
    resume = Event()
    monkeypatch.setattr(resume, "set", lambda: fail_at("polling resume"))
    with pytest.raises(RuntimeError) if fault is not None else nullcontext():
        journey._finalize_worker_probe(lambda: fail_at("diagnostics"), [tmp_path / "barrier"], resume,
            lambda: harness.cleanup_compose_project_artifacts(env))
    assert len(cleanup_commands) == 1
    assert ("--retain" in cleanup_commands[0]) is (fault is not None)
    assert project not in harness._runtime_fixtures
