"""HTTP integration tests for commit-pinned versioned reads."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx2 as httpx
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway_repository_contracts import VERSIONED_READ_ARROW_MEDIA_TYPE
from gateway_repository_service.arrow_mapping import SqlValueConversionError
from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_read.application import VersionedReadApplication
from gateway_repository_service.versioned_read.arrow_bridge import (
    BRIDGE_REGISTRY,
    ArrowIpcStreamBridge,
    BridgeShutdownError,
    BridgeStreamAbortedError,
)
from gateway_repository_service.versioned_read.provider import CandidateAReadProvider
from support.http_harness import ReadyReadiness, create_test_client
from support.lifecycle_harness import lifecycle_settings
from support.arrow_ipc_assertions import assert_has_stream_eos, assert_lacks_stream_eos
from support.streaming_http_harness import (
    create_async_streaming_client,
    read_first_chunk,
    read_stream_until_error,
    run_async,
    stream_rows,
)

pytestmark = pytest.mark.integration

_LOGGER = logging.getLogger(__name__)

CancellationCallback = Callable[[], bool]


def _patch_gated_open_table_rows(
    env: ReadHttpIntegrationEnvironment,
    *,
    producer_waiting: threading.Event,
    release: threading.Event,
    captured_cancellations: list[CancellationCallback | None],
    worker_exit_barrier: threading.Event | None = None,
) -> None:
    original_open = env.runtime.versioned_read_application.open_table_rows

    def gated_open(*args: Any, **kwargs: Any) -> tuple[Any, Iterator[pa.RecordBatch]]:
        captured_cancellations.append(kwargs.get("cancellation"))
        plan, rows = original_open(*args, **kwargs)
        cancellation = kwargs.get("cancellation")

        def _gated() -> Iterator[pa.RecordBatch]:
            for index, batch in enumerate(rows):
                yield batch
                if index == 0:
                    producer_waiting.set()
                    while not release.wait(timeout=0.05):
                        if cancellation is not None and cancellation():
                            if worker_exit_barrier is not None:
                                worker_exit_barrier.wait()
                            return

        return plan, _gated()

    env.runtime.versioned_read_application.open_table_rows = gated_open  # type: ignore[method-assign]


def _wait_until_pid_reaped(pid: int, *, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} was not reaped")


def _wait_until(condition: Any, *, timeout_seconds: float = 5.0, message: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(message)


@dataclass
class ReadHttpIntegrationEnvironment:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    runtime: ServiceRuntime
    app: FastAPI
    client: TestClient
    repository_id: UUID
    offline: OfflineCliProvider
    read_provider: CandidateAReadProvider
    runner: DoltRunner
    control_store: ControlStore

    def close(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()


def _open_mutation_store(tmp_path: Path) -> MutationStore:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    control_store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
    control_store.close()
    connection = sqlite3.connect(db_path)
    configure_connection(connection)
    return MutationStore(connection)


def _seed_visible_repository(store: MutationStore, repository_id: UUID) -> None:
    scope = IdempotencyScope.for_create()
    key_hash = MutationStore.hash_idempotency_key(f"create-{repository_id}")
    fingerprint = create_repository_fingerprint_v1()
    store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
    effect = store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=repository_id,
    )
    store.mark_succeeded(
        effect.effect_id,
        response_body={
            "repository_id": str(repository_id),
            "default_ref": "main",
            "initial_commit_id": "abc",
        },
    )


def _write_sql(layout: DurableLayout, name: str, sql: str) -> Path:
    path = layout.staging_artifacts / name
    path.write_text(sql, encoding="utf-8")
    return path


def _commit_changes(offline: OfflineCliProvider, marker: str) -> str:
    return offline.commit_marker(marker)


def create_read_http_environment(tmp_path: Path) -> ReadHttpIntegrationEnvironment:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create(settings.data_root)
    repository_id = uuid4()
    published = layout.published_repository(repository_key(repository_id))
    published.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    offline = OfflineCliProvider(settings, layout, published, runner)
    offline.initialize_repository()
    read_provider = CandidateAReadProvider(settings, layout, published, runner)
    db_path = settings.control_db_path
    control_store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
    import_store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    mutation_store = MutationStore(control_store.connection, transaction_lock=control_store.transaction_lock)
    _seed_visible_repository(mutation_store, repository_id)
    application = VersionedReadApplication(
        mutation_store,
        layout,
        lambda _repository_id: read_provider,
    )
    root_lock = MagicMock()
    root_lock.is_held.return_value = True
    provider_gate = MagicMock(spec=OfflineCliCapabilityGate)
    provider_gate.executable_path.return_value = settings.dolt_binary
    runtime = ServiceRuntime(
        settings=settings,
        layout=layout,
        root_lock=root_lock,
        control_store=control_store,
        mutation_store=mutation_store,
        import_store=import_store,
        import_locks=RepositoryLockRegistry(),
        import_worker_pool=MagicMock(),
        versioned_read_application=application,
        dolt_runner=runner,
        provider_gate=provider_gate,
        auth_state=AuthState(bearer_token=settings.resolve_bearer_token()),
        _stopping=threading.Event(),
    )
    from gateway_repository_service.app import create_app

    app = create_app(settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = ReadyReadiness()
    client = create_test_client(app)
    return ReadHttpIntegrationEnvironment(
        settings=settings,
        layout=layout,
        runtime=runtime,
        app=app,
        client=client,
        repository_id=repository_id,
        offline=offline,
        read_provider=read_provider,
        runner=runner,
        control_store=control_store,
    )


def _force_read_http_cleanup(
    env: ReadHttpIntegrationEnvironment,
    *,
    release: threading.Event | None = None,
) -> None:
    if release is not None:
        release.set()
    try:
        BRIDGE_REGISTRY.close_all(env.runner, join_timeout_seconds=30.0)
    except BridgeShutdownError as exc:
        _LOGGER.warning("forced read http cleanup: %s", exc)
    env.runner.terminate_active_children()
    _wait_until(
        lambda: BRIDGE_REGISTRY.snapshot() == (),
        timeout_seconds=10.0,
        message="bridge registry did not drain during forced cleanup",
    )
    _wait_until(
        lambda: env.runner._active_children.snapshot() == (),
        timeout_seconds=10.0,
        message="active children did not drain during forced cleanup",
    )


@pytest.fixture
def read_http_env(tmp_path: Path) -> Iterator[ReadHttpIntegrationEnvironment]:
    ArrowIpcStreamBridge._test_worker_finish_barrier = None
    ArrowIpcStreamBridge._test_close_entered_barrier = None
    ArrowIpcStreamBridge._test_close_completed_barrier = None
    assert BRIDGE_REGISTRY.snapshot() == ()
    environment = create_read_http_environment(tmp_path)
    try:
        yield environment
    finally:
        ArrowIpcStreamBridge._test_worker_finish_barrier = None
        ArrowIpcStreamBridge._test_close_entered_barrier = None
        ArrowIpcStreamBridge._test_close_completed_barrier = None
        _force_read_http_cleanup(environment)
        environment.close()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-bearer-token"}


def test_http_resolve_main(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    c0 = read_http_env.read_provider.read_ref("main")
    response = read_http_env.client.get(
        f"/v1/repositories/{read_http_env.repository_id}/versioned/refs/main",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {"ref_name": "main", "commit_id": c0}


def test_http_c1_c2_catalog_and_rows_are_pinned(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    c0 = env.read_provider.read_ref("main")
    env.offline.replay(
        _write_sql(
            env.layout,
            "c1.sql",
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO items (id, label) VALUES (1, 'c1-value');\n",
        )
    )
    c1 = _commit_changes(env.offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000001")
    env.offline.replay(
        _write_sql(
            env.layout,
            "c2.sql",
            "INSERT INTO items (id, label) VALUES (2, 'c2-value');\n",
        )
    )
    c2 = _commit_changes(env.offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000002")

    c1_catalog = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{c1}/catalog",
        headers=_auth_headers(),
    )
    assert c1_catalog.status_code == 200
    tables = c1_catalog.json()["catalog"]["tables"]
    items = next(table for table in tables if table["name"] == "items")
    assert items["row_count"] == 1

    c2_catalog = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{c2}/catalog",
        headers=_auth_headers(),
    )
    assert next(table for table in c2_catalog.json()["catalog"]["tables"] if table["name"] == "items")["row_count"] == 2

    rows_response = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{c1}/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert rows_response.status_code == 200
    assert rows_response.headers["content-type"].startswith(VERSIONED_READ_ARROW_MEDIA_TYPE)
    decoded = list(pa_ipc.open_stream(rows_response.content))
    assert_has_stream_eos(rows_response.content)
    ids = {int(batch.column("id")[row].as_py()) for batch in decoded for row in range(batch.num_rows)}
    assert ids == {1}
    assert c0 != c1 != c2


def test_http_empty_table_returns_schema_and_zero_batches(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    env.offline.replay(
        _write_sql(
            env.layout,
            "empty.sql",
            "CREATE TABLE empty_items (id BIGINT NOT NULL PRIMARY KEY);\n",
        )
    )
    commit_id = _commit_changes(
        env.offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000003",
    )
    response = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{commit_id}/rows",
        params={"table_name": "empty_items"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert_has_stream_eos(response.content)
    reader = pa_ipc.open_stream(response.content)
    assert reader.schema.names == ["id"]
    assert list(reader) == []


def test_http_rows_decode_known_types_and_stringify_metadata(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    env.offline.replay(
        _write_sql(
            env.layout,
            "types.sql",
            "CREATE TABLE typed (id BIGINT NOT NULL PRIMARY KEY, payload VARCHAR(16) NOT NULL, odd ENUM('a','b'));\n"
            "INSERT INTO typed (id, payload, odd) VALUES (1, 'x', 'a');\n",
        )
    )
    commit_id = _commit_changes(
        env.offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000004",
    )
    response = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{commit_id}/rows",
        params={"table_name": "typed", "unknown_type_policy": "STRINGIFY"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    batch = next(iter(pa_ipc.open_stream(response.content)))
    odd_field = batch.schema.field("odd")
    assert odd_field.metadata is not None
    assert odd_field.metadata.get(b"gateway.sql_type") is not None
    assert odd_field.metadata.get(b"gateway.lossy") == b"true"


@pytest.mark.serial
def test_http_branch_movement_keeps_pinned_rows(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    env.offline.replay(
        _write_sql(
            env.layout,
            "setup.sql",
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO items (id, label) VALUES (1, 'pinned');\n",
        )
    )
    c1 = _commit_changes(env.offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000010")
    env.offline.replay(
        _write_sql(
            env.layout,
            "advance.sql",
            "INSERT INTO items (id, label) VALUES (2, 'moved-main');\n",
        )
    )
    _commit_changes(env.offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000011")
    response = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{c1}/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    ids = {
        int(batch.column("id")[row].as_py())
        for batch in pa_ipc.open_stream(response.content)
        for row in range(batch.num_rows)
    }
    assert ids == {1}


@pytest.mark.serial
def test_http_large_table_emits_multiple_batches(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    column_defs = ", ".join(f"col_{index} BIGINT NOT NULL" for index in range(1, 9))
    inserts = "".join(
        f"INSERT INTO wide (id, {', '.join(f'col_{index}' for index in range(1, 9))}) "
        f"VALUES ({row_id}, {', '.join(str(row_id + index) for index in range(1, 9))});\n"
        for row_id in range(1, 2501)
    )
    env.offline.replay(
        _write_sql(
            env.layout,
            "wide.sql",
            f"CREATE TABLE wide (id BIGINT NOT NULL PRIMARY KEY, {column_defs});\n" + inserts,
        )
    )
    commit_id = _commit_changes(
        env.offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000012",
    )
    response = env.client.get(
        f"/v1/repositories/{env.repository_id}/versioned/commits/{commit_id}/rows",
        params={"table_name": "wide"},
        headers=_auth_headers(),
    )
    batches = list(pa_ipc.open_stream(response.content))
    assert len(batches) > 1
    assert len(batches[0].schema.names) >= 8
    total_rows = sum(batch.num_rows for batch in batches)
    assert total_rows == 2500


def _rows_url(env: ReadHttpIntegrationEnvironment, commit_id: str) -> str:
    return f"/v1/repositories/{env.repository_id}/versioned/commits/{commit_id}/rows"


def _seed_large_items_table(env: ReadHttpIntegrationEnvironment, *, sql_name: str, marker_suffix: str) -> str:
    inserts = "".join(f"INSERT INTO items (id, label) VALUES ({index}, 'v{index}');\n" for index in range(1, 2501))
    env.offline.replay(
        _write_sql(
            env.layout,
            sql_name,
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n" + inserts,
        )
    )
    return _commit_changes(
        env.offline,
        f"gateway-versioned-import operation_id=00000000-0000-4000-8000-0000000000{marker_suffix}",
    )


@pytest.mark.serial
def test_http_midstream_failure_aborts_transport(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    commit_id = _seed_large_items_table(env, sql_name="fail.sql", marker_suffix="13")
    original_open = env.runtime.versioned_read_application.open_table_rows

    def exploding_open(*args: Any, **kwargs: Any) -> tuple[Any, Iterator[pa.RecordBatch]]:
        plan, rows = original_open(*args, **kwargs)

        def _explode() -> Iterator[pa.RecordBatch]:
            for index, batch in enumerate(rows):
                yield batch
                if index == 0:
                    raise SqlValueConversionError(table="items", column="label", sql_type="VARCHAR(32)")

        return plan, _explode()

    env.runtime.versioned_read_application.open_table_rows = exploding_open  # type: ignore[method-assign]

    async def exercise() -> tuple[int, bytes, BaseException | None]:
        async with create_async_streaming_client(env.app) as client:
            return await read_stream_until_error(
                client,
                path=_rows_url(env, commit_id),
                params={"table_name": "items"},
                headers=_auth_headers(),
            )

    status_code, body, error = run_async(exercise())
    assert status_code == 200
    assert body
    assert_lacks_stream_eos(body)
    assert error is not None
    if not isinstance(error, BridgeStreamAbortedError):
        assert isinstance(error, (httpx.ReadError, httpx.RemoteProtocolError, RuntimeError))


@pytest.mark.serial
def test_http_disconnect_cancels_worker_and_cleans_query_files(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    commit_id = _seed_large_items_table(env, sql_name="cancel.sql", marker_suffix="14")
    producer_waiting = threading.Event()
    release = threading.Event()
    worker_can_finish = threading.Event()
    close_entered = threading.Event()
    close_completed = threading.Event()
    observed_pids: list[int] = []
    captured_cancellations: list[CancellationCallback | None] = []
    disconnect_errors: list[BaseException] = []
    disconnect_done = threading.Event()
    ArrowIpcStreamBridge._test_worker_finish_barrier = worker_can_finish
    ArrowIpcStreamBridge._test_close_entered_barrier = close_entered
    ArrowIpcStreamBridge._test_close_completed_barrier = close_completed
    try:
        _patch_gated_open_table_rows(
            env,
            producer_waiting=producer_waiting,
            release=release,
            captured_cancellations=captured_cancellations,
        )

        def disconnect_in_background() -> None:
            try:

                async def exercise() -> None:
                    async with create_async_streaming_client(env.app) as client:
                        response = await stream_rows(
                            client,
                            path=_rows_url(env, commit_id),
                            params={"table_name": "items"},
                            headers=_auth_headers(),
                        )
                        assert response.status_code == 200
                        first_chunk = await read_first_chunk(response)
                        assert first_chunk
                        observed_pids.extend(
                            process.pid for process in env.runner._active_children.snapshot()
                        )
                        await response.aclose()
                        disconnect_done.set()

                run_async(exercise())
            except BaseException as exc:
                disconnect_errors.append(exc)

        disconnect_thread = threading.Thread(target=disconnect_in_background)
        disconnect_thread.start()
        assert producer_waiting.wait(timeout=10.0)
        _wait_until(
            lambda: bool(
                captured_cancellations
                and captured_cancellations[0] is not None
                and captured_cancellations[0]()
            ),
            timeout_seconds=15.0,
            message="disconnect did not set cancellation",
        )
        assert close_entered.wait(timeout=15.0), "response close did not enter bridge cleanup"
        assert not close_completed.wait(timeout=0.5), "bridge cleanup finished before worker release"
        assert not disconnect_done.is_set(), "response close returned before worker cleanup finished"
        assert BRIDGE_REGISTRY.snapshot() != ()
        worker_can_finish.set()
        assert close_completed.wait(timeout=15.0), "bridge cleanup did not finish after worker release"
        disconnect_thread.join(timeout=30.0)
        if disconnect_errors:
            raise disconnect_errors[0]
        assert disconnect_done.is_set()
        _wait_until(
            lambda: BRIDGE_REGISTRY.snapshot() == (),
            timeout_seconds=10.0,
            message="versioned read bridge worker did not exit after disconnect",
        )
        _wait_until(
            lambda: env.runner._active_children.snapshot() == (),
            timeout_seconds=10.0,
            message="dolt child processes were not reaped after disconnect",
        )
        for process in observed_pids:
            _wait_until_pid_reaped(process)
        query_dir = env.layout.staging_artifacts
        assert list(query_dir.glob("query-*.sql")) == []
    finally:
        worker_can_finish.set()
        close_completed.set()
        ArrowIpcStreamBridge._test_worker_finish_barrier = None
        ArrowIpcStreamBridge._test_close_entered_barrier = None
        ArrowIpcStreamBridge._test_close_completed_barrier = None


@pytest.mark.serial
def test_http_runtime_shutdown_closes_active_row_stream(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    commit_id = _seed_large_items_table(env, sql_name="shutdown.sql", marker_suffix="15")
    first_chunk_received = threading.Event()
    shutdown_complete = threading.Event()
    consumer_done = threading.Event()
    consumer_errors: list[BaseException] = []

    async def consume_shutdown_stream() -> None:
        async with create_async_streaming_client(env.app) as client:
            response = await stream_rows(
                client,
                path=_rows_url(env, commit_id),
                params={"table_name": "items"},
                headers=_auth_headers(),
            )
            assert response.status_code == 200
            async for chunk in response.aiter_bytes():
                if chunk:
                    first_chunk_received.set()
                    break
            await asyncio.to_thread(shutdown_complete.wait, 15.0)
            await response.aclose()

    def consume() -> None:
        try:
            run_async(consume_shutdown_stream())
        except BaseException as exc:
            consumer_errors.append(exc)
        finally:
            consumer_done.set()

    consumer = threading.Thread(target=consume)
    consumer.start()
    assert first_chunk_received.wait(timeout=10.0)
    bridges = BRIDGE_REGISTRY.snapshot()
    assert len(bridges) == 1
    bridge = bridges[0]
    assert not bridge._cancellation.is_set()
    env.runtime.shutdown()
    assert BRIDGE_REGISTRY.snapshot() == ()
    assert not bridge.is_worker_alive()
    assert env.runner._active_children.snapshot() == ()
    shutdown_complete.set()
    consumer.join(timeout=15.0)
    assert consumer_done.is_set()
    assert not consumer.is_alive()


@pytest.mark.serial
def test_http_disconnect_does_not_break_concurrent_stream(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    commit_id = _seed_large_items_table(env, sql_name="concurrent-disconnect.sql", marker_suffix="17")
    producer_waiting = threading.Event()
    release = threading.Event()
    captured_cancellations: list[CancellationCallback | None] = []
    disconnect_errors: list[BaseException] = []
    disconnect_done = threading.Event()
    _patch_gated_open_table_rows(
        env,
        producer_waiting=producer_waiting,
        release=release,
        captured_cancellations=captured_cancellations,
    )

    def disconnect_in_background() -> None:
        try:

            async def exercise() -> None:
                async with create_async_streaming_client(env.app) as client:
                    response = await stream_rows(
                        client,
                        path=_rows_url(env, commit_id),
                        params={"table_name": "items"},
                        headers=_auth_headers(),
                    )
                    assert response.status_code == 200
                    first_chunk = await read_first_chunk(response)
                    assert first_chunk
                    await response.aclose()
                    disconnect_done.set()

            run_async(exercise())
        except BaseException as exc:
            disconnect_errors.append(exc)

    disconnect_thread = threading.Thread(target=disconnect_in_background)
    disconnect_thread.start()
    try:
        assert producer_waiting.wait(timeout=10.0)
        _wait_until(
            lambda: bool(
                captured_cancellations
                and captured_cancellations[0] is not None
                and captured_cancellations[0]()
            ),
            timeout_seconds=15.0,
            message="disconnect did not set cancellation",
        )
    finally:
        release.set()
        disconnect_thread.join(timeout=30.0)
    if disconnect_errors:
        raise disconnect_errors[0]
    assert disconnect_done.is_set()
    _wait_until(
        lambda: BRIDGE_REGISTRY.snapshot() == (),
        timeout_seconds=10.0,
        message="versioned read bridge worker did not exit after disconnect",
    )

    response = env.client.get(
        _rows_url(env, commit_id),
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    total_rows = sum(batch.num_rows for batch in pa_ipc.open_stream(response.content))
    assert total_rows == 2500


@pytest.mark.serial
def test_http_concurrent_row_streams_do_not_interfere(read_http_env: ReadHttpIntegrationEnvironment) -> None:
    env = read_http_env
    inserts = "".join(f"INSERT INTO items (id, label) VALUES ({index}, 'v{index}');\n" for index in range(1, 2501))
    env.offline.replay(
        _write_sql(
            env.layout,
            "concurrent.sql",
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n" + inserts,
        )
    )
    commit_id = _commit_changes(
        env.offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000016",
    )
    row_counts: list[int | None] = [None, None]
    errors: list[BaseException] = []

    def read_all_rows(index: int) -> None:
        try:
            response = env.client.get(
                f"/v1/repositories/{env.repository_id}/versioned/commits/{commit_id}/rows",
                params={"table_name": "items"},
                headers=_auth_headers(),
            )
            assert response.status_code == 200
            batches = list(pa_ipc.open_stream(response.content))
            row_counts[index] = sum(batch.num_rows for batch in batches)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=read_all_rows, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30.0)
        assert not thread.is_alive()
    if errors:
        raise errors[0]
    assert row_counts == [2500, 2500]
    _wait_until(
        lambda: env.runner._active_children.snapshot() == (),
        timeout_seconds=10.0,
        message="dolt child processes were not reaped after concurrent reads",
    )
