"""Single-operation executor for durable Versioned import workers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gateway_repository_contracts import SimpleError, VersionedImportResult

from gateway_repository_service.capacity import CapacityAdmissionError, assert_import_disk_admission
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import (
    try_unlink_ready_artifact_with_recheck,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.errors import (
    ImportProviderError,
    sanitize_import_error_detail,
    sanitize_import_error_details,
)
from gateway_repository_service.versioned_import.faults import (
    ImportWorkerFaultInjector,
    ImportWorkerFaultPoint,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportOperationExecutionContext,
    ImportPackageRejected,
)
from gateway_repository_service.versioned_import.package import validate_and_extract_import_package
from gateway_repository_service.versioned_import.ports import (
    MarkerInspectionAmbiguous,
    MarkerInspectionUnique,
    MarkerInspectionZero,
    PublishMainAmbiguous,
    PublishMainMismatch,
    PublishMainPublished,
    VersionedImportProvider,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.verification import (
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
    ImportVerificationError,
    verify_import_candidate,
)

_LOGGER = logging.getLogger(__name__)

MarkerInspectionKind = Literal["zero", "unique", "ambiguous", "unknown"]


@dataclass(slots=True)
class ExecutionEvidence:
    expected_commit_id: str
    main_before: str | None = None
    main_after_first_check: str | None = None
    main_after_second_check: str | None = None
    private_ref_created: bool = False
    candidate: str | None = None
    marker_inspection_kind: MarkerInspectionKind = "unknown"
    publish_attempted: bool = False

    def main_unchanged(self) -> bool:
        if self.main_before is None:
            return False
        current = self.main_after_second_check or self.main_after_first_check
        if current is None:
            return False
        return current == self.main_before == self.expected_commit_id

    def provably_no_repository_effect(self) -> bool:
        if self.publish_attempted or self.private_ref_created or self.has_marker_evidence():
            return False
        if self.main_before is None:
            return True
        return self.main_unchanged()

    def has_marker_evidence(self) -> bool:
        return self.marker_inspection_kind in {"unique", "ambiguous"}


class ImportOperationExecutor:
    """Runs one claimed import operation through validation, CAS and cleanup."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        store: ImportOperationStore,
        fault_injector: ImportWorkerFaultInjector | None = None,
        interruption_check: Callable[[], bool] | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._store = store
        self._fault_injector = fault_injector or NoOpImportWorkerFaultInjector()
        self._interruption_check = interruption_check

    def _is_interrupted(self) -> bool:
        return self._interruption_check is not None and self._interruption_check()

    def execute(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
    ) -> None:
        evidence = ExecutionEvidence(expected_commit_id=context.expected_commit_id)
        staging_dir = self._layout.staging_artifacts / f"import-{context.operation_id.hex}"
        try:
            self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM)
            self._run_pipeline(context, provider, evidence, staging_dir)
        except Exception as exc:
            if self._is_interrupted():
                _LOGGER.info(
                    "import operation %s interrupted; preserving RUNNING",
                    context.operation_id,
                )
                return
            self._handle_failure(context, provider, evidence, exc)

    def _run_pipeline(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        evidence: ExecutionEvidence,
        staging_dir: Path,
    ) -> None:
        artifact_path = artifact_ready_path(
            self._layout,
            context.repository_id,
            context.artifact_id,
        )
        try:
            assert_import_disk_admission(self._layout.root, self._settings)
        except CapacityAdmissionError as exc:
            raise _terminal_error(
                IMPORT_REJECTED_CODE,
                "disk admission denied before package extraction",
            ) from exc
        package = validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=context.artifact_size_bytes,
            expected_raw_sha256=context.artifact_raw_sha256,
            staging_dir=staging_dir,
            settings=self._settings,
        )
        self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED)

        if context.target_ref != "main":
            raise _terminal_error(
                IMPORT_REJECTED_CODE,
                "unsupported target ref",
                detail={"target_ref": context.target_ref},
            )

        evidence.main_before = provider.read_ref(context.target_ref)
        if evidence.main_before != context.expected_commit_id:
            raise _terminal_error(
                "EXPECTED_COMMIT_MISMATCH",
                "target ref does not match expected commit",
                detail={
                    "expected": context.expected_commit_id,
                    "actual": evidence.main_before,
                },
            )
        evidence.main_after_first_check = evidence.main_before

        provider.create_private_ref(context.private_ref_name, context.expected_commit_id)
        evidence.private_ref_created = True
        provider.checkout_private_ref(context.private_ref_name)
        self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED)

        provider.replay_sql(context.private_ref_name, package.replay_sql_path)
        self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER)

        candidate = provider.commit_operation_marker(
            context.private_ref_name,
            context.operation_marker,
        )
        evidence.candidate = candidate
        inspection = provider.inspect_marker(context.operation_marker)
        evidence.marker_inspection_kind = _marker_kind(inspection)
        if isinstance(inspection, MarkerInspectionAmbiguous):
            raise _manual_recovery("operation marker evidence is ambiguous")
        if isinstance(inspection, MarkerInspectionZero):
            raise _manual_recovery("operation marker evidence is missing after commit")
        if not isinstance(inspection, MarkerInspectionUnique):
            raise _manual_recovery("operation marker evidence is not unique")
        if inspection.parent != context.expected_commit_id:
            raise _manual_recovery("operation marker parent does not match expected commit")
        if inspection.candidate != candidate:
            raise _manual_recovery("operation marker candidate does not match private ref head")

        self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION)

        verify_import_candidate(
            provider,
            candidate=candidate,
            manifest=package.manifest,
            verification_policy=context.verification_policy,
            unknown_type_policy=context.unknown_type_policy,
        )
        self._fault_injector.maybe_raise(
            ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK
        )

        evidence.main_after_second_check = provider.read_ref(context.target_ref)
        if evidence.main_after_second_check != context.expected_commit_id:
            raise _terminal_error(
                "EXPECTED_COMMIT_MISMATCH",
                "target ref changed before publication",
                detail={
                    "expected": context.expected_commit_id,
                    "actual": evidence.main_after_second_check,
                },
            )
        self._fault_injector.maybe_raise(
            ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH
        )

        evidence.publish_attempted = True
        publish_result = provider.publish_main(context.expected_commit_id, candidate)
        if isinstance(publish_result, PublishMainMismatch):
            raise _terminal_error(
                "EXPECTED_COMMIT_MISMATCH",
                "target ref mismatch during publication",
                detail={
                    "expected": context.expected_commit_id,
                    "actual": publish_result.actual,
                },
            )
        if isinstance(publish_result, PublishMainAmbiguous):
            raise _manual_recovery("main publication evidence is ambiguous")
        if not isinstance(publish_result, PublishMainPublished):
            raise _manual_recovery("main publication result is not provably published")

        readback = provider.read_ref(context.target_ref)
        if readback != candidate:
            raise _manual_recovery("main readback does not match candidate commit")

        result = VersionedImportResult(
            commit_id=candidate,
            target_ref="main",
            artifact_id=context.artifact_id,
            canonicalization_manifest_digest=package.manifest.canonicalization_manifest_digest,
            expected_commit_id=context.expected_commit_id,
            completed_verification_policy=context.verification_policy,
            unknown_type_policy=context.unknown_type_policy,
        )
        self._fault_injector.maybe_raise(ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED)
        self._store.mark_succeeded(context.operation_id, result=result)
        self._fault_injector.maybe_raise(
            ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP
        )
        self._best_effort_delete_private_ref(provider, context, candidate)
        self._fault_injector.maybe_raise(
            ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP
        )
        self._best_effort_delete_artifact_bytes(context, artifact_path)

    def _handle_failure(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        evidence: ExecutionEvidence,
        exc: BaseException,
    ) -> None:
        if self._is_interrupted():
            _LOGGER.info(
                "import operation %s interrupted; preserving RUNNING",
                context.operation_id,
            )
            return

        if isinstance(exc, _TerminalFailure):
            self._persist_terminal_failure(context, provider, evidence, exc.error)
            return

        if isinstance(exc, ImportVerificationError):
            code = exc.code
            if code == IMPORT_REJECTED_CODE:
                self._persist_terminal_failure(
                    context,
                    provider,
                    evidence,
                    _simple_error(code, "import rejected", detail=exc.detail),
                )
                return
            if code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE:
                if evidence.main_unchanged():
                    self._best_effort_delete_private_ref(
                        provider,
                        context,
                        evidence.candidate,
                    )
                self._persist_terminal_failure(
                    context,
                    provider,
                    evidence,
                    _simple_error(code, "verification failed before publication", detail=exc.detail),
                )
                return
            self._persist_terminal_failure(
                context,
                provider,
                evidence,
                _manual_error("verification failure evidence is ambiguous"),
            )
            return

        if isinstance(exc, ImportPackageRejected):
            self._persist_terminal_failure(
                context,
                provider,
                evidence,
                _simple_error(IMPORT_REJECTED_CODE, "import package rejected", detail=str(exc)),
            )
            return

        if isinstance(exc, ImportProviderError):
            mapped = _map_provider_failure(evidence, detail=str(exc))
            self._persist_terminal_failure(context, provider, evidence, mapped)
            return

        mapped = _map_unknown_failure(evidence, detail=str(exc))
        self._persist_terminal_failure(context, provider, evidence, mapped)

    def _persist_terminal_failure(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        evidence: ExecutionEvidence,
        error: SimpleError,
    ) -> None:
        if (
            error.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
            and evidence.main_unchanged()
        ):
            self._best_effort_delete_private_ref(provider, context, evidence.candidate)
        self._store.mark_failed(context.operation_id, error=error)

    def _best_effort_delete_private_ref(
        self,
        provider: VersionedImportProvider,
        context: ImportOperationExecutionContext,
        candidate: str | None,
    ) -> None:
        if not context.private_ref_name:
            return
        try:
            provider.delete_private_ref(
                context.private_ref_name,
                expected_candidate=candidate,
            )
        except Exception:
            _LOGGER.exception(
                "failed to delete private ref for operation %s",
                context.operation_id,
            )

    def _best_effort_delete_artifact_bytes(
        self,
        context: ImportOperationExecutionContext,
        artifact_path: Path,
    ) -> None:
        try:
            stamped = {"ok": False}

            def _stamp() -> None:
                self._store.mark_artifact_bytes_deleted(
                    context.artifact_id,
                    repository_id=context.repository_id,
                )
                stamped["ok"] = True

            outcome = try_unlink_ready_artifact_with_recheck(
                artifact_path,
                recheck=lambda: self._store.can_delete_artifact_bytes(
                    context.artifact_id,
                    ttl_seconds=self._settings.artifact_ttl_seconds,
                ),
                layout=self._layout,
                repository_id=context.repository_id,
                artifact_id=context.artifact_id,
                on_deleted=_stamp,
            )
            if outcome != "deleted" or not stamped["ok"]:
                return
        except Exception:
            _LOGGER.exception(
                "failed to delete artifact bytes for operation %s",
                context.operation_id,
            )


