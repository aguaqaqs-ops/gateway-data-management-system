"""Unit and serial tests for the bounded Arrow IPC bridge."""

from __future__ import annotations

import asyncio
import io
import signal
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from support.arrow_ipc_assertions import (
    assert_has_stream_eos,
    assert_lacks_stream_eos,
    count_decoded_rows_without_error,
)
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog, compile_table_plan
from gateway_repository_service.versioned_read.arrow_bridge import (
    BRIDGE_REGISTRY,
    ArrowIpcStreamBridge,
    BridgeJoinTimeoutError,
    BridgeShutdownError,
    BridgeStreamAbortedError,
    _POLL_TIMEOUT_SECONDS,
)

pytestmark = pytest.mark.unit


def _plan_and_batches(batch_count: int, rows_per_batch: int) -> tuple[Any, list[pa.RecordBatch]]:
    table = TableCatalog(
        "items",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=batch_count * rows_per_batch,
    )
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    batches: list[pa.RecordBatch] = []
    value = 0
    for _ in range(batch_count):
        normalized = []
        for _ in range(rows_per_batch):
            value += 1
            normalized.append(plan.normalize_row((value,)))
        batches.append(plan.record_batch(normalized))
    return plan, batches


def _wait_until(condition: Any, *, timeout_seconds: float = 2.0, message: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def _force_unregister_bridge(
    bridge: ArrowIpcStreamBridge,
    *,
    release: threading.Event | None = None,
) -> None:
    if release is not None:
        release.set()
    bridge._worker.join(timeout=5.0)
    try:
        if bridge in BRIDGE_REGISTRY.snapshot():
            bridge.close_sync(join_timeout_seconds=5.0)
    except BridgeJoinTimeoutError:
        pass
    BRIDGE_REGISTRY.unregister(bridge)


@pytest.fixture(autouse=True)
def _reset_bridge_test_hooks() -> Iterator[None]:
    ArrowIpcStreamBridge._test_worker_finish_barrier = None
    ArrowIpcStreamBridge._test_close_entered_barrier = None
    ArrowIpcStreamBridge._test_close_completed_barrier = None
    ArrowIpcStreamBridge._test_unregister_barrier = None
    yield
    for bridge in BRIDGE_REGISTRY.snapshot():
        _force_unregister_bridge(bridge)


def test_arrow_bridge_sink_peak_stays_bounded_across_many_batches() -> None:
    peak_sizes: list[int] = []

    class TrackingBytesIO(io.BytesIO):
        def getvalue(self) -> bytes:
            value = super().getvalue()
            peak_sizes.append(len(value))
            return value

    with patch(
        "gateway_repository_service.versioned_read.arrow_bridge.io.BytesIO",
        TrackingBytesIO,
    ):
        plan, batches = _plan_and_batches(batch_count=20, rows_per_batch=64)
        cancellation = threading.Event()

        def rows() -> Iterator[pa.RecordBatch]:
            yield from batches

        bridge = ArrowIpcStreamBridge(plan, rows(), cancellation)

        async def consume() -> int:
            total = 0
            async for chunk in bridge.iter_bytes():
                total += len(chunk)
            return total

        total_bytes = asyncio.run(consume())
    assert total_bytes > 0
    assert peak_sizes
    single_batch_peak = max(peak_sizes[:3])
    assert max(peak_sizes) <= single_batch_peak * 2


@pytest.mark.serial
def test_arrow_bridge_backpressure_blocks_producer_until_consumer_reads() -> None:
    plan, batches = _plan_and_batches(batch_count=3, rows_per_batch=64)
    cancellation = threading.Event()
    batches_yielded = 0
    third_batch_requested = threading.Event()

    def tracked_batches() -> Iterator[pa.RecordBatch]:
        nonlocal batches_yielded
        for index, batch in enumerate(batches):
            batches_yielded = index + 1
            if index == 2:
                third_batch_requested.set()
            yield batch

    bridge = ArrowIpcStreamBridge(plan, tracked_batches(), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before consumer started",
    )
    assert batches_yielded <= 2
    assert not third_batch_requested.is_set()

    async def consume() -> int:
        total = 0
        async for chunk in bridge.iter_bytes():
            total += len(chunk)
        return total

    total_bytes = asyncio.run(consume())
    assert total_bytes > 0
    assert third_batch_requested.is_set()
    assert bridge._terminal_outcome == "success"

    async def collect_all() -> bytes:
        chunks: list[bytes] = []
        plan2, batches2 = _plan_and_batches(batch_count=3, rows_per_batch=64)
        bridge2 = ArrowIpcStreamBridge(plan2, iter(batches2), threading.Event())
        async for chunk in bridge2.iter_bytes():
            chunks.append(chunk)
        return b"".join(chunks)

    success_body = asyncio.run(collect_all())
    assert_has_stream_eos(success_body)


def test_arrow_bridge_worker_failure_aborts_consumer() -> None:
    plan, batches = _plan_and_batches(batch_count=2, rows_per_batch=1)

    def failing_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        raise RuntimeError("conversion failed")

    bridge = ArrowIpcStreamBridge(plan, failing_rows(), threading.Event())
    collected: list[bytes] = []

    async def consume() -> None:
        async for chunk in bridge.iter_bytes():
            collected.append(chunk)

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())
    body = b"".join(collected)
    assert body
    assert_lacks_stream_eos(body)
    assert bridge._terminal_outcome == "failure"
    assert count_decoded_rows_without_error(body) == 1


