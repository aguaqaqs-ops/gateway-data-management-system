"""Serial process evidence for production HTTP admission-first shutdown."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

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
from tests.support.runtime_settings import TEST_REPOSITORY_TOKEN

pytestmark = pytest.mark.serial

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
    with repository_ready_stub_context(tmp_path) as repository_stub:
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


def test_uvicorn_sigterm_rejects_new_history_compare_while_reads_remain(tmp_path: Path) -> None:
    seed = seed_production_history_compare_ready(tmp_path)
    operation_id = seed["operation_id"]
    node_a = seed["node_a"]
    node_b = seed["node_b"]
    port_file = tmp_path / "http-port-history.json"
    with repository_ready_stub_context(tmp_path) as repository_stub:
        environment = http_server_subprocess_environment(
            tmp_path,
            port_file=port_file,
            repository_base_url=repository_stub.base_url,
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
            os.kill(process.pid, signal.SIGTERM)
            drain_deadline = time.monotonic() + 3.0
            ready_status = None
            rejected_status = None
            rejected_body: dict[str, object] | None = None
            while time.monotonic() < drain_deadline and process.poll() is None:
                try:
                    ready = httpx.get(f"{base_url}/readyz", timeout=0.3)
                    ready_status = ready.status_code
                except httpx.HTTPError:
                    pass
                try:
                    rejected = httpx.post(
                        f"{base_url}/v1/history-compares",
                        headers={
                            "Authorization": f"Bearer {TEST_BEARER}",
                            "Idempotency-Key": "compare-sigterm-drain",
                        },
                        json={
                            "nodes": [
                                {"ref_kind": "baseline_node", "ref_id": node_a},
                                {"ref_kind": "baseline_node", "ref_id": node_b},
                            ]
                        },
                        timeout=0.3,
                    )
                    rejected_status = rejected.status_code
                    rejected_body = rejected.json()
                except httpx.HTTPError:
                    pass
                if ready_status == 503 and rejected_status == 409:
                    break
                time.sleep(0.02)
            history_status = None
            operation_status = None
            bundle_status = None
            bundle_body: dict[str, object] | None = None
            read_deadline = time.monotonic() + 3.0
            while time.monotonic() < read_deadline and process.poll() is None:
                try:
                    history = httpx.get(
                        f"{base_url}/v1/history",
                        headers={"Authorization": f"Bearer {TEST_BEARER}"},
                        timeout=0.3,
                    )
                    history_status = history.status_code
                except httpx.HTTPError:
                    pass
                try:
                    operation = httpx.get(
                        f"{base_url}/v1/history-compares/{operation_id}",
                        headers={"Authorization": f"Bearer {TEST_BEARER}"},
                        timeout=0.3,
                    )
                    operation_status = operation.status_code
                except httpx.HTTPError:
                    pass
                try:
                    bundle = httpx.get(
                        f"{base_url}/v1/history-compares/{operation_id}/bundle",
                        headers={"Authorization": f"Bearer {TEST_BEARER}"},
                        timeout=0.3,
                    )
                    bundle_status = bundle.status_code
                    bundle_body = bundle.json()
                except httpx.HTTPError:
                    pass
                if (
                    history_status == 200
                    and operation_status == 200
                    and bundle_status == 404
                ):
                    break
                time.sleep(0.02)
            assert ready_status == 503
            assert rejected_status == 409
            assert rejected_body is not None
            assert rejected_body["code"] == "ADMISSION_CONFLICT"
            assert history_status == 200
            assert operation_status == 200
            assert bundle_status == 404
            assert bundle_body is not None
            assert bundle_body["code"] == "RESOURCE_NOT_FOUND"
            output, _ = process.communicate(timeout=10)
            assert process.returncode in {0, -signal.SIGTERM}
            assert TEST_REPOSITORY_TOKEN not in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
