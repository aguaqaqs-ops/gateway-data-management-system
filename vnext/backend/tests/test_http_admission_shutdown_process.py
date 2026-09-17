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
    http_server_subprocess_environment,
    http_server_unreachable_repository_environment,
    repository_ready_stub_context,
    seed_production_submit_ready_workspace,
    wait_for_http_server_ready,
    wait_for_http_server_startup_failure,
)
from tests.support.http_workspace_harness import BASELINE_HEAD, TEST_BEARER
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
                            "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
                            "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
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
