from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import threading
from time import perf_counter
import uuid

from ..artifacts import ArtifactRef
from ..capabilities.snapshot_materialization import (
    materialize_sql_dump_source_preview,
    resolve_required_sql_document,
)
from ..core.digests import DigestRef, stable_sha256
from ..core.diagnostics import ErrorRecord
from ..formal_upload_benchmark import (
    benchmark_elapsed_ms,
    log_formal_upload_benchmark_event,
)
from ..core.results import ResultRecord
from ..operations import (
    OperationCallerType,
    OperationKind,
    OperationPlan,
    OperationRecord,
    OperationRuntime,
    OperationStatus,
    OperationStepContext,
    OperationStepOutcome,
    OperationStepPlan,
    OperationStore,
)
from .formal_state_store import VNextFormalStateStore
from .formal_upload import operation_envelope


@dataclass(frozen=True)
class FormalArchiveExecuteRequest:
    batch_id: str
    actor_id: str
    idempotency_key: str
    expected_base_main_hash: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    workspace_confirmation_set_hash: str
    candidate_set_hash: str
    override_reason: str | None = None


@dataclass(frozen=True)
class _ArchiveExecuteJob:
    request: FormalArchiveExecuteRequest
    operation_id: str
    preparation_source: dict[str, object] | None


ArchiveNextBaselinePreparer = Callable[[Mapping[str, object]], dict[str, object]]


