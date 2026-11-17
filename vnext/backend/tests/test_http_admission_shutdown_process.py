"""Serial process evidence for production HTTP admission-first shutdown."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from gateway_backend.device_identity import device_route_key
from tests.support.http_inflight_read_barrier import HttpInflightReadBarrier
from tests.support.http_shutdown_harness import (
    HTTP_SERVER_MODULE,
    apply_production_history_session,
    http_server_subprocess_environment,
    http_server_unreachable_repository_environment,
    repository_ready_stub_context,
    seed_production_history_compare_ready,
    seed_production_submit_ready_workspace,
    wait_for_http_server_ready,
    wait_for_http_server_startup_failure,
)
from tests.support.http_workspace_harness import TEST_BEARER
from tests.support.runtime_settings import (
    TEST_DEVICE_KEY,
    TEST_INTERNAL_BEARER_TOKEN,
    TEST_REPOSITORY_TOKEN,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_http_server_subprocess_fails_closed_when_repository_unreachable(tmp_path: Path) -> None:
    port_file = tmp_path / "http-port.json"
    environment = http_server_unreachable_repository_environment(tmp_path, port_file=port_file)
    process = subprocess.Popen(
        [sys.executable, "-m", HTTP_SERVER_MODULE],
        cwd=BACKEND_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_http_server_startup_failure(process, port_file)
        output, _ = process.communicate(timeout=5)
        assert process.returncode != 0
        assert TEST_REPOSITORY_TOKEN not in output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_uvicorn_sigterm_rejects_new_submit_before_exit(tmp_path: Path) -> None:
    seed = seed_production_submit_ready_workspace(tmp_path)
    workspace = seed["workspace"]
    upload = seed["upload_revision"]
    preview = seed["preview_result"]
    baseline_head = seed["baseline_head"]
    port_file = tmp_path / "http-port.json"
    with repository_ready_stub_context(
        tmp_path, storage_layout_file=tmp_path / "artifacts-storage-layout.json"
    ) as repository_stub:
        environment = http_server_subprocess_environment(
            tmp_path,
            port_file=port_file,
            repository_base_url=repository_stub.base_url,
        )
        process = subprocess.Popen(
            [sys.executable, "-m", HTTP_SERVER_MODULE],
            cwd=BACKEND_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            base_url = wait_for_http_server_ready(port_file)
            os.kill(process.pid, signal.SIGTERM)
            deadline = time.monotonic() + 3.0
            ready_status = None
            rejected_status = None
            rejected_body: dict[str, object] | None = None
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    ready = httpx.get(f"{base_url}/readyz", timeout=0.3)
                    ready_status = ready.status_code
                except httpx.HTTPError:
                    pass
                try:
                    rejected = httpx.post(
                        f"{base_url}/v1/workspaces/{workspace.workspace_id}/submit-attempts",
                        headers={
                            "Authorization": f"Bearer {TEST_BEARER}",
                            "X-Gateway-Device-Key": device_route_key(TEST_DEVICE_KEY),
                            "Idempotency-Key": "submit-sigterm-drain",
                        },
                        json={
                            "expected_workspace_version": workspace.optimistic_version,
                            "upload_revision_id": upload.upload_revision_id,
                            "preview_result_id": preview.preview_result_id,
                            "generation": upload.generation,
                            "expected_baseline_node_id": baseline_head.business_baseline_node_id,
                            "expected_baseline_head_version": baseline_head.baseline_head_version,
                            "options": {},
                        },
                        timeout=0.3,
                    )
                    rejected_status = rejected.status_code
                    rejected_body = rejected.json()
                except httpx.HTTPError:
                    pass
                if ready_status == 503 and rejected_status == 429:
                    break
                time.sleep(0.02)
            assert ready_status == 503
            assert rejected_status == 429
            assert rejected_body is not None
            assert rejected_body["code"] == "ADMISSION_LIMIT_REACHED"
            output, _ = process.communicate(timeout=10)
            assert process.returncode in {0, -signal.SIGTERM}
            assert TEST_REPOSITORY_TOKEN not in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def test_maintenance_drain_rejects_compare_and_sigterm_completes_inflight_reads(
    tmp_path: Path,
) -> None:
    seed = seed_production_history_compare_ready(tmp_path)
    operation_id = seed["operation_id"]
    node_a = seed["node_a"]
    node_b = seed["node_b"]
    port_file = tmp_path / "http-port-history.json"
    inflight_barrier = HttpInflightReadBarrier(tmp_path)
    with repository_ready_stub_context(
        tmp_path, storage_layout_file=tmp_path / "artifacts-storage-layout.json"
    ) as repository_stub:
        environment = http_server_subprocess_environment(
            tmp_path,
            port_file=port_file,
            repository_base_url=repository_stub.base_url,
            inflight_barrier_dir=inflight_barrier.barrier_dir_for_env(),
        )
        apply_production_history_session(tmp_path, environment)
        process = subprocess.Popen(
            [sys.executable, "-m", HTTP_SERVER_MODULE],
            cwd=BACKEND_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            base_url = wait_for_http_server_ready(port_file)
            auth_headers = {
                "Authorization": f"Bearer {TEST_BEARER}",
                "X-Gateway-Device-Key": device_route_key(TEST_DEVICE_KEY),
            }
            history_result: dict[str, object] = {}
            operation_result: dict[str, object] = {}
            bundle_result: dict[str, object] = {}

            def read_history() -> None:
                response = httpx.get(
                    f"{base_url}/v1/history",
                    headers=auth_headers,
                    timeout=30.0,
                )
                history_result["status"] = response.status_code

            def read_operation() -> None:
                response = httpx.get(
                    f"{base_url}/v1/history-compares/{operation_id}",
                    headers=auth_headers,
                    timeout=30.0,
                )
                operation_result["status"] = response.status_code

            def read_bundle() -> None:
                response = httpx.get(
                    f"{base_url}/v1/history-compares/{operation_id}/bundle",
                    headers=auth_headers,
                    timeout=30.0,
                )
                bundle_result["status"] = response.status_code
                bundle_result["body"] = response.json()

            in_flight_reads = (
                threading.Thread(target=read_history, name="history-read"),
                threading.Thread(target=read_operation, name="operation-read"),
                threading.Thread(target=read_bundle, name="bundle-read"),
            )
            for thread in in_flight_reads:
                thread.start()

            inflight_barrier.wait_entered(3, timeout_seconds=5.0)

            # Explicit drain closes admission while the HTTP listener remains open.
            # SIGTERM instead closes the listener; it only guarantees in-flight reads.
            drained = httpx.post(
                f"{base_url}/internal/v1/maintenance/drain",
                headers={"Authorization": f"Bearer {TEST_INTERNAL_BEARER_TOKEN}"},
                timeout=5.0,
            )
            assert drained.status_code == 200
            assert drained.json() == {"accepting_new_work": False, "in_flight": 0}
            assert httpx.get(f"{base_url}/readyz", timeout=5.0).status_code == 503
            rejected = httpx.post(
                f"{base_url}/v1/history-compares",
                headers={**auth_headers, "Idempotency-Key": "compare-maintenance-drain"},
                json={
                    "nodes": [
                        {"ref_kind": "baseline_node", "ref_id": node_a},
                        {"ref_kind": "baseline_node", "ref_id": node_b},
                    ]
                },
                timeout=5.0,
            )
            assert rejected.status_code == 409
            assert rejected.json()["code"] == "ADMISSION_CONFLICT"

            os.kill(process.pid, signal.SIGTERM)
            inflight_barrier.wait_drain_started(base_url, process, margin_seconds=1.0)
            inflight_barrier.release()

            for thread in in_flight_reads:
                thread.join(timeout=5.0)
                assert not thread.is_alive()

            assert operation_result.get("status") == 200
            assert history_result.get("status") == 200
            assert bundle_result.get("status") == 404
            bundle_body = bundle_result.get("body")
            assert isinstance(bundle_body, dict)
            assert bundle_body["code"] == "RESOURCE_NOT_FOUND"
            output, _ = process.communicate(timeout=10)
            assert process.returncode in {0, -signal.SIGTERM}
            assert TEST_REPOSITORY_TOKEN not in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
