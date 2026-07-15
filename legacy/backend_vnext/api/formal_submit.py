from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from time import perf_counter
import threading
import uuid

from fastapi import status

from ..artifacts import ArtifactRef, LocalArtifactStore
from ..capabilities.repository_import import (
    RepositoryImportArtifactBuilder,
    RepositoryImportCallerPolicy,
    RepositoryImportExecutionContext,
    RepositoryImportPlan,
    RepositoryImportProvider,
    RepositoryImportProviderRunner,
    RepositoryImportServerMode,
    RepositoryImportStatus,
    RepositoryImportValidationPolicy,
    build_physical_repository_import_plan_tables,
)
from ..capabilities.snapshot_materialization import (
    SourcePackageInput,
    materialize_sql_dump_source,
    resolve_required_sql_document,
    stage_source_package,
    store_snapshot_rows_archive,
)
from ..contracts import PreviewInputBinding, SubmitSourcePackage
from ..core.diagnostics import ErrorRecord
from ..core.results import ResultRecord
from ..flows import (
    SubmitAcceptanceFlowInput,
    SubmitAcceptanceFlowResult,
    SubmitFinalizeFlowInput,
    run_submit_acceptance,
    run_submit_finalize,
)
from ..operations import OperationRecord, OperationRuntime, OperationStatus, OperationStore
from .formal_state_store import VNextFormalStateStore
from .formal_upload import (
    FormalUploadFile,
    benchmark_elapsed_ms,
    log_formal_upload_benchmark_event,
    operation_envelope,
)


@dataclass(frozen=True)
class FormalSubmitRequest:
    workspace_id: str
    actor_id: str
    preview_token: str
    preview_revision_id: str
    preview_strategy_manifest_digest: str
    source_file: FormalUploadFile
    expected_source_payload_sha256: str | None = None
    benchmark_run_id: str | None = None


class FormalSubmitContractError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)


def _formal_upload_file_sha256_hex(file: FormalUploadFile) -> str:
    if file.sha256_digest is not None:
        return file.sha256_digest.removeprefix("sha256:")
    if file.content is not None:
        return hashlib.sha256(file.content).hexdigest()
    if file.source_path is None:
        raise ValueError("FormalUploadFile has no content or source_path")
    hasher = hashlib.sha256()
    with file.source_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class _FixedSubmissionIdentityStore:
    def __init__(self, submission_id: str) -> None:
        self._submission_id = submission_id
        self._used = False

    def next_identity(self) -> str:
        if self._used:
            raise RuntimeError("fixed submission identity was already consumed")
        self._used = True
        return self._submission_id


@dataclass(frozen=True)
class _SubmitFinalizeJob:
    workspace_id: str
    actor_id: str
    raw_sha256: str
    workspace: dict[str, object]
    preview_refs: dict[str, object]
    bundle: dict[str, object]
    accepted: SubmitAcceptanceFlowResult
    submit_source_package: SubmitSourcePackage
    benchmark_run_id: str | None = None