@pytest.mark.serial
def test_arrow_bridge_eos_enqueue_cancel_preserves_failure_terminal() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=128)
    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before EOS cancellation",
    )

    bridge.close_sync()
    assert bridge._terminal_outcome == "failure"

    async def consume() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return chunks

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())


def test_arrow_bridge_empty_stream_has_eos() -> None:
    table = TableCatalog("items", (ColumnCatalog("id", "BIGINT", False, 1),), 0)
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    bridge = ArrowIpcStreamBridge(plan, iter(()), threading.Event())

    async def consume() -> bytes:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return b"".join(chunks)

    body = asyncio.run(consume())
    assert_has_stream_eos(body)
    assert bridge._terminal_outcome == "success"


@pytest.mark.serial
def test_arrow_bridge_queue_full_cancel_preserves_failure_terminal() -> None:
    plan, batches = _plan_and_batches(batch_count=2, rows_per_batch=64)
    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before cancellation",
    )

    bridge.close_sync()
    assert bridge._terminal_outcome == "failure"

    async def consume() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return chunks

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())


@pytest.mark.serial
def test_arrow_bridge_close_sync_is_idempotent_for_concurrent_callers() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), threading.Event())
    errors: list[BaseException] = []

    def close_once() -> None:
        try:
            bridge.close_sync()
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=close_once)
    second = threading.Thread(target=close_once)
    first.start()
    second.start()
    release.set()
    first.join(timeout=5.0)
    second.join(timeout=5.0)
    assert not errors
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_close_sync_join_runs_outside_worker_condition_lock() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    finish_worker_entered = threading.Event()
    finish_worker_can_complete = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), threading.Event())
    original_finish_worker = bridge._finish_worker

    def delayed_finish_worker(*, completed: bool) -> None:
        finish_worker_entered.set()
        assert finish_worker_can_complete.wait(timeout=2.0)
        original_finish_worker(completed=completed)

    bridge._finish_worker = delayed_finish_worker  # type: ignore[method-assign]

    async def consume() -> None:
        async for _chunk in bridge.iter_bytes():
            pass

    consumer = threading.Thread(target=lambda: asyncio.run(consume()))
    consumer.start()
    assert finish_worker_entered.wait(timeout=2.0)
    assert consumer.is_alive()
    assert not bridge._worker_joined
    finish_worker_can_complete.set()
    consumer.join(timeout=5.0)
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_close_sync_join_timeout_terminates_only_bridge_owned_children() -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.process import ActiveChildRegistry

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    producer_blocked = threading.Event()
    import_owner = object()
    bridge_owner = object()
    pre_existing = MagicMock()
    pre_existing.pid = 100
    pre_existing.poll.return_value = None
    bridge_owned = MagicMock()
    bridge_owned.pid = 200
    bridge_owned.poll.return_value = None
    concurrent_owned = MagicMock()
    concurrent_owned.pid = 300
    concurrent_owned.poll.return_value = None

    registry = ActiveChildRegistry()
    registry.register(pre_existing, owner=import_owner)
    registry.register(concurrent_owned, owner=import_owner)

    runner = MagicMock()
    runner._active_children = registry
    runner.settings.terminate_grace_seconds = 0.01
    terminated: list[int] = []

    def terminate_and_reap(process: MagicMock, *, grace_seconds: float) -> None:
        del grace_seconds
        terminated.append(process.pid)
        process.poll.return_value = 0

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else runner.settings.terminate_grace_seconds
        for process in registry.snapshot_for_owner(owner):
            if process.poll() is None:
                terminate_and_reap(process, grace_seconds=grace)  # type: ignore[arg-type]

    runner.terminate_and_reap.side_effect = terminate_and_reap
    runner.terminate_owned = terminate_owned

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_blocked.set()
        release.wait()

    bridge = ArrowIpcStreamBridge(
        plan,
        gated_rows(),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )
    registry.register(bridge_owned, owner=bridge_owner)
    errors: list[BaseException] = []

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")

    def close_in_thread() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.05)
        except BaseException as exc:
            errors.append(exc)

    closer = threading.Thread(target=close_in_thread)
    closer.start()
    closer.join(timeout=5.0)
    assert len(errors) == 1
    assert isinstance(errors[0], BridgeJoinTimeoutError)
    assert terminated == [200]
    assert 100 not in terminated
    assert 300 not in terminated
    release.set()
    drainer.join(timeout=2.0)
    bridge._worker.join(timeout=5.0)


