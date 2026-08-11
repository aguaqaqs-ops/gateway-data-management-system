"""Focused unit tests for row-stream concurrency admission."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from gateway_repository_contracts import (
    SERVICE_NOT_READY_CODE,
    StreamVersionedTableRowsQuery,
    UnknownTypePolicy,
)
from gateway_repository_service.admission import PermitPool
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.versioned_read.http_service import VersionedReadHttpService
from gateway_repository_service.versioned_read.streaming_response import VersionedReadStreamingResponse


def test_resolve_and_catalog_do_not_take_row_stream_permit() -> None:
    pool = PermitPool(1)
    held = pool.try_acquire()
    assert held is not None
    application = MagicMock()
    application.resolve_main.return_value = "commit-1"
    application.get_catalog.return_value = ()
    service = VersionedReadHttpService(application, row_stream_admission=pool)
    repository_id = uuid4()
    service.resolve_ref(repository_id)
    service.get_catalog(repository_id, "commit-1")
    assert pool.in_use == 1
    application.open_table_rows.assert_not_called()
    held.release()


def test_ninth_row_stream_rejected_before_provider_open() -> None:
    pool = PermitPool(8)
    held = [pool.try_acquire() for _ in range(8)]
    assert all(item is not None for item in held)
    application = MagicMock()
    service = VersionedReadHttpService(application, row_stream_admission=pool)
    with pytest.raises(ServiceError) as exc_info:
        service.open_row_stream(
            uuid4(),
            "commit-1",
            StreamVersionedTableRowsQuery(
                table_name="items",
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == SERVICE_NOT_READY_CODE
    application.open_table_rows.assert_not_called()
    assert pool.in_use == 8
    for lease in held:
        assert lease is not None
        lease.release()


def test_open_failure_releases_row_stream_permit() -> None:
    pool = PermitPool(1)
    application = MagicMock()
    application.open_table_rows.side_effect = RuntimeError("provider boom")
    service = VersionedReadHttpService(application, row_stream_admission=pool)
    with pytest.raises(ServiceError):
        service.open_row_stream(
            uuid4(),
            "commit-1",
            StreamVersionedTableRowsQuery(
                table_name="items",
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
    assert pool.in_use == 0


@pytest.mark.serial
def test_ninth_row_stream_rejected_before_response_start() -> None:
    pool = PermitPool(1)
    held = pool.try_acquire()
    assert held is not None
    application = MagicMock()
    service = VersionedReadHttpService(application, row_stream_admission=pool)
    started: list[int] = []

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        del receive
        assert scope["type"] == "http"
        try:
            service.open_row_stream(
                uuid4(),
                "commit-1",
                StreamVersionedTableRowsQuery(
                    table_name="items",
                    unknown_type_policy=UnknownTypePolicy.REJECT,
                ),
            )
        except ServiceError as exc:
            await send(
                {
                    "type": "http.response.start",
                    "status": exc.status_code,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            started.append(exc.status_code)
            await send(
                {
                    "type": "http.response.body",
                    "body": exc.code.encode("utf-8"),
                    "more_body": False,
                }
            )
            return
        raise AssertionError("expected admission denial before headers")

    async def run() -> None:
        messages: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        await app(
            {"type": "http", "method": "GET", "path": "/rows"},
            receive,
            send,
        )
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 503
        assert started == [503]
        assert application.open_table_rows.call_count == 0

    asyncio.run(run())
    held.release()


@pytest.mark.serial
def test_permit_held_until_bridge_cleanup_and_released_on_aclose_error() -> None:
    pool = PermitPool(1)
    lease = pool.try_acquire()
    assert lease is not None
    assert pool.in_use == 1

    class FakeBridge:
        def __init__(self) -> None:
            self.aclose_entered = asyncio.Event()
            self.release_gate = asyncio.Event()
            self.closed = False

        async def aclose(self) -> None:
            self.aclose_entered.set()
            await self.release_gate.wait()
            self.closed = True
            raise RuntimeError("bridge cleanup failed")

        async def iter_bytes(self) -> Any:
            if False:  # pragma: no cover
                yield b""

    bridge = FakeBridge()

    async def content() -> Any:
        async for chunk in bridge.iter_bytes():
            yield chunk

    response = VersionedReadStreamingResponse(
        bridge,  # type: ignore[arg-type]
        content(),
        media_type="application/vnd.apache.arrow.stream",
        permit_lease=lease,
        admission_capacity=1,
    )

    async def run() -> None:
        from collections.abc import MutableMapping

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.disconnect"}

        async def send(message: MutableMapping[str, Any]) -> None:
            del message

        task = asyncio.create_task(
            response(
                {"type": "http", "method": "GET", "path": "/rows"},
                receive,
                send,
            )
        )
        assert await asyncio.wait_for(bridge.aclose_entered.wait(), timeout=2.0)
        assert pool.in_use == 1
        bridge.release_gate.set()
        with pytest.raises(RuntimeError, match="bridge cleanup failed"):
            await task
        assert bridge.closed is True
        assert pool.in_use == 0

    asyncio.run(run())
