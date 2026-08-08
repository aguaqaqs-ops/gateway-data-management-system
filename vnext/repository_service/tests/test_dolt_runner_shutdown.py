"""Directed tests for DoltRunner shutdown kill/reap behavior."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from support.lifecycle_harness import lifecycle_settings

pytestmark = pytest.mark.integration


@pytest.mark.serial
def test_terminate_and_reap_sends_term_then_kill(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    runner = DoltRunner(settings, layout.root)
    signals: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 4242
        returncode: int | None = None

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd="dolt", timeout=timeout)
            self.returncode = -9
            return -9

    process = FakeProcess()
    runner._active_children.register(process)  # type: ignore[arg-type]

    with patch("gateway_repository_service.process.os.killpg", side_effect=lambda pid, sig: signals.append((pid, sig))):
        runner.reap_adopted_dolt_children = lambda: None  # type: ignore[method-assign]
        runner.terminate_and_reap(process, grace_seconds=0.01)  # type: ignore[arg-type]

    assert (4242, signal.SIGTERM) in signals
    assert (4242, signal.SIGKILL) in signals
    assert runner._active_children.snapshot() == ()


@pytest.mark.serial
def test_terminate_active_children_reaps_all_registered(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    runner = DoltRunner(settings, layout.root)
    reaped: list[int] = []

    def _terminate_and_reap(process: object, *, grace_seconds: float | None = None) -> None:
        del grace_seconds
        reaped.append(getattr(process, "pid"))
        runner._active_children.unregister(process)  # type: ignore[arg-type]

    runner.terminate_and_reap = _terminate_and_reap  # type: ignore[method-assign]

    class FakeProcess:
        __slots__ = ("pid",)

        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self) -> None:
            return None

        def __hash__(self) -> int:
            return self.pid

        def __eq__(self, other: object) -> bool:
            return isinstance(other, FakeProcess) and other.pid == self.pid

    runner._active_children.register(FakeProcess(1))  # type: ignore[arg-type]
    runner._active_children.register(FakeProcess(2))  # type: ignore[arg-type]

    runner.terminate_active_children(grace_seconds=0.01)

    assert sorted(reaped) == [1, 2]
    assert runner._active_children.snapshot() == ()