class _TerminalFailure(Exception):
    def __init__(self, error: SimpleError) -> None:
        self.error = error
        super().__init__(error.message)


def _terminal_error(
    code: str,
    message: str,
    *,
    detail: str | dict[str, object] | None = None,
) -> _TerminalFailure:
    return _TerminalFailure(_simple_error(code, message, detail=detail))


def _manual_recovery(message: str, *, detail: str | None = None) -> _TerminalFailure:
    return _TerminalFailure(_manual_error(message, detail=detail))


def _manual_error(message: str, *, detail: str | None = None) -> SimpleError:
    return _simple_error(MANUAL_RECOVERY_REQUIRED_CODE, message, detail=detail)


def _simple_error(
    code: str,
    message: str,
    *,
    detail: str | dict[str, object] | None = None,
) -> SimpleError:
    details: dict[str, object] | None
    if isinstance(detail, dict):
        details = sanitize_import_error_details(detail)
    elif detail is None:
        details = None
    else:
        sanitized = sanitize_import_error_detail(detail)
        details = {"reason": sanitized} if sanitized is not None else None
    return SimpleError(code=code, message=message, details=details, request_id=None)


def _marker_kind(inspection: object) -> MarkerInspectionKind:
    if isinstance(inspection, MarkerInspectionZero):
        return "zero"
    if isinstance(inspection, MarkerInspectionUnique):
        return "unique"
    if isinstance(inspection, MarkerInspectionAmbiguous):
        return "ambiguous"
    return "unknown"


