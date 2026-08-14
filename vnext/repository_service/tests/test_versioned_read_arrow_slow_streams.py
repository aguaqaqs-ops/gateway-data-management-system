"""Slow-stream pressure and instance-scoped bridge probe tests for P2-R6-S3-D."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_service.versioned_read.arrow_bridge import (
    BRIDGE_REGISTRY,
    ArrowIpcStreamBridge,
    BridgeTestProbe,
)

from test_versioned_read_arrow_bridge import _force_unregister_bridge, _plan_and_batches, _wait_until

SLOW_STREAM_COUNTS = (1, 4, 8)
SLOW_WINDOW_SECONDS = 0.25


@dataclass(frozen=True)
class SlowStreamSample:
    stream_count: int
    default_executor_to_thread_calls: int
    bridge_thread_count: int
    cleanup_duration_seconds: float


def _make_gated_rows(
    batches: list[pa.RecordBatch],
    *,
    producer_blocked: threading.Event,
    release: threading.Event,
) -> Iterator[pa.RecordBatch]:
    for index, batch in enumerate(batches):
        yield batch
        if index == 0:
            producer_blocked.set()
            release.wait()


@pytest.mark.unit
@pytest.mark.serial
def test_bridge_test_probe_is_instance_scoped() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    probe_a = BridgeTestProbe(close_entered_barrier=threading.Event())
    probe_b = BridgeTestProbe(close_entered_barrier=threading.Event())
    bridge_a = ArrowIpcStreamBridge(plan, iter(batches), threading.Event(), test_probe=probe_a)
    bridge_b = ArrowIpcStreamBridge(plan, iter(batches), threading.Event(), test_probe=probe_b)
    errors: list[BaseException] = []

    def close_a() -> None:
        try:
            bridge_a.close_sync(join_timeout_seconds=5.0)
        except BaseException as exc:
            errors.append(exc)

    closer = threading.Thread(target=close_a)
    closer.start()
    assert probe_a.close_entered_barrier is not None
    assert probe_a.close_entered_barrier.wait(timeout=2.0)
    assert probe_b.close_entered_barrier is not None
    assert not probe_b.close_entered_barrier.is_set()
    closer.join(timeout=5.0)
    bridge_b.close_sync(join_timeout_seconds=5.0)
    assert errors == []


@pytest.mark.serial
@pytest.mark.parametrize("stream_count", SLOW_STREAM_COUNTS)
def test_slow_streams_do_not_poll_default_executor(stream_count: int) -> None:
    plan, batches = _plan_and_batches(batch_count=3, rows_per_batch=1)
    bridges: list[ArrowIpcStreamBridge] = []
    releases: list[threading.Event] = []
    producer_blockeds: list[threading.Event] = []

    for _ in range(stream_count):
        release = threading.Event()
        producer_blocked = threading.Event()
        releases.append(release)
        producer_blockeds.append(producer_blocked)
        bridge = ArrowIpcStreamBridge(
            plan,
            _make_gated_rows(
                batches,
                producer_blocked=producer_blocked,
                release=release,
            ),
            threading.Event(),
        )
        bridges.append(bridge)

    to_thread_calls = 0
    measuring = False
    original_to_thread = asyncio.to_thread

    async def counting_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        nonlocal to_thread_calls
        if measuring:
            to_thread_calls += 1
        return await original_to_thread(func, *args, **kwargs)

    async def slow_consume(
        bridge: ArrowIpcStreamBridge,
        blocked: threading.Event,
        release: threading.Event,
    ) -> float:
        stream = bridge.iter_bytes()
        first_chunk = await anext(stream)
        assert first_chunk
        _wait_until(blocked.is_set, timeout_seconds=2.0, message="producer did not block")
        await asyncio.sleep(SLOW_WINDOW_SECONDS)
        cleanup_started = time.monotonic()
        release.set()
        close_stream = getattr(stream, "aclose")
        await close_stream()
        return time.monotonic() - cleanup_started

    try:
        with patch("asyncio.to_thread", counting_to_thread):
            measuring = True

            async def exercise() -> tuple[float, ...]:
                durations = await asyncio.gather(
                    *(
                        slow_consume(bridge, producer_blocked, release)
                        for bridge, producer_blocked, release in zip(
                            bridges,
                            producer_blockeds,
                            releases,
                            strict=True,
                        )
                    )
                )
                return tuple(durations)

            cleanup_durations = asyncio.run(exercise())
            measuring = False

        sample = SlowStreamSample(
            stream_count=stream_count,
            default_executor_to_thread_calls=to_thread_calls,
            bridge_thread_count=sum(1 for bridge in bridges if bridge.is_worker_alive()),
            cleanup_duration_seconds=max(cleanup_durations, default=0.0),
        )
        assert sample.default_executor_to_thread_calls == 0, sample
        assert sample.bridge_thread_count == 0, sample
        assert sample.cleanup_duration_seconds < 5.0, sample
        assert BRIDGE_REGISTRY.snapshot() == ()
    finally:
        for release in releases:
            release.set()
        for bridge in bridges:
            _force_unregister_bridge(bridge)
        assert BRIDGE_REGISTRY.snapshot() == ()