@pytest.mark.serial
def test_close_sync_does_not_close_iterator_from_close_thread() -> None:
    from unittest.mock import MagicMock

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    producer_blocked = threading.Event()
    unblock_producer = threading.Event()
    bridge_owner = object()
    close_calls = 0

    class BlockingIterator:
        def __init__(self, batch: pa.RecordBatch) -> None:
            self._batch = batch
            self._yielded = False

        def __iter__(self) -> BlockingIterator:
            return self

        def __next__(self) -> pa.RecordBatch:
            if not self._yielded:
                self._yielded = True
                return self._batch
            producer_blocked.set()
            unblock_producer.wait()
            raise StopIteration

        def close(self) -> None:
            nonlocal close_calls
            if threading.current_thread().name != "versioned-read-arrow-bridge":
                raise RuntimeError("iterator close from non-worker thread")
            close_calls += 1

    runner = MagicMock()
    runner.settings.terminate_grace_seconds = 0.01

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        del owner, grace_seconds
        unblock_producer.set()

    runner.terminate_owned = terminate_owned

    bridge = ArrowIpcStreamBridge(
        plan,
        BlockingIterator(batches[0]),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")
    bridge.close_sync(join_timeout_seconds=1.0)
    drainer.join(timeout=2.0)
    assert close_calls == 1
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_close_sync_concurrent_timeout_escalates_once() -> None:
    from unittest.mock import MagicMock

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    producer_blocked = threading.Event()
    bridge_owner = object()
    terminate_owned_calls = 0
    terminate_owned_lock = threading.Lock()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_blocked.set()
        release.wait()

    runner = MagicMock()
    runner.settings.terminate_grace_seconds = 0.01

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        del owner, grace_seconds
        nonlocal terminate_owned_calls
        with terminate_owned_lock:
            terminate_owned_calls += 1

    runner.terminate_owned = terminate_owned

    bridge = ArrowIpcStreamBridge(
        plan,
        gated_rows(),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )
    errors: list[BaseException] = []

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")

    def close_in_thread() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.1)
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=close_in_thread)
    second = threading.Thread(target=close_in_thread)
    try:
        first.start()
        second.start()
        first.join(timeout=5.0)
        second.join(timeout=5.0)
        assert terminate_owned_calls == 1
        assert len(errors) == 2
        assert all(isinstance(exc, BridgeJoinTimeoutError) for exc in errors)
    finally:
        release.set()
        drainer.join(timeout=2.0)
        bridge._worker.join(timeout=5.0)


@pytest.mark.serial
def test_close_sync_terminate_owned_failure_still_joins_worker() -> None:
    from unittest.mock import MagicMock

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    producer_blocked = threading.Event()
    unblock_producer = threading.Event()
    bridge_owner = object()

    class BlockingIterator:
        def __init__(self, batch: pa.RecordBatch) -> None:
            self._batch = batch
            self._yielded = False

        def __iter__(self) -> BlockingIterator:
            return self

        def __next__(self) -> pa.RecordBatch:
            if not self._yielded:
                self._yielded = True
                return self._batch
            producer_blocked.set()
            unblock_producer.wait()
            raise StopIteration

        def close(self) -> None:
            return

    runner = MagicMock()
    runner.settings.terminate_grace_seconds = 0.01

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        del owner, grace_seconds
        unblock_producer.set()
        raise RuntimeError("terminate_owned failed")

    runner.terminate_owned = terminate_owned

    bridge = ArrowIpcStreamBridge(
        plan,
        BlockingIterator(batches[0]),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )
    join_calls = 0
    original_worker_join = bridge._worker.join

    def tracked_join(timeout: float | None = None) -> None:
        nonlocal join_calls
        join_calls += 1
        original_worker_join(timeout)

    bridge._worker.join = tracked_join  # type: ignore[method-assign]

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")
    with pytest.raises(RuntimeError, match="terminate_owned failed"):
        bridge.close_sync(join_timeout_seconds=1.0)
    drainer.join(timeout=2.0)
    assert join_calls >= 1
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_bridge_registry_close_all_aggregates_errors_and_survivors() -> None:
    from unittest.mock import MagicMock

    cleanup_bridge = MagicMock()
    cleanup_bridge.close_sync.side_effect = ValueError("cleanup failed")
    cleanup_bridge.is_worker_alive.return_value = False

    survivor_bridge = MagicMock()
    survivor_bridge.close_sync.side_effect = BridgeJoinTimeoutError("worker did not exit")
    survivor_bridge.is_worker_alive.return_value = True

    with patch.object(BRIDGE_REGISTRY, "snapshot", return_value=(cleanup_bridge, survivor_bridge)):
        with pytest.raises(BridgeShutdownError) as exc_info:
            BRIDGE_REGISTRY.close_all(None, join_timeout_seconds=0.01)

    error = exc_info.value
    assert len(error.cleanup_errors) >= 1
    assert len(error.failures) >= 1
    assert error.survivor_count >= 1


