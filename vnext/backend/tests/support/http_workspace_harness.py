"""Test harness for 5A workspace HTTP contract tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.app import create_app
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.preview_jobs import preview_job_definitions
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.artifacts.bounded_store import (
    BoundedArtifactStorePort,
    CleanupClassification,
    CleanupDecision,
    DeleteDisposition,
    VerifyReadableResult,
)
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    PreviewAcceptanceRecord,
    PreviewResult,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)
from gateway_backend.http.auth import BearerSessionPort
from gateway_backend.http.dependencies import (
    OpenAdmissionGate,
    ReadOnlyOperationStore,
    WorkspaceHttpDependencies,
)
from gateway_backend.http.wiring import register_workspace_http
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    MutableBaselineHeadReadPort,
    make_baseline_head,
    make_identity,
)

TEST_BEARER = "test-session-token"
TEST_BEARER_LIMITED = "limited-session-token"
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


class InMemoryBoundedArtifactStore:
    """Minimal BoundedArtifactStorePort backed by InMemoryArtifactStore."""

    def __init__(self, store: InMemoryArtifactStore | None = None) -> None:
        self._store = store or InMemoryArtifactStore()
        self._counter = 0

    def put_stream(
        self,
        kind: str,
        stream: Iterable[bytes],
        *,
        declared_size: int,
        declared_raw_sha256: DigestRef,
        media_type: str,
    ) -> ArtifactRef:
        raw_bytes = b"".join(stream)
        if len(raw_bytes) != declared_size:
            raise ValueError("declared_size mismatch")
        digest = raw_blob_digest(raw_bytes)
        if digest.value != declared_raw_sha256.value:
            raise ValueError("declared_raw_sha256 mismatch")
        self._counter += 1
        ref = ArtifactRef(
            artifact_id=f"{kind}-{self._counter}",
            media_type=media_type,
            size_bytes=len(raw_bytes),
            raw_sha256=digest,
        )
        return self._store.put(raw_bytes, ref)

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        yield self._store.locate(ref)

    def verify_readable(
        self,
        ref: ArtifactRef,
        *,
        expected_size: int,
        expected_raw_sha256: DigestRef,
    ) -> VerifyReadableResult:
        try:
            raw_bytes = self._store.locate(ref)
        except Exception:
            return VerifyReadableResult(verified=False, reason="missing")
        if len(raw_bytes) != expected_size:
            return VerifyReadableResult(verified=False, reason="size mismatch")
        if raw_blob_digest(raw_bytes).value != expected_raw_sha256.value:
            return VerifyReadableResult(verified=False, reason="digest mismatch")
        return VerifyReadableResult(verified=True)

    def set_protection(
        self,
        refs: Iterable[ArtifactRef],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool:
        del refs, owner_kind, owner_id, intent
        return True

    def classify_cleanup(self, ref: ArtifactRef, now: datetime) -> CleanupDecision:
        del ref
        return CleanupDecision(classification=CleanupClassification.ELIGIBLE_AFTER, eligible_after=now)

    def delete_eligible(
        self,
        ref: ArtifactRef,
        *,
        expected_classification: CleanupClassification,
        now: datetime,
    ) -> DeleteDisposition:
        del ref, expected_classification, now
        return DeleteDisposition.ABSENT


class InMemoryBundleReader:
    def __init__(self, bundles: dict[str, tuple[str, bytes]] | None = None) -> None:
        self._bundles = dict(bundles or {})

    def register(self, artifact_id: str, logical_name: str, payload: bytes) -> None:
        self._bundles[artifact_id] = (logical_name, payload)

    def read_bundle(self, artifact_id: str) -> tuple[str, Iterator[bytes]]:
        try:
            logical_name, payload = self._bundles[artifact_id]
        except KeyError:
            raise KeyError(artifact_id)
        return logical_name, iter([payload])


class SqliteWorkspaceRepositoryFacade:
    """WorkspaceRepository that opens one transaction per call."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _read_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self._db_path, read_only=True)

    def _write_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self._db_path)

    def find_open_by_scope(self, scope: WorkspaceScope) -> Workspace | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_open_by_scope(scope)

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_workspace(workspace_id)

    def get_upload_revision(self, upload_revision_id: str) -> UploadRevision | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_upload_revision(upload_revision_id)

    def get_preview_result(self, preview_result_id: str) -> PreviewResult | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_preview_result(preview_result_id)

    def find_upload_idempotency(self, workspace_id: str, idempotency_key: str) -> UploadRevision | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_upload_idempotency(workspace_id, idempotency_key)

    def find_preview_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> PreviewAcceptanceRecord | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_preview_idempotency(workspace_id, idempotency_key)

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        with self._write_uow() as unit_of_work:
            return unit_of_work.workspace.save_workspace(workspace, expected_version=expected_version)

    def save_upload_revision(self, revision: UploadRevision) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_upload_revision(revision)

    def save_preview_result(self, result: PreviewResult) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_result(result)

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_acceptance(record)


