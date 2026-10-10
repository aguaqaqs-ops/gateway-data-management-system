"""Submit job integration harness: Repository Service fixture and worker composition."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
import httpx

from gateway_backend.application.submit_jobs import (
    SubmitRuntimeDependencies,
    build_submit_recovery_port,
    submit_composition_bundle,
)
from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
)
from gateway_backend.artifacts.store import ArtifactStorePort, put_with_built_ref
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
)
from gateway_backend.application.submission.artifact_refs import backend_artifact_ref_from_store_ref
from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database, build_worker_runtime
from gateway_backend.operations.worker import WorkerEvent, WorkerObserver
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from gateway_backend.infrastructure.repository_write.terminal_evidence_codec import (
    WireRepositoryTerminalEvidenceDecodePort,
)
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from gateway_backend.settings import OperationWorkerSettings
from tests.support.runtime_settings import make_operation_worker_settings

REPOSITORY_SERVICE_ROOT = Path(__file__).resolve().parents[3] / "repository_service"
STARTER_SCRIPT = Path(__file__).with_name("repository_service_starter.py")
DEFAULT_BEARER_TOKEN = "test-bearer-token"
LIVE_RESTART_OWNER_MANIFEST_DIGEST = (
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)


def _repository_service_build_package_bytes(
    *,
    manifest: dict[str, object],
    replay_sql: bytes,
) -> bytes:
    for candidate in (REPOSITORY_SERVICE_ROOT / "src", REPOSITORY_SERVICE_ROOT / "tests"):
        path = str(candidate)
        if path not in sys.path:
            sys.path.insert(0, path)
    from test_import_package import build_package_bytes  # type: ignore[import-not-found]

    return build_package_bytes(manifest=manifest, replay_sql=replay_sql)  # type: ignore[no-any-return]


def build_dolt_compatible_prepare_publication(
    *,
    build_input: PrepareImportBuildInput,
    store: ArtifactStorePort,
) -> PrepareImportPublicationResult:
    """Publish a minimal import package known to succeed against live Dolt in integration tests."""

    artifact_store = store
    manifest: dict[str, object] = {
        "package_version": 1,
        "canonicalization_manifest_digest": LIVE_RESTART_OWNER_MANIFEST_DIGEST,
        "tables": [
            {
                "name": "records",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "BIGINT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }
    replay_sql = b"CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
    package_bytes = _repository_service_build_package_bytes(
        manifest=manifest,
        replay_sql=replay_sql,
    )
    manifest_bytes = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    manifest_ref = put_with_built_ref(
        artifact_store,
        manifest_bytes,
        artifact_id=f"manifest-{build_input.submit_attempt_id}",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    )
    package_ref = put_with_built_ref(
        artifact_store,
        package_bytes,
        artifact_id=f"package-{build_input.submit_attempt_id}",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
    )
    checkpoint = PrepareImportCheckpoint(
        schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
        attempt_id=build_input.submit_attempt_id,
        canonicalization_manifest_ref=backend_artifact_ref_from_store_ref(manifest_ref),
        canonicalization_manifest_digest=LIVE_RESTART_OWNER_MANIFEST_DIGEST,
        backend_import_artifact_ref=backend_artifact_ref_from_store_ref(package_ref),
        package_raw_size=package_ref.size_bytes,
        package_raw_sha256=package_ref.raw_sha256.value,
        input_closure_digest=build_input.input_closure_digest,
        builder_mutation_policy=build_input.builder_mutation_policy,
    )
    return PrepareImportPublicationResult(checkpoint=checkpoint, replay=False)


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes


class RecordingTransport(httpx.AsyncBaseTransport):
    """Capture outbound Repository HTTP requests for wire-mapping assertions."""

    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response] | None = None,
    ) -> None:
        self.requests: list[RecordedRequest] = []
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.requests.append(
            RecordedRequest(
                method=request.method,
                url=str(request.url),
                headers={key: value for key, value in request.headers.items()},
                body=bytes(body),
            )
        )
        if self._handler is not None:
            return self._handler(request)
        return default_repository_handler(request)


def default_repository_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/repositories" and request.method == "POST":
        return httpx.Response(
            201,
            json={
                "repository_id": "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
                "default_ref": "main",
                "initial_commit_id": "commit-c0",
            },
            headers={"X-Request-ID": "req-create"},
        )
    if path.endswith("/artifacts") and request.method == "POST":
        return httpx.Response(
            201,
            json={
                "artifact_ref": {
                    "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
                    "media_type": "application/vnd.gateway.repository-import.v1+tar+zstd",
                    "size_bytes": len(request.read()),
                    "raw_sha256": request.headers.get("X-Artifact-SHA256", "a" * 64),
                }
            },
            headers={"X-Request-ID": "req-upload"},
        )
    if path.endswith("/versioned/imports") and request.method == "POST":
        return httpx.Response(
            202,
            json={"operation_id": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11"},
            headers={"X-Request-ID": "req-import"},
        )
    if "/operations/" in path and request.method == "GET":
        operation_id = path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "operation": {
                    "operation_id": operation_id,
                    "status": "SUCCEEDED",
                    "error": None,
                    "result": {
                        "commit_id": "commit-c1",
                        "target_ref": "main",
                        "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
                        "canonicalization_manifest_digest": "sha256:" + "f" * 64,
                        "expected_commit_id": "commit-c0",
                        "completed_verification_policy": "STRUCTURAL",
                        "unknown_type_policy": "REJECT",
                    },
                }
            },
            headers={"X-Request-ID": "req-operation"},
        )
    return httpx.Response(404, json={"code": "NOT_FOUND", "message": "unmapped test route"})


@dataclass(frozen=True, slots=True)
class SeededRepository:
    repository_id: str
    initial_commit_id: str


@dataclass
class RepositoryServiceClient:
    base_url: str
    bearer_token: str
    data_root: Path
    _process: subprocess.Popen[str] | None = None
    _pgid: int | None = None
    _runtime: Any = None
    _server: Any = None
    _thread: Any = None

    def repository_id_factory(self, *, idempotency_key: str = "create-submit-harness") -> SeededRepository:
        return seed_minimal_repository(self, idempotency_key=idempotency_key)

    def write_client(self, *, transport: httpx.AsyncBaseTransport | None = None) -> HttpRepositoryWriteClient:
        return HttpRepositoryWriteClient(
            base_url=self.base_url,
            bearer_token=self.bearer_token,
            transport=transport,
        )

    def close(self) -> None:
        shutdown_repository_service_client(self, preserve_data=False)

    def shutdown(self, *, preserve_data: bool = True) -> None:
        shutdown_repository_service_client(self, preserve_data=preserve_data)


def shutdown_repository_service_client(
    client: RepositoryServiceClient,
    *,
    preserve_data: bool = True,
) -> None:
    """Stop a Repository Service fixture; optionally retain ``data_root`` for restart tests."""

    if client._server is not None:
        client._server.should_exit = True
        if client._thread is not None:
            client._thread.join(timeout=20.0)
        if client._runtime is not None:
            client._runtime.shutdown()
        client._server = None
        client._thread = None
        client._runtime = None
        if preserve_data:
            port_file = client.data_root / "port.json"
            if port_file.is_file():
                port_file.unlink()
        if not preserve_data and client.data_root.exists():
            shutil.rmtree(client.data_root, ignore_errors=True)
        return

    if client._process is None:
        return

    pgid = client._pgid
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if client._process.poll() is not None:
                break
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if client._process.poll() is None:
        client._process.wait(timeout=10.0)
    client._process = None
    client._pgid = None
    if preserve_data:
        port_file = client.data_root / "port.json"
        if port_file.is_file():
            port_file.unlink()
    if not preserve_data and client.data_root.exists():
        shutil.rmtree(client.data_root, ignore_errors=True)


def seed_minimal_repository(
    client: RepositoryServiceClient,
    *,
    idempotency_key: str = "create-submit-harness",
) -> SeededRepository:
    response = httpx.post(
        f"{client.base_url}/v1/repositories",
        headers={
            "Authorization": f"Bearer {client.bearer_token}",
            "Idempotency-Key": idempotency_key,
        },
        timeout=30.0,
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return SeededRepository(
        repository_id=str(payload["repository_id"]),
        initial_commit_id=str(payload["initial_commit_id"]),
    )


def _try_import_service_runtime() -> bool:
    for candidate in (REPOSITORY_SERVICE_ROOT / "src", REPOSITORY_SERVICE_ROOT / "tests"):
        path = str(candidate)
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import fastapi  # noqa: F401
        from gateway_repository_service.runtime import ServiceRuntime  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def _start_inprocess_repository_service(
    tmp_path: Path,
    *,
    bearer_token: str,
) -> RepositoryServiceClient:
    import uvicorn

    from gateway_repository_service.app import create_app  # type: ignore[import-not-found]
    from gateway_repository_service.http.readiness import LifecycleReadiness  # type: ignore[import-not-found]
    from gateway_repository_service.runtime import ServiceRuntime
    from support.lifecycle_harness import lifecycle_settings  # type: ignore[import-not-found]

    settings = lifecycle_settings(tmp_path, bearer_token=bearer_token)
    runtime = ServiceRuntime.start(settings)
    app = create_app(settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=False)
    thread.start()

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if server.started and server.servers and server.servers[0].sockets:
            port = int(server.servers[0].sockets[0].getsockname()[1])
            base_url = f"http://127.0.0.1:{port}"
            try:
                ready = httpx.get(
                    f"{base_url}/readyz",
                    headers={"Authorization": f"Bearer {bearer_token}"},
                    timeout=2.0,
                )
                if ready.status_code == 200:
                    client = RepositoryServiceClient(
                        base_url=base_url,
                        bearer_token=bearer_token,
                        data_root=settings.data_root,
                    )
                    client._runtime = runtime
                    client._server = server
                    client._thread = thread
                    return client
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    server.should_exit = True
    thread.join(timeout=5.0)
    runtime.shutdown()
    raise RuntimeError("in-process repository service did not become ready")


def _repository_service_python() -> Path:
    python = REPOSITORY_SERVICE_ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise RuntimeError(
            "repository_service .venv is missing; run ./vnext/scripts/prepare-dev-dependencies.sh"
        )
    return python


def _start_subprocess_repository_service(
    tmp_path: Path,
    *,
    bearer_token: str,
) -> RepositoryServiceClient:
    data_root = tmp_path / "repository-service"
    data_root.mkdir(parents=True, exist_ok=True)
    port_file = data_root / "port.json"
    command = [
        str(_repository_service_python()),
        str(STARTER_SCRIPT),
        str(data_root),
        bearer_token,
        str(port_file),
    ]
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    pythonpath_parts = [
        str(REPOSITORY_SERVICE_ROOT / "src"),
        str(REPOSITORY_SERVICE_ROOT / "tests"),
        env.get("PYTHONPATH", ""),
    ]
    env["PYTHONPATH"] = os.pathsep.join(part for part in pythonpath_parts if part)
    process = subprocess.Popen(
        command,
        cwd=REPOSITORY_SERVICE_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    pgid = os.getpgid(process.pid)
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if port_file.is_file():
            payload = json.loads(port_file.read_text(encoding="utf-8"))
            return RepositoryServiceClient(
                base_url=str(payload["base_url"]),
                bearer_token=str(payload["bearer_token"]),
                data_root=data_root,
                _process=process,
                _pgid=pgid,
            )
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1.0)
            raise RuntimeError(
                "repository service subprocess exited before publishing port: "
                f"stdout={stdout!r} stderr={stderr!r}"
            )
        time.sleep(0.05)
    process.terminate()
    stdout, stderr = process.communicate(timeout=5.0)
    raise RuntimeError(
        "repository service subprocess did not publish port in time: "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def start_repository_service_client(tmp_path: Path) -> RepositoryServiceClient:
    mode = os.environ.get("GATEWAY_SUBMIT_TEST_REPOSITORY_MODE", "subprocess").lower()
    if mode == "inprocess" and _try_import_service_runtime():
        return _start_inprocess_repository_service(tmp_path, bearer_token=DEFAULT_BEARER_TOKEN)
    return _start_subprocess_repository_service(tmp_path, bearer_token=DEFAULT_BEARER_TOKEN)


@contextmanager
def repository_service_session(tmp_path: Path) -> Iterator[RepositoryServiceClient]:
    client = start_repository_service_client(tmp_path)
    try:
        yield client
    finally:
        if client._server is not None:
            client._server.should_exit = True
            if client._thread is not None:
                client._thread.join(timeout=20.0)
            if client._runtime is not None:
                client._runtime.shutdown()
            if client.data_root.exists():
                shutil.rmtree(client.data_root, ignore_errors=True)
        else:
            client.close()


@dataclass
class SubmitWorkerHarness:
    settings: OperationWorkerSettings
    artifact_store: InMemoryArtifactStore
    submit_deps: SubmitRuntimeDependencies
    definitions: tuple[Any, ...]
    handlers: dict[str, Any]
    payload_decoders: dict[str, Any]
    runtime: Any

    @property
    def db_path(self) -> Path:
        return self.settings.control_db_path


def build_submit_worker_harness(
    tmp_path: Path,
    *,
    repository_base_url: str,
    observer: WorkerObserver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    control_clock: dict[str, datetime] | None = None,
) -> SubmitWorkerHarness:
    tmp_path.mkdir(parents=True, exist_ok=True)
    token_file = tmp_path / "repository-bearer-token"
    token_file.write_text(DEFAULT_BEARER_TOKEN + "\n", encoding="utf-8")
    settings = make_operation_worker_settings(
        tmp_path,
        control_db_path=tmp_path / "control.sqlite3",
        repository_base_url=repository_base_url,
        repository_bearer_token_file=token_file,
    )
    def control_now() -> datetime:
        if control_clock is not None:
            return control_clock["value"]
        return datetime.now(UTC)

    if control_clock is not None:
        settings.control_db_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        from gateway_backend.infrastructure.control_db.database import initialize_and_verify_control_db

        initialize_and_verify_control_db(settings.control_db_path, now=control_now)
    else:
        bootstrap_control_database(settings)
    artifact_store = InMemoryArtifactStore()

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path, now=control_now)

    def read_uow_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path, read_only=True, now=control_now)

    bound_worker_write_uow = build_worker_write_uow_factory(control_transaction_factory)
    submit_deps = SubmitRuntimeDependencies(
        artifact_store=artifact_store,
        publication=SubmitImportPublicationAdapter(),
        repository_write=HttpRepositoryWriteClient(
            base_url=repository_base_url,
            bearer_token=DEFAULT_BEARER_TOKEN,
            transport=transport,
        ),
        terminal_evidence_decode=WireRepositoryTerminalEvidenceDecodePort(),
        control_transaction_factory=control_transaction_factory,
        submission_id_factory=lambda: "sub-test-1",
    )
    submit_definitions, submit_handlers, submit_decoders, bound_submit_deps = (
        submit_composition_bundle(submit_deps)
    )
    def _noop_observer(_event: WorkerEvent) -> None:
        return None

    runtime = build_worker_runtime(
        settings,
        observer=cast(WorkerObserver, observer or _noop_observer),
        job_definitions=submit_definitions,
        handlers=dict(submit_handlers),
        payload_decoders=dict(submit_decoders),
        submit_recovery=build_submit_recovery_port(bound_submit_deps),
        write_uow_factory=bound_worker_write_uow,
        read_uow_factory=read_uow_factory if control_clock is not None else None,
        now_factory=control_now if control_clock is not None else None,
    )
    return SubmitWorkerHarness(
        settings=settings,
        artifact_store=artifact_store,
        submit_deps=bound_submit_deps,
        definitions=submit_definitions,
        handlers=dict(submit_handlers),
        payload_decoders=dict(submit_decoders),
        runtime=runtime,
    )


def submit_step_id(operation_id: str, step_name: str) -> str:
    suffix = {
        SUBMIT_STEP_PREPARE: "1",
        SUBMIT_STEP_SUBMIT: "2",
        SUBMIT_STEP_AWAIT: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


def assert_occupancy_retained(
    db_path: Path,
    *,
    workspace_id: str,
    repository_id: str,
    submit_attempt_id: str,
) -> None:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(repository_id)
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submit_attempt_id == submit_attempt_id
    assert repository_occupancy is not None
    assert repository_occupancy.submit_attempt_id == submit_attempt_id


def assert_occupancy_released(db_path: Path, *, workspace_id: str, repository_id: str) -> None:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(repository_id)
    assert workspace_occupancy is None
    assert repository_occupancy is None