@pytest.mark.serial
def test_request_close_sets_cancellation_before_worker_join() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    close_started = threading.Event()
    cancellation = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), cancellation)

    def close_in_thread() -> None:
        close_started.set()
        bridge.close_sync(join_timeout_seconds=30.0)

    closer = threading.Thread(target=close_in_thread)
    closer.start()
    assert close_started.wait(timeout=2.0)
    assert cancellation.is_set()
    release.set()
    closer.join(timeout=5.0)
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_aclose_sets_cancellation_before_thread_cleanup() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    cancellation = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), cancellation)

    async def close_while_worker_blocked() -> None:
        await bridge.aclose()

    closer = threading.Thread(target=lambda: asyncio.run(close_while_worker_blocked()))
    closer.start()
    _wait_until(cancellation.is_set, message="aclose did not set cancellation before cleanup thread")
    release.set()
    closer.join(timeout=5.0)
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_aclose_completes_cleanup_when_awaiting_task_cancelled() -> None:
    """Smoke test that asyncio.Task.cancel() interrupts blocked bridge consumption."""

    bridge, release, producer_blocked, _close_completed, _cancellation = _gated_bridge_for_cancel_cleanup()
    try:

        async def consume_and_cancel() -> None:
            iter_task = asyncio.create_task(_block_on_second_chunk(bridge))
            while not producer_blocked.is_set():
                await asyncio.sleep(0.01)
            iter_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await iter_task

        asyncio.run(consume_and_cancel())
        asyncio.run(bridge.aclose())
        assert not bridge.is_worker_alive()
        assert BRIDGE_REGISTRY.snapshot() == ()
    finally:
        release.set()
        ArrowIpcStreamBridge._test_close_completed_barrier = None
        BRIDGE_REGISTRY.unregister(bridge)


async def _block_on_second_chunk(bridge: ArrowIpcStreamBridge) -> None:
    stream = bridge.iter_bytes()
    first = await stream.__anext__()
    assert first
    await stream.__anext__()


def _gated_bridge_for_cancel_cleanup(
    *,
    batch_count: int = 2,
) -> tuple[ArrowIpcStreamBridge, threading.Event, threading.Event, threading.Event, threading.Event]:
    plan, batches = _plan_and_batches(batch_count=batch_count, rows_per_batch=1)
    release = threading.Event()
    producer_blocked = threading.Event()
    close_completed = threading.Event()
    cancellation = threading.Event()
    ArrowIpcStreamBridge._test_close_completed_barrier = close_completed

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_blocked.set()
        while not release.is_set():
            if cancellation.is_set():
                return
            time.sleep(0.01)
        if batch_count > 1:
            yield batches[1]

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), cancellation)
    return bridge, release, producer_blocked, close_completed, cancellation


@pytest.mark.serial
def test_aclose_completes_cleanup_under_anyio_cancel_scope() -> None:
    import anyio

    bridge, release, producer_blocked, close_completed, _cancellation = _gated_bridge_for_cancel_cleanup()
    try:

        async def exercise() -> None:
            async def consume_until_blocked() -> None:
                stream = bridge.iter_bytes()
                await stream.__anext__()
                while not producer_blocked.is_set():
                    await anyio.sleep(0.01)
                await stream.__anext__()

            with anyio.CancelScope() as scope:
                async with anyio.create_task_group() as task_group:
                    task_group.start_soon(consume_until_blocked)
                    while not producer_blocked.is_set():
                        await anyio.sleep(0.01)
                    scope.cancel()

            assert close_completed.is_set()
            assert not bridge.is_worker_alive()

        anyio.run(exercise)
        assert BRIDGE_REGISTRY.snapshot() == ()
    finally:
        release.set()
        ArrowIpcStreamBridge._test_close_completed_barrier = None
        BRIDGE_REGISTRY.unregister(bridge)


