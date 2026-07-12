from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import threading
import uuid

from fastapi import status
from fastapi.responses import FileResponse

from ..artifacts import ArtifactRef, LocalArtifactStore, RecordsArtifact
from ..cache import InMemoryComparisonCoreCache
from ..capabilities.comparison import (
    COMPARISON_DEFAULT_DIRECTION,
    ComparisonInput,
    ComparisonRole,
    DirectedComparisonInput,
)
from ..capabilities.bundle_assembly.ref_rewrite import rewrite_surface_for_bundle
from ..capabilities.snapshot_materialization import (
    SourcePackageInput,
    SnapshotTableSet,
    SnapshotMaterializationResult,
    build_provisional_fast_table_aliases,
    materialize_sql_dump_source_preview,
    resolve_required_sql_document,
    restore_snapshot_rows_archive,
    stage_source_package,
)
from ..capabilities.upload_preview_bundle import (
    BundleArtifact,
    UploadPreviewBundleAssembler,
    UploadPreviewBundlePayloadInput,
    business_projection_bundle_artifacts,
    comparison_records_bundle_artifacts,
    preview_snapshot_table_artifacts,
    risk_annotation_bundle_artifacts,
    visible_preview_table_aliases,
    with_preview_snapshot_fast_candidate_refs,
    with_preview_snapshot_table_refs,
)
from ..contracts import PreviewInputBinding, PreviewInputBindingEntry, SubmitSourcePackage
from ..core.diagnostics import ErrorRecord
from ..core.digests import DigestRef
from ..core.results import ResultRecord
from ..formal_upload_benchmark import (
    BenchmarkingLocalArtifactStore,
    benchmark_elapsed_ms,
    formal_upload_benchmark_run_id,
    log_formal_upload_benchmark_event,
)
from ..flows import UploadPreviewFlowInput, complete_upload_preview_cache, run_upload_preview
from ..operations import (
    InMemoryOperationStore,
    OperationCallerType,
    OperationKind,
    OperationRecord,
    OperationStatus,
    OperationStore,
)
from .formal_state_store import VNextFormalStateStore


@dataclass(frozen=True)
class FormalUploadFile:
    filename: str
    content: bytes | None = None
    source_path: Path | None = None
    size_bytes: int | None = None
    sha256_digest: str | None = None

    def __post_init__(self) -> None:
        if self.content is None and self.source_path is None:
            raise ValueError("FormalUploadFile requires content or source_path")
        if self.content is not None and not isinstance(self.content, (bytes, bytearray, memoryview)):
            raise TypeError("content must be bytes-like or None")
        if self.source_path is not None and not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path or None")
        if self.content is not None:
            content_bytes = bytes(self.content)
            object.__setattr__(self, "content", content_bytes)
            if self.size_bytes is None:
                object.__setattr__(self, "size_bytes", len(content_bytes))
        elif self.size_bytes is None and self.source_path is not None:
            object.__setattr__(self, "size_bytes", self.source_path.stat().st_size)


@dataclass(frozen=True)
class FormalUploadRequest:
    workspace_id: str
    upload_mode: str
    actor_id: str
    initial_file: FormalUploadFile | None = None
    modified_file: FormalUploadFile | None = None
    package_format: str = "directory-tar-gzip"
    client_selected_root_name: str | None = None
    client_validation_summary: str | None = None
    benchmark_run_id: str | None = None


@dataclass(frozen=True)
class _PreviewPairSpec:
    view_id: str
    label: str
    display_before_role: str
    display_current_role: str
    before_materialized: SnapshotMaterializationResult
    current_materialized: SnapshotMaterializationResult


@dataclass(frozen=True)
class _PreviewPairBuildResult:
    spec: _PreviewPairSpec
    flow_input: UploadPreviewFlowInput
    flow_result: object
    surface: object
    table_aliases: tuple[dict[str, object], ...]
    snapshot_artifacts: object
    bundle_artifacts: tuple[object, ...]


def _bundle_artifact_size_bytes(artifact: BundleArtifact) -> int:
    if artifact.content_bytes is not None:
        return len(artifact.content_bytes)
    if artifact.source_path is not None:
        return artifact.source_path.stat().st_size
    if artifact.json_payload is not None:
        # Keep this as a rough payload cost signal; the assembler writes compact JSON
        # separately, so exact bytes are less useful than avoiding a second encoder pass.
        return 0
    return 0


def _bundle_artifact_kind(ref: str) -> str:
    if ref.endswith(".parquet") and "/tables/" in ref:
        return "snapshot_parquet"
    if ref.endswith(".parquet") and "/comparison/records/" in ref:
        return "records_parquet"
    if "/risk/" in ref:
        return "risk"
    if "/projections/" in ref:
        return "projection"
    if ref.endswith("comparison-surface.json"):
        return "comparison_surface"
    return "other"


def _bundle_artifact_stats(artifacts: tuple[object, ...]) -> dict[str, object]:
    typed_artifacts = tuple(artifact for artifact in artifacts if isinstance(artifact, BundleArtifact))
    kind_counts = Counter(_bundle_artifact_kind(artifact.relative_ref) for artifact in typed_artifacts)
    return {
        "artifact_count": len(typed_artifacts),
        "artifact_count_by_kind": dict(sorted(kind_counts.items())),
        "snapshot_artifact_count": kind_counts.get("snapshot_parquet", 0),
        "snapshot_artifact_bytes": sum(
            _bundle_artifact_size_bytes(artifact)
            for artifact in typed_artifacts
            if _bundle_artifact_kind(artifact.relative_ref) == "snapshot_parquet"
        ),
        "records_artifact_count": kind_counts.get("records_parquet", 0),
        "records_artifact_bytes": sum(
            _bundle_artifact_size_bytes(artifact)
            for artifact in typed_artifacts
            if _bundle_artifact_kind(artifact.relative_ref) == "records_parquet"
        ),
        "risk_artifact_count": kind_counts.get("risk", 0),
        "projection_artifact_count": kind_counts.get("projection", 0),
    }


class FormalUploadContractError(Exception):
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


