"""Run cooperating filesystem/SQLite clients in distinct Linux processes."""

from __future__ import annotations

import multiprocessing
from collections.abc import Callable, Sequence


def run_processes(actions: Sequence[Callable[[], None]]) -> None:
    context = multiprocessing.get_context("fork")
    start = context.Barrier(len(actions))

    def run(action: Callable[[], None]) -> None:
        start.wait(timeout=10)
        action()

    processes = [context.Process(target=run, args=(action,)) for action in actions]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert not process.is_alive(), "cooperating process failed to finish"
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