@pytest.mark.serial
def test_streaming_response_waits_cleanup_under_anyio_cancel_scope() -> None:
    import anyio

    from gateway_repository_service.versioned_read.streaming_response import VersionedReadStreamingResponse

    bridge, release, producer_blocked, close_completed, _cancellation = _gated_bridge_for_cancel_cleanup()
    try:

        async def body() -> AsyncIterator[bytes]:
            async for chunk in bridge.iter_bytes():
                yield chunk

        response = VersionedReadStreamingResponse(
            bridge,
            body(),
            media_type="application/vnd.apache.arrow.stream",
        )

        async def exercise() -> None:
            scope: Scope = {
                "type": "http",
                "method": "GET",
                "path": "/rows",
                "headers": [],
                "query_string": b"",
            }
            started = asyncio.Event()

            from starlette.types import Message, Receive, Scope, Send

            async def send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    started.set()

            async def receive() -> Message:
                return {"type": "http.disconnect"}

            with anyio.CancelScope() as cancel_scope:
                async with anyio.create_task_group() as task_group:

                    async def invoke_response() -> None:
                        await response(scope, cast(Receive, receive), cast(Send, send))

                    task_group.start_soon(invoke_response)
                    while not started.is_set():
                        await anyio.sleep(0.01)
                    while not producer_blocked.is_set():
                        await anyio.sleep(0.01)
                    cancel_scope.cancel()

            assert close_completed.is_set()
            assert not bridge.is_worker_alive()

        anyio.run(exercise)
        assert BRIDGE_REGISTRY.snapshot() == ()
    finally:
        release.set()
        ArrowIpcStreamBridge._test_close_completed_barrier = None
        BRIDGE_REGISTRY.unregister(bridge)


@pytest.mark.serial
def test_sustained_cancel_cleanup_does_not_spin_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import anyio

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    unregister_blocked = threading.Event()
    unregister_release = threading.Event()
    close_completed = threading.Event()
    shield_calls = 0
    original_shield = asyncio.shield

    async def counting_shield(awaitable: Any) -> Any:
        nonlocal shield_calls
        shield_calls += 1
        return await original_shield(awaitable)

    monkeypatch.setattr(asyncio, "shield", counting_shield)
    ArrowIpcStreamBridge._test_unregister_barrier = unregister_blocked
    ArrowIpcStreamBridge._test_close_completed_barrier = close_completed
    bridge = ArrowIpcStreamBridge(plan, iter(batches), threading.Event())
    try:

        def release_unregister_after_delay() -> None:
            time.sleep(0.3)
            unregister_release.set()
            unregister_blocked.set()

        async def exercise() -> None:
            waiter_done = asyncio.Event()

            async def cooperative_waiter() -> None:
                await asyncio.sleep(0.05)
                waiter_done.set()

            async def sustained_cancel_close() -> None:
                with anyio.CancelScope() as scope:
                    scope.cancel()
                    try:
                        await bridge.aclose()
                    except asyncio.CancelledError:
                        pass

            releaser = threading.Thread(target=release_unregister_after_delay, daemon=True)
            releaser.start()
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(cooperative_waiter)
                task_group.start_soon(sustained_cancel_close)
                while not unregister_blocked.is_set():
                    await anyio.sleep(0.01)
                await asyncio.wait_for(waiter_done.wait(), timeout=0.2)

            releaser.join(timeout=2.0)
            _wait_until(close_completed.is_set, message="cleanup did not complete under sustained cancel")

        anyio.run(exercise)
        assert shield_calls < 50
        assert not bridge.is_worker_alive()
    finally:
        unregister_release.set()
        unregister_blocked.set()
        ArrowIpcStreamBridge._test_unregister_barrier = None
        ArrowIpcStreamBridge._test_close_completed_barrier = None
        bridge._worker.join(timeout=5.0)
        BRIDGE_REGISTRY.unregister(bridge)


@pytest.mark.serial
def test_close_all_waits_for_worker_thread_not_false_survivor() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    unregister_barrier = threading.Event()
    close_started = threading.Event()
    close_finished = threading.Event()
    close_errors: list[BaseException] = []
    close_all_errors: list[BaseException] = []
    close_all_finished = threading.Event()
    ArrowIpcStreamBridge._test_unregister_barrier = unregister_barrier
    bridge = ArrowIpcStreamBridge(plan, iter(batches), threading.Event())
    try:

        def close_in_thread() -> None:
            close_started.set()
            try:
                bridge.close_sync(join_timeout_seconds=30.0)
            except BaseException as exc:
                close_errors.append(exc)
            finally:
                close_finished.set()

        def close_all_in_thread() -> None:
            try:
                BRIDGE_REGISTRY.close_all(None, join_timeout_seconds=30.0)
            except BaseException as exc:
                close_all_errors.append(exc)
            finally:
                close_all_finished.set()

        closer = threading.Thread(target=close_in_thread)
        closer.start()
        assert close_started.wait(timeout=2.0)
        _wait_until(lambda: bridge._worker_finished, message="worker did not finish before unregister")
        assert bridge.is_worker_alive() is False
        assert bridge in BRIDGE_REGISTRY.snapshot()

        close_all_thread = threading.Thread(target=close_all_in_thread)
        close_all_thread.start()
        time.sleep(0.2)
        assert not close_all_finished.is_set()

        unregister_barrier.set()
        closer.join(timeout=5.0)
        close_all_thread.join(timeout=5.0)
        assert close_finished.is_set()
        assert close_all_finished.is_set()
        assert close_errors == []
        assert close_all_errors == []
        assert BRIDGE_REGISTRY.snapshot() == ()
    finally:
        unregister_barrier.set()
        ArrowIpcStreamBridge._test_unregister_barrier = None
        BRIDGE_REGISTRY.unregister(bridge)