def preview_job_registry() -> JobDefinitionRegistry:
    return JobDefinitionRegistry.build(preview_job_definitions())


@dataclass
class WorkspaceHttpTestEnvironment:
    client: TestClient
    db_path: Path
    repository: SqliteWorkspaceRepositoryFacade
    artifact_store: InMemoryBoundedArtifactStore
    bundle_reader: InMemoryBundleReader
    baseline_head_read: MutableBaselineHeadReadPort
    identity: IdentityContext
    now: Callable[[], datetime]

    def auth_headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {TEST_BEARER}"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers


def create_workspace_http_environment(
    tmp_path: Path,
    *,
    identity: IdentityContext | None = None,
    admission_open: bool = True,
    include_preview_registry: bool = True,
    extra_sessions: dict[str, IdentityContext] | None = None,
    now: Callable[[], datetime] | None = None,
) -> WorkspaceHttpTestEnvironment:
    db_path = tmp_path / "control.db"
    initialize_control_db(db_path)
    resolved_identity = identity or make_identity()
    sessions = {TEST_BEARER: resolved_identity}
    if extra_sessions:
        sessions.update(extra_sessions)
    scope_resolution = FixedScopeResolutionPort(
        repository_id="repo-1",
        baseline_head=BASELINE_HEAD,
    )
    baseline_head_read = MutableBaselineHeadReadPort({"repo-1": BASELINE_HEAD})
    repository = SqliteWorkspaceRepositoryFacade(db_path)
    artifact_store = InMemoryBoundedArtifactStore()
    bundle_reader = InMemoryBundleReader()

    def unit_of_work_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(db_path)

    operation_reader = ReadOnlyOperationStore(unit_of_work_factory)

    class _AdmissionGate:
        def allows_new_work(self) -> bool:
            return admission_open

    def fixed_now() -> datetime:
        return FIXED_NOW

    clock = now if now is not None else fixed_now

    deps = WorkspaceHttpDependencies(
        session_port=BearerSessionPort(sessions),
        scope_resolution=scope_resolution,
        baseline_head_read=baseline_head_read,
        workspace_repository=repository,
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=cast(BoundedArtifactStorePort, artifact_store),
        job_registry=preview_job_registry() if include_preview_registry else JobDefinitionRegistry.build(()),
        bundle_reader=bundle_reader,
        admission_gate=_AdmissionGate() if not admission_open else OpenAdmissionGate(),
        operation_reader=operation_reader,
        now=clock,
    )
    app = create_app(workspace_http=deps)
    return WorkspaceHttpTestEnvironment(
        client=TestClient(app, raise_server_exceptions=False),
        db_path=db_path,
        repository=repository,
        artifact_store=artifact_store,
        bundle_reader=bundle_reader,
        baseline_head_read=baseline_head_read,
        identity=resolved_identity,
        now=clock,
    )


def create_test_http_app_without_routes(
    tmp_path: Path,
    deps: WorkspaceHttpDependencies,
) -> FastAPI:
    del tmp_path
    app = FastAPI(title="Gateway Backend vNext")
    register_workspace_http(app, deps)
    return app
