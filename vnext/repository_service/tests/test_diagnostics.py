"""Unit tests for structured diagnostics helper."""

from __future__ import annotations

import logging
from uuid import uuid4

from pathlib import Path

import pytest

from gateway_repository_service.diagnostics import log_event, operational_limits
from gateway_repository_service.settings import RepositoryServiceSettings


def test_operational_limits_omit_paths_and_tokens() -> None:
    settings = RepositoryServiceSettings(
        profile="test",
        bearer_token="secret-token-value",
        data_root=Path("/var/lib/gateway/repository"),
    )
    limits = operational_limits(settings)
    assert limits["max_concurrent_uploads"] == 8
    assert limits["max_concurrent_row_streams"] == 8
    assert limits["artifact_cleanup_interval_seconds"] == 300
    assert limits["full_scan_timeout_seconds"] == 3600
    assert "bearer_token" not in limits
    assert "data_root" not in limits
    assert "dolt_binary" not in limits


def test_log_event_writes_stable_fields_and_omits_absent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository_id = uuid4()
    with caplog.at_level(logging.INFO, logger="gateway_repository_service.diagnostics"):
        log_event(
            "upload_admission_acquired",
            request_id="abc123",
            repository_id=repository_id,
            capacity=8,
            in_use=1,
            result="acquired",
        )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    fields = getattr(record, "gateway_fields")
    assert fields["event"] == "upload_admission_acquired"
    assert fields["request_id"] == "abc123"
    assert fields["repository_id"] == str(repository_id)
    assert fields["capacity"] == 8
    assert fields["in_use"] == 1
    assert fields["result"] == "acquired"
    assert "operation_id" not in fields
    assert "artifact_id" not in fields
    assert "secret-token-value" not in caplog.text
    assert "idempotency" not in fields
    assert "Authorization" not in str(fields)


def test_log_event_is_fail_safe_when_logger_raises() -> None:
    class BoomLogger(logging.Logger):
        def log(self, level: int, msg: object, *args: object, **kwargs: object) -> None:
            raise RuntimeError("logger boom")

    boom = BoomLogger("gateway_repository_service.diagnostics.boom")
    log_event("http_request_completed", request_id="rid", logger=boom)


@pytest.mark.serial
def test_streaming_cleanup_error_survives_failing_log_event(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from typing import Any

    from gateway_repository_service import diagnostics as diagnostics_mod
    from gateway_repository_service.admission import PermitPool
    from gateway_repository_service.versioned_read.streaming_response import VersionedReadStreamingResponse

    def boom_log(level: int, msg: object, *args: object, **kwargs: object) -> None:
        del level, msg, args, kwargs
        raise RuntimeError("logger boom")

    monkeypatch.setattr(diagnostics_mod._LOGGER, "log", boom_log)

    pool = PermitPool(1)
    lease = pool.try_acquire()
    assert lease is not None

    class FakeBridge:
        async def aclose(self) -> None:
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

        with pytest.raises(RuntimeError, match="bridge cleanup failed"):
            await response(
                {"type": "http", "method": "GET", "path": "/rows"},
                receive,
                send,
            )
        assert pool.in_use == 0

    asyncio.run(run())