@pytest.mark.serial
def test_join_timeout_keeps_alive_worker_registered_until_exit() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    worker_finish_release = threading.Event()
    ArrowIpcStreamBridge._test_worker_finish_barrier = worker_finish_release
    bridge = ArrowIpcStreamBridge(plan, iter(batches), threading.Event())
    try:
        with pytest.raises(BridgeJoinTimeoutError):
            bridge.close_sync(join_timeout_seconds=0.05)

        assert bridge.is_worker_alive()
        assert bridge._worker_finished is False
        assert bridge._worker_joined is False
        assert bridge in BRIDGE_REGISTRY.snapshot()

        worker_finish_release.set()
        _wait_until(lambda: not bridge.is_worker_alive(), message="worker did not exit after finish barrier release")

        BRIDGE_REGISTRY.close_all(None, join_timeout_seconds=30.0)
        assert BRIDGE_REGISTRY.snapshot() == ()
        assert not bridge.is_worker_alive()
    finally:
        worker_finish_release.set()
        ArrowIpcStreamBridge._test_worker_finish_barrier = None
        bridge._worker.join(timeout=5.0)
        BRIDGE_REGISTRY.unregister(bridge)


@pytest.mark.serial
def test_close_sync_follower_waits_when_worker_joins_during_escalation() -> None:
    from unittest.mock import MagicMock

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    producer_blocked = threading.Event()
    terminate_barrier = threading.Event()
    terminate_continue = threading.Event()
    follower_finished = threading.Event()
    bridge_owner = object()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_blocked.set()
        release.wait()

    runner = MagicMock()
    runner.settings.terminate_grace_seconds = 0.01

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        del owner, grace_seconds
        terminate_barrier.set()
        assert terminate_continue.wait(timeout=2.0)

    runner.terminate_owned = terminate_owned

    bridge = ArrowIpcStreamBridge(
        plan,
        gated_rows(),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )
    leader_errors: list[BaseException] = []
    follower_errors: list[BaseException] = []

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")

    def leader_close() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.05)
        except BaseException as exc:
            leader_errors.append(exc)

    leader = threading.Thread(target=leader_close)
    leader.start()
    assert terminate_barrier.wait(timeout=2.0)

    def follower_close() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.05)
        except BaseException as exc:
            follower_errors.append(exc)
        finally:
            follower_finished.set()

    follower = threading.Thread(target=follower_close)
    follower.start()
    try:
        assert not follower_finished.wait(timeout=0.2)
        terminate_continue.set()
        leader.join(timeout=5.0)
        follower.join(timeout=5.0)
        assert follower_finished.is_set()
        assert len(leader_errors) == 1
        assert len(follower_errors) == 1
        assert isinstance(leader_errors[0], BridgeJoinTimeoutError)
        assert isinstance(follower_errors[0], BridgeJoinTimeoutError)
    finally:
        release.set()
        drainer.join(timeout=2.0)
        bridge._worker.join(timeout=5.0)


@pytest.mark.serial
def test_close_sync_chains_terminate_error_under_join_timeout() -> None:
    from unittest.mock import MagicMock

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    producer_blocked = threading.Event()
    keep_worker_alive = threading.Event()
    bridge_owner = object()

    class BlockingIterator:
        def __init__(self, batch: pa.RecordBatch) -> None:
            self._batch = batch
            self._yielded = False

        def __iter__(self) -> BlockingIterator:
            return self

        def __next__(self) -> pa.RecordBatch:
            if not self._yielded:
                self._yielded = True
                return self._batch
            producer_blocked.set()
            keep_worker_alive.wait()
            raise StopIteration

        def close(self) -> None:
            return

    runner = MagicMock()
    runner.settings.terminate_grace_seconds = 0.01

    def terminate_owned(owner: object, *, grace_seconds: float | None = None) -> None:
        del owner, grace_seconds
        raise RuntimeError("terminate_owned failed")

    runner.terminate_owned = terminate_owned

    bridge = ArrowIpcStreamBridge(
        plan,
        BlockingIterator(batches[0]),
        threading.Event(),
        dolt_runner=runner,
        stream_owner=bridge_owner,
    )

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    try:
        _wait_until(producer_blocked.is_set, message="producer did not block on second batch")
        with pytest.raises(BridgeJoinTimeoutError) as exc_info:
            bridge.close_sync(join_timeout_seconds=0.05)
        assert isinstance(exc_info.value.__cause__, RuntimeError)
    finally:
        keep_worker_alive.set()
        drainer.join(timeout=2.0)
        bridge._worker.join(timeout=5.0)