class FormalArchiveService:
    def __init__(
        self,
        *,
        store: VNextFormalStateStore,
        operation_store: OperationStore,
        next_baseline_preparer: ArchiveNextBaselinePreparer | None = None,
        max_workers: int = 1,
    ) -> None:
        self.store = store
        self.operation_store = operation_store
        self._next_baseline_preparer = next_baseline_preparer or _prepare_next_baseline_source
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="formal-archive-execute",
        )
        self._inflight_lock = threading.Lock()
        self._inflight_by_batch_id: dict[str, str] = {}
        self._inflight_by_idempotency_key: dict[str, str] = {}

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def active_operation_envelopes_for_workspace_ids(
        self,
        workspace_ids: set[str],
    ) -> list[dict[str, object]]:
        envelopes: list[dict[str, object]] = []
        with self._inflight_lock:
            operation_ids = set(self._inflight_by_batch_id.values())
        for operation_id in operation_ids:
            operation = self.operation_store.get(operation_id)
            if operation is None or operation.status in _TERMINAL_STATUSES:
                self._clear_inflight_batch_operation(operation_id)
                continue
            operation_workspace_ids = operation.request_payload.get("workspace_ids", [])
            if not isinstance(operation_workspace_ids, list):
                continue
            if workspace_ids.intersection(str(item) for item in operation_workspace_ids):
                envelopes.append(operation_envelope(operation))
        return envelopes

    def execute(self, request: FormalArchiveExecuteRequest) -> dict[str, object]:
        in_flight = self._existing_inflight_operation(request)
        if in_flight is not None:
            return operation_envelope(in_flight)

        validate_started_at = perf_counter()
        validation = self.store.validate_archive_mainline_execute(
            batch_id=request.batch_id,
            requested_by_actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
            expected_base_main_hash=request.expected_base_main_hash,
            selected_modified_candidate_id=request.selected_modified_candidate_id,
            selected_initial_candidate_ids=request.selected_initial_candidate_ids,
            workspace_confirmation_set_hash=request.workspace_confirmation_set_hash,
            candidate_set_hash=request.candidate_set_hash,
            override_reason=request.override_reason,
        )
        log_formal_upload_benchmark_event(
            "archive.execute.sync_validate",
            batch_id=request.batch_id,
            workspace_ids=validation.get("workspace_ids", []),
            selected_modified_candidate_id=request.selected_modified_candidate_id,
            selected_initial_candidate_count=len(request.selected_initial_candidate_ids),
            idempotent_replay=validation.get("idempotent_replay") is True,
            blocks_upload=True,
            duration_ms=benchmark_elapsed_ms(validate_started_at),
        )
        operation_started_at = perf_counter()
        operation_runtime = OperationRuntime(store=self.operation_store)
        operation = operation_runtime.create_operation(
            OperationPlan(
                operation_kind=OperationKind.ARCHIVE_PROMOTE,
                caller_type=OperationCallerType.FINALIZE_WRITE_CALLER,
                request_payload={
                    "batch_id": request.batch_id,
                    "workspace_ids": validation.get("workspace_ids", []),
                    "idempotency_key": request.idempotency_key,
                    "selected_modified_candidate_id": request.selected_modified_candidate_id,
                    "selected_initial_candidate_ids": list(request.selected_initial_candidate_ids),
                    "candidate_set_hash": request.candidate_set_hash,
                    "workspace_confirmation_set_hash": request.workspace_confirmation_set_hash,
                    "blocks_archive": True,
                    "blocks_upload": True,
                },
                steps=(
                    OperationStepPlan(step_name="LOAD_ARCHIVE_EXECUTE_REQUEST"),
                    OperationStepPlan(step_name="PREPARE_NEXT_BASELINE_SOURCE", retryable=True),
                    OperationStepPlan(step_name="EXECUTE_ARCHIVE_MAINLINE", retryable=True),
                ),
            ),
            operation_id=f"operation:archive-promote:{uuid.uuid4().hex}",
        )
        log_formal_upload_benchmark_event(
            "archive.execute.operation_create",
            batch_id=request.batch_id,
            operation_id=operation.operation_id,
            workspace_ids=validation.get("workspace_ids", []),
            blocks_upload=True,
            duration_ms=benchmark_elapsed_ms(operation_started_at),
        )
        self._register_inflight(request, operation.operation_id)
        self._executor.submit(
            self._execute_in_background,
            _ArchiveExecuteJob(
                request=request,
                operation_id=operation.operation_id,
                preparation_source=(
                    None
                    if validation.get("idempotent_replay") is True
                    else _optional_mapping_payload(validation.get("preparation_source"))
                ),
            ),
        )
        return operation_envelope(operation)

    def _execute_in_background(self, job: _ArchiveExecuteJob) -> None:
        try:
            self._run_execute(job)
        except Exception as exc:  # pragma: no cover - defensive worker guard
            self._save_failed_operation(
                operation_id=job.operation_id,
                code="ARCHIVE_EXECUTE_FAILED",
                message=str(exc) or "Archive execute operation failed.",
                details={"batch_id": job.request.batch_id},
            )
        finally:
            self._clear_inflight_batch(job.request, job.operation_id)

    def _run_execute(self, job: _ArchiveExecuteJob) -> None:
        total_started_at = perf_counter()
        operation_runtime = OperationRuntime(store=self.operation_store)

        def load_request(context: OperationStepContext) -> OperationStepOutcome:
            return OperationStepOutcome.success(
                value={
                    "batch_id": job.request.batch_id,
                    "selected_modified_candidate_id": job.request.selected_modified_candidate_id,
                    "selected_initial_candidate_ids": list(job.request.selected_initial_candidate_ids),
                    "idempotency_key": job.request.idempotency_key,
                }
            )

        def prepare_next_baseline_source(context: OperationStepContext) -> OperationStepOutcome:
            prepare_started_at = perf_counter()
            if job.preparation_source is None:
                value = {
                    "status": "SKIPPED",
                    "reason": "idempotent replay already has archive execution",
                    "duration_ms": benchmark_elapsed_ms(prepare_started_at),
                }
                log_formal_upload_benchmark_event(
                    "archive.prepare_next_baseline_source",
                    batch_id=job.request.batch_id,
                    operation_id=job.operation_id,
                    status="SKIPPED",
                    blocks_upload=True,
                    duration_ms=value["duration_ms"],
                )
                return OperationStepOutcome.success(value=value)
            try:
                value = self._next_baseline_preparer(job.preparation_source)
                log_formal_upload_benchmark_event(
                    "archive.prepare_next_baseline_source",
                    batch_id=job.request.batch_id,
                    operation_id=job.operation_id,
                    status=value.get("status"),
                    source_submission_id=value.get("source_submission_id"),
                    workspace_id=value.get("workspace_id"),
                    table_count=value.get("table_count"),
                    row_count=value.get("row_count"),
                    blocks_upload=True,
                    duration_ms=benchmark_elapsed_ms(prepare_started_at),
                )
                return OperationStepOutcome.success(
                    value=value
                )
            except Exception as exc:
                log_formal_upload_benchmark_event(
                    "archive.prepare_next_baseline_source",
                    batch_id=job.request.batch_id,
                    operation_id=job.operation_id,
                    status="FAILED_FINAL",
                    source_submission_id=job.preparation_source.get("source_submission_id"),
                    blocks_upload=True,
                    duration_ms=benchmark_elapsed_ms(prepare_started_at),
                    error_code="ARCHIVE_BASELINE_SOURCE_PREPARATION_FAILED",
                )
                return OperationStepOutcome.failure(
                    code="ARCHIVE_BASELINE_SOURCE_PREPARATION_FAILED",
                    message=str(exc) or "Archive baseline source preparation failed.",
                    retryable=False,
                    value={
                        "batch_id": job.request.batch_id,
                        "source_submission_id": job.preparation_source.get("source_submission_id"),
                    },
                )

        def execute_mainline(context: OperationStepContext) -> OperationStepOutcome:
            execute_started_at = perf_counter()
            try:
                payload = self.store.execute_archive_mainline(
                    batch_id=job.request.batch_id,
                    requested_by_actor_id=job.request.actor_id,
                    idempotency_key=job.request.idempotency_key,
                    expected_base_main_hash=job.request.expected_base_main_hash,
                    selected_modified_candidate_id=job.request.selected_modified_candidate_id,
                    selected_initial_candidate_ids=job.request.selected_initial_candidate_ids,
                    workspace_confirmation_set_hash=job.request.workspace_confirmation_set_hash,
                    candidate_set_hash=job.request.candidate_set_hash,
                    override_reason=job.request.override_reason,
                )
            except (KeyError, ValueError, PermissionError) as exc:
                log_formal_upload_benchmark_event(
                    "archive.execute_mainline",
                    batch_id=job.request.batch_id,
                    operation_id=job.operation_id,
                    status="FAILED_FINAL",
                    blocks_upload=True,
                    duration_ms=benchmark_elapsed_ms(execute_started_at),
                    error_code="ARCHIVE_EXECUTE_FAILED",
                )
                return OperationStepOutcome.failure(
                    code="ARCHIVE_EXECUTE_FAILED",
                    message=str(exc),
                    retryable=False,
                )
            log_formal_upload_benchmark_event(
                "archive.execute_mainline",
                batch_id=job.request.batch_id,
                operation_id=job.operation_id,
                status="READY",
                workspace_ids=payload.get("workspace_ids"),
                baseline_archive_node_count=len(payload.get("baseline_archive_nodes", []))
                if isinstance(payload.get("baseline_archive_nodes"), list)
                else None,
                blocks_upload=True,
                duration_ms=benchmark_elapsed_ms(execute_started_at),
            )
            return OperationStepOutcome.success(
                value=payload,
                ready_closure_digest=DigestRef.from_payload(payload),
            )

        run_result = operation_runtime.run_operation(
            job.operation_id,
            {
                "LOAD_ARCHIVE_EXECUTE_REQUEST": load_request,
                "PREPARE_NEXT_BASELINE_SOURCE": prepare_next_baseline_source,
                "EXECUTE_ARCHIVE_MAINLINE": execute_mainline,
            },
            worker_id="formal-archive-execute",
        )
        if run_result.operation.status is not OperationStatus.READY:
            log_formal_upload_benchmark_event(
                "archive.execute.total_until_ready",
                batch_id=job.request.batch_id,
                operation_id=job.operation_id,
                status=run_result.operation.status.value,
                blocks_upload=True,
                duration_ms=benchmark_elapsed_ms(total_started_at),
            )
            return
        ready_payload = run_result.outputs.get("EXECUTE_ARCHIVE_MAINLINE")
        if not isinstance(ready_payload, dict):
            log_formal_upload_benchmark_event(
                "archive.execute.total_until_ready",
                batch_id=job.request.batch_id,
                operation_id=job.operation_id,
                status="READY_WITHOUT_PAYLOAD",
                blocks_upload=True,
                duration_ms=benchmark_elapsed_ms(total_started_at),
            )
            return
        ready_operation = replace(
            run_result.operation,
            result=ResultRecord(
                status=OperationStatus.READY.value,
                value=ready_payload,
                error=None,
                diagnostics=run_result.operation.diagnostics,
            ),
            updated_at=datetime.now(timezone.utc),
            version=run_result.operation.version + 1,
        )
        self.operation_store.save(
            ready_operation,
            expected_version=run_result.operation.version,
        )
        log_formal_upload_benchmark_event(
            "archive.execute.total_until_ready",
            batch_id=job.request.batch_id,
            operation_id=job.operation_id,
            status="READY",
            blocks_upload=True,
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )

    def _existing_inflight_operation(
        self,
        request: FormalArchiveExecuteRequest,
    ) -> OperationRecord | None:
        with self._inflight_lock:
            operation_id = self._inflight_by_idempotency_key.get(request.idempotency_key)
            if operation_id is None:
                operation_id = self._inflight_by_batch_id.get(request.batch_id)
        if operation_id is None:
            return None
        operation = self.operation_store.get(operation_id)
        if operation is None or operation.status in _TERMINAL_STATUSES:
            if operation is None:
                self._clear_inflight_operation(operation_id)
                return None
            return operation
        return operation

    def _register_inflight(
        self,
        request: FormalArchiveExecuteRequest,
        operation_id: str,
    ) -> None:
        with self._inflight_lock:
            self._inflight_by_batch_id[request.batch_id] = operation_id
            self._inflight_by_idempotency_key[request.idempotency_key] = operation_id

    def _clear_inflight_batch(
        self,
        request: FormalArchiveExecuteRequest,
        operation_id: str,
    ) -> None:
        with self._inflight_lock:
            if self._inflight_by_batch_id.get(request.batch_id) == operation_id:
                del self._inflight_by_batch_id[request.batch_id]

    def _clear_inflight_operation(self, operation_id: str) -> None:
        with self._inflight_lock:
            for batch_id, current_operation_id in list(self._inflight_by_batch_id.items()):
                if current_operation_id == operation_id:
                    del self._inflight_by_batch_id[batch_id]
            for idempotency_key, current_operation_id in list(self._inflight_by_idempotency_key.items()):
                if current_operation_id == operation_id:
                    del self._inflight_by_idempotency_key[idempotency_key]

    def _clear_inflight_batch_operation(self, operation_id: str) -> None:
        with self._inflight_lock:
            for batch_id, current_operation_id in list(self._inflight_by_batch_id.items()):
                if current_operation_id == operation_id:
                    del self._inflight_by_batch_id[batch_id]

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
        if operation.status in _TERMINAL_STATUSES and operation.status is not OperationStatus.READY:
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