class FormalUploadService:
    def __init__(
        self,
        *,
        store: VNextFormalStateStore,
        operation_store: OperationStore | None = None,
        max_cache_workers: int = 2,
    ) -> None:
        self.store = store
        self.operation_store = operation_store or InMemoryOperationStore()
        self._cache_executor = ThreadPoolExecutor(
            max_workers=max_cache_workers,
            thread_name_prefix="formal-preview-cache",
        )
        self._background_lock = threading.Lock()
        self._background_by_workspace_id: dict[str, str] = {}

    def shutdown(self) -> None:
        self._cache_executor.shutdown(wait=False, cancel_futures=False)

    def submit_upload(self, request: FormalUploadRequest) -> dict[str, object]:
        total_started_at = perf_counter()
        operation_started_at = perf_counter()
        operation = self._create_operation(request)
        log_formal_upload_benchmark_event(
            "upload.operation_create",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=_normalize_upload_mode(request.upload_mode),
            duration_ms=benchmark_elapsed_ms(operation_started_at),
        )
        try:
            ready_result = self._run_upload(request)
        except _TerminalUploadFailure as exc:
            operation = self._save_failed_operation(
                operation=operation,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
            log_formal_upload_benchmark_event(
                "upload.total",
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                upload_mode=_normalize_upload_mode(request.upload_mode),
                status="FAILED_FINAL",
                duration_ms=benchmark_elapsed_ms(total_started_at),
                error_code=exc.code,
            )
            return operation_envelope(operation)
        except Exception as exc:
            operation = self._save_failed_operation(
                operation=operation,
                code="UPLOAD_PREVIEW_FAILED",
                message=str(exc) or "Upload preview operation failed.",
                details={"workspace_id": request.workspace_id},
            )
            log_formal_upload_benchmark_event(
                "upload.total",
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                upload_mode=_normalize_upload_mode(request.upload_mode),
                status="FAILED_FINAL",
                duration_ms=benchmark_elapsed_ms(total_started_at),
                error_code="UPLOAD_PREVIEW_FAILED",
            )
            return operation_envelope(operation)

        save_started_at = perf_counter()
        operation = self._save_ready_operation(operation=operation, ready_result=ready_result)
        log_formal_upload_benchmark_event(
            "upload.operation_save_ready",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=_normalize_upload_mode(request.upload_mode),
            duration_ms=benchmark_elapsed_ms(save_started_at),
        )
        log_formal_upload_benchmark_event(
            "upload.total",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=_normalize_upload_mode(request.upload_mode),
            status="READY",
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )
        return operation_envelope(operation)

    def get_operation(self, operation_id: str) -> OperationRecord | None:
        return self.operation_store.get(operation_id)

    def active_operation_envelopes_for_workspace_ids(
        self,
        workspace_ids: set[str],
    ) -> list[dict[str, object]]:
        envelopes: list[dict[str, object]] = []
        with self._background_lock:
            pairs = [
                (workspace_id, operation_id)
                for workspace_id, operation_id in self._background_by_workspace_id.items()
                if workspace_id in workspace_ids
            ]
        for workspace_id, operation_id in pairs:
            operation = self.operation_store.get(operation_id)
            if operation is None:
                self._clear_background_operation(workspace_id, operation_id)
                continue
            if operation.status is OperationStatus.READY:
                self._clear_background_operation(workspace_id, operation_id)
                continue
            envelopes.append(operation_envelope(operation))
        return envelopes

    def preview_bundle_metadata(self, preview_bundle_id: str, *, download_url: str) -> dict[str, object]:
        bundle = self.store.get_preview_bundle(preview_bundle_id)
        if bundle is None:
            raise FormalUploadContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="PREVIEW_BUNDLE_NOT_FOUND",
                message="Preview bundle not found.",
                details={"preview_bundle_id": preview_bundle_id},
            )
        tar_path = Path(str(bundle["tar_path"]))
        if not tar_path.is_file():
            raise FormalUploadContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="PREVIEW_BUNDLE_NOT_READY",
                message="Preview bundle artifact is not ready.",
                details={"preview_bundle_id": preview_bundle_id},
            )
        return {
            "download_url": download_url,
            "expires_at": None,
            "package_format": bundle["package_format"],
            "size_bytes": bundle["size_bytes"],
            "sha256": bundle["sha256"],
        }

    def preview_bundle_artifact(self, preview_bundle_id: str) -> FileResponse:
        bundle = self.store.get_preview_bundle(preview_bundle_id)
        if bundle is None:
            raise FormalUploadContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="PREVIEW_BUNDLE_NOT_FOUND",
                message="Preview bundle not found.",
                details={"preview_bundle_id": preview_bundle_id},
            )
        tar_path = Path(str(bundle["tar_path"]))
        if not tar_path.is_file():
            raise FormalUploadContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="PREVIEW_BUNDLE_NOT_READY",
                message="Preview bundle artifact is not ready.",
                details={"preview_bundle_id": preview_bundle_id},
            )
        return FileResponse(
            tar_path,
            media_type="application/x-tar",
            filename=f"{preview_bundle_id.replace(':', '-')}.tar",
        )

    def _create_operation(self, request: FormalUploadRequest) -> OperationRecord:
        now = datetime.now(timezone.utc)
        operation = OperationRecord(
            operation_id=f"operation:upload-preview:{uuid.uuid4().hex}",
            operation_kind=OperationKind.UPLOAD_PREVIEW,
            caller_type=OperationCallerType.DIRECT_RESPONSE_CALLER,
            status=OperationStatus.RUNNING,
            request_payload={
                "workspace_id": request.workspace_id,
                "upload_mode": _normalize_upload_mode(request.upload_mode),
                "package_format": request.package_format,
            },
            created_at=now,
            updated_at=now,
        )
        return self.operation_store.create(operation)

    def _save_ready_operation(
        self,
        *,
        operation: OperationRecord,
        ready_result: dict[str, object],
    ) -> OperationRecord:
        now = datetime.now(timezone.utc)
        updated = replace(
            operation,
            status=OperationStatus.READY,
            result=ResultRecord(status="READY", value=ready_result),
            ready_closure_digest=DigestRef.from_payload(ready_result),
            updated_at=now,
            version=operation.version + 1,
        )
        return self.operation_store.save(updated, expected_version=operation.version)

    def _save_failed_operation(
        self,
        *,
        operation: OperationRecord,
        code: str,
        message: str,
        details: dict[str, object],
    ) -> OperationRecord:
        now = datetime.now(timezone.utc)
        error = ErrorRecord(code=code, message=message, details=details, retryable=False)
        updated = replace(
            operation,
            status=OperationStatus.FAILED_FINAL,
            failure_summary=message,
            result=ResultRecord(status="FAILED_FINAL", error=error),
            updated_at=now,
            version=operation.version + 1,
        )
        return self.operation_store.save(updated, expected_version=operation.version)

    def _run_upload(self, request: FormalUploadRequest) -> dict[str, object]:
        started_at = perf_counter()
        upload_mode = _normalize_upload_mode(request.upload_mode)
        try:
            if upload_mode == "FULL":
                if request.initial_file is None or request.modified_file is None:
                    raise FormalUploadContractError(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        code="VALIDATION_FAILED",
                        message="FULL upload requires initial_file and modified_file.",
                    )
                return self._run_full_upload(request)
            if upload_mode == "MODIFIED_ONLY":
                if request.modified_file is None:
                    raise FormalUploadContractError(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        code="VALIDATION_FAILED",
                        message="MODIFIED_ONLY upload requires modified_file.",
                    )
                return self._run_modified_only_upload(request)
            if upload_mode == "INITIALIZE_BASELINE":
                source_file = request.modified_file or request.initial_file
                if source_file is None:
                    raise FormalUploadContractError(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        code="VALIDATION_FAILED",
                        message="INITIALIZE_BASELINE upload requires a source file.",
                    )
                return self._run_initialize_baseline_upload(request, source_file=source_file)
            raise FormalUploadContractError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_FAILED",
                message=f"Unsupported upload_mode: {request.upload_mode}.",
            )
        finally:
            log_formal_upload_benchmark_event(
                "upload.mode_dispatch",
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                upload_mode=upload_mode,
                duration_ms=benchmark_elapsed_ms(started_at),
            )

    def _run_full_upload(self, request: FormalUploadRequest) -> dict[str, object]:
        assert request.initial_file is not None
        assert request.modified_file is not None
        baseline_resolution_started_at = perf_counter()
        baseline_resolution = self.store.resolve_modified_only_baseline_source(request.workspace_id)
        log_formal_upload_benchmark_event(
            "upload.full.resolve_baseline_source",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            status=baseline_resolution.get("status"),
            duration_ms=benchmark_elapsed_ms(baseline_resolution_started_at),
        )
        pair_started_at = perf_counter()
        with ThreadPoolExecutor(max_workers=2) as executor:
            initial_future = executor.submit(
                self._stage_and_materialize,
                request=request,
                upload_kind="initial",
                file=request.initial_file,
            )
            modified_future = executor.submit(
                self._stage_and_materialize,
                request=request,
                upload_kind="modified",
                file=request.modified_file,
            )
            initial_staged, initial_materialized = initial_future.result()
            modified_staged, modified_materialized = modified_future.result()
        log_formal_upload_benchmark_event(
            "upload.full.stage_materialize_pair",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            duration_ms=benchmark_elapsed_ms(pair_started_at),
        )
        baseline_materialized = None
        baseline_pair_source: dict[str, object] | None = None
        if baseline_resolution.get("status") == "READY":
            baseline_kind = baseline_resolution.get("baseline_source_kind")
            baseline_materialize_started_at = perf_counter()
            if baseline_kind == "ARCHIVED_MAINLINE":
                baseline_materialized, restore_source = self._restore_baseline_snapshot_rows(
                    artifact_ref_payload=baseline_resolution.get("snapshot_rows_artifact_ref"),
                    request=request,
                    event_name="upload.full.baseline_snapshot_rows_restore",
                )
                artifact_ref_payload = baseline_resolution.get("artifact_ref")
                if baseline_materialized is None and isinstance(artifact_ref_payload, dict):
                    fallback_started_at = perf_counter()
                    baseline_materialized = self._materialize_staged_package(
                        ArtifactRef.from_payload(artifact_ref_payload),
                        benchmark_run_id=request.benchmark_run_id,
                    )
                    restore_source = "SOURCE_PACKAGE_FALLBACK"
                    log_formal_upload_benchmark_event(
                        "upload.full.baseline_snapshot_rows_restore",
                        benchmark_run_id=request.benchmark_run_id,
                        workspace_id=request.workspace_id,
                        status="FALLBACK",
                        fallback_reason="source_package_materialized_after_snapshot_rows_miss",
                        table_count=baseline_materialized.summary.table_count,
                        row_count=baseline_materialized.summary.row_count_total,
                        duration_ms=benchmark_elapsed_ms(fallback_started_at),
                    )
                if baseline_materialized is not None:
                    baseline_pair_source = {
                        key: value
                        for key, value in baseline_resolution.items()
                        if key not in {"status", "artifact_ref", "snapshot_rows_artifact_ref"}
                    }
                    baseline_pair_source["restore_source"] = restore_source
            elif baseline_kind == "EXPLICIT_EMPTY":
                baseline_materialized = materialize_sql_dump_source_preview(
                    b"",
                    benchmark_run_id=request.benchmark_run_id,
                )
                baseline_pair_source = {
                    key: value
                    for key, value in baseline_resolution.items()
                    if key not in {"status", "artifact_ref"}
                }
            log_formal_upload_benchmark_event(
                "upload.full.materialize_baseline_source",
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                baseline_source_kind=baseline_kind,
                materialized=baseline_materialized is not None,
            duration_ms=benchmark_elapsed_ms(baseline_materialize_started_at),
            )

        workspace_started_at = perf_counter()
        updated = self.store.mark_workspace_initial_ready(
            workspace_id=request.workspace_id,
            initial_commit_hash=initial_materialized.snapshot.snapshot_digest.to_payload(),
            source_artifact_ref=initial_staged.artifact_ref.to_payload(),
            source_package=_submit_source_package_from_staged(
                initial_staged,
                actor_id=request.actor_id,
            ).to_payload(),
            initial_configuration_generated_at=_summary_configuration_generated_at(initial_materialized),
        )
        log_formal_upload_benchmark_event(
            "upload.workspace_initial_ready",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode="FULL",
            duration_ms=benchmark_elapsed_ms(workspace_started_at),
        )
        baseline_source = {
            "kind": "WORKSPACE_INITIAL",
            "workspace_id": request.workspace_id,
            "baseline_pair_source": baseline_pair_source,
            "baseline_pair_skipped": baseline_materialized is None,
            "baseline_pair_skip_reason": (
                None
                if baseline_materialized is not None
                else str(baseline_resolution.get("error_code") or "formal.baseline_source_unresolved")
            ),
        }
        return self._build_preview(
            request=request,
            before_materialized=initial_materialized,
            current_materialized=modified_materialized,
            current_staged=modified_staged,
            upload_mode="FULL",
            upload_semantics="FULL",
            baseline_source=baseline_source,
            workspace_after_initial=updated,
            additional_pair_specs=(
                (
                    _PreviewPairSpec(
                        view_id="baseline_to_initial",
                        label="baseline_to_initial",
                        display_before_role="baseline",
                        display_current_role="initial",
                        before_materialized=baseline_materialized,
                        current_materialized=initial_materialized,
                    ),
                )
                if baseline_materialized is not None
                else ()
            ),
            primary_view_id="initial_to_modified",
            primary_display_before_role="initial",
            primary_display_current_role="modified",
        )

    def _run_modified_only_upload(self, request: FormalUploadRequest) -> dict[str, object]:
        assert request.modified_file is not None
        resolution_started_at = perf_counter()
        baseline_resolution = self.store.resolve_modified_only_baseline_source(request.workspace_id)
        log_formal_upload_benchmark_event(
            "upload.modified_only.resolve_baseline_source",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            status=baseline_resolution.get("status"),
            duration_ms=benchmark_elapsed_ms(resolution_started_at),
        )
        if baseline_resolution.get("status") != "READY":
            raise _TerminalUploadFailure(
                code=str(baseline_resolution.get("error_code", "BASELINE_SOURCE_UNRESOLVED")),
                message=str(
                    baseline_resolution.get(
                        "message",
                        "Modified-only baseline source could not be resolved.",
                    )
                ),
                details={
                    key: value
                    for key, value in baseline_resolution.items()
                    if key not in {"artifact_ref", "status"}
                },
            )
        upload_semantics = str(baseline_resolution["upload_semantics"])
        if upload_semantics == "INITIALIZE_BASELINE":
            return self._run_initialize_baseline_upload(request, source_file=request.modified_file)
        artifact_ref_payload = baseline_resolution.get("artifact_ref")
        snapshot_rows_artifact_ref_payload = baseline_resolution.get("snapshot_rows_artifact_ref")
        if not isinstance(artifact_ref_payload, dict) and not isinstance(
            snapshot_rows_artifact_ref_payload,
            dict,
        ):
            raise _TerminalUploadFailure(
                code="BASELINE_SOURCE_UNRESOLVED",
                message="Modified-only baseline source artifact is missing.",
                details={"workspace_id": request.workspace_id, "upload_mode": "MODIFIED_ONLY"},
            )
        current_staged, current_materialized = self._stage_and_materialize(
            request=request,
            upload_kind="modified",
            file=request.modified_file,
        )
        baseline_materialize_started_at = perf_counter()
        before_materialized, restore_source = self._restore_baseline_snapshot_rows(
            artifact_ref_payload=snapshot_rows_artifact_ref_payload,
            request=request,
            event_name="upload.modified_only.baseline_snapshot_rows_restore",
        )
        if before_materialized is None:
            if not isinstance(artifact_ref_payload, dict):
                raise _TerminalUploadFailure(
                    code="BASELINE_SOURCE_UNRESOLVED",
                    message="Modified-only baseline source artifact is missing.",
                    details={"workspace_id": request.workspace_id, "upload_mode": "MODIFIED_ONLY"},
                )
            before_materialized = self._materialize_staged_package(
                ArtifactRef.from_payload(artifact_ref_payload),
                benchmark_run_id=request.benchmark_run_id,
            )
            restore_source = "SOURCE_PACKAGE_FALLBACK"
        log_formal_upload_benchmark_event(
            "upload.modified_only.materialize_baseline_source",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            duration_ms=benchmark_elapsed_ms(baseline_materialize_started_at),
        )
        baseline_source = {
            key: value
            for key, value in baseline_resolution.items()
            if key not in {"status", "artifact_ref", "snapshot_rows_artifact_ref"}
        }
        baseline_source["restore_source"] = restore_source
        return self._build_preview(
            request=request,
            before_materialized=before_materialized,
            current_materialized=current_materialized,
            current_staged=current_staged,
            upload_mode="MODIFIED_ONLY",
            upload_semantics="MODIFIED_ONLY",
            baseline_source=baseline_source,
            workspace_after_initial=None,
        )

    def _run_initialize_baseline_upload(
        self,
        request: FormalUploadRequest,
        *,
        source_file: FormalUploadFile,
    ) -> dict[str, object]:
        current_staged, current_materialized = self._stage_and_materialize(
            request=request,
            upload_kind="initialize",
            file=source_file,
        )
        workspace_started_at = perf_counter()
        updated = self.store.mark_workspace_initial_ready(
            workspace_id=request.workspace_id,
            initial_commit_hash=current_materialized.snapshot.snapshot_digest.to_payload(),
            source_artifact_ref=current_staged.artifact_ref.to_payload(),
            source_package=_submit_source_package_from_staged(
                current_staged,
                actor_id=request.actor_id,
            ).to_payload(),
            initial_configuration_generated_at=_summary_configuration_generated_at(current_materialized),
        )
        log_formal_upload_benchmark_event(
            "upload.workspace_initial_ready",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode="INITIALIZE_BASELINE",
            duration_ms=benchmark_elapsed_ms(workspace_started_at),
        )
        batch_started_at = perf_counter()
        batch = self.store.get_current_baseline_batch(str(updated["gateway_device_external_key"]))
        log_formal_upload_benchmark_event(
            "upload.initialize.get_current_batch",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            duration_ms=benchmark_elapsed_ms(batch_started_at),
        )
        baseline_source = {
            "kind": "EXPLICIT_EMPTY",
            "workspace_id": request.workspace_id,
            "batch_id": None if batch is None else batch.get("batch_id"),
            "base_main_hash": None if batch is None else batch.get("base_main_hash"),
        }
        return self._build_preview(
            request=request,
            before_materialized=current_materialized,
            current_materialized=current_materialized,
            current_staged=current_staged,
            upload_mode="INITIALIZE_BASELINE",
            upload_semantics="INITIALIZE_BASELINE",
            baseline_source=baseline_source,
            workspace_after_initial=updated,
        )

    def _stage_and_materialize(
        self,
        *,
        request: FormalUploadRequest,
        upload_kind: str,
        file: FormalUploadFile,
    ):
        total_started_at = perf_counter()
        stage_started_at = perf_counter()
        staged = self._stage_uploaded_package(
            workspace_id=request.workspace_id,
            upload_kind=upload_kind,
            file=file,
            filename=file.filename,
            actor_id=request.actor_id,
            benchmark_run_id=request.benchmark_run_id,
        )
        log_formal_upload_benchmark_event(
            "upload.stage_package",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_kind=upload_kind,
            input_size_bytes=file.size_bytes,
            entry_count=len(getattr(staged, "entries", ())),
            duration_ms=benchmark_elapsed_ms(stage_started_at),
        )
        materialize_started_at = perf_counter()
        materialized = self._materialize_staged_package(
            staged,
            benchmark_run_id=request.benchmark_run_id,
        )
        log_formal_upload_benchmark_event(
            "upload.materialize_sql",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_kind=upload_kind,
            table_count=materialized.summary.table_count,
            row_count_total=materialized.summary.row_count_total,
            duration_ms=benchmark_elapsed_ms(materialize_started_at),
        )
        log_formal_upload_benchmark_event(
            "upload.stage_and_materialize_total",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_kind=upload_kind,
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )
        return staged, materialized

    def _stage_uploaded_package(
        self,
        *,
        workspace_id: str,
        upload_kind: str,
        file: FormalUploadFile,
        filename: str,
        actor_id: str,
        benchmark_run_id: str | None = None,
    ):
        if file.size_bytes == 0:
            raise FormalUploadContractError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_FAILED",
                message=f"{upload_kind} upload body is empty.",
            )
        safe_name = filename.replace("/", "_").replace("\\", "_") or f"{upload_kind}.tar.gz"
        if file.source_path is not None:
            upload_path = file.source_path
        else:
            if not file.content:
                raise FormalUploadContractError(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    code="VALIDATION_FAILED",
                    message=f"{upload_kind} upload body is empty.",
                )
            upload_dir = self.store.root / "uploads" / workspace_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            upload_path = upload_dir / f"{uuid.uuid4().hex}-{safe_name}"
            upload_path.write_bytes(file.content)
        return stage_source_package(
            SourcePackageInput(
                source_path=upload_path,
                package_kind="TAR_GZ",
                source_origin=f"formal:{upload_kind}:{safe_name}",
                created_by=actor_id,
                benchmark_run_id=benchmark_run_id,
            )
        )

    def _materialize_staged_package(self, staged_package, *, benchmark_run_id: str | None = None):
        if isinstance(staged_package, ArtifactRef):
            staged_package = resolve_required_sql_document(staged_package)
        materialized = materialize_sql_dump_source_preview(
            staged_package,
            benchmark_run_id=benchmark_run_id,
        )
        if materialized.table_set is None:
            raise FormalUploadContractError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_FAILED",
                message="Uploaded package did not produce tables.",
            )
        return materialized

    def _restore_baseline_snapshot_rows(
        self,
        *,
        artifact_ref_payload: object,
        request: FormalUploadRequest,
        event_name: str,
    ) -> tuple[SnapshotMaterializationResult | None, str | None]:
        started_at = perf_counter()
        if not isinstance(artifact_ref_payload, dict):
            log_formal_upload_benchmark_event(
                event_name,
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                status="MISS",
                fallback_reason="snapshot_rows_artifact_ref_missing",
                duration_ms=benchmark_elapsed_ms(started_at),
            )
            return None, None
        try:
            restored = restore_snapshot_rows_archive(
                artifact_ref=ArtifactRef.from_payload(artifact_ref_payload),
                artifact_store=LocalArtifactStore(self.store.root / "snapshot-rows-archive-store"),
            )
        except Exception as exc:
            log_formal_upload_benchmark_event(
                event_name,
                benchmark_run_id=request.benchmark_run_id,
                workspace_id=request.workspace_id,
                status="INVALID",
                fallback_reason=str(exc) or exc.__class__.__name__,
                duration_ms=benchmark_elapsed_ms(started_at),
            )
            return None, None
        log_formal_upload_benchmark_event(
            event_name,
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            status="HIT",
            table_count=restored.table_count,
            physical_table_count=restored.physical_table_count,
            row_count=restored.row_count,
            size_bytes=restored.size_bytes,
            duration_ms=benchmark_elapsed_ms(started_at),
        )
        return restored.materialized, "SNAPSHOT_ROWS_ARCHIVE"

    def _build_preview_pair(
        self,
        *,
        request: FormalUploadRequest,
        spec: _PreviewPairSpec,
        preview_bundle_id: str,
        bundle_root: Path,
        upload_mode: str,
        upload_semantics: str,
    ) -> _PreviewPairBuildResult:
        pair_started_at = perf_counter()
        log_formal_upload_benchmark_event(
            "upload.preview.prepare_pair",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            upload_semantics=upload_semantics,
            view_id=spec.view_id,
            duration_ms=benchmark_elapsed_ms(pair_started_at),
        )
        table_aliases = tuple(
            build_provisional_fast_table_aliases(
                spec.before_materialized.summary,
                input_role=ComparisonRole.BEFORE.value,
                pair_id=spec.view_id,
            )
        ) + tuple(
            build_provisional_fast_table_aliases(
                spec.current_materialized.summary,
                input_role=ComparisonRole.CURRENT.value,
                pair_id=spec.view_id,
            )
        )
        comparison_input = DirectedComparisonInput(
            before=ComparisonInput(
                role=ComparisonRole.BEFORE,
                snapshot=spec.before_materialized.snapshot,
                summary=spec.before_materialized.summary,
                table_set_ref=spec.before_materialized.table_set,
            ),
            current=ComparisonInput(
                role=ComparisonRole.CURRENT,
                snapshot=spec.current_materialized.snapshot,
                summary=spec.current_materialized.summary,
                table_set_ref=spec.current_materialized.table_set,
            ),
            table_aliases=table_aliases,
        )
        preview_started_at = perf_counter()
        flow_input = UploadPreviewFlowInput(
            comparison_input=comparison_input,
            records_store=BenchmarkingLocalArtifactStore(
                self.store.root / "records" / preview_bundle_id.replace(":", "-") / spec.view_id,
                benchmark_run_id=request.benchmark_run_id,
                event_prefix="upload.preview.records",
                workspace_id=request.workspace_id,
            ),
            comparison_core_cache=InMemoryComparisonCoreCache(),
            operation_id=f"operation:{preview_bundle_id}:{spec.view_id}",
            complete_comparison_core_cache_sync=False,
            benchmark_run_id=request.benchmark_run_id,
        )
        flow_result = run_upload_preview(flow_input)
        log_formal_upload_benchmark_event(
            "upload.preview.run_upload_preview",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            view_id=spec.view_id,
            comparison_status=str(
                getattr(
                    flow_result.comparison_result.summary.status,
                    "value",
                    flow_result.comparison_result.summary.status,
                )
            ),
            duration_ms=benchmark_elapsed_ms(preview_started_at),
        )
        preview_surface = flow_result.surface_result.comparison_surface
        preview_surface = replace(
            preview_surface,
            surface_digest=None,
            view=replace(
                preview_surface.view,
                view_id=spec.view_id,
                label=spec.label,
                display_before_role=spec.display_before_role,
                display_current_role=spec.display_current_role,
            ),
        )
        visible_aliases = visible_preview_table_aliases(
            table_aliases,
            view_id=preview_surface.view.view_id,
            visible_table_names={table.table_name for table in preview_surface.tables},
        )
        preview_surface = with_preview_snapshot_table_refs(
            preview_surface,
            before_table_set=spec.before_materialized.table_set,
            current_table_set=spec.current_materialized.table_set,
            table_aliases=visible_aliases,
        )
        preview_snapshot_fast_dedupe = with_preview_snapshot_fast_candidate_refs(
            preview_surface,
            before_table_set=spec.before_materialized.table_set,
            current_table_set=spec.current_materialized.table_set,
        )
        preview_surface = rewrite_surface_for_bundle(
            preview_snapshot_fast_dedupe.surface,
            spec.view_id,
        )
        snapshot_started_at = perf_counter()
        snapshot_artifacts = preview_snapshot_table_artifacts(
            surface=preview_surface,
            before_table_set=spec.before_materialized.table_set,
            current_table_set=spec.current_materialized.table_set,
            bundle_root=bundle_root,
            fast_ref_dedupe=preview_snapshot_fast_dedupe,
        )
        log_formal_upload_benchmark_event(
            "upload.preview.snapshot_parquet_encode",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            view_id=spec.view_id,
            table_count=snapshot_artifacts.table_count,
            row_count=snapshot_artifacts.row_count,
            logical_table_count=snapshot_artifacts.logical_table_count,
            export_task_count=snapshot_artifacts.export_task_count,
            deduped_table_count=snapshot_artifacts.deduped_table_count,
            logical_row_count=snapshot_artifacts.logical_row_count,
            exported_row_count=snapshot_artifacts.exported_row_count,
            deduped_row_count=snapshot_artifacts.deduped_row_count,
            snapshot_ref_reuse_count=snapshot_artifacts.snapshot_ref_reuse_count,
            size_bytes=snapshot_artifacts.size_bytes,
            worker_count=snapshot_artifacts.worker_count,
            parallel_enabled=snapshot_artifacts.parallel_enabled,
            export_strategy=snapshot_artifacts.export_strategy,
            worker_config=snapshot_artifacts.worker_config,
            worker_config_invalid=snapshot_artifacts.worker_config_invalid,
            top_slow_tables=snapshot_artifacts.top_slow_tables,
            cache_dry_run_enabled=snapshot_artifacts.cache_dry_run_enabled,
            exact_cache_eligible_table_count=snapshot_artifacts.exact_cache_eligible_table_count,
            exact_cache_ineligible_table_count=snapshot_artifacts.exact_cache_ineligible_table_count,
            exact_cache_miss_reasons=snapshot_artifacts.exact_cache_miss_reasons,
            fast_candidate_eligible_table_count=snapshot_artifacts.fast_candidate_eligible_table_count,
            fast_candidate_ineligible_table_count=snapshot_artifacts.fast_candidate_ineligible_table_count,
            fast_candidate_miss_reasons=snapshot_artifacts.fast_candidate_miss_reasons,
            fast_candidate_key_reuse_count=snapshot_artifacts.fast_candidate_key_reuse_count,
            fast_candidate_reused_row_count=snapshot_artifacts.fast_candidate_reused_row_count,
            fast_candidate_reused_size_bytes=snapshot_artifacts.fast_candidate_reused_size_bytes,
            top_fast_candidate_reuse_groups=snapshot_artifacts.top_fast_candidate_reuse_groups,
            fast_snapshot_ref_dedupe_count=snapshot_artifacts.fast_snapshot_ref_dedupe_count,
            fast_snapshot_ref_deduped_row_count=snapshot_artifacts.fast_snapshot_ref_deduped_row_count,
            fast_snapshot_ref_deduped_estimated_size_bytes=snapshot_artifacts.fast_snapshot_ref_deduped_estimated_size_bytes,
            fast_snapshot_ref_dedupe_groups=snapshot_artifacts.fast_snapshot_ref_dedupe_groups,
            duration_ms=benchmark_elapsed_ms(snapshot_started_at),
        )
        records_copy_started_at = perf_counter()
        comparison_records_artifacts = comparison_records_bundle_artifacts(
            surface=preview_surface,
            records_artifacts=flow_result.comparison_result.records_artifacts,
            bundle_root=bundle_root,
        )
        log_formal_upload_benchmark_event(
            "upload.preview.records_copy",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            view_id=spec.view_id,
            artifact_count=sum(1 for artifact in comparison_records_artifacts if artifact.source_path is not None),
            size_bytes=sum(
                artifact.source_path.stat().st_size
                for artifact in comparison_records_artifacts
                if artifact.source_path is not None
            ),
            duration_ms=benchmark_elapsed_ms(records_copy_started_at),
        )
        bundle_artifacts = (
            *snapshot_artifacts.artifacts,
            *comparison_records_artifacts,
            *risk_annotation_bundle_artifacts(
                surface=preview_surface,
                annotation_artifacts=flow_result.risk_result.annotation_artifacts,
            ),
            *business_projection_bundle_artifacts(
                flow_result.business_projection_result,
                ref_prefix=f"pairs/{spec.view_id}",
            ),
        )
        artifact_stats = _bundle_artifact_stats(bundle_artifacts)
        log_formal_upload_benchmark_event(
            "upload.preview.pair_total",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            upload_semantics=upload_semantics,
            view_id=spec.view_id,
            table_count=len(preview_surface.tables),
            row_count=sum(table.row_count or 0 for table in preview_surface.tables),
            snapshot_artifact_count=artifact_stats["snapshot_artifact_count"],
            snapshot_artifact_bytes=artifact_stats["snapshot_artifact_bytes"],
            records_artifact_count=artifact_stats["records_artifact_count"],
            records_artifact_bytes=artifact_stats["records_artifact_bytes"],
            risk_artifact_count=artifact_stats["risk_artifact_count"],
            projection_artifact_count=artifact_stats["projection_artifact_count"],
            artifact_count=artifact_stats["artifact_count"],
            artifact_count_by_kind=artifact_stats["artifact_count_by_kind"],
            duration_ms=benchmark_elapsed_ms(pair_started_at),
        )
        return _PreviewPairBuildResult(
            spec=spec,
            flow_input=flow_input,
            flow_result=flow_result,
            surface=preview_surface,
            table_aliases=visible_aliases,
            snapshot_artifacts=snapshot_artifacts,
            bundle_artifacts=bundle_artifacts,
        )

    def _build_preview(
        self,
        *,
        request: FormalUploadRequest,
        before_materialized,
        current_materialized,
        current_staged,
        upload_mode: str,
        upload_semantics: str,
        baseline_source: dict[str, object],
        workspace_after_initial: dict[str, object] | None,
        additional_pair_specs: tuple[_PreviewPairSpec, ...] = (),
        primary_view_id: str | None = None,
        primary_display_before_role: str = "before",
        primary_display_current_role: str = "current",
    ) -> dict[str, object]:
        total_started_at = perf_counter()
        del workspace_after_initial
        preview_bundle_id = f"preview-bundle:{uuid.uuid4().hex}"
        preview_revision_id = f"preview-revision:{uuid.uuid4().hex}"
        primary_view_id = primary_view_id or COMPARISON_DEFAULT_DIRECTION.lower()
        bundle_root = self.store.root / "preview-bundles" / preview_bundle_id.replace(":", "-") / "bundle"
        tar_path = bundle_root.parent / "formal-preview-bundle.tar"
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        alignment_report = _alignment_report(
            upload_semantics=upload_semantics,
            baseline_source=baseline_source,
        )
        primary_pair_spec = _PreviewPairSpec(
            view_id=primary_view_id,
            label=primary_view_id,
            display_before_role=primary_display_before_role,
            display_current_role=primary_display_current_role,
            before_materialized=before_materialized,
            current_materialized=current_materialized,
        )
        pair_specs = (*additional_pair_specs, primary_pair_spec)
        pair_results = tuple(
            self._build_preview_pair(
                request=request,
                spec=pair_spec,
                preview_bundle_id=preview_bundle_id,
                bundle_root=bundle_root,
                upload_mode=upload_mode,
                upload_semantics=upload_semantics,
            )
            for pair_spec in pair_specs
        )
        primary_pair_result = next(
            (result for result in pair_results if result.spec.view_id == primary_view_id),
            pair_results[-1],
        )
        all_visible_aliases = tuple(
            alias
            for pair_result in pair_results
            for alias in pair_result.table_aliases
        )
        all_bundle_artifacts = tuple(
            artifact
            for pair_result in pair_results
            for artifact in pair_result.bundle_artifacts
        )
        preview_strategy_manifest = {
            "schema_version": "preview-strategy-manifest/v2",
            "workspace_id": request.workspace_id,
            "preview_bundle_id": preview_bundle_id,
            "preview_revision_id": preview_revision_id,
            "upload_mode": upload_mode,
            "upload_semantics": upload_semantics,
            "default_view_id": primary_view_id,
            "baseline_source": baseline_source,
            "before_snapshot_digest": before_materialized.snapshot.snapshot_digest.to_payload(),
            "current_snapshot_digest": current_materialized.snapshot.snapshot_digest.to_payload(),
            "comparison_digest": primary_pair_result.flow_result.comparison_result.facts.comparison_digest.to_payload(),
            "risk_evaluation_digest": primary_pair_result.flow_result.risk_result.risk_evaluation.risk_evaluation_digest.to_payload(),
            "table_aliases": list(all_visible_aliases),
            "pairs": [
                {
                    "view_id": pair_result.spec.view_id,
                    "label": pair_result.spec.label,
                    "display_before_role": pair_result.spec.display_before_role,
                    "display_current_role": pair_result.spec.display_current_role,
                    "before_snapshot_digest": pair_result.spec.before_materialized.snapshot.snapshot_digest.to_payload(),
                    "current_snapshot_digest": pair_result.spec.current_materialized.snapshot.snapshot_digest.to_payload(),
                    "comparison_digest": pair_result.flow_result.comparison_result.facts.comparison_digest.to_payload(),
                    "risk_evaluation_digest": pair_result.flow_result.risk_result.risk_evaluation.risk_evaluation_digest.to_payload(),
                }
                for pair_result in pair_results
            ],
        }
        preview_strategy_manifest_digest = DigestRef.from_payload(preview_strategy_manifest).to_payload()
        bundle_started_at = perf_counter()
        bundle_result = UploadPreviewBundleAssembler().assemble_payloads(
            UploadPreviewBundlePayloadInput(
                bundle_root=bundle_root,
                preview_bundle_id=preview_bundle_id,
                preview_revision_id=preview_revision_id,
                preview_strategy_manifest_digest=preview_strategy_manifest_digest,
                workspace_id=request.workspace_id,
                baseline_alignment="NOT_EVALUATED",
                generated_at=generated_at,
                surfaces=tuple(pair_result.surface for pair_result in pair_results),
                risk_reports=tuple(pair_result.flow_result.risk_result.risk_report for pair_result in pair_results),
                default_view_id=primary_view_id,
                preview_strategy_manifest=preview_strategy_manifest,
                alignment_report=alignment_report,
                table_aliases=all_visible_aliases,
                bundle_artifacts=all_bundle_artifacts,
                tar_path=tar_path,
            )
        )
        if bundle_result.tarball is None:
            raise RuntimeError("Preview tarball was not generated.")
        artifact_stats = _bundle_artifact_stats(all_bundle_artifacts)
        preview_table_count = sum(len(pair_result.surface.tables) for pair_result in pair_results)
        preview_row_count = sum(
            table.row_count or 0
            for pair_result in pair_results
            for table in pair_result.surface.tables
        )
        log_formal_upload_benchmark_event(
            "upload.preview.bundle_write",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            pair_count=len(pair_results),
            table_count=preview_table_count,
            row_count=preview_row_count,
            **artifact_stats,
            duration_ms=bundle_result.bundle_write_duration_ms or 0,
        )
        log_formal_upload_benchmark_event(
            "upload.preview.tar_create",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            pair_count=len(pair_results),
            table_count=preview_table_count,
            row_count=preview_row_count,
            size_bytes=bundle_result.tarball.size_bytes,
            tar_entry_count=len(bundle_result.tarball.entries),
            duration_ms=bundle_result.tar_create_duration_ms or 0,
        )
        log_formal_upload_benchmark_event(
            "upload.preview.bundle_assemble",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            pair_count=len(pair_results),
            table_count=preview_table_count,
            row_count=preview_row_count,
            preview_bundle_size_bytes=bundle_result.tarball.size_bytes,
            tar_entry_count=len(bundle_result.tarball.entries),
            **artifact_stats,
            duration_ms=benchmark_elapsed_ms(bundle_started_at),
        )
        preview_bundle_digest = f"sha256:{bundle_result.tarball.sha256}"
        preview_token = f"preview-token:{DigestRef.from_payload({'preview_bundle_digest': preview_bundle_digest}).hex_digest}"
        refs = _preview_refs(
            preview_bundle_id=preview_bundle_id,
            preview_token=preview_token,
            preview_revision_id=preview_revision_id,
            preview_strategy_manifest_digest=preview_strategy_manifest_digest,
            preview_bundle_digest=preview_bundle_digest,
        )
        binding_entries = tuple(
            PreviewInputBindingEntry(
                entry_name=entry.original_path or entry.normalized_path,
                normalized_path=entry.normalized_path,
                entry_kind=entry.entry_kind,
                content_digest=entry.content_digest,
            )
            for entry in current_staged.entries
            if entry.content_digest is not None
        )
        binding = PreviewInputBinding(
            binding_id=f"binding:{preview_bundle_id}",
            workspace_id=request.workspace_id,
            upload_generation=preview_revision_id,
            preview_source_digest=current_staged.source_package_digest,
            required_entries=binding_entries,
            before_snapshot_digest=before_materialized.snapshot.snapshot_digest,
            current_snapshot_digest=current_materialized.snapshot.snapshot_digest,
            comparison_digest=primary_pair_result.flow_result.comparison_result.facts.comparison_digest,
            generated_at=datetime.now(timezone.utc),
        )
        workspace_started_at = perf_counter()
        updated_workspace = self.store.mark_workspace_preview_ready(
            workspace_id=request.workspace_id,
            preview_refs=refs,
            preview_input_binding=binding.to_payload(),
            preview_source_package=_submit_source_package_from_staged(
                current_staged,
                actor_id=request.actor_id,
            ).to_payload(),
            upload_semantics=upload_semantics,
            baseline_source=baseline_source,
            preview_bundle_record={
                "preview_bundle_id": preview_bundle_id,
                "tar_path": str(bundle_result.tarball.path),
                "bundle_root": str(bundle_result.bundle_root),
                "size_bytes": bundle_result.tarball.size_bytes,
                "sha256": bundle_result.tarball.sha256,
                "package_format": "tar",
            },
        )
        log_formal_upload_benchmark_event(
            "upload.preview.workspace_preview_ready",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            duration_ms=benchmark_elapsed_ms(workspace_started_at),
        )
        metadata = {
            "download_url": f"/api/preview-bundles/{preview_bundle_id}/artifact",
            "expires_at": None,
            "package_format": "tar",
            "size_bytes": bundle_result.tarball.size_bytes,
            "sha256": bundle_result.tarball.sha256,
        }
        cache_started_at = perf_counter()
        for pair_result in pair_results:
            self._start_cache_completion(
                workspace_id=request.workspace_id,
                preview_bundle_id=preview_bundle_id,
                upload_preview_operation_id=pair_result.flow_result.operation.operation_id,
                flow_input=pair_result.flow_input,
                flow_result=pair_result.flow_result,
            )
        log_formal_upload_benchmark_event(
            "upload.preview.cache_completion_enqueue",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            pair_count=len(pair_results),
            duration_ms=benchmark_elapsed_ms(cache_started_at),
        )
        log_formal_upload_benchmark_event(
            "upload.preview.total",
            benchmark_run_id=request.benchmark_run_id,
            workspace_id=request.workspace_id,
            upload_mode=upload_mode,
            upload_semantics=upload_semantics,
            pair_count=len(pair_results),
            table_count=preview_table_count,
            row_count=preview_row_count,
            preview_bundle_size_bytes=bundle_result.tarball.size_bytes,
            tar_entry_count=len(bundle_result.tarball.entries),
            **artifact_stats,
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )
        baseline_pair_skipped = baseline_source.get("baseline_pair_skipped")
        baseline_initial_diagnostics_status = (
            "AVAILABLE"
            if baseline_pair_skipped is False
            else "FAILED"
            if upload_mode == "FULL"
            else "NOT_REQUIRED"
        )
        baseline_initial_diagnostics_error = (
            str(baseline_source.get("baseline_pair_skip_reason") or "baseline_to_initial pair was not published.")
            if baseline_initial_diagnostics_status == "FAILED"
            else None
        )
        return {
            "workspace": updated_workspace,
            "preview_bundle": refs,
            "workspace_id": request.workspace_id,
            "upload_mode": upload_mode,
            "upload_semantics": upload_semantics,
            "baseline_source": baseline_source,
            "upload_role": "FULL" if upload_mode == "FULL" else "MODIFIED",
            "latest_preview_bundle_id": preview_bundle_id,
            "latest_preview_token": preview_token,
            "baseline_alignment": "NOT_EVALUATED",
            "alignment_report": alignment_report,
            "preview_bundle_download_url": metadata["download_url"],
            "preview_bundle_download_expires_at": metadata["expires_at"],
            "preview_bundle_package_format": metadata["package_format"],
            "preview_bundle_size_bytes": metadata["size_bytes"],
            "preview_bundle_sha256": metadata["sha256"],
            "initial_resolution": "NORMAL",
            "normal_initial": None,
            "baseline_initial_diagnostics_status": baseline_initial_diagnostics_status,
            "baseline_initial_diagnostics_ref": None,
            "baseline_initial_diagnostics_error": baseline_initial_diagnostics_error,
            "baseline_initial_diagnostics_summary": None,
            "baseline_initial_diagnostics": None,
        }

    def _start_cache_completion(
        self,
        *,
        workspace_id: str,
        preview_bundle_id: str,
        upload_preview_operation_id: str,
        flow_input: UploadPreviewFlowInput,
        flow_result,
    ) -> None:
        operation = self._create_cache_completion_operation(
            workspace_id=workspace_id,
            preview_bundle_id=preview_bundle_id,
            upload_preview_operation_id=upload_preview_operation_id,
            comparison_digest=flow_result.comparison_result.facts.comparison_digest.to_payload(),
        )
        self._register_background_operation(workspace_id, operation.operation_id)
        self._cache_executor.submit(
            self._complete_cache_in_background,
            workspace_id,
            operation.operation_id,
            flow_input,
            flow_result.comparison_result,
        )

    def _create_cache_completion_operation(
        self,
        *,
        workspace_id: str,
        preview_bundle_id: str,
        upload_preview_operation_id: str,
        comparison_digest: str,
    ) -> OperationRecord:
        now = datetime.now(timezone.utc)
        operation = OperationRecord(
            operation_id=f"operation:preview-cache-completion:{uuid.uuid4().hex}",
            operation_kind=OperationKind.PREVIEW_CACHE_COMPLETION,
            caller_type=OperationCallerType.WARMUP_CALLER,
            status=OperationStatus.RUNNING,
            request_payload={
                "workspace_id": workspace_id,
                "preview_bundle_id": preview_bundle_id,
                "upload_preview_operation_id": upload_preview_operation_id,
                "comparison_digest": comparison_digest,
                "background": True,
                "blocks_preview": False,
                "blocks_submit": False,
            },
            created_at=now,
            updated_at=now,
        )
        return self.operation_store.create(operation)

    def _complete_cache_in_background(
        self,
        workspace_id: str,
        operation_id: str,
        flow_input: UploadPreviewFlowInput,
        comparison_result,
    ) -> None:
        try:
            completion_details, diagnostics = complete_upload_preview_cache(
                flow_input=flow_input,
                comparison_result=comparison_result,
            )
            self._save_cache_ready_operation(
                operation_id=operation_id,
                ready_result=completion_details,
                diagnostics=diagnostics,
            )
        except Exception as exc:  # pragma: no cover - defensive worker guard
            self._save_cache_failed_operation(
                operation_id=operation_id,
                code="PREVIEW_CACHE_COMPLETION_FAILED",
                message=str(exc) or "Preview cache completion failed.",
                details={"workspace_id": workspace_id},
            )

    def _save_cache_ready_operation(
        self,
        *,
        operation_id: str,
        ready_result: dict[str, object],
        diagnostics: tuple[object, ...],
    ) -> None:
        operation = self.operation_store.get(operation_id)
        if operation is None:
            return
        now = datetime.now(timezone.utc)
        updated = replace(
            operation,
            status=OperationStatus.READY,
            result=ResultRecord(status="READY", value=ready_result),
            ready_closure_digest=DigestRef.from_payload(ready_result),
            diagnostics=tuple(operation.diagnostics) + tuple(diagnostics),
            updated_at=now,
            version=operation.version + 1,
        )
        self.operation_store.save(updated, expected_version=operation.version)

    def _save_cache_failed_operation(
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
        now = datetime.now(timezone.utc)
        error = ErrorRecord(code=code, message=message, details=details, retryable=False)
        updated = replace(
            operation,
            status=OperationStatus.FAILED_FINAL,
            failure_summary=message,
            result=ResultRecord(status="FAILED_FINAL", error=error),
            updated_at=now,
            version=operation.version + 1,
        )
        self.operation_store.save(updated, expected_version=operation.version)

    def _register_background_operation(self, workspace_id: str, operation_id: str) -> None:
        with self._background_lock:
            self._background_by_workspace_id[workspace_id] = operation_id

    def _clear_background_operation(self, workspace_id: str, operation_id: str) -> None:
        with self._background_lock:
            if self._background_by_workspace_id.get(workspace_id) == operation_id:
                del self._background_by_workspace_id[workspace_id]


class _TerminalUploadFailure(Exception):
    def __init__(self, *, code: str, message: str, details: dict[str, object]) -> None:
        self.code = code
        self.message = message
        self.details = dict(details)


def operation_envelope(operation: OperationRecord) -> dict[str, object]:
    result = operation.result
    ready_result = result.value if result is not None and result.status == "READY" else None
    effective_status = operation.status
    effective_phase = _operation_phase(operation)
    if (
        operation.operation_kind is OperationKind.SUBMIT_FINALIZE
        and operation.status is OperationStatus.READY
        and isinstance(ready_result, dict)
        and "submission" not in ready_result
    ):
        effective_status = OperationStatus.RUNNING
        effective_phase = "RUNNING"
    error = None if result is None or result.error is None else result.error.to_payload()
    resource_refs: dict[str, object] = {
        key: operation.request_payload[key]
        for key in (
            "workspace_id",
            "workspace_ids",
            "preview_bundle_id",
            "preview_revision_id",
            "submission_id",
            "submission_status",
            "upload_preview_operation_id",
            "batch_id",
            "selected_modified_candidate_id",
            "background",
            "blocks_preview",
            "blocks_submit",
            "blocks_archive",
            "blocks_upload",
        )
        if key in operation.request_payload
    }
    if isinstance(ready_result, dict):
        preview_bundle = ready_result.get("preview_bundle")
        if isinstance(preview_bundle, dict):
            resource_refs = {
                "workspace_id": ready_result.get("workspace_id"),
                "preview_bundle_id": preview_bundle.get("preview_bundle_id"),
                "preview_revision_id": preview_bundle.get("preview_revision_id"),
            }
        submission = ready_result.get("submission")
        workspace = ready_result.get("workspace")
        if isinstance(submission, dict) and isinstance(workspace, dict):
            resource_refs = {
                "workspace_id": workspace.get("id"),
                "submission_id": submission.get("id"),
                "submission_status": submission.get("status"),
            }
    return {
        "operation_id": operation.operation_id,
        "operation_kind": operation.operation_kind.value,
        "status": effective_status.value,
        "phase": effective_phase,
        "resource_refs": resource_refs,
        "ready_result": ready_result,
        "error": error,
        "diagnostics": [diagnostic.to_payload() for diagnostic in operation.diagnostics],
        "poll_after_ms": None if effective_status in _TERMINAL_STATUSES else 3000,
        "submitted_at": operation.created_at.astimezone(timezone.utc).isoformat(),
        "updated_at": operation.updated_at.astimezone(timezone.utc).isoformat(),
    }


_TERMINAL_STATUSES = {
    OperationStatus.READY,
    OperationStatus.FAILED_RETRYABLE,
    OperationStatus.FAILED_FINAL,
    OperationStatus.CANCELLED,
    OperationStatus.SUPERSEDED,
}


def _operation_phase(operation: OperationRecord) -> str:
    if operation.status is OperationStatus.READY:
        return "READY"
    if operation.status in {OperationStatus.FAILED_FINAL, OperationStatus.FAILED_RETRYABLE}:
        return "FAILED"
    if (
        operation.operation_kind is OperationKind.PREVIEW_CACHE_COMPLETION
        and operation.status is OperationStatus.RUNNING
    ):
        return "CACHE_COMPLETION"
    if operation.status is OperationStatus.RUNNING:
        return "COMPUTING"
    return operation.status.value


def _normalize_upload_mode(value: str) -> str:
    return value.strip().upper().replace("-", "_")


def _preview_refs(
    *,
    preview_bundle_id: str,
    preview_token: str,
    preview_revision_id: str,
    preview_strategy_manifest_digest: str,
    preview_bundle_digest: str,
) -> dict[str, object]:
    return {
        "artifact_owner": "WORKSPACE",
        "preview_bundle_id": preview_bundle_id,
        "preview_token": preview_token,
        "preview_revision_id": preview_revision_id,
        "preview_strategy_manifest_ref": "preview_strategy_manifest.json",
        "preview_strategy_manifest_digest": preview_strategy_manifest_digest,
        "preview_bundle_digest": preview_bundle_digest,
        "preview_manifest_ref": "manifest.json",
        "preview_index_ref": "preview_index.json",
        "preview_bundle_root_ref": ".",
        "manifest_ref": "manifest.json",
        "bundle_root_ref": ".",
        "manifest_path": "manifest.json",
        "bundle_path": ".",
        "preview_index_path": "preview_index.json",
    }


def _alignment_report(
    *,
    upload_semantics: str,
    baseline_source: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "alignment-report/v1",
        "rule_version": "alignment/v1",
        "compare_scope": "ALL_TABLES",
        "compare_mode": (
            "INITIALIZE_BASELINE"
            if upload_semantics == "INITIALIZE_BASELINE"
            else "TABLE_FINGERPRINTS"
        ),
        "status": "NORMAL",
        "upload_semantics": upload_semantics,
        "baseline_source": baseline_source,
        "matched_target_type": None,
        "matched_workspace_id": None,
        "matched_preview_role": None,
        "matched_commit_hash": None,
        "is_equal_to_baseline": False,
        "matched_table_count": 0,
        "mismatched_table_count": 0,
        "ignored_table_count": 0,
        "mismatched_tables": [],
        "compared_targets": [],
    }


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


def _summary_configuration_generated_at(materialized) -> str | None:
    value = getattr(getattr(materialized, "summary", None), "configuration_generated_at", None)
    if value is None:
        value = getattr(
            getattr(getattr(materialized, "snapshot", None), "summary", None),
            "configuration_generated_at",
            None,
        )
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)