@pytest.mark.serial
def test_terminate_and_reap_gate_dedupes_concurrent_callers(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from gateway_repository_service.layout import DurableLayout
    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    del layout
    registry = ActiveChildRegistry()
    process = MagicMock()
    process.pid = 4242
    process.poll.return_value = None
    registry.register(process)

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None

    sigterm_calls = 0
    sigterm_lock = threading.Lock()
    inside_terminate = threading.Event()
    release_terminate = threading.Event()

    def slow_killpg(pid: int, sig: int) -> None:
        nonlocal sigterm_calls
        del pid
        if sig == signal.SIGTERM:
            with sigterm_lock:
                sigterm_calls += 1
            inside_terminate.set()
            assert release_terminate.wait(timeout=2.0)
        process.poll.return_value = 0

    with patch("gateway_repository_service.process.os.killpg", side_effect=slow_killpg):
        errors: list[BaseException] = []

        def terminate_once() -> None:
            try:
                DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=terminate_once)
        second = threading.Thread(target=terminate_once)
        first.start()
        assert inside_terminate.wait(timeout=2.0)
        second.start()
        release_terminate.set()
        first.join(timeout=5.0)
        second.join(timeout=5.0)
    assert not errors
    assert sigterm_calls == 1


@pytest.mark.serial
def test_terminate_and_reap_unregisters_already_exited_process(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    registry = ActiveChildRegistry()
    process = MagicMock()
    process.pid = 5151
    process.poll.return_value = 0
    registry.register(process)

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None

    DoltRunner.terminate_and_reap(runner, process)
    assert registry.snapshot() == ()
    assert registry._termination_gates == {}


@pytest.mark.serial
def test_terminate_and_reap_gate_table_stable_across_repeated_success(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    registry = ActiveChildRegistry()
    process = MagicMock()
    process.pid = 5152
    process.poll.return_value = 0

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None

    for _ in range(3):
        registry.register(process)
        DoltRunner.terminate_and_reap(runner, process)
        assert registry.snapshot() == ()
        assert registry._termination_gates == {}


@pytest.mark.serial
def test_terminate_and_reap_propagates_leader_failure_to_waiter(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    registry = ActiveChildRegistry()
    process = MagicMock()
    process.pid = 5252
    process.poll.return_value = None
    registry.register(process)

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None

    inside_terminate = threading.Event()
    release_terminate = threading.Event()

    def deny_killpg(pid: int, sig: int) -> None:
        del pid, sig
        inside_terminate.set()
        assert release_terminate.wait(timeout=2.0)
        raise PermissionError("signal denied")

    leader_errors: list[BaseException] = []
    waiter_errors: list[BaseException | None] = []

    def leader_terminate() -> None:
        try:
            DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)
        except BaseException as exc:
            leader_errors.append(exc)

    with patch("gateway_repository_service.process.os.killpg", side_effect=deny_killpg):
        leader = threading.Thread(target=leader_terminate)
        leader.start()
        assert inside_terminate.wait(timeout=2.0)
        waiter = threading.Thread(
            target=lambda: waiter_errors.append(
                _terminate_and_reap_capturing(runner, process),
            ),
        )
        waiter.start()
        release_terminate.set()
        leader.join(timeout=5.0)
        waiter.join(timeout=5.0)

    assert len(leader_errors) == 1
    assert len(waiter_errors) == 1
    assert isinstance(leader_errors[0], PermissionError)
    assert isinstance(waiter_errors[0], PermissionError)
    assert process.poll.return_value is None
    assert registry.snapshot() == (process,)
    assert registry._termination_gates == {}


@pytest.mark.serial
def test_terminate_and_reap_retries_after_leader_failure(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    registry = ActiveChildRegistry()
    process = MagicMock()
    process.pid = 5253
    process.poll.return_value = None
    registry.register(process)

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None

    kill_calls = 0
    fail_first_kill = True

    def flaky_killpg(pid: int, sig: int) -> None:
        nonlocal kill_calls, fail_first_kill
        del pid
        if sig == signal.SIGTERM:
            kill_calls += 1
            if fail_first_kill:
                fail_first_kill = False
                raise PermissionError("signal denied")
        process.poll.return_value = 0

    with patch("gateway_repository_service.process.os.killpg", side_effect=flaky_killpg):
        with pytest.raises(PermissionError):
            DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)
        assert registry.snapshot() == (process,)
        assert registry._termination_gates == {}
        DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)

    assert kill_calls == 2
    assert registry.snapshot() == ()
    assert registry._termination_gates == {}


def _terminate_and_reap_capturing(runner: Any, process: Any) -> BaseException | None:
    from gateway_repository_service.process import DoltRunner

    try:
        DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)
    except BaseException as exc:
        return exc
    return None


