"""Helpers for production HTTP shutdown process tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from tests.support.http_workspace_harness import (
    InMemoryBoundedArtifactStore,
    seed_submit_ready_workspace,
)
from tests.support.runtime_settings import (
    TEST_REPOSITORY_TOKEN,
    make_backend_settings,
    prepare_backend_runtime_paths,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
HTTP_SERVER_MODULE = "gateway_backend.bootstrap.http_server"
REPOSITORY_READY_STUB_SCRIPT = Path(__file__).with_name("repository_ready_stub.py")
UNREACHABLE_REPOSITORY_BASE_URL = "http://127.0.0.1:9"


@dataclass(frozen=True, slots=True)
class RepositoryReadyStub:
    process: subprocess.Popen[str]
    base_url: str
    port_file: Path

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def _pythonpath_environment() -> str:
    return os.pathsep.join(
        part
        for part in (
            str(BACKEND_ROOT / "src"),
            os.environ.get("PYTHONPATH"),
        )
        if part
    )


def start_repository_ready_stub(
    tmp_path: Path,
    *,
    bearer_token: str = TEST_REPOSITORY_TOKEN,
) -> RepositoryReadyStub:
    port_file = tmp_path / "repository-ready-stub.json"
    process = subprocess.Popen(
        [sys.executable, str(REPOSITORY_READY_STUB_SCRIPT), bearer_token, str(port_file)],
        env={"PYTHONPATH": _pythonpath_environment(), **os.environ},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("repository ready stub exited before publishing port")
        if port_file.is_file():
            base_url = str(json.loads(port_file.read_text(encoding="utf-8"))["base_url"])
            try:
                response = httpx.get(
                    f"{base_url}/readyz",
                    headers={"Authorization": f"Bearer {bearer_token}"},
                    timeout=1.0,
                )
                if response.status_code == 200:
                    return RepositoryReadyStub(process=process, base_url=base_url, port_file=port_file)
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("repository ready stub did not become ready in time")


@contextmanager
def repository_ready_stub_context(
    tmp_path: Path,
    *,
    bearer_token: str = TEST_REPOSITORY_TOKEN,
) -> Iterator[RepositoryReadyStub]:
    stub = start_repository_ready_stub(tmp_path, bearer_token=bearer_token)
    try:
        yield stub
    finally:
        stub.terminate()


def seed_production_history_compare_ready(tmp_path: Path) -> dict[str, Any]:
    """Seed control DB for production HTTP history compare admission tests."""

    from datetime import UTC, datetime

    from gateway_backend.application.history.compare_jobs import history_compare_job_definitions
    from gateway_backend.application.history.contracts import (
        HistoryCompareAcceptCommand,
        HistoryNodeRef,
        HistoryNodeRefKind,
        PERMISSION_READ_PROJECT_HISTORY,
    )
    from gateway_backend.application.job_definitions import JobDefinitionRegistry
    from gateway_backend.application.submission.finalize_transaction import (
        FinalizeSubmitTransactionRequest,
        finalize_submit_transaction,
    )
    from gateway_backend.domain.submission.review import ReviewAction
    from gateway_backend.http.dependencies import OpenAdmissionGate
    from gateway_backend.http.orchestration.history_compare import accept_compare_operation
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.support.baseline_fixtures import read_authoritative_baseline_head
    from tests.support.history_compare_job_harness import seed_archived_baseline_node
    from tests.support.runtime_settings import (
        TEST_DEVICE_KEY,
        TEST_MAPPING_REPOSITORY_ID,
        TEST_PROJECT_ID,
        prepare_backend_runtime_paths,
        write_session_file,
    )
    from tests.support.workspace_fixtures import make_identity
    from tests.support.table_rules import _runtime_comparison_ruleset_digest
    from tests.test_review_transactions import (
        ReviewSeed,
        _apply_command,
        _apply_review,
        _reviewer_context,
    )
    from tests.test_submit_transactions import (
        TS1,
        _finalize_facts,
        _read_finalize_versions,
        _seed_effect_pending_attempt,
        seed_submit_ready_workspace,
    )

    prepare_backend_runtime_paths(tmp_path)
    write_session_file(tmp_path / "session.json", _production_session_with_history_permission())

    db_path = tmp_path / "control" / "control.sqlite3"
    submit_seed = seed_submit_ready_workspace(
        db_path,
        repository_id=TEST_MAPPING_REPOSITORY_ID,
        device_key=TEST_DEVICE_KEY,
        project_id=TEST_PROJECT_ID,
    )
    attempt = _seed_effect_pending_attempt(db_path, submit_seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=_finalize_facts(submit_seed),
                submission_id="sub-prod-history",
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission("sub-prod-history")
    assert submission is not None
    review_seed = ReviewSeed(
        db_path=db_path,
        submission_id="sub-prod-history",
        workspace_id=submit_seed.workspace.workspace_id,
        repository_id=TEST_MAPPING_REPOSITORY_ID,
        reviewer_context=_reviewer_context(TEST_DEVICE_KEY, TEST_PROJECT_ID),
        submission=submission,
    )
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-prod-history"),
    )

    baseline_head = read_authoritative_baseline_head(db_path, TEST_MAPPING_REPOSITORY_ID)
    node_a = baseline_head.business_baseline_node_id
    node_b = "bn-prod-compare-b"
    seed_archived_baseline_node(
        db_path,
        node_id=node_b,
        commit_id="commit-b",
        created_at_us=2,
        repository_id=TEST_MAPPING_REPOSITORY_ID,
        device_key=TEST_DEVICE_KEY,
        project_id=TEST_PROJECT_ID,
    )

    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    identity = make_identity(
        device_key=TEST_DEVICE_KEY,
        project_id=TEST_PROJECT_ID,
        permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY}),
    )
    result = accept_compare_operation(
        command=HistoryCompareAcceptCommand(
            context=identity,
            idempotency_key="prod-history-compare-seed",
            node_refs=(
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, node_a),
                HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, node_b),
            ),
        ),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(db_path, read_only=read_only),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
        now=datetime(2026, 9, 24, tzinfo=UTC),
    )

    return {
        "operation_id": result.response.operation_id,
        "node_a": node_a,
        "node_b": node_b,
        "baseline_head": baseline_head,
        "db_path": db_path,
    }


def seed_production_submit_ready_workspace(tmp_path: Path) -> dict[str, Any]:
    """Seed control DB and on-disk artifacts for production HTTP submit admission tests."""

    from tests.support.baseline_fixtures import read_authoritative_baseline_head
    from tests.support.runtime_settings import TEST_MAPPING_REPOSITORY_ID

    prepare_backend_runtime_paths(tmp_path)
    db_path = tmp_path / "control" / "control.sqlite3"
    memory_store = InMemoryBoundedArtifactStore()
    seed = seed_submit_ready_workspace(
        db_path,
        memory_store,
        repository_id=TEST_MAPPING_REPOSITORY_ID,
    )
    local_store = LocalArtifactStore(tmp_path / "artifacts")
    for ref in memory_store._registered_refs.values():
        local_store.put(memory_store._store.locate(ref), ref)
    seed["baseline_head"] = read_authoritative_baseline_head(db_path, TEST_MAPPING_REPOSITORY_ID)
    return seed


def _base_http_server_environment(
    tmp_path: Path,
    *,
    repository_base_url: str,
    port_file: Path,
    inflight_barrier_dir: str | None = None,
) -> dict[str, str]:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
        repository_base_url=repository_base_url,
        session_file=tmp_path / "session.json",
        internal_bearer_token_file=tmp_path / "internal-bearer-token",
        provisioned_mapping_file=tmp_path / "provisioned-mapping.json",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = _pythonpath_environment()
    environment["GATEWAY_BACKEND_CONTROL_DB_PATH"] = str(settings.control_db_path)
    environment["GATEWAY_BACKEND_ARTIFACT_ROOT"] = str(settings.artifact_root)
    environment["GATEWAY_BACKEND_REPOSITORY_BASE_URL"] = settings.repository_base_url
    environment["GATEWAY_BACKEND_REPOSITORY_BEARER_TOKEN_FILE"] = str(
        settings.repository_bearer_token_file
    )
    environment["GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE"] = str(
        settings.internal_bearer_token_file
    )
    environment["GATEWAY_BACKEND_SESSION_FILE"] = str(settings.session_file)
    environment["GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE"] = str(settings.provisioned_mapping_file)
    environment["GATEWAY_BACKEND_HTTP_HOST"] = "127.0.0.1"
    environment["GATEWAY_BACKEND_HTTP_LOG_LEVEL"] = "error"
    environment["GATEWAY_BACKEND_HTTP_PORT_FILE"] = str(port_file)
    if inflight_barrier_dir is not None:
        from gateway_backend.http.inflight_barrier import INFLIGHT_BARRIER_ENV

        environment[INFLIGHT_BARRIER_ENV] = inflight_barrier_dir
    return environment


def _production_session_with_history_permission() -> dict[str, object]:
    from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
    from tests.support.runtime_settings import default_session_document

    session_doc = default_session_document()
    sessions_raw = session_doc.get("sessions")
    assert isinstance(sessions_raw, list)
    first_session = sessions_raw[0]
    assert isinstance(first_session, dict)
    permissions_raw = first_session.get("permissions")
    assert isinstance(permissions_raw, list)
    permissions = list(permissions_raw)
    if PERMISSION_READ_PROJECT_HISTORY not in permissions:
        permissions.append(PERMISSION_READ_PROJECT_HISTORY)
    first_session["permissions"] = permissions
    return session_doc


def apply_production_history_session(tmp_path: Path, environment: dict[str, str]) -> None:
    from tests.support.runtime_settings import write_session_file

    session_path = tmp_path / "session.json"
    write_session_file(session_path, _production_session_with_history_permission())
    environment["GATEWAY_BACKEND_SESSION_FILE"] = str(session_path)


def http_server_subprocess_environment(
    tmp_path: Path,
    *,
    port_file: Path,
    repository_base_url: str,
    inflight_barrier_dir: str | None = None,
) -> dict[str, str]:
    return _base_http_server_environment(
        tmp_path,
        repository_base_url=repository_base_url,
        port_file=port_file,
        inflight_barrier_dir=inflight_barrier_dir,
    )


def http_server_unreachable_repository_environment(tmp_path: Path, *, port_file: Path) -> dict[str, str]:
    return _base_http_server_environment(
        tmp_path,
        repository_base_url=UNREACHABLE_REPOSITORY_BASE_URL,
        port_file=port_file,
    )


def wait_for_http_server_ready(port_file: Path, *, timeout_seconds: float = 20.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if port_file.is_file():
            payload = json.loads(port_file.read_text(encoding="utf-8"))
            base_url = str(payload["base_url"])
            try:
                response = httpx.get(f"{base_url}/readyz", timeout=1.0)
                if response.status_code == 200:
                    return base_url
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    raise RuntimeError(f"http server did not publish ready endpoint via {port_file}")


def wait_for_http_server_startup_failure(
    process: subprocess.Popen[str],
    port_file: Path,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if process.returncode == 0:
                raise AssertionError("http server exited successfully without repository readiness")
            return
        if port_file.is_file():
            payload = json.loads(port_file.read_text(encoding="utf-8"))
            base_url = str(payload["base_url"])
            try:
                response = httpx.get(f"{base_url}/readyz", timeout=0.5)
                if response.status_code == 200:
                    raise AssertionError("http server became ready without repository readiness")
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    raise AssertionError("http server did not fail closed within startup timeout")
