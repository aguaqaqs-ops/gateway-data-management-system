"""Subprocess crash worker for Versioned import HTTP admission tests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.faults import ImportAdmissionFaultPoint
from support.crash_recovery_worker import CRASH_EXIT_CODE
from support.http_harness import import_headers, import_request_body

_RUNTIME: ServiceRuntime | None = None
_STATUS_OUT: Path | None = None
_RESPONSE_STATUS: str | None = None


def _crash() -> None:
    global _RUNTIME
    if _STATUS_OUT is not None:
        _STATUS_OUT.write_text(_RESPONSE_STATUS or "crashed", encoding="utf-8")
    if _RUNTIME is not None:
        runtime = _RUNTIME
        _RUNTIME = None
        runtime._stopping.set()
        if runtime.control_store.is_open():
            runtime.control_store.close()
        if runtime.root_lock.is_held():
            runtime.root_lock.release()
    os._exit(CRASH_EXIT_CODE)


class _CrashAdmissionFaultInjector:
    def __init__(self, point: ImportAdmissionFaultPoint) -> None:
        self._point = point

    def maybe_raise(self, point: ImportAdmissionFaultPoint) -> None:
        global _RESPONSE_STATUS
        if point == self._point:
            if point == ImportAdmissionFaultPoint.AFTER_QUEUED_PUBLISH_BEFORE_202:
                _RESPONSE_STATUS = "202"
            _crash()


def _settings_from_args(args: argparse.Namespace) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=Path(args.data_root),
        bearer_token="test-bearer-token",
        dolt_binary=Path(args.dolt_binary),
        dolt_version=args.dolt_version,
    )


def _run_submit_import(args: argparse.Namespace) -> None:
    global _RUNTIME, _STATUS_OUT
    settings = _settings_from_args(args)
    fault_point = ImportAdmissionFaultPoint(args.fault_point)
    _STATUS_OUT = Path(args.status_out) if args.status_out is not None else None
    runtime = ServiceRuntime.start(
        settings,
        admission_fault_injector=_CrashAdmissionFaultInjector(fault_point),
    )
    _RUNTIME = runtime
    try:
        app = create_app(settings, enable_lifecycle=False)
        app.state.auth_state = runtime.auth_state
        app.state.runtime = runtime
        client = TestClient(app)
        repository_id = UUID(args.repository_id)
        artifact_id = UUID(args.artifact_id)
        body = import_request_body(
            repository_id=repository_id,
            artifact_id=artifact_id,
            size_bytes=int(args.size_bytes),
            raw_sha256=args.raw_sha256,
            expected_commit_id=args.expected_commit_id,
        )
        response = client.post(
            f"/v1/repositories/{repository_id}/versioned/imports",
            headers=import_headers(idempotency_key=args.idempotency_key),
            content=json.dumps(body),
        )
        if args.status_out is not None:
            Path(args.status_out).write_text(str(response.status_code), encoding="utf-8")
    finally:
        if _RUNTIME is runtime:
            runtime.shutdown()
            _RUNTIME = None
        _STATUS_OUT = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dolt-binary", default="/usr/local/bin/dolt")
    parser.add_argument("--dolt-version", default="2.1.11")
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--size-bytes", required=True)
    parser.add_argument("--raw-sha256", required=True)
    parser.add_argument("--expected-commit-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument(
        "--fault-point",
        choices=tuple(point.value for point in ImportAdmissionFaultPoint),
        required=True,
    )
    parser.add_argument("--status-out")
    args = parser.parse_args(argv)
    _run_submit_import(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