class FormalSubmitService:
    def __init__(
        self,
        *,
        store: VNextFormalStateStore,
        operation_store: OperationStore,
        repository_import_runner: object | None = None,
        max_workers: int = 2,
    ) -> None:
        self.store = store
        self.operation_store = operation_store
        self.repository_import_runner = repository_import_runner or RepositoryImportProviderRunner(
            store.root / "repository-import",
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="formal-submit-finalize",
        )
        self._inflight_lock = threading.Lock()
        self._inflight_by_workspace_id: dict[str, str] = {}

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def active_operation_envelopes_for_workspace_ids(
        self,
        workspace_ids: set[str],
    ) -> list[dict[str, object]]:
        envelopes: list[dict[str, object]] = []
        with self._inflight_lock:
            pairs = [
                (workspace_id, operation_id)
                for workspace_id, operation_id in self._inflight_by_workspace_id.items()
                if workspace_id in workspace_ids
            ]
        for workspace_id, operation_id in pairs:
            operation = self.operation_store.get(operation_id)
            if operation is None or operation.status in _TERMINAL_STATUSES:
                self._clear_inflight(workspace_id, operation_id)
                continue
            envelopes.append(operation_envelope(operation))
        return envelopes

    def submit(self, request: FormalSubmitRequest) -> dict[str, object]:
        total_started_at = perf_counter()
        workspace = self._require_workspace(request.workspace_id)
        in_flight = self._existing_inflight_operation(request.workspace_id)
        if in_flight is not None:
            return operation_envelope(in_flight)

        sha_started_at = perf_counter()
        raw_sha256 = _formal_upload_file_sha256_hex(request.source_file)
        log_formal_upload_benchmark_event(
            "submit.sync.sha256",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            size_bytes=request.source_file.size_bytes,
            file_backed=request.source_file.source_path is not None,
            duration_ms=benchmark_elapsed_ms(sha_started_at),
        )
        self._require_expected_source_payload_sha256(request, raw_sha256=raw_sha256)
        preview_refs, bundle, binding = self._require_latest_preview(
            workspace,
            preview_token=request.preview_token,
            preview_revision_id=request.preview_revision_id,
            preview_strategy_manifest_digest=request.preview_strategy_manifest_digest,
        )
        stage_started_at = perf_counter()
        staged = self._stage_uploaded_package(request=request)
        log_formal_upload_benchmark_event(
            "submit.sync.stage_package",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            entry_count=len(getattr(staged, "entries", ())),
            duration_ms=benchmark_elapsed_ms(stage_started_at),
        )
        submit_source_package = _align_submit_source_package_to_binding(
            _submit_source_package_from_staged(staged, actor_id=request.actor_id),
            binding,
        )
        operation_runtime = OperationRuntime(store=self.operation_store)
        submission_id = self.store.next_submission_id()
        try:
            acceptance_started_at = perf_counter()
            accepted = run_submit_acceptance(
                SubmitAcceptanceFlowInput(
                    submit_source_package=submit_source_package,
                    preview_input_binding=binding,
                    submission_identity_store=_FixedSubmissionIdentityStore(submission_id),
                    operation_runtime=operation_runtime,
                    worker_id="formal-submit-acceptance",
                    operation_id=f"operation:submit-finalize:{uuid.uuid4().hex}",
                )
            )
            log_formal_upload_benchmark_event(
                "submit.sync.acceptance",
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                operation_id=accepted.operation.operation_id,
                duration_ms=benchmark_elapsed_ms(acceptance_started_at),
            )
        except ValueError as exc:
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_BINDING_MISMATCH",
                message=str(exc),
                details={"workspace_id": request.workspace_id},
            ) from exc

        self._register_inflight(request.workspace_id, accepted.operation.operation_id)
        self._executor.submit(
            self._finalize_in_background,
            _SubmitFinalizeJob(
                workspace_id=request.workspace_id,
                actor_id=request.actor_id,
                raw_sha256=raw_sha256,
                workspace=workspace,
                preview_refs=preview_refs,
                bundle=bundle,
                accepted=accepted,
                submit_source_package=submit_source_package,
                benchmark_run_id=request.benchmark_run_id,
            ),
        )
        log_formal_upload_benchmark_event(
            "submit.sync.total",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            operation_id=accepted.operation.operation_id,
            status=accepted.operation.status.value,
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )
        return operation_envelope(accepted.operation)

    def _finalize_in_background(self, job: _SubmitFinalizeJob) -> None:
        operation_runtime = OperationRuntime(store=self.operation_store)
        total_started_at = perf_counter()
        try:
            self._finalize_and_publish(job=job, operation_runtime=operation_runtime)
        except Exception as exc:  # pragma: no cover - defensive guard for worker failures
            self._save_failed_operation(
                operation_id=job.accepted.accepted.operation_id,
                code="SUBMIT_FINALIZE_FAILED",
                message=str(exc) or "Submit finalize operation failed.",
                details={"workspace_id": job.workspace_id},
            )
        finally:
            operation = self.operation_store.get(job.accepted.accepted.operation_id)
            log_formal_upload_benchmark_event(
                "submit.async.total",
                benchmark_run_id=job.benchmark_run_id,
                workspace_id=job.workspace_id,
                operation_id=job.accepted.accepted.operation_id,
                status=None if operation is None else operation.status.value,
                duration_ms=benchmark_elapsed_ms(total_started_at),
            )
            self._clear_inflight(job.workspace_id, job.accepted.accepted.operation_id)

    def _finalize_and_publish(
        self,
        *,
        job: _SubmitFinalizeJob,
        operation_runtime: OperationRuntime,
    ) -> None:
        finalize_started_at = perf_counter()
        finalize_result = self._run_finalize(
            workspace=job.workspace,
            submission_id=job.accepted.submission_id,
            operation_id=job.accepted.accepted.operation_id,
            operation_runtime=operation_runtime,
            submit_source_package=job.submit_source_package,
            benchmark_run_id=job.benchmark_run_id,
        )
        log_formal_upload_benchmark_event(
            "submit.async.finalize",
            benchmark_run_id=job.benchmark_run_id,
            workspace_id=job.workspace_id,
            operation_id=job.accepted.accepted.operation_id,
            status=finalize_result.operation.status.value,
            duration_ms=benchmark_elapsed_ms(finalize_started_at),
        )
        if finalize_result.operation.status is not OperationStatus.READY:
            return

        repository_import_result = finalize_result.repository_import_result
        if (
            repository_import_result.status is not RepositoryImportStatus.PASSED
            or repository_import_result.commit_hash is None
        ):
            self._save_failed_operation(
                operation_id=job.accepted.accepted.operation_id,
                code="SUBMIT_FINALIZE_FAILED",
                message="Submit finalize did not produce a repository commit.",
                details={"workspace_id": job.workspace_id},
            )
            return

        try:
            publish_started_at = perf_counter()
            configuration_generated_at = (
                None
                if finalize_result.source_snapshot.summary.configuration_generated_at is None
                else finalize_result.source_snapshot.summary.configuration_generated_at.astimezone(
                    timezone.utc
                ).isoformat()
            )
            snapshot_rows_artifact_stats: dict[str, object] | None = None
            if finalize_result.snapshot_rows_artifact_ref is not None:
                stored_snapshot_rows = LocalArtifactStore(
                    self.store.root / "snapshot-rows-archive-store"
                ).read(finalize_result.snapshot_rows_artifact_ref)
                snapshot_rows_artifact_stats = {
                    "table_count": stored_snapshot_rows.manifest.metadata.get("table_count"),
                    "physical_table_count": stored_snapshot_rows.manifest.metadata.get(
                        "physical_table_count"
                    ),
                    "row_count": stored_snapshot_rows.manifest.metadata.get("row_count"),
                    "size_bytes": stored_snapshot_rows.manifest.content_size_bytes,
                }
            submission, submit_operation, updated_workspace = self.store.create_submission(
                workspace_id=job.workspace_id,
                submitter_actor_id=job.actor_id,
                preview_refs=job.preview_refs,
                preview_input_binding=dict(job.bundle["preview_input_binding"]),
                submit_source_package=job.submit_source_package.to_payload(),
                accepted_payload=job.accepted.accepted.to_payload(),
                operation_payload=finalize_result.operation.to_payload(),
                source_artifact_ref=job.submit_source_package.artifact_ref.storage_key,
                source_artifact_payload_sha256=job.raw_sha256,
                operation_status="SUCCEEDED",
                final_modified_commit_hash=repository_import_result.commit_hash,
                repository_id=repository_import_result.repository_id,
                repository_target_ref=repository_import_result.target_ref,
                repository_commit_hash=repository_import_result.commit_hash,
                configuration_generated_at=configuration_generated_at,
                snapshot_rows_artifact_ref=(
                    None
                    if finalize_result.snapshot_rows_artifact_ref is None
                    else finalize_result.snapshot_rows_artifact_ref.to_payload()
                ),
                snapshot_rows_artifact_stats=snapshot_rows_artifact_stats,
            )
            log_formal_upload_benchmark_event(
                "submit.async.publish_submission",
                benchmark_run_id=job.benchmark_run_id,
                workspace_id=job.workspace_id,
                operation_id=job.accepted.accepted.operation_id,
                submission_id=submission.get("id"),
                duration_ms=benchmark_elapsed_ms(publish_started_at),
            )
        except (KeyError, ValueError) as exc:
            self._save_failed_operation(
                operation_id=job.accepted.accepted.operation_id,
                code="SUBMIT_STATE_CONFLICT",
                message=str(exc),
                details={"workspace_id": job.workspace_id},
            )
            return

        ready_result = {
            "submit_operation": submit_operation,
            "submission": submission,
            "workspace": updated_workspace,
            "accepted": True,
            "created": True,
        }
        ready_operation = replace(
            finalize_result.operation,
            result=replace(finalize_result.operation.result, value=ready_result)
            if finalize_result.operation.result is not None
            else finalize_result.operation.result,
            updated_at=datetime.now(timezone.utc),
            version=finalize_result.operation.version + 1,
        )
        saved = self.operation_store.save(
            ready_operation,
            expected_version=finalize_result.operation.version,
        )
        return None

    def _require_expected_source_payload_sha256(
        self,
        request: FormalSubmitRequest,
        *,
        raw_sha256: str,
    ) -> None:
        expected_source_payload_sha256 = _normalize_optional_sha256(
            request.expected_source_payload_sha256,
        )
        if (
            expected_source_payload_sha256 is not None
            and expected_source_payload_sha256 != raw_sha256
        ):
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_SOURCE_DIGEST_MISMATCH",
                message="Submit source payload sha256 mismatch.",
                details={"workspace_id": request.workspace_id},
            )

    def _existing_inflight_operation(self, workspace_id: str) -> OperationRecord | None:
        with self._inflight_lock:
            operation_id = self._inflight_by_workspace_id.get(workspace_id)
        if operation_id is None:
            return None
        operation = self.operation_store.get(operation_id)
        if operation is None or operation.status in _TERMINAL_STATUSES:
            self._clear_inflight(workspace_id, operation_id)
            return None
        return operation

    def _register_inflight(self, workspace_id: str, operation_id: str) -> None:
        with self._inflight_lock:
            self._inflight_by_workspace_id[workspace_id] = operation_id

    def _clear_inflight(self, workspace_id: str, operation_id: str) -> None:
        with self._inflight_lock:
            if self._inflight_by_workspace_id.get(workspace_id) == operation_id:
                del self._inflight_by_workspace_id[workspace_id]

    def _save_failed_operation(
        self,
        *,
        operation_id: str,
        code: str,
        message: str,
        details: dict[str, object],
    ) -> None:
        operation = self.operation_store.get(operation_id)
        if operation is None:
            return
        if (
            operation.status in _TERMINAL_STATUSES
            and operation.status is not OperationStatus.READY
        ):
            return
        failed = replace(
            operation,
            status=OperationStatus.FAILED_FINAL,
            result=ResultRecord(
                status=OperationStatus.FAILED_FINAL.value,
                error=ErrorRecord(
                    code=code,
                    message=message,
                    details=details,
                    retryable=False,
                ),
            ),
            failure_summary=message,
            updated_at=datetime.now(timezone.utc),
            version=operation.version + 1,
        )
        self.operation_store.save(failed, expected_version=operation.version)

    def _require_workspace(self, workspace_id: str) -> dict[str, object]:
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            raise FormalSubmitContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )
        return workspace

    def _require_latest_preview(
        self,
        workspace: dict[str, object],
        *,
        preview_token: str,
        preview_revision_id: str,
        preview_strategy_manifest_digest: str,
    ) -> tuple[dict[str, object], dict[str, object], PreviewInputBinding]:
        if workspace.get("submitted_submission_id") is not None or workspace.get("status") == "SUBMITTED":
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="WORKSPACE_ALREADY_SUBMITTED",
                message="Workspace is already submitted.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        preview_refs = workspace.get("latest_preview")
        if not isinstance(preview_refs, dict):
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="WORKSPACE_PREVIEW_NOT_READY",
                message="Workspace does not have a preview ready.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        expected = {
            "preview_token": preview_token,
            "preview_revision_id": preview_revision_id,
            "preview_strategy_manifest_digest": preview_strategy_manifest_digest,
        }
        for key, value in expected.items():
            if preview_refs.get(key) != value:
                raise FormalSubmitContractError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="SUBMIT_PREVIEW_MISMATCH",
                    message=f"{key} does not match latest preview.",
                    details={"workspace_id": str(workspace.get("id")), "field": key},
                )
        preview_bundle_id = preview_refs.get("preview_bundle_id")
        if not isinstance(preview_bundle_id, str) or not preview_bundle_id:
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_PREVIEW_MISMATCH",
                message="Latest preview bundle id is missing.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        bundle = self.store.get_preview_bundle(preview_bundle_id)
        if bundle is None or bundle.get("workspace_id") != workspace.get("id"):
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_PREVIEW_MISMATCH",
                message="Latest preview bundle does not match workspace.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        binding_payload = bundle.get("preview_input_binding")
        if not isinstance(binding_payload, dict):
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_PREVIEW_MISMATCH",
                message="Latest preview binding is missing.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        binding = PreviewInputBinding.from_payload(binding_payload)
        if binding.workspace_id != workspace.get("id"):
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_PREVIEW_MISMATCH",
                message="Preview binding workspace mismatch.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        if binding.upload_generation != preview_revision_id:
            raise FormalSubmitContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMIT_PREVIEW_MISMATCH",
                message="Preview revision does not match binding.",
                details={"workspace_id": str(workspace.get("id"))},
            )
        return dict(preview_refs), bundle, binding

    def _stage_uploaded_package(self, *, request: FormalSubmitRequest):
        if request.source_file.size_bytes == 0:
            raise FormalSubmitContractError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_FAILED",
                message="Submit source file is empty.",
            )
        safe_name = request.source_file.filename.replace("/", "_").replace("\\", "_") or "submit.tar.gz"
        if request.source_file.source_path is not None:
            upload_path = request.source_file.source_path
        else:
            if not request.source_file.content:
                raise FormalSubmitContractError(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    code="VALIDATION_FAILED",
                    message="Submit source file is empty.",
                )
            upload_dir = self.store.root / "uploads" / request.workspace_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / f"{uuid.uuid4().hex}-{safe_name}"
            upload_path.write_bytes(request.source_file.content)
        return stage_source_package(
            SourcePackageInput(
                source_path=upload_path,
                package_kind="TAR_GZ",
                source_origin=f"formal:submit:{safe_name}",
                created_by=request.actor_id,
                benchmark_run_id=request.benchmark_run_id,
            )
        )

    def _materialize_staged_package(self, staged_package, *, benchmark_run_id: str | None = None):
        if isinstance(staged_package, ArtifactRef):
            staged_package = resolve_required_sql_document(staged_package)
        materialized = materialize_sql_dump_source(
            staged_package,
            benchmark_run_id=benchmark_run_id,
        )
        if materialized.table_set is None:
            raise FormalSubmitContractError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_FAILED",
                message="Submit source package did not produce importable tables.",
            )
        return materialized

    def _run_finalize(
        self,
        *,
        workspace: dict[str, object],
        submission_id: str,
        operation_id: str,
        operation_runtime: OperationRuntime,
        submit_source_package: SubmitSourcePackage,
        benchmark_run_id: str | None = None,
    ):
        current_snapshot = self._materialize_staged_package(
            submit_source_package.artifact_ref,
            benchmark_run_id=benchmark_run_id,
        )
        import_artifact = RepositoryImportArtifactBuilder(
            self.store.root / "submit-finalize-artifacts" / _safe_ref_component(submission_id),
        ).build(current_snapshot)
        archive_started_at = perf_counter()
        snapshot_rows_archive = store_snapshot_rows_archive(
            result=current_snapshot,
            artifact_store=LocalArtifactStore(self.store.root / "snapshot-rows-archive-store"),
            work_root=self.store.root / "snapshot-rows-archive-work" / _safe_ref_component(submission_id),
        )
        log_formal_upload_benchmark_event(
            "submit.finalize.snapshot_rows_archive_write",
            benchmark_run_id=benchmark_run_id,
            submission_id=submission_id,
            table_count=snapshot_rows_archive.table_count,
            physical_table_count=snapshot_rows_archive.physical_table_count,
            row_count=snapshot_rows_archive.row_count,
            size_bytes=snapshot_rows_archive.size_bytes,
            reused=snapshot_rows_archive.stored_artifact.reused,
            duration_ms=benchmark_elapsed_ms(archive_started_at),
        )
        import_plan = _repository_import_plan_for_submit(
            store=self.store,
            workspace=workspace,
            submission_id=submission_id,
            source_snapshot=current_snapshot,
        )
        return run_submit_finalize(
            SubmitFinalizeFlowInput(
                repository_import_plan=import_plan,
                source_snapshot=current_snapshot,
                import_artifact=import_artifact,
                runner=self.repository_import_runner,
                snapshot_rows_artifact_ref=snapshot_rows_archive.artifact_ref,
                submission_id=submission_id,
                operation_id=operation_id,
                execution_context=RepositoryImportExecutionContext(
                    caller_policy=RepositoryImportCallerPolicy.FINALIZE_WRITE_CALLER,
                    idempotency_key=f"formal-submit-finalize:{submission_id}",
                ),
                operation_runtime=operation_runtime,
                worker_id="formal-submit-finalize",
            )
        )


