"""Process initialization and the explicit per-operation deployment budget."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway_backend.settings import OperationWorkerSettings
from tests.support.runtime_settings import make_operation_worker_settings


@pytest.mark.parametrize("value", (0, -1, True, 1.5, "1.5", "", 8589934593))
def test_worker_rejects_invalid_or_excessive_kernel_budget(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValidationError):
        make_operation_worker_settings(tmp_path, kernel_memory_budget_bytes=value)


def test_worker_requires_explicit_memory_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_MEMORY_BUDGET_BYTES", raising=False)
    valid = make_operation_worker_settings(tmp_path).model_dump()
    del valid["kernel_memory_budget_bytes"]
    with pytest.raises(ValidationError, match="kernel_memory_budget_bytes"):
        OperationWorkerSettings(**valid)


@pytest.mark.parametrize("threads", (0, 257, True, 1.5))
def test_worker_rejects_invalid_kernel_threads(tmp_path: Path, threads: object) -> None:
    with pytest.raises(ValidationError):
        make_operation_worker_settings(tmp_path, kernel_threads=threads)


@pytest.mark.parametrize("threads", (1, 2))
def test_kernel_requires_initialization_and_reuses_the_fixed_process_pool(threads: int) -> None:
    # Each N has its own process; the production OnceLock is never reset.
    script = '''
from gateway_compute._native import _init_kernel_native, _parse_sql_native
from gateway_backend.capabilities.table_access.contracts import NeverCancel
try:
    _parse_sql_native(b"CREATE TABLE t (id INT);", NeverCancel())
except RuntimeError as exc:
    assert "has not been initialized" in str(exc)
else:
    raise AssertionError("uninitialized kernel accepted work")
assert _init_kernel_native(N) == N
assert _init_kernel_native(N) == N
for _ in range(2):
    assert _parse_sql_native(b"CREATE TABLE t (id INT);", NeverCancel(), None, N)["status"] == "COMPLETE"
try:
    _init_kernel_native(N + 1)
except ValueError as exc:
    assert "initialized with" in str(exc)
else:
    raise AssertionError("pool accepted conflicting N")
'''.replace("N", str(threads))
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
