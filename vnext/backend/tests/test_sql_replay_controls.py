"""SQL facades preserve operation control and the returned bytes owner."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.mutation_planning import render_change_set_replay
from gateway_backend.capabilities.mutation_planning import native as mutation_native
from gateway_backend.capabilities.storage_projection import (
    PACKAGE_VERSION,
    RepositoryImportArtifactInput,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext,
    NeverCancel,
    OperationMemoryBudget,
    kernel_execution_scope,
)
from tests.support.mutation_renderer_fixtures import load_closure
from tests.support.sql_replay_inputs import frozen_replay_cap_closure


@pytest.mark.parametrize("facade", ("mutation", "schema"))
def test_returned_sql_bytes_stay_charged_until_operation_scope_ends(facade: str) -> None:
    closure = load_closure("valid/patch-single-update")
    schema = RepositoryImportArtifactInput(
        package_version=PACKAGE_VERSION,
        canonicalization_manifest_digest=DigestRef("sha256:" + "11" * 32),
        tables=(),
    )
    memory = OperationMemoryBudget(8 * 1024**2)
    context = KernelExecutionContext(memory, NeverCancel(), 1)

    def render() -> bytes:
        if facade == "schema":
            return render_repository_import_schema_replay_sql(
                schema, removed_tables=("t",), context=context,
            )
        result = render_change_set_replay(closure, context=context)
        assert result.status == "READY" and result.sql_bytes is not None
        return result.sql_bytes

    with kernel_execution_scope(context, new_operation=True):
        first = render()
        first_charge = memory.used_bytes
        second = render()
        assert first == second and first
        # The same structural caller input is retained once; a second live
        # result adds precisely its bytes after temporary FFI owners close.
        assert first_charge >= len(first)
        assert memory.used_bytes - first_charge == len(second)
    assert memory.used_bytes == 0


def test_expired_sql_deadline_raises_without_retaining_output() -> None:
    memory = OperationMemoryBudget(8 * 1024**2)
    context = KernelExecutionContext(memory, NeverCancel(), 1, deadline_monotonic=0.0)
    with kernel_execution_scope(context, new_operation=True):
        with pytest.raises(TimeoutError):
            render_change_set_replay(load_closure("valid/patch-single-update"), context=context)
    assert memory.used_bytes == 0


@pytest.mark.serial
def test_sql_native_work_releases_gil_and_observes_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure = frozen_replay_cap_closure(0)
    entered, finished, progressed, cancelled = (threading.Event() for _ in range(4))
    native = mutation_native._render_change_set_native

    def observed_native(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        try:
            return native(*args, **kwargs)
        finally:
            finished.set()

    def cancel_during_native() -> None:
        if entered.wait(timeout=5):
            # Skip the Python wrapper-to-native handoff: if Rust retains the
            # GIL, this thread resumes only after observed_native marks done.
            time.sleep(0.01)
            if not finished.is_set():
                progressed.set()
                cancelled.set()

    monkeypatch.setattr(mutation_native, "_render_change_set_native", observed_native)
    memory = OperationMemoryBudget(4 * 1024**3)
    context = KernelExecutionContext(memory, cancelled, 1)
    stopper = threading.Thread(target=cancel_during_native)
    stopper.start()
    try:
        with kernel_execution_scope(context, new_operation=True):
            with pytest.raises(InterruptedError):
                render_change_set_replay(closure, context=context)
    finally:
        finished.set()
        entered.set()
        stopper.join(timeout=5)
    assert not stopper.is_alive()
    assert progressed.is_set()
    assert memory.used_bytes == 0
