"""Production HTTP runtime composition for 5A readiness and admission."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Request

from gateway_backend.application.preview_registry import (
    assert_preview_registry_ready,
    build_preview_job_registry,
)
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    PreviewAcceptanceRecord,
    PreviewResult,
    ResolvedScope,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)
from gateway_backend.http.auth import LiveFileSessionPort, load_session_file
from gateway_backend.http.dependencies import (
    ClosableAdmissionGate,
    ReadOnlyOperationStore,
    WorkspaceHttpDependencies,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.infrastructure.artifact_store import (
    BoundedArtifactStore,
    LocalArtifactStore,
    validate_artifact_root,
)
from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    initialize_and_verify_control_db,
)
from gateway_backend.infrastructure.control_db.sqlite_mapping import (
    ProvisionedBaselineHeadRead,
    ProvisionedScopeResolution,
    seed_provisioned_mappings,
)
from gateway_backend.infrastructure.repository_read import load_repository_bearer_token
from gateway_backend.settings import BackendSettings


class FailClosedSessionPort:
    """Reject callers until an identity provider is composed outside this slice."""

    def resolve(self, request: Request) -> IdentityContext:
        del request
        raise ApiError(
            code="AUTHENTICATION_REQUIRED",
            message="authentication required",
            status_code=401,
        )


class FailClosedScopeResolution:
    def resolve(self, context: IdentityContext) -> ResolvedScope:
        del context
        raise ScopeResolutionError("provisioned mapping is missing")


class TransactionWorkspaceRepository:
    """WorkspaceRepository that opens one control-DB transaction per call."""

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

    def list_preview_acceptances(self, workspace_id: str) -> tuple[PreviewAcceptanceRecord, ...]:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.list_preview_acceptances(workspace_id)

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_acceptance(record)

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        with self._write_uow() as unit_of_work:
            return unit_of_work.workspace.save_workspace(workspace, expected_version=expected_version)

    def save_upload_revision(self, revision: UploadRevision) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_upload_revision(revision)

    def save_preview_result(self, result: PreviewResult) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_result(result)


class LocalArtifactBundleReader:
    def __init__(self, local_store: LocalArtifactStore) -> None:
        self._local_store = local_store

    def read_bundle(self, artifact_id: str) -> tuple[str, Iterator[bytes]]:
        try:
            ref = self._local_store._load_stored_ref(artifact_id)  # noqa: SLF001
            payload = self._local_store.locate(ref)
        except ManifestVerificationError:
            raise KeyError(artifact_id) from None
        return artifact_id, iter([payload])


@dataclass(frozen=True, slots=True)
class BackendRuntime:
    settings: BackendSettings
    admission_gate: ClosableAdmissionGate
    workspace_http: WorkspaceHttpDependencies


def prepare_backend_runtime(settings: BackendSettings) -> BackendRuntime:
    """Validate settings, SQLite, artifact root, and preview registry before /readyz."""

    load_repository_bearer_token(settings.repository_bearer_token_file)
    load_session_file(settings.session_file)
    validate_artifact_root(settings.artifact_root)
    parent = settings.control_db_path.parent
    parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("control DB parent is not a directory")
    initialize_and_verify_control_db(settings.control_db_path)
    seed_provisioned_mappings(settings.control_db_path, settings.provisioned_mapping_file)
    registry = build_preview_job_registry()
    assert_preview_registry_ready(registry)
    local_store = LocalArtifactStore(settings.artifact_root)

    def is_protected(artifact_id: str) -> bool:
        with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
            return unit_of_work.protection.is_protected(artifact_id)

    artifact_store = BoundedArtifactStore(
        local_store,
        is_protected=is_protected,
        unpinned_ttl=timedelta(seconds=settings.cleanup_unpinned_ttl_seconds),
    )
    admission_gate = ClosableAdmissionGate(limit=settings.http_new_work_limit)

    def unit_of_work_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    workspace_http = WorkspaceHttpDependencies(
        session_port=LiveFileSessionPort(settings.session_file),
        scope_resolution=ProvisionedScopeResolution(settings.control_db_path),
        baseline_head_read=ProvisionedBaselineHeadRead(settings.control_db_path),
        workspace_repository=TransactionWorkspaceRepository(settings.control_db_path),
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=artifact_store,
        job_registry=registry,
        bundle_reader=LocalArtifactBundleReader(local_store),
        admission_gate=admission_gate,
        operation_reader=ReadOnlyOperationStore(unit_of_work_factory),
        now=lambda: datetime.now(UTC),
    )
    return BackendRuntime(
        settings=settings,
        admission_gate=admission_gate,
        workspace_http=workspace_http,
    )


__all__ = [
    "BackendRuntime",
    "ClosableAdmissionGate",
    "FailClosedScopeResolution",
    "FailClosedSessionPort",
    "LocalArtifactBundleReader",
    "TransactionWorkspaceRepository",
    "prepare_backend_runtime",
]
