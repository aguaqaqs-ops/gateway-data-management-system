"""Test harness for 5A workspace HTTP contract tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.app import create_app
from gateway_backend.application.job_definitions import (
    JobDefinition,
    JobDefinitionRegistry,
)
from gateway_backend.application.preview_jobs import preview_job_definitions
from gateway_backend.application.submit_registry import submit_job_definitions
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.ports import (
    BaselineCanonicalDigestPort,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.capabilities.table_rules.contracts import RULESET_VERSION
from gateway_backend.application.submission.errors import AbortProofNotSatisfied
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.application.workspace.services import create_or_get_workspace
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
    InputCompleteness,
    PreviewAcceptanceRecord,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)
from gateway_backend.http.auth import BearerSessionPort, StaticInternalBearerPort
from gateway_backend.http.dependencies import (
    AdmissionGatePort,
    ArtifactRefLookupPort,
    FailClosedOperatorRecoveryPort,
    OpenAdmissionGate,
    OperatorRecoveryApplicationPort,
    ReadOnlyOperationStore,
    ReadOnlySubmissionStore,
    WorkspaceHttpDependencies,
)
from gateway_backend.http.wiring import register_workspace_http
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.contracts import OperationDiagnostic
from gateway_backend.operations.recovery import (
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityValue,
    build_authorized_operator_recovery,
)
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    MutableBaselineHeadReadPort,
    make_baseline_head,
    make_identity,
)

TEST_BEARER = "test-session-token"
TEST_BEARER_LIMITED = "limited-session-token"
TEST_INTERNAL_BEARER = "test-internal-bearer"
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
BASELINE_CANONICAL_DIGEST = "sha256:baseline-canonical"
FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
_PAYLOAD_INITIAL = b"a"
_PAYLOAD_MODIFIED = b"ab"
_PAYLOAD_CLOSURE = b"c"
_PAYLOAD_SNAP = b"d"
_SHA_INITIAL = raw_blob_digest(_PAYLOAD_INITIAL).value
_SHA_MODIFIED = raw_blob_digest(_PAYLOAD_MODIFIED).value
_SHA_CLOSURE = raw_blob_digest(_PAYLOAD_CLOSURE).value
_SHA_SNAP = raw_blob_digest(_PAYLOAD_SNAP).value
_PREVIEW_CANONICAL_DIGEST = "sha256:" + "p" * 62 + "ca"


class InMemoryBoundedArtifactStore:
    """Minimal BoundedArtifactStorePort backed by InMemoryArtifactStore."""

    def __init__(self, store: InMemoryArtifactStore | None = None) -> None:
        self._store = store or InMemoryArtifactStore()
        self._counter = 0
        self._registered_refs: dict[str, ArtifactRef] = {}

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

    def drop(self, ref: ArtifactRef) -> None:
        self._store._artifacts.pop(ref.artifact_id, None)  # noqa: SLF001

    def register_bytes(self, ref: ArtifactRef, payload: bytes) -> None:
        if len(payload) != ref.size_bytes:
            raise ValueError("payload size mismatch")
        self._store.put(payload, ref)
        self._registered_refs[ref.artifact_id] = ref

    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        return self._registered_refs.get(artifact_id)

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

    def list_preview_acceptances(self, workspace_id: str) -> tuple[PreviewAcceptanceRecord, ...]:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.list_preview_acceptances(workspace_id)

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


def workspace_job_registry(*, include_preview: bool = True, include_submit: bool = True) -> JobDefinitionRegistry:
    definitions: list[JobDefinition] = []
    if include_preview:
        definitions.extend(preview_job_definitions())
    if include_submit:
        definitions.extend(submit_job_definitions())
    return JobDefinitionRegistry.build(tuple(definitions))


@dataclass
class FakeBaselineCanonicalDigestPort:
    digest: str = BASELINE_CANONICAL_DIGEST

    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: object,
        input_completeness: object,
        ruleset_version: str,
    ) -> str:
        del repository_id, baseline_head, input_completeness, ruleset_version
        return self.digest


@dataclass
class RecordingBaselineCanonicalDigestPort:
    digest: str = BASELINE_CANONICAL_DIGEST
    digest_calls: int = 0

    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: object,
        input_completeness: object,
        ruleset_version: str,
    ) -> str:
        del repository_id, baseline_head, input_completeness, ruleset_version
        self.digest_calls += 1
        return self.digest


@dataclass
class RecordingMainResolvePort:
    commit_id: str = "commit-main"
    resolve_calls: int = 0

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        self.resolve_calls += 1
        return self.commit_id


class FailingMainResolvePort:
    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="DEPENDENCY_UNAVAILABLE",
            message="repository main resolve is unavailable",
            status_code=503,
        )


class LocalOperatorRecoveryPort:
    def __init__(
        self,
        unit_of_work_factory: SubmitControlUnitOfWorkFactory,
        *,
        job_registry: JobDefinitionRegistry,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

        def write_uow_factory() -> ControlDbUnitOfWork:
            return cast(ControlDbUnitOfWork, unit_of_work_factory(read_only=False))

        self._recovery = build_authorized_operator_recovery(
            write_uow_factory=write_uow_factory,
            capability_lookup=_submit_recovery_capability_lookup(job_registry),
        )

    def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        if request.command is OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
            with self._unit_of_work_factory() as unit_of_work:
                operation = unit_of_work.operations.get_operation(request.operation_id)
                step = unit_of_work.operations.get_step(request.step_id)
            if not (
                operation.status is OperationStatus.FAILED and step.status is StepStatus.FAILED
            ):
                raise AbortProofNotSatisfied("repository abort proof is deferred to S5")
        return self._recovery.execute(request)


def _submit_recovery_capability_lookup(
    registry: JobDefinitionRegistry,
) -> Callable[[str, str], RecoveryCapabilityValue]:
    mapping: dict[tuple[str, str], RecoveryCapabilityValue] = {}
    for step_name in (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT):
        definition = registry.resolve_runnable(
            JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=step_name),
            SUBMIT_JOB_CONTRACT_VERSION,
        )
        capability = definition.recovery_capability
        if capability is RecoveryCapability.PURE_RECOMPUTE:
            mapped = RecoveryCapabilityValue.PURE_RECOMPUTE
        elif capability is RecoveryCapability.EXTERNAL_EFFECT:
            mapped = RecoveryCapabilityValue.EXTERNAL_EFFECT
        else:
            mapped = RecoveryCapabilityValue.NON_RETRYABLE
        mapping[(SUBMIT_JOB_KIND, step_name)] = mapped

    def lookup(job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        return mapping[(job_kind, step_name)]

    return lookup


def _seed_provisioned_mapping(db_path: Path, *, repository_id: str = "repo-1") -> None:
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head

    seed_provisioned_mapping_with_head(
        db_path,
        repository_id=repository_id,
        baseline_head=BASELINE_HEAD,
    )


def _protected_preview_refs() -> tuple[ArtifactRef, ...]:
    return (
        ArtifactRef(
            artifact_id="initial-1",
            media_type="application/gzip",
            size_bytes=len(_PAYLOAD_INITIAL),
            raw_sha256=DigestRef(_SHA_INITIAL),
        ),
        ArtifactRef(
            artifact_id="modified-1",
            media_type="application/gzip",
            size_bytes=len(_PAYLOAD_MODIFIED),
            raw_sha256=DigestRef(_SHA_MODIFIED),
        ),
        ArtifactRef(
            artifact_id="closure-1",
            media_type="application/json",
            size_bytes=len(_PAYLOAD_CLOSURE),
            raw_sha256=DigestRef(_SHA_CLOSURE),
        ),
        ArtifactRef(
            artifact_id="snap-1",
            media_type="application/octet-stream",
            size_bytes=len(_PAYLOAD_SNAP),
            raw_sha256=DigestRef(_SHA_SNAP),
        ),
    )


def seed_submit_ready_workspace(
    db_path: Path,
    artifact_store: InMemoryBoundedArtifactStore,
    *,
    repository_id: str = "repo-1",
) -> dict[str, Any]:
    from tests.support.baseline_fixtures import read_authoritative_baseline_head

    _seed_provisioned_mapping(db_path, repository_id=repository_id)
    baseline_head = read_authoritative_baseline_head(db_path, repository_id)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=repository_id,
        baseline_head=baseline_head,
    )
    context = make_identity(permissions=frozenset({"upload_submit_workspace", "workspace_read"}))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )
        workspace = created.workspace
        upload_revision = UploadRevision(
            upload_revision_id="ur-1",
            workspace_id=workspace.workspace_id,
            generation=1,
            input_completeness=InputCompleteness.FULL,
            source_artifacts={
                SourceArtifactRole.INITIAL: SourceArtifactBinding(
                    artifact_id="initial-1",
                    media_type="application/gzip",
                    size_bytes=len(_PAYLOAD_INITIAL),
                    raw_sha256=_SHA_INITIAL,
                ),
                SourceArtifactRole.MODIFIED: SourceArtifactBinding(
                    artifact_id="modified-1",
                    media_type="application/gzip",
                    size_bytes=len(_PAYLOAD_MODIFIED),
                    raw_sha256=_SHA_MODIFIED,
                ),
            },
            idempotency_key="upload-key",
            request_fingerprint="fp-upload",
            created_by="actor-1",
            created_at=TS0,
        )
        preview = PreviewResult(
            preview_result_id="pr-1",
            workspace_id=workspace.workspace_id,
            upload_revision_id=upload_revision.upload_revision_id,
            generation=1,
            repository_id=repository_id,
            business_baseline_node_id=baseline_head.business_baseline_node_id,
            business_baseline_commit_id=baseline_head.business_baseline_commit_id,
            baseline_head_version=baseline_head.baseline_head_version,
            ruleset_version=RULESET_VERSION,
            contract_version="contract-1",
            provider_versions={"comparison": "v1"},
            digests=PreviewResultDigests(
                source_digest="d-source",
                input_digest="d-input",
                snapshot_digest="d-snapshot",
                comparison_digest="d-comparison",
                risk_digest="d-risk",
                surface_digest="d-surface",
                bundle_digest=_PREVIEW_CANONICAL_DIGEST,
            ),
            bundle_artifact_id="bundle-1",
            ready_closure_artifact_id="closure-1",
            operation_id="op-preview-1",
            created_at=TS1,
        )
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated_workspace = replace(
            workspace,
            repository_id=repository_id,
            generation=1,
            optimistic_version=workspace.optimistic_version + 1,
            current_upload_revision_id=upload_revision.upload_revision_id,
            current_preview_result_id=preview.preview_result_id,
            updated_at=TS1,
        )
        unit_of_work.workspace.save_workspace(
            updated_workspace,
            expected_version=workspace.optimistic_version,
        )
        preview_operation_id = preview.operation_id
        protected_refs = _protected_preview_refs()
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=updated_workspace.workspace_id,
            intent="current-preview",
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="preview-operation",
            owner_id=preview_operation_id,
            intent="preview-operation",
        )

    payload_by_id = {
        "initial-1": _PAYLOAD_INITIAL,
        "modified-1": _PAYLOAD_MODIFIED,
        "closure-1": _PAYLOAD_CLOSURE,
        "snap-1": _PAYLOAD_SNAP,
    }
    for ref in protected_refs:
        artifact_store.register_bytes(ref, payload_by_id[ref.artifact_id])

    return {
        "workspace": updated_workspace,
        "upload_revision": upload_revision,
        "preview_result": preview,
        "preview_operation_id": preview_operation_id,
    }


def promote_submit_recovery_target(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    when: datetime = FIXED_NOW,
) -> None:
    from datetime import timedelta

    diagnostic = OperationDiagnostic(
        code="MANUAL",
        message="manual recovery required for test",
    )
    lease_expires_at = datetime.now(UTC) + timedelta(hours=1)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        if operation.status is OperationStatus.QUEUED:
            running_operation = replace(
                operation,
                status=OperationStatus.RUNNING,
                updated_at=when,
                optimistic_version=operation.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_operation(
                running_operation,
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            operation = running_operation

        step = unit_of_work.operations.get_step(step_id)
        if step.status is StepStatus.PENDING:
            running_step = replace(
                step,
                status=StepStatus.RUNNING,
                attempt_count=1,
                started_at=when,
                updated_at=when,
                worker_id="worker-test",
                lease_token="lease-test",
                lease_expires_at=lease_expires_at,
                optimistic_version=step.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_step(
                running_step,
                WritePrecondition(
                    expected_optimistic_version=step.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            step = running_step

        if step.status is StepStatus.RUNNING:
            recovery_step = replace(
                step,
                status=StepStatus.MANUAL_RECOVERY_REQUIRED,
                diagnostic=diagnostic,
                updated_at=when,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                optimistic_version=step.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_step(
                recovery_step,
                WritePrecondition(
                    expected_optimistic_version=step.optimistic_version,
                    worker_id=step.worker_id,
                    lease_token=step.lease_token,
                ),
            )

        if operation.status is OperationStatus.RUNNING:
            recovery_operation = replace(
                operation,
                status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
                diagnostic=diagnostic,
                updated_at=when,
                optimistic_version=operation.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_operation(
                recovery_operation,
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )


def promote_submit_terminal_failed(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    when: datetime = FIXED_NOW,
) -> None:
    from datetime import timedelta

    diagnostic = OperationDiagnostic(code="FAILED", message="terminal failure for test")
    lease_expires_at = datetime.now(UTC) + timedelta(hours=1)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        if operation.status is OperationStatus.QUEUED:
            running_operation = replace(
                operation,
                status=OperationStatus.RUNNING,
                updated_at=when,
                optimistic_version=operation.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_operation(
                running_operation,
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            operation = running_operation

        step = unit_of_work.operations.get_step(step_id)
        if step.status is StepStatus.PENDING:
            running_step = replace(
                step,
                status=StepStatus.RUNNING,
                attempt_count=1,
                started_at=when,
                updated_at=when,
                worker_id="worker-test",
                lease_token="lease-test",
                lease_expires_at=lease_expires_at,
                optimistic_version=step.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_step(
                running_step,
                WritePrecondition(
                    expected_optimistic_version=step.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            step = running_step

        if step.status is StepStatus.RUNNING:
            failed_step = replace(
                step,
                status=StepStatus.FAILED,
                diagnostic=diagnostic,
                completed_at=when,
                updated_at=when,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                optimistic_version=step.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_step(
                failed_step,
                WritePrecondition(
                    expected_optimistic_version=step.optimistic_version,
                    worker_id=step.worker_id,
                    lease_token=step.lease_token,
                ),
            )

        if operation.status is OperationStatus.RUNNING:
            failed_operation = replace(
                operation,
                status=OperationStatus.FAILED,
                diagnostic=diagnostic,
                completed_at=when,
                updated_at=when,
                optimistic_version=operation.optimistic_version + 1,
            )
            unit_of_work.operations.compare_and_set_operation(
                failed_operation,
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )


def advance_submit_to_external_step(
    db_path: Path,
    operation_id: str,
    *,
    when: datetime = FIXED_NOW,
) -> str:
    from datetime import timedelta

    prepare_step_id = f"{operation_id}-step-1"
    external_step_id = f"{operation_id}-step-2"
    lease_expires_at = datetime.now(UTC) + timedelta(hours=1)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        prepare = unit_of_work.operations.get_step(prepare_step_id)
        running_prepare = replace(
            prepare,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=when,
            updated_at=when,
            worker_id="worker-test",
            lease_token="lease-test",
            lease_expires_at=lease_expires_at,
            optimistic_version=prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_prepare,
            WritePrecondition(
                expected_optimistic_version=prepare.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        succeeded_prepare = replace(
            running_prepare,
            status=StepStatus.SUCCEEDED,
            completed_at=when,
            updated_at=when,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=running_prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            succeeded_prepare,
            WritePrecondition(
                expected_optimistic_version=running_prepare.optimistic_version,
                worker_id=running_prepare.worker_id,
                lease_token=running_prepare.lease_token,
            ),
        )
        submit_step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=external_step_id,
            operation_id=operation_id,
            step_name=SUBMIT_STEP_SUBMIT,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=when,
            updated_at=when,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_successor_step(submit_step)

    promote_submit_recovery_target(
        db_path,
        operation_id=operation_id,
        step_id=external_step_id,
        when=when,
    )
    return external_step_id


@dataclass
class WorkspaceHttpTestEnvironment:
    client: TestClient
    db_path: Path
    repository: SqliteWorkspaceRepositoryFacade
    artifact_store: InMemoryBoundedArtifactStore
    bundle_reader: InMemoryBundleReader
    baseline_head_read: MutableBaselineHeadReadPort
    scope_resolution: FixedScopeResolutionPort
    main_resolve: RecordingMainResolvePort | FailingMainResolvePort
    identity: IdentityContext
    now: Callable[[], datetime]

    def auth_headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {TEST_BEARER}"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def internal_auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {TEST_INTERNAL_BEARER}"}


def create_workspace_http_environment(
    tmp_path: Path,
    *,
    identity: IdentityContext | None = None,
    admission_open: bool = True,
    admission_gate: AdmissionGatePort | None = None,
    include_preview_registry: bool = True,
    include_submit_registry: bool = True,
    extra_sessions: dict[str, IdentityContext] | None = None,
    now: Callable[[], datetime] | None = None,
    baseline_canonical_digest: BaselineCanonicalDigestPort | None = None,
    main_resolve_port: RecordingMainResolvePort | FailingMainResolvePort | None = None,
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

    def unit_of_work_factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(db_path, read_only=read_only)

    operation_reader = ReadOnlyOperationStore(unit_of_work_factory)
    submission_reader = ReadOnlySubmissionStore(unit_of_work_factory)
    baseline_digest = baseline_canonical_digest or FakeBaselineCanonicalDigestPort()
    main_resolve = main_resolve_port or RecordingMainResolvePort()
    job_registry = workspace_job_registry(
        include_preview=include_preview_registry,
        include_submit=include_submit_registry,
    )
    operator_recovery_port: OperatorRecoveryApplicationPort
    if include_submit_registry:
        operator_recovery_port = LocalOperatorRecoveryPort(
            unit_of_work_factory,
            job_registry=job_registry,
        )
    else:
        operator_recovery_port = FailClosedOperatorRecoveryPort()

    class _AdmissionGate:
        def allows_new_work(self) -> bool:
            return admission_open

        def try_acquire(self) -> bool:
            return admission_open

        def release(self) -> None:
            return None

    resolved_gate: AdmissionGatePort
    if admission_gate is not None:
        resolved_gate = admission_gate
    elif not admission_open:
        resolved_gate = _AdmissionGate()
    else:
        resolved_gate = OpenAdmissionGate()

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
        artifact_ref_lookup=cast(ArtifactRefLookupPort, artifact_store),
        job_registry=job_registry,
        bundle_reader=bundle_reader,
        admission_gate=resolved_gate,
        operation_reader=operation_reader,
        submission_reader=submission_reader,
        internal_bearer_port=StaticInternalBearerPort(TEST_INTERNAL_BEARER),
        baseline_canonical_digest=baseline_digest,
        main_resolve=main_resolve,
        operator_recovery_port=operator_recovery_port,
        now=clock,
    )
    app = create_app(workspace_http=deps)
    return WorkspaceHttpTestEnvironment(
        client=TestClient(app, raise_server_exceptions=False),
        scope_resolution=scope_resolution,
        main_resolve=main_resolve,
        db_path=db_path,
        repository=repository,
        artifact_store=artifact_store,
        bundle_reader=bundle_reader,
        baseline_head_read=baseline_head_read,
        identity=resolved_identity,
        now=clock,
    )


@dataclass(frozen=True, slots=True)
class PendingReviewHttpSeed:
    submission_id: str
    workspace_id: str
    repository_id: str
    device_key: str
    project_id: str


def seed_pending_review_submission(
    db_path: Path,
    *,
    submission_id: str = "sub-1",
) -> PendingReviewHttpSeed:
    from gateway_backend.application.submission.finalize_transaction import (
        FinalizeSubmitTransactionRequest,
        finalize_submit_transaction,
    )
    from tests.test_submit_transactions import (
        TS1,
        _finalize_facts,
        _read_finalize_versions,
        _seed_effect_pending_attempt,
        seed_submit_ready_workspace as seed_submit_transaction_workspace,
    )

    submit_seed = seed_submit_transaction_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, submit_seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=_finalize_facts(submit_seed),
                submission_id=submission_id,
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    return PendingReviewHttpSeed(
        submission_id=submission_id,
        workspace_id=submit_seed.workspace.workspace_id,
        repository_id=submit_seed.workspace.repository_id,
        device_key=submit_seed.workspace.gateway_device_external_key,
        project_id=submit_seed.workspace.business_project_id,
    )


def create_test_http_app_without_routes(
    tmp_path: Path,
    deps: WorkspaceHttpDependencies,
) -> FastAPI:
    del tmp_path
    app = FastAPI(title="Gateway Backend vNext")
    register_workspace_http(app, deps)
    return app
