"""Shared HTTP service harness and measurement helpers for P2-R6-S6 evidence."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

import compression.zstd
import httpx2 as httpx
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]
import uvicorn

from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    SERVICE_NOT_READY_CODE,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_repository_service.app import create_app
from gateway_repository_service.capacity import measure_import_disk_admission
from gateway_repository_service.http.readiness import LifecycleReadiness
from gateway_repository_service.process import process_tree_rss_kib
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings

BEARER_TOKEN = "stage-i-s6-capacity"


@dataclass
class ResourceSample:
    peak_rss_kib: int = 0
    peak_durable_root_bytes: int = 0
    stop: threading.Event = field(default_factory=threading.Event)


def directory_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = Path(root) / name
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def start_sampler(data_root: Path, pid: int) -> tuple[ResourceSample, threading.Thread]:
    sample = ResourceSample()

    def _loop() -> None:
        while not sample.stop.wait(0.2):
            rss = process_tree_rss_kib(pid)
            if rss > sample.peak_rss_kib:
                sample.peak_rss_kib = rss
            used = directory_bytes(data_root)
            if used > sample.peak_durable_root_bytes:
                sample.peak_durable_root_bytes = used

    thread = threading.Thread(target=_loop, name="s6-resource-sampler", daemon=True)
    thread.start()
    return sample, thread


def stop_sampler(sample: ResourceSample, thread: threading.Thread) -> None:
    sample.stop.set()
    thread.join(timeout=2.0)


def settings_snapshot(settings: RepositoryServiceSettings) -> dict[str, int]:
    return {
        "max_upload_bytes": settings.max_upload_bytes,
        "max_decompressed_tar_stream_bytes": settings.max_decompressed_tar_stream_bytes,
        "max_total_expanded_entry_bytes": settings.max_total_expanded_entry_bytes,
        "max_replay_sql_bytes": settings.max_replay_sql_bytes,
        "record_batch_bytes": settings.record_batch_bytes,
        "min_free_disk_bytes": settings.min_free_disk_bytes,
        "import_headroom_bytes": settings.import_headroom_bytes,
        "max_concurrent_uploads": settings.max_concurrent_uploads,
        "max_import_workers": settings.max_import_workers,
        "max_concurrent_row_streams": settings.max_concurrent_row_streams,
    }


def decoded_package_entry_sizes(payload: bytes) -> dict[str, int]:
    tar_bytes = compression.zstd.decompress(payload)
    sizes: dict[str, int] = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            sizes[member.name] = int(member.size)
    return sizes


def package_manifest_tables(payload: bytes) -> list[dict[str, Any]]:
    tar_bytes = compression.zstd.decompress(payload)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        member = archive.extractfile("manifest.json")
        if member is None:
            raise RuntimeError("package is missing manifest.json")
        manifest = json.loads(member.read().decode("utf-8"))
    tables = manifest.get("tables")
    if not isinstance(tables, list) or not tables:
        raise RuntimeError("package manifest has no tables")
    return tables


def _wait_until(condition: Callable[[], bool], *, timeout_seconds: float, message: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise TimeoutError(message)


@dataclass
class RunningService:
    settings: RepositoryServiceSettings
    runtime: ServiceRuntime
    server: uvicorn.Server
    thread: threading.Thread
    base_url: str
    data_root: Path


def start_service(work: Path) -> RunningService:
    data_root = work / "data-root"
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=data_root,
        bearer_token=BEARER_TOKEN,
        catalog_parallel_workers=4,
        metadata_timeout_seconds=180.0,
        import_timeout_seconds=4.0 * 60.0 * 60.0,
        full_scan_timeout_seconds=3600,
    )
    runtime = ServiceRuntime.start(settings)
    app = create_app(settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=False)
    thread.start()

    def _started() -> bool:
        return bool(server.started and server.servers and server.servers[0].sockets)

    try:
        _wait_until(_started, timeout_seconds=15.0, message="uvicorn did not start")
        port = int(server.servers[0].sockets[0].getsockname()[1])
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30.0
        headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
        while time.monotonic() < deadline:
            try:
                with httpx.Client(base_url=base_url, timeout=2.0) as client:
                    response = client.get("/readyz", headers=headers)
                    if response.status_code == 200:
                        return RunningService(
                            settings=settings,
                            runtime=runtime,
                            server=server,
                            thread=thread,
                            base_url=base_url,
                            data_root=data_root,
                        )
            except httpx.HTTPError:
                time.sleep(0.05)
        raise TimeoutError("service did not become ready")
    except Exception:
        stop_service(
            RunningService(
                settings=settings,
                runtime=runtime,
                server=server,
                thread=thread,
                base_url="http://127.0.0.1:0",
                data_root=data_root,
            )
        )
        raise


def stop_service(service: RunningService) -> None:
    service.server.should_exit = True
    service.thread.join(timeout=20.0)
    try:
        service.runtime.dolt_runner.terminate_active_children()
    except Exception:
        pass
    try:
        service.runtime.shutdown()
    except Exception:
        try:
            service.runtime.dolt_runner.terminate_active_children()
        except Exception:
            pass


class ServiceClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 3600.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self._auth = {"Authorization": f"Bearer {BEARER_TOKEN}"}

    def close(self) -> None:
        self._client.close()

    def create_repository(self) -> tuple[UUID, str]:
        response = self._client.post(
            "/v1/repositories",
            headers={**self._auth, "Idempotency-Key": f"create-{uuid4().hex}"},
        )
        if response.status_code != 201:
            raise RuntimeError(f"create repository failed: {response.status_code} {response.text}")
        body = response.json()
        return UUID(body["repository_id"]), str(body["initial_commit_id"])

    def upload_artifact(
        self,
        repository_id: UUID,
        payload: bytes,
        raw_sha256: str,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers={
                **self._auth,
                "Content-Type": REPOSITORY_IMPORT_MEDIA_TYPE,
                "Content-Length": str(len(payload)),
                "Idempotency-Key": f"upload-{uuid4().hex}",
                "X-Artifact-SHA256": raw_sha256,
            },
            content=payload,
        )
        if response.status_code != 201:
            raise RuntimeError(f"upload failed: {response.status_code} {response.text}")
        return response.json()["artifact_ref"]

    def submit_import(
        self,
        repository_id: UUID,
        artifact_ref: dict[str, Any],
        expected_commit_id: str,
    ) -> UUID:
        response = self._client.post(
            f"/v1/repositories/{repository_id}/versioned/imports",
            headers={
                **self._auth,
                "Idempotency-Key": f"import-{uuid4().hex}",
                "Content-Type": "application/json",
            },
            json={
                "repository_id": str(repository_id),
                "artifact_ref": artifact_ref,
                "target_ref": "main",
                "expected_commit_id": expected_commit_id,
                "verification_policy": VerificationPolicy.FULL_SCAN.value,
                "unknown_type_policy": UnknownTypePolicy.REJECT.value,
            },
        )
        if response.status_code != 202:
            raise RuntimeError(f"submit import failed: {response.status_code} {response.text}")
        return UUID(response.json()["operation_id"])

    def wait_operation(self, repository_id: UUID, operation_id: UUID) -> dict[str, Any]:
        deadline = time.monotonic() + 4.0 * 60.0 * 60.0
        delay = 0.05
        while time.monotonic() < deadline:
            response = self._client.get(
                f"/v1/repositories/{repository_id}/operations/{operation_id}",
                headers=self._auth,
            )
            if response.status_code != 200:
                raise RuntimeError(f"get operation failed: {response.status_code} {response.text}")
            operation = response.json()["operation"]
            status = operation["status"]
            if status in {"SUCCEEDED", "FAILED"}:
                return operation
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
        raise TimeoutError(f"operation {operation_id} did not terminate")

    def resolve_main(self, repository_id: UUID) -> str:
        response = self._client.get(
            f"/v1/repositories/{repository_id}/versioned/refs/main",
            headers=self._auth,
        )
        if response.status_code != 200:
            raise RuntimeError(f"resolve main failed: {response.status_code} {response.text}")
        return str(response.json()["commit_id"])

    def get_catalog(self, repository_id: UUID, commit_id: str) -> dict[str, Any]:
        from gateway_repository_contracts import encode_commit_id_path_segment

        encoded = encode_commit_id_path_segment(commit_id)
        response = self._client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog",
            headers=self._auth,
        )
        if response.status_code != 200:
            raise RuntimeError(f"catalog failed: {response.status_code} {response.text}")
        return response.json()

    def stream_table_rows(
        self,
        repository_id: UUID,
        commit_id: str,
        table_name: str,
    ) -> tuple[int, pa.Schema, int, int]:
        from gateway_repository_contracts import encode_commit_id_path_segment

        encoded = encode_commit_id_path_segment(commit_id)
        with self._client.stream(
            "GET",
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
            headers=self._auth,
            params={
                "table_name": table_name,
                "unknown_type_policy": UnknownTypePolicy.REJECT.value,
            },
        ) as response:
            status = response.status_code
            payload = response.read()
        if status != 200:
            raise RuntimeError(f"row stream failed: {status} {payload[:300]!r}")
        reader = pa_ipc.open_stream(io.BytesIO(payload))
        schema = reader.schema
        batches = list(reader)
        rows = sum(batch.num_rows for batch in batches)
        max_batch = max((batch.nbytes for batch in batches), default=0)
        return status, schema, rows, max_batch

    def open_row_stream_raw(
        self,
        repository_id: UUID,
        commit_id: str,
        table_name: str,
    ) -> httpx.Response:
        from gateway_repository_contracts import encode_commit_id_path_segment

        encoded = encode_commit_id_path_segment(commit_id)
        request = self._client.build_request(
            "GET",
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
            headers=self._auth,
            params={
                "table_name": table_name,
                "unknown_type_policy": UnknownTypePolicy.REJECT.value,
            },
        )
        return self._client.send(request, stream=True)


def inspect_arrow_schema(schema: pa.Schema) -> tuple[int, int]:
    unknown = 0
    lossy = 0
    for arrow_field in schema:
        metadata = arrow_field.metadata or {}
        if metadata.get(b"gateway.lossy") == b"true":
            lossy += 1
        if metadata.get(b"gateway.logical_type") in {b"unknown", b"unmappable"}:
            unknown += 1
    return unknown, lossy


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def disk_admission_view(root: Path, settings: RepositoryServiceSettings) -> dict[str, int]:
    admission = measure_import_disk_admission(root, settings)
    return {
        "free_bytes": admission.free_bytes,
        "total_bytes": admission.total_bytes,
        "required_free_bytes": admission.required_free_bytes,
        "admitted": int(admission.admitted),
    }


def leftover_temp_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    leftovers: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            leftovers.append(str(path.relative_to(root)))
    return leftovers


def query_temp_count(data_root: Path) -> int:
    staging_artifacts = data_root / "staging" / "artifacts"
    if not staging_artifacts.is_dir():
        return 0
    return len(list(staging_artifacts.glob("query-*.sql")))


def runtime_resource_view(service: RunningService, pid: int) -> dict[str, int]:
    children = service.runtime.dolt_runner._active_children.snapshot()
    return {
        "rss_kib": process_tree_rss_kib(pid),
        "dolt_child_count": len(children),
        "query_temp_count": query_temp_count(service.data_root),
    }


def wait_runtime_idle(service: RunningService, *, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not service.runtime.dolt_runner._active_children.snapshot():
            return
        time.sleep(0.2)
    raise TimeoutError("dolt children did not drain")


def ninth_stream_code() -> str:
    return SERVICE_NOT_READY_CODE
