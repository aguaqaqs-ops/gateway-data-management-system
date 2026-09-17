"""Production HTTP runtime composition for readiness, admission, and submit wiring."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from gateway_repository_client import RepositoryClient

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.preview_jobs import (
    PreviewJobError,
    compute_baseline_canonical_bundle_digest,
    preview_job_definitions,
)
from gateway_backend.application.preview_registry import assert_preview_registry_ready
from gateway_backend.application.submit_jobs import (
    SubmitRuntimeDependencies,
    bind_submit_control_transaction_factory,
    build_submit_operator_recovery_port,
    _read_write_factory,
)
from gateway_backend.application.submit_registry import (
    assert_submit_registry_decoders,
    build_submit_recovery_capability_lookup,
    submit_job_definitions,
)
from gateway_backend.application.submission.accept_transaction import assert_submit_job_registered
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryTableAccessProvider
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    InputCompleteness,
    PreviewAcceptanceRecord,
    PreviewResult,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)
from gateway_backend.http.auth import (
    LiveFileSessionPort,
    StaticInternalBearerPort,
    load_internal_bearer_token,
    load_session_file,
)
from gateway_backend.http.dependencies import (
    ClosableAdmissionGate,
    ReadOnlyOperationStore,
    ReadOnlySubmissionStore,
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
from gateway_backend.infrastructure.repository_read import (
    build_http_repository_provider_factory,
    load_repository_bearer_token,
)
from gateway_backend.infrastructure.repository_write import (
    HttpRepositoryAbortEvidencePort,
    HttpRepositoryWriteClient,
)
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from gateway_backend.settings import BackendSettings

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


class LocalArtifactRefLookup:
    def __init__(self, local_store: LocalArtifactStore) -> None:
        self._local_store = local_store

    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        try:
            return self._local_store._load_stored_ref(artifact_id)  # noqa: SLF001
        except ManifestVerificationError:
            return None


@dataclass(frozen=True, slots=True)
class BackendRuntime:
    settings: BackendSettings
    admission_gate: ClosableAdmissionGate
    workspace_http: WorkspaceHttpDependencies


def build_workspace_job_registry() -> JobDefinitionRegistry:
    """Immutable preview+submit registry shared by HTTP acceptance and the worker."""

    return JobDefinitionRegistry.build(preview_job_definitions() + submit_job_definitions())


def assert_workspace_registry_ready(registry: JobDefinitionRegistry) -> None:
    assert_preview_registry_ready(registry)
    assert_submit_job_registered(registry)
    assert_submit_registry_decoders(registry)


def assert_repository_service_ready(
    base_url: str,
    bearer_token: str,
    *,
    timeout_seconds: float,
) -> None:
    """Fail closed when Repository Service /readyz is unavailable."""

    if type(base_url) is not str or base_url == "":
        raise ValueError("repository base URL is missing")
    if type(bearer_token) is not str or bearer_token == "":
        raise ValueError("repository bearer token is missing")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/readyz",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise ValueError("repository service is not ready")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ValueError("repository service is not ready") from None


class HttpBaselineCanonicalDigestPort:
    def __init__(
        self,
        *,
        provider_factory: Callable[[str, str], RepositoryTableAccessProvider],
    ) -> None:
        self._provider_factory = provider_factory

    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: BaselineHead,
        input_completeness: InputCompleteness,
        ruleset_version: str,
    ) -> str:
        store = InMemoryArtifactStore()
        try:
            return compute_baseline_canonical_bundle_digest(
                repository_id=repository_id,
                baseline_head=baseline_head,
                input_completeness=input_completeness,
                ruleset_version=ruleset_version,
                provider_factory=self._provider_factory,
                store=store,
            )
        except (PreviewJobError, ValueError) as exc:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="baseline canonical digest is unavailable",
                status_code=503,
            ) from exc


class HttpRepositoryMainResolvePort:
    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        client = RepositoryClient(
            base_url=self._base_url,
            bearer_token=self._bearer_token,
            timeout_seconds=self._timeout_seconds,
            transport=self._transport,
        )
        try:
            response = asyncio.run(
                client.resolve_versioned_ref(
                    repository_id=UUID(repository_id),
                    ref_name="main",
                )
            )
        except Exception:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="repository main resolve is unavailable",
                status_code=503,
            ) from None
        return str(response.commit_id)


def prepare_backend_runtime(
    settings: BackendSettings,
    *,
    repository_transport: httpx.AsyncBaseTransport | None = None,
    skip_repository_ready_probe: bool = False,
) -> BackendRuntime:
    """Validate settings, SQLite, artifact root, registry, and Repository readiness before /readyz."""

    repository_token = load_repository_bearer_token(settings.repository_bearer_token_file)
    load_internal_bearer_token(settings.internal_bearer_token_file)
    load_session_file(settings.session_file)
    validate_artifact_root(settings.artifact_root)
    parent = settings.control_db_path.parent
    parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("control DB parent is not a directory")
    initialize_and_verify_control_db(settings.control_db_path)
    seed_provisioned_mappings(settings.control_db_path, settings.provisioned_mapping_file)
    if not skip_repository_ready_probe:
        assert_repository_service_ready(
            settings.repository_base_url,
            repository_token,
            timeout_seconds=settings.repository_timeout_seconds,
        )
    registry = build_workspace_job_registry()
    assert_workspace_registry_ready(registry)
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

    def unit_of_work_factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path, read_only=read_only)

    provider_factory = build_http_repository_provider_factory(
        base_url=settings.repository_base_url,
        bearer_token=repository_token,
        timeout_seconds=settings.repository_timeout_seconds,
        transport=repository_transport,
    )
    write_client = HttpRepositoryWriteClient(
        base_url=settings.repository_base_url,
        bearer_token=repository_token,
        timeout_seconds=settings.repository_timeout_seconds,
        transport=repository_transport,
    )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    submit_deps = SubmitRuntimeDependencies(
        artifact_store=artifact_store,
        publication=SubmitImportPublicationAdapter(),
        repository_write=write_client,
        control_transaction_factory=control_transaction_factory,
        submission_id_factory=lambda: f"sub-{uuid4()}",
    )
    submit_control_uow_factory = bind_submit_control_transaction_factory(control_transaction_factory)
    operator_recovery_port = build_submit_operator_recovery_port(
        write_uow_factory=control_transaction_factory,
        capability_lookup=build_submit_recovery_capability_lookup(registry),
        submit_control_uow_factory=_read_write_factory(submit_control_uow_factory),
        abort_evidence=HttpRepositoryAbortEvidencePort(client=write_client),
        submit_deps=submit_deps,
    )

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
        submission_reader=ReadOnlySubmissionStore(unit_of_work_factory),
        artifact_ref_lookup=LocalArtifactRefLookup(local_store),
        internal_bearer_port=StaticInternalBearerPort(
            load_internal_bearer_token(settings.internal_bearer_token_file)
        ),
        baseline_canonical_digest=HttpBaselineCanonicalDigestPort(
            provider_factory=provider_factory,
        ),
        main_resolve=HttpRepositoryMainResolvePort(
            base_url=settings.repository_base_url,
            bearer_token=repository_token,
            timeout_seconds=settings.repository_timeout_seconds,
            transport=repository_transport,
        ),
        operator_recovery_port=operator_recovery_port,
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
    "HttpBaselineCanonicalDigestPort",
    "HttpRepositoryMainResolvePort",
    "LocalArtifactBundleReader",
    "LocalArtifactRefLookup",
    "TransactionWorkspaceRepository",
    "assert_repository_service_ready",
    "assert_workspace_registry_ready",
    "build_workspace_job_registry",
    "prepare_backend_runtime",
]