def _has_private_ref_without_marker(evidence: ExecutionEvidence) -> bool:
    return evidence.private_ref_created and not evidence.has_marker_evidence()


def _map_provider_failure(evidence: ExecutionEvidence, *, detail: str) -> SimpleError:
    if evidence.provably_no_repository_effect():
        return _simple_error(
            IMPORT_REJECTED_CODE,
            "import provider rejected request",
            detail=detail,
        )
    if evidence.publish_attempted or evidence.marker_inspection_kind == "ambiguous":
        return _manual_error("provider failure after publication evidence", detail=detail)
    if evidence.has_marker_evidence() and not evidence.main_unchanged():
        return _manual_error("provider failure with contradictory marker evidence", detail=detail)
    if evidence.private_ref_created and evidence.has_marker_evidence():
        return _manual_error("provider failure after durable marker evidence", detail=detail)
    if evidence.private_ref_created and not evidence.main_unchanged():
        return _manual_error("provider failure after private ref with main movement", detail=detail)
    if _has_private_ref_without_marker(evidence):
        return _manual_error("provider failure after private ref creation", detail=detail)
    return _manual_error("provider failure evidence is ambiguous", detail=detail)


def _map_unknown_failure(evidence: ExecutionEvidence, *, detail: str) -> SimpleError:
    if evidence.provably_no_repository_effect():
        return _simple_error(IMPORT_REJECTED_CODE, "import rejected", detail=detail)
    if evidence.publish_attempted:
        return _manual_error("unexpected failure after publication attempt", detail=detail)
    if evidence.private_ref_created and evidence.has_marker_evidence():
        return _manual_error("unexpected failure after marker evidence", detail=detail)
    if _has_private_ref_without_marker(evidence):
        return _manual_error("unexpected failure after private ref creation", detail=detail)
    return _manual_error("unexpected failure with ambiguous evidence", detail=detail)