_TERMINAL_STATUSES = {
    OperationStatus.READY,
    OperationStatus.FAILED_RETRYABLE,
    OperationStatus.FAILED_FINAL,
    OperationStatus.CANCELLED,
    OperationStatus.SUPERSEDED,
}


def _optional_mapping_payload(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("preparation_source must be a mapping")
    return {str(key): item for key, item in value.items()}


def _prepare_next_baseline_source(source: Mapping[str, object]) -> dict[str, object]:
    started_at = perf_counter()
    artifact_ref_payload = source.get("artifact_ref")
    if not isinstance(artifact_ref_payload, Mapping):
        raise ValueError("selected archive source package artifact is missing")
    artifact_ref = ArtifactRef.from_payload(artifact_ref_payload)
    materialized = materialize_sql_dump_source_preview(
        resolve_required_sql_document(artifact_ref)
    )
    if materialized.table_set is None:
        raise ValueError("selected archive source package did not produce tables")
    return {
        "status": "READY",
        "source_submission_id": source.get("source_submission_id"),
        "workspace_id": source.get("workspace_id"),
        "source_package_id": source.get("source_package_id"),
        "source_package_digest": source.get("source_package_digest"),
        "artifact": _artifact_ref_summary(artifact_ref),
        "table_count": materialized.summary.table_count,
        "row_count": materialized.summary.row_count_total,
        "duration_ms": benchmark_elapsed_ms(started_at),
    }


def _artifact_ref_summary(artifact_ref: ArtifactRef) -> dict[str, object]:
    return {
        "artifact_kind": artifact_ref.artifact_kind,
        "artifact_contract_version": artifact_ref.artifact_contract_version,
        "manifest_digest": artifact_ref.manifest_digest.to_payload(),
        "content_digest": artifact_ref.content_digest.to_payload(),
        "storage_key_digest": stable_sha256(artifact_ref.storage_key),
    }