def _repository_import_plan_for_submit(
    *,
    store: VNextFormalStateStore,
    workspace: dict[str, object],
    submission_id: str,
    source_snapshot,
) -> RepositoryImportPlan:
    if source_snapshot.table_set is None:
        raise FormalSubmitContractError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="Submit source package did not produce importable tables.",
        )
    gateway = store.get_gateway_device(str(workspace["gateway_device_external_key"]))
    if gateway is None:
        raise FormalSubmitContractError(
            status_code=status.HTTP_409_CONFLICT,
            code="GATEWAY_DEVICE_NOT_FOUND",
            message="Gateway device record was not found.",
            details={"workspace_id": str(workspace["id"])},
        )
    repository_id = str(gateway["repo_key"])
    target_ref = (
        f"refs/heads/formal/{_safe_ref_component(repository_id)}"
        f"/submissions/{_safe_ref_component(submission_id)}"
    )
    plan_tables = build_physical_repository_import_plan_tables(source_snapshot)
    return RepositoryImportPlan(
        repository_id=repository_id,
        base_ref_or_commit="main",
        target_branch_ref=target_ref,
        source_snapshot_id=source_snapshot.summary.snapshot_id,
        source_snapshot_digest=source_snapshot.summary.snapshot_digest,
        table_ruleset_version=source_snapshot.summary.table_ruleset_version,
        provider_preference=RepositoryImportProvider.SQL_DUMP_REPLAY,
        server_mode=RepositoryImportServerMode.DISABLED,
        tables=plan_tables,
        validation_policy=RepositoryImportValidationPolicy.VERIFY_HIDDEN_SUMMARY_CATALOG,
        validation_table_names=tuple(table.table_name for table in plan_tables),
    )