@pytest.mark.serial
def test_terminate_owned_races_process_stream_close_path(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from gateway_repository_service.process import ActiveChildRegistry, DoltRunner
    from support.lifecycle_harness import lifecycle_settings

    settings = lifecycle_settings(tmp_path)
    registry = ActiveChildRegistry()
    owner = object()
    process = MagicMock()
    process.pid = 5353
    process.poll.return_value = None
    registry.register(process, owner=owner)

    runner = MagicMock(spec=DoltRunner)
    runner.settings = settings
    runner._active_children = registry
    runner._unregister_active_child = lambda proc: registry.unregister(proc)
    runner.reap_adopted_dolt_children = lambda: None
    runner.terminate_owned = lambda owner, *, grace_seconds=None: DoltRunner.terminate_owned(
        runner,
        owner,
        grace_seconds=grace_seconds,
    )

    sigterm_calls = 0
    sigterm_lock = threading.Lock()
    inside_terminate = threading.Event()
    release_terminate = threading.Event()

    def slow_killpg(pid: int, sig: int) -> None:
        nonlocal sigterm_calls
        del pid
        if sig == signal.SIGTERM:
            with sigterm_lock:
                sigterm_calls += 1
            inside_terminate.set()
            assert release_terminate.wait(timeout=2.0)
        process.poll.return_value = 0

    errors: list[BaseException] = []

    def close_path() -> None:
        try:
            DoltRunner.terminate_and_reap(runner, process, grace_seconds=0.01)
        except BaseException as exc:
            errors.append(exc)

    def owned_path() -> None:
        try:
            runner.terminate_owned(owner, grace_seconds=0.01)
        except BaseException as exc:
            errors.append(exc)

    with patch("gateway_repository_service.process.os.killpg", side_effect=slow_killpg):
        close_thread = threading.Thread(target=close_path)
        owned_thread = threading.Thread(target=owned_path)
        close_thread.start()
        assert inside_terminate.wait(timeout=2.0)
        owned_thread.start()
        release_terminate.set()
        close_thread.join(timeout=5.0)
        owned_thread.join(timeout=5.0)

    assert not errors
    assert sigterm_calls == 1


@pytest.mark.serial
def test_close_sync_long_deadline_follower_wakes_on_published_outcome() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    producer_blocked = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_blocked.set()
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), threading.Event())
    follower_errors: list[BaseException] = []
    follower_elapsed: list[float] = []

    def drain_queue() -> None:
        while bridge.is_worker_alive():
            try:
                bridge._queue.get(timeout=_POLL_TIMEOUT_SECONDS)
            except Exception:
                pass

    drainer = threading.Thread(target=drain_queue, daemon=True)
    drainer.start()
    _wait_until(producer_blocked.is_set, message="producer did not block on second batch")

    def follower_close() -> None:
        started = time.monotonic()
        try:
            bridge.close_sync(join_timeout_seconds=5.0)
        except BaseException as exc:
            follower_errors.append(exc)
        finally:
            follower_elapsed.append(time.monotonic() - started)

    follower = threading.Thread(target=follower_close)
    follower.start()
    time.sleep(0.1)

    leader_errors: list[BaseException] = []

    def leader_close() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.1)
        except BaseException as exc:
            leader_errors.append(exc)

    leader = threading.Thread(target=leader_close)
    leader.start()
    leader.join(timeout=5.0)
    follower.join(timeout=1.0)
    release.set()
    drainer.join(timeout=2.0)
    bridge._worker.join(timeout=5.0)

    assert follower_elapsed
    assert follower_elapsed[0] < 1.0
    assert len(leader_errors) == 1
    assert len(follower_errors) == 1
    assert isinstance(leader_errors[0], BridgeJoinTimeoutError)
    assert isinstance(follower_errors[0], BridgeJoinTimeoutError)


@pytest.mark.unit
def test_production_modules_only_import_declared_dependencies() -> None:
    import ast
    from pathlib import Path

    source_root = Path(__file__).resolve().parents[1] / "src" / "gateway_repository_service"
    forbidden: set[str] = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    assert root_name not in forbidden, f"{path} imports forbidden module {root_name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".")[0]
                assert root_name not in forbidden, f"{path} imports forbidden module {root_name}"
