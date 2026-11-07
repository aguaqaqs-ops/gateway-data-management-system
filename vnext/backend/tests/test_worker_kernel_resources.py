"""Process initialization and the explicit per-operation deployment budget."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway_backend.settings import OperationWorkerSettings
from tests.support.runtime_settings import make_operation_worker_settings


@pytest.mark.parametrize("value", (0, -1, True, 1.5, "1.5", "", 25769803777))
def test_worker_rejects_invalid_or_excessive_kernel_budget(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValidationError):
        make_operation_worker_settings(tmp_path, kernel_memory_budget_bytes=value)


def test_worker_deployment_profile_has_explicit_budget_and_one_active_operation(tmp_path: Path) -> None:
    settings = make_operation_worker_settings(tmp_path, kernel_memory_budget_bytes=24 * 1024**3)
    assert settings.memory_envelope_bytes == 32 * 1024**3
    assert settings.memory_reserve_bytes == 8 * 1024**3
    assert settings.kernel_memory_budget_bytes == 24 * 1024**3
    assert settings.kernel_threads == 1
    assert settings.max_in_flight == settings.claim_limit == 1


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


@pytest.mark.integration
@pytest.mark.parametrize("threads", (1, 2))
def test_kernel_requires_initialization_and_reuses_the_fixed_process_pool(threads: int) -> None:
    # Each N has its own process; the production OnceLock is never reset.
    script = '''
import pyarrow as pa
from gateway_compute._native import _init_kernel_native, _inspect_canonical_ipc_native, _parse_sql_native
from gateway_backend.capabilities.table_access.contracts import NeverCancel
try:
    _parse_sql_native(b"CREATE TABLE t (id INT);", NeverCancel())
except RuntimeError as exc:
    assert "has not been initialized" in str(exc)
else:
    raise AssertionError("uninitialized kernel accepted work")
try:
    _inspect_canonical_ipc_native([], pa.RecordBatchReader.from_batches(pa.schema([]), []), NeverCancel(), {})
except RuntimeError as exc:
    assert "has not been initialized" in str(exc)
else:
    raise AssertionError("uninitialized inspect accepted work")
assert _init_kernel_native(__THREADS__) == __THREADS__
assert _parse_sql_native(b"CREATE TABLE t (id INT);", NeverCancel())["status"] == "COMPLETE"
assert _init_kernel_native(__THREADS__) == __THREADS__
for _ in range(2):
    assert _parse_sql_native(b"CREATE TABLE t (id INT);", NeverCancel(), None, __THREADS__)["status"] == "COMPLETE"
try:
    _init_kernel_native(__THREADS__ + 1)
except ValueError as exc:
    assert "initialized with" in str(exc)
else:
    raise AssertionError("pool accepted conflicting N")
'''.replace("__THREADS__", str(threads))
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False, timeout=15)
    assert completed.returncode == 0, completed.stdout + completed.stderr