def _submit_source_package_from_staged(staged_package, *, actor_id: str) -> SubmitSourcePackage:
    staged_source_package = staged_package.source_package
    return SubmitSourcePackage(
        source_package_id=staged_package.source_package_id,
        source_kind="SUBMIT_FULL",
        package_kind=(
            staged_source_package.package_kind
            if staged_source_package is not None
            else "TAR_GZ"
        ),
        source_package_digest=staged_package.source_package_digest,
        package_manifest_digest=staged_package.package_manifest_digest,
        required_entries_manifest_digest=staged_package.required_entries_manifest_digest,
        artifact_ref=staged_package.artifact_ref,
        size_bytes=(
            staged_source_package.size_bytes
            if staged_source_package is not None
            else sum(entry.size_bytes for entry in staged_package.entries)
        ),
        created_by=actor_id,
    )


def _align_submit_source_package_to_binding(
    submit_source_package: SubmitSourcePackage,
    binding: PreviewInputBinding,
) -> SubmitSourcePackage:
    return replace(
        submit_source_package,
        required_entries_manifest_digest=binding.required_entries_manifest_digest,
        parser_version=binding.parser_version,
        table_ruleset_version=binding.table_ruleset_version,
    )


def _safe_ref_component(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in value.strip()
    ).strip("-")
    return normalized or "repository"


def _normalize_optional_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "":
        return None
    if normalized.startswith("sha256:"):
        normalized = normalized.removeprefix("sha256:")
    return normalized


_TERMINAL_STATUSES = {
    OperationStatus.READY,
    OperationStatus.FAILED_RETRYABLE,
    OperationStatus.FAILED_FINAL,
    OperationStatus.CANCELLED,
    OperationStatus.SUPERSEDED,
}
