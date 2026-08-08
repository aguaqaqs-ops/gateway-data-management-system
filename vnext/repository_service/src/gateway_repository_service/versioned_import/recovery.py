"""Startup reconciliation for interrupted Versioned import operations."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from gateway_repository_contracts import (
    OperationStatus,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import try_unlink_ready_artifact
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.faults import (
    ImportRecoveryFaultInjector,
    ImportRecoveryFaultPoint,
    NoOpImportRecoveryFaultInjector,
)
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportOperationExecutionContext,
    ImportPackageRejected,
    ManualCorrectionDecision,
    RecoveryAuditAction,
    StoredImportOperation,
    is_manual_recovery_error,
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
    ImportVerificationError,
    verify_import_candidate,
)

_LOGGER = logging.getLogger(__name__)

MarkerInspectionKind = Literal["zero", "unique", "ambiguous"]


@dataclass(frozen=True, slots=True)
class ImportRecoveryEvidence:
    operation_id: UUID
    repository_id: UUID
    artifact_id: UUID
    main_commit_id: str
    expected_commit_id: str
    marker_inspection: MarkerInspectionKind
    candidate_commit_id: str | None
    marker_parent_commit_id: str | None
    private_ref_present: bool
    artifact_bytes_present: bool
    artifact_size_bytes: int
    artifact_valid: bool
    manifest_digest: str | None
    verification_policy: VerificationPolicy
    unknown_type_policy: UnknownTypePolicy


def artifact_is_valid(
    *,
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    context: ImportOperationExecutionContext,
    artifact_path: Path,
) -> bool:
    if not artifact_path.is_file():
        return False
    try:
        size = artifact_path.stat().st_size
    except OSError:
        return False
    if size != context.artifact_size_bytes:
        return False
    staging_dir = layout.staging_artifacts / f"import-{context.operation_id.hex}-probe"
    try:
        validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=context.artifact_size_bytes,
            expected_raw_sha256=context.artifact_raw_sha256,
            staging_dir=staging_dir,
            settings=settings,
        )
        return True
    except ImportPackageRejected:
        return False
    except Exception:
        _LOGGER.exception(
            "failed to validate artifact for operation %s",
            context.operation_id,
        )
        return False
    finally:
        cleanup_staging_dir(staging_dir, operation_id=context.operation_id)


def resolve_manifest_digest(
    *,
    store: ImportOperationStore,
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    context: ImportOperationExecutionContext,
) -> str | None:
    stored = store.get_operation(context.repository_id, context.operation_id)
    if stored is not None and stored.canonicalization_manifest_digest is not None:
        return stored.canonicalization_manifest_digest
    artifact_path = artifact_ready_path(
        layout,
        context.repository_id,
        context.artifact_id,
    )
    staging_dir = layout.staging_artifacts / f"import-{context.operation_id.hex}-digest"
    try:
        package = validate_and_extract_import_package(
            artifact_path=artifact_path,
            expected_size_bytes=context.artifact_size_bytes,
            expected_raw_sha256=context.artifact_raw_sha256,
            staging_dir=staging_dir,
            settings=settings,
        )
        return package.manifest.canonicalization_manifest_digest
    except Exception:
        return None
    finally:
        cleanup_staging_dir(staging_dir, operation_id=context.operation_id)


def _private_ref_exists(provider: VersionedImportProvider, private_ref_name: str) -> bool:
    exists = getattr(provider, "private_ref_exists", None)
    if callable(exists):
        return bool(exists(private_ref_name))
    try:
        provider.read_ref(private_ref_name)
        return True
    except Exception:
        return False


def _marker_inspection_kind(
    inspection: MarkerInspectionAmbiguous | MarkerInspectionUnique | MarkerInspectionZero,
) -> MarkerInspectionKind:
    if isinstance(inspection, MarkerInspectionAmbiguous):
        return "ambiguous"
    if isinstance(inspection, MarkerInspectionZero):
        return "zero"
    if isinstance(inspection, MarkerInspectionUnique):
        return "unique"
    raise TypeError("unsupported marker inspection result")


def collect_recovery_evidence(
    *,
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    store: ImportOperationStore,
    provider: VersionedImportProvider,
    context: ImportOperationExecutionContext,
) -> ImportRecoveryEvidence | None:
    try:
        main_commit_id = provider.read_ref(context.target_ref)
        inspection = provider.inspect_marker(context.operation_marker)
        marker_kind = _marker_inspection_kind(inspection)
        candidate_commit_id = inspection.candidate if isinstance(inspection, MarkerInspectionUnique) else None
        marker_parent_commit_id = inspection.parent if isinstance(inspection, MarkerInspectionUnique) else None
        artifact_path = artifact_ready_path(
            layout,
            context.repository_id,
            context.artifact_id,
        )
        artifact_bytes_present = artifact_path.is_file()
        artifact_valid = (
            artifact_is_valid(
                settings=settings,
                layout=layout,
                context=context,
                artifact_path=artifact_path,
            )
            if artifact_bytes_present
            else False
        )
        manifest_digest = resolve_manifest_digest(
            store=store,
            settings=settings,
            layout=layout,
            context=context,
        )
        return ImportRecoveryEvidence(
            operation_id=context.operation_id,
            repository_id=context.repository_id,
            artifact_id=context.artifact_id,
            main_commit_id=main_commit_id,
            expected_commit_id=context.expected_commit_id,
            marker_inspection=marker_kind,
            candidate_commit_id=candidate_commit_id,
            marker_parent_commit_id=marker_parent_commit_id,
            private_ref_present=_private_ref_exists(provider, context.private_ref_name),
            artifact_bytes_present=artifact_bytes_present,
            artifact_size_bytes=context.artifact_size_bytes,
            artifact_valid=artifact_valid,
            manifest_digest=manifest_digest,
            verification_policy=context.verification_policy,
            unknown_type_policy=context.unknown_type_policy,
        )
    except Exception:
        _LOGGER.exception(
            "failed to collect recovery evidence for operation %s",
            context.operation_id,
        )
        return None


def evidence_supports_succeeded_decision(evidence: ImportRecoveryEvidence) -> bool:
    if evidence.marker_inspection != "unique":
        return False
    if evidence.candidate_commit_id is None or evidence.marker_parent_commit_id is None:
        return False
    if evidence.marker_parent_commit_id != evidence.expected_commit_id:
        return False
    if evidence.main_commit_id != evidence.candidate_commit_id:
        return False
    return evidence.manifest_digest is not None


def build_succeeded_result(
    evidence: ImportRecoveryEvidence,
    context: ImportOperationExecutionContext,
) -> VersionedImportResult | None:
    if not evidence_supports_succeeded_decision(evidence):
        return None
    assert evidence.candidate_commit_id is not None
    assert evidence.manifest_digest is not None
    return VersionedImportResult(
        commit_id=evidence.candidate_commit_id,
        target_ref="main",
        artifact_id=context.artifact_id,
        canonicalization_manifest_digest=evidence.manifest_digest,
        expected_commit_id=context.expected_commit_id,
        completed_verification_policy=context.verification_policy,
        unknown_type_policy=context.unknown_type_policy,
    )


def evidence_supports_not_published_decision(evidence: ImportRecoveryEvidence) -> bool:
    if evidence.marker_inspection == "ambiguous":
        return False
    if (
        evidence.marker_inspection == "unique"
        and evidence.candidate_commit_id is not None
        and evidence.main_commit_id == evidence.candidate_commit_id
    ):
        return False
    if evidence.main_commit_id != evidence.expected_commit_id:
        return False
    return evidence.artifact_valid


def resolve_not_published_error(evidence: ImportRecoveryEvidence) -> SimpleError | None:
    if not evidence_supports_not_published_decision(evidence):
        return None
    return SimpleError(
        code="IMPORT_REJECTED",
        message="operator confirmed import was not published",
        details={"reason": "operator_confirmed_not_published"},
        request_id=None,
    )


def build_evidence_summary(
    evidence: ImportRecoveryEvidence,
    *,
    operation: StoredImportOperation,
    decision: ManualCorrectionDecision | None = None,
    action: RecoveryAuditAction | None = None,
    prior_status: str | None = None,
    prior_code: str | None = None,
    final_status: str | None = None,
    final_code: str | None = None,
    stable_code: str | None = None,
    applied_at: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "operation_id": str(evidence.operation_id),
        "repository_id": str(evidence.repository_id),
        "artifact_id": str(evidence.artifact_id),
        "status": operation.status.value,
        "prior_status": prior_status,
        "prior_code": prior_code,
        "final_status": final_status,
        "final_code": final_code,
        "marker_inspection": evidence.marker_inspection,
        "main_commit_id": evidence.main_commit_id,
        "expected_commit_id": evidence.expected_commit_id,
        "candidate_commit_id": evidence.candidate_commit_id,
        "manifest_digest": evidence.manifest_digest,
        "verification_policy": evidence.verification_policy.value,
        "unknown_type_policy": evidence.unknown_type_policy.value,
        "artifact_size_bytes": evidence.artifact_size_bytes,
        "artifact_bytes_present": evidence.artifact_bytes_present,
        "private_ref_present": evidence.private_ref_present,
    }
    if stable_code is not None:
        summary["stable_code"] = stable_code
    elif operation.error is not None:
        summary["stable_code"] = operation.error.code
    if decision is not None:
        summary["decision"] = decision.value
    if action is not None:
        summary["action"] = action.value
    if applied_at is not None:
        summary["applied_at"] = applied_at
    return {key: value for key, value in summary.items() if value is not None}


def cleanup_staging_dir(staging_dir: Path, *, operation_id: UUID) -> None:
    if not staging_dir.exists():
        return
    try:
        shutil.rmtree(staging_dir)
    except OSError:
        _LOGGER.exception("failed to remove staging for operation %s", operation_id)


def cleanup_staging(operation_id: UUID, layout: DurableLayout) -> None:
    staging_dir = layout.staging_artifacts / f"import-{operation_id.hex}"
    cleanup_staging_dir(staging_dir, operation_id=operation_id)


def cleanup_after_succeeded_correction(
    *,
    store: ImportOperationStore,
    layout: DurableLayout,
    context: ImportOperationExecutionContext,
    provider: VersionedImportProvider,
    candidate: str,
) -> None:
    try:
        provider.delete_private_ref(context.private_ref_name, expected_candidate=candidate)
    except Exception:
        _LOGGER.exception(
            "failed to delete private ref during admin succeeded cleanup for %s",
            context.operation_id,
        )
    cleanup_staging(context.operation_id, layout)
    artifact_path = artifact_ready_path(
        layout,
        context.repository_id,
        context.artifact_id,
    )
    try:
        if store.can_delete_artifact_bytes(context.artifact_id) and artifact_path.is_file():
            try_unlink_ready_artifact(artifact_path)
            if not artifact_path.is_file():
                store.mark_artifact_bytes_deleted(context.artifact_id)
    except Exception:
        _LOGGER.exception(
            "failed to delete artifact bytes during admin succeeded cleanup for %s",
            context.operation_id,
        )


def cleanup_after_not_published_correction(
    *,
    layout: DurableLayout,
    context: ImportOperationExecutionContext,
    provider: VersionedImportProvider,
) -> None:
    try:
        provider.delete_private_ref(context.private_ref_name)
    except Exception:
        _LOGGER.exception(
            "failed to delete private ref during admin not-published cleanup for %s",
            context.operation_id,
        )
    cleanup_staging(context.operation_id, layout)


@dataclass(frozen=True, slots=True)
class ImportReconciliationResult:
    queued_operations: int
    running_reconciled: int
    running_manual: int
    succeeded_cleaned: int


class ImportStartupReconciler:
    """Evidence-first startup recovery for durable import operations."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        store: ImportOperationStore,
        provider_factory: Callable[[UUID], VersionedImportProvider],
        fault_injector: ImportRecoveryFaultInjector | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._store = store
        self._provider_factory = provider_factory
        self._fault_injector = fault_injector or NoOpImportRecoveryFaultInjector()

    def reconcile(self) -> ImportReconciliationResult:
        queued = len(self._store.list_operations_by_status(OperationStatus.QUEUED))
        running_reconciled = 0
        running_manual = 0
        succeeded_cleaned = 0

        for operation in self._store.list_operations_by_status(OperationStatus.SUCCEEDED):
            if self._cleanup_succeeded_residuals(operation):
                succeeded_cleaned += 1

        for operation in self._store.list_operations_by_status(OperationStatus.FAILED):
            if is_manual_recovery_error(operation.error):
                continue
            self._cleanup_staging(operation.operation_id)

        for operation in self._store.list_running_operations():
            outcome = self._reconcile_running(operation)
            if outcome == "recovered":
                running_reconciled += 1
            elif outcome == "manual":
                running_manual += 1

        return ImportReconciliationResult(
            queued_operations=queued,
            running_reconciled=running_reconciled,
            running_manual=running_manual,
            succeeded_cleaned=succeeded_cleaned,
        )

    def _reconcile_running(self, operation: StoredImportOperation) -> str:
        context = self._store.load_execution_context(operation.operation_id)
        if context is None:
            self._mark_manual(operation.operation_id, "execution context is missing")
            return "manual"

        artifact_path = artifact_ready_path(
            self._layout,
            context.repository_id,
            context.artifact_id,
        )
        if not artifact_is_valid(
            settings=self._settings,
            layout=self._layout,
            context=context,
            artifact_path=artifact_path,
        ):
            self._mark_manual(operation.operation_id, "artifact evidence is missing or invalid")
            return "manual"

        try:
            provider = self._provider_factory(context.repository_id)
        except Exception:
            _LOGGER.exception(
                "failed to open provider for running operation %s",
                operation.operation_id,
            )
            return "unchanged"

        try:
            main = provider.read_ref(context.target_ref)
        except Exception:
            _LOGGER.exception(
                "failed to read main for running operation %s",
                operation.operation_id,
            )
            return "unchanged"

        marker_outcome = self._try_recover_published_marker(context, provider, main)
        if marker_outcome == "recovered":
            return "recovered"
        if marker_outcome == "manual":
            return "manual"

        if main != context.expected_commit_id:
            self._mark_manual(
                operation.operation_id,
                "main does not match expected commit during recovery",
            )
            return "manual"

        continue_outcome = self._try_continue_verification_cas(context, provider)
        if continue_outcome == "recovered":
            return "recovered"
        if continue_outcome == "manual":
            return "manual"

        replay_count = operation.automatic_replay_count
        if replay_count == 0:
            replay_outcome = self._try_automatic_replay(context, provider, artifact_path)
            if replay_outcome == "recovered":
                return "recovered"
            if replay_outcome == "manual":
                return "manual"

        if replay_count >= 1:
            self._mark_manual(
                operation.operation_id,
                "automatic replay already consumed without recoverable evidence",
            )
            return "manual"

        return "unchanged"

    def _try_recover_published_marker(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        main: str,
    ) -> str:
        try:
            inspection = provider.inspect_marker(context.operation_marker)
        except Exception:
            _LOGGER.exception(
                "failed to inspect marker for operation %s",
                context.operation_id,
            )
            return "unchanged"

        if isinstance(inspection, MarkerInspectionAmbiguous):
            self._mark_manual(context.operation_id, "operation marker evidence is ambiguous")
            return "manual"
        if isinstance(inspection, MarkerInspectionZero):
            return "unchanged"
        if not isinstance(inspection, MarkerInspectionUnique):
            self._mark_manual(context.operation_id, "operation marker evidence is not unique")
            return "manual"
        if inspection.parent != context.expected_commit_id:
            self._mark_manual(
                context.operation_id,
                "operation marker parent does not match expected commit",
            )
            return "manual"
        if main != inspection.candidate:
            return "unchanged"

        manifest_digest = resolve_manifest_digest(
            store=self._store,
            settings=self._settings,
            layout=self._layout,
            context=context,
        )
        if manifest_digest is None:
            self._mark_manual(context.operation_id, "canonicalization manifest digest is unavailable")
            return "manual"

        result = VersionedImportResult(
            commit_id=inspection.candidate,
            target_ref="main",
            artifact_id=context.artifact_id,
            canonicalization_manifest_digest=manifest_digest,
            expected_commit_id=context.expected_commit_id,
            completed_verification_policy=context.verification_policy,
            unknown_type_policy=context.unknown_type_policy,
        )
        self._store.mark_succeeded(context.operation_id, result=result)
        cleanup_after_succeeded_correction(
            store=self._store,
            layout=self._layout,
            context=context,
            provider=provider,
            candidate=inspection.candidate,
        )
        return "recovered"

    def _try_continue_verification_cas(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
    ) -> str:
        try:
            private_head = provider.read_ref(context.private_ref_name)
        except Exception:
            return "unchanged"

        try:
            inspection = provider.inspect_marker(context.operation_marker)
        except Exception:
            _LOGGER.exception(
                "failed to inspect marker while continuing verification for %s",
                context.operation_id,
            )
            return "unchanged"

        if isinstance(inspection, MarkerInspectionAmbiguous):
            self._mark_manual(context.operation_id, "operation marker evidence is ambiguous")
            return "manual"
        if isinstance(inspection, MarkerInspectionZero):
            if private_head != context.expected_commit_id:
                return "unchanged"
            try:
                provider.checkout_private_ref(context.private_ref_name)
                private_head = provider.commit_operation_marker(
                    context.private_ref_name,
                    context.operation_marker,
                )
                inspection = provider.inspect_marker(context.operation_marker)
                if isinstance(inspection, MarkerInspectionUnique) and inspection.candidate != private_head:
                    self._mark_manual(
                        context.operation_id,
                        "operation marker candidate does not match private ref head",
                    )
                    return "manual"
            except Exception:
                _LOGGER.debug(
                    "marker commit was not possible while continuing interrupted replay for %s",
                    context.operation_id,
                    exc_info=True,
                )
                return "unchanged"
        if isinstance(inspection, MarkerInspectionZero):
            return "unchanged"
        if not isinstance(inspection, MarkerInspectionUnique):
            self._mark_manual(context.operation_id, "operation marker evidence is not unique")
            return "manual"
        if inspection.parent != context.expected_commit_id:
            self._mark_manual(
                context.operation_id,
                "operation marker parent does not match expected commit",
            )
            return "manual"
        if inspection.candidate != private_head:
            self._mark_manual(
                context.operation_id,
                "operation marker candidate does not match private ref head",
            )
            return "manual"

        candidate = inspection.candidate
        staging_dir = self._layout.staging_artifacts / f"import-{context.operation_id.hex}"
        try:
            artifact_path = artifact_ready_path(
                self._layout,
                context.repository_id,
                context.artifact_id,
            )
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self._settings,
            )
            verify_import_candidate(
                provider,
                candidate=candidate,
                manifest=package.manifest,
                verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=context.unknown_type_policy,
            )
            main_after = provider.read_ref(context.target_ref)
            if main_after != context.expected_commit_id:
                self._mark_manual(
                    context.operation_id,
                    "target ref changed before publication during recovery",
                )
                return "manual"
            publish_result = provider.publish_main(context.expected_commit_id, candidate)
            if isinstance(publish_result, PublishMainMismatch):
                self._mark_manual(
                    context.operation_id,
                    "target ref mismatch during publication recovery",
                )
                return "manual"
            if isinstance(publish_result, PublishMainAmbiguous):
                self._mark_manual(context.operation_id, "main publication evidence is ambiguous")
                return "manual"
            if not isinstance(publish_result, PublishMainPublished):
                self._mark_manual(
                    context.operation_id,
                    "main publication result is not provably published",
                )
                return "manual"
            readback = provider.read_ref(context.target_ref)
            if readback != candidate:
                self._mark_manual(context.operation_id, "main readback does not match candidate commit")
                return "manual"
            result = VersionedImportResult(
                commit_id=candidate,
                target_ref="main",
                artifact_id=context.artifact_id,
                canonicalization_manifest_digest=package.manifest.canonicalization_manifest_digest,
                expected_commit_id=context.expected_commit_id,
                completed_verification_policy=context.verification_policy,
                unknown_type_policy=context.unknown_type_policy,
            )
            self._store.mark_succeeded(context.operation_id, result=result)
            cleanup_after_succeeded_correction(
                store=self._store,
                layout=self._layout,
                context=context,
                provider=provider,
                candidate=candidate,
            )
            return "recovered"
        except ImportVerificationError as exc:
            self._mark_manual(context.operation_id, f"verification failed during recovery: {exc.code}")
            return "manual"
        except ImportPackageRejected:
            self._mark_manual(context.operation_id, "import package rejected during recovery")
            return "manual"
        except ImportProviderError:
            self._mark_manual(context.operation_id, "provider failure during recovery continuation")
            return "manual"
        except Exception:
            _LOGGER.exception(
                "unexpected failure while continuing verification for %s",
                context.operation_id,
            )
            return "unchanged"
        finally:
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    _LOGGER.exception(
                        "failed to remove import staging for operation %s",
                        context.operation_id,
                    )

    def _try_automatic_replay(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        artifact_path: Path,
    ) -> str:
        staging_dir = self._layout.staging_artifacts / f"import-{context.operation_id.hex}"
        try:
            self._store.increment_automatic_replay_count(context.operation_id)
            self._fault_injector.maybe_raise(
                ImportRecoveryFaultPoint.AFTER_AUTOMATIC_REPLAY_COUNT_INCREMENT
            )
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self._settings,
            )
            try:
                provider.delete_private_ref(context.private_ref_name)
            except Exception:
                _LOGGER.debug(
                    "private ref cleanup before automatic replay failed for %s",
                    context.operation_id,
                    exc_info=True,
                )
            provider.create_private_ref(context.private_ref_name, context.expected_commit_id)
            provider.checkout_private_ref(context.private_ref_name)
            provider.replay_sql(context.private_ref_name, package.replay_sql_path)
            candidate = provider.commit_operation_marker(
                context.private_ref_name,
                context.operation_marker,
            )
            inspection = provider.inspect_marker(context.operation_marker)
            if isinstance(inspection, MarkerInspectionAmbiguous):
                self._mark_manual(context.operation_id, "operation marker evidence is ambiguous")
                return "manual"
            if isinstance(inspection, MarkerInspectionZero):
                self._mark_manual(context.operation_id, "operation marker evidence is missing after replay")
                return "manual"
            if not isinstance(inspection, MarkerInspectionUnique):
                self._mark_manual(context.operation_id, "operation marker evidence is not unique")
                return "manual"
            if inspection.parent != context.expected_commit_id:
                self._mark_manual(
                    context.operation_id,
                    "operation marker parent does not match expected commit",
                )
                return "manual"
            if inspection.candidate != candidate:
                self._mark_manual(
                    context.operation_id,
                    "operation marker candidate does not match private ref head",
                )
                return "manual"
            verify_import_candidate(
                provider,
                candidate=candidate,
                manifest=package.manifest,
                verification_policy=context.verification_policy,
                unknown_type_policy=context.unknown_type_policy,
            )
            main_after = provider.read_ref(context.target_ref)
            if main_after != context.expected_commit_id:
                self._mark_manual(
                    context.operation_id,
                    "target ref changed before publication during automatic replay",
                )
                return "manual"
            publish_result = provider.publish_main(context.expected_commit_id, candidate)
            if isinstance(publish_result, PublishMainMismatch):
                self._mark_manual(
                    context.operation_id,
                    "target ref mismatch during automatic replay publication",
                )
                return "manual"
            if isinstance(publish_result, PublishMainAmbiguous):
                self._mark_manual(context.operation_id, "main publication evidence is ambiguous")
                return "manual"
            if not isinstance(publish_result, PublishMainPublished):
                self._mark_manual(
                    context.operation_id,
                    "main publication result is not provably published",
                )
                return "manual"
            readback = provider.read_ref(context.target_ref)
            if readback != candidate:
                self._mark_manual(context.operation_id, "main readback does not match candidate commit")
                return "manual"
            result = VersionedImportResult(
                commit_id=candidate,
                target_ref="main",
                artifact_id=context.artifact_id,
                canonicalization_manifest_digest=package.manifest.canonicalization_manifest_digest,
                expected_commit_id=context.expected_commit_id,
                completed_verification_policy=context.verification_policy,
                unknown_type_policy=context.unknown_type_policy,
            )
            self._store.mark_succeeded(context.operation_id, result=result)
            cleanup_after_succeeded_correction(
                store=self._store,
                layout=self._layout,
                context=context,
                provider=provider,
                candidate=candidate,
            )
            return "recovered"
        except ImportVerificationError as exc:
            self._mark_manual(context.operation_id, f"verification failed during automatic replay: {exc.code}")
            return "manual"
        except ImportPackageRejected:
            self._mark_manual(context.operation_id, "import package rejected during automatic replay")
            return "manual"
        except ImportProviderError:
            self._mark_manual(context.operation_id, "provider failure during automatic replay")
            return "manual"
        except Exception:
            _LOGGER.exception(
                "unexpected failure during automatic replay for %s",
                context.operation_id,
            )
            return "unchanged"
        finally:
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    _LOGGER.exception(
                        "failed to remove import staging for operation %s",
                        context.operation_id,
                    )

    def _cleanup_succeeded_residuals(self, operation: StoredImportOperation) -> bool:
        context = self._store.load_execution_context(operation.operation_id)
        if context is None or operation.result is None:
            return False
        try:
            provider = self._provider_factory(context.repository_id)
        except Exception:
            _LOGGER.exception(
                "failed to open provider for succeeded cleanup %s",
                operation.operation_id,
            )
            return False
        cleanup_after_succeeded_correction(
            store=self._store,
            layout=self._layout,
            context=context,
            provider=provider,
            candidate=operation.result.commit_id,
        )
        return True

    def _cleanup_staging(self, operation_id: UUID) -> None:
        cleanup_staging(operation_id, self._layout)

    def _mark_manual(self, operation_id: UUID, message: str) -> None:
        try:
            self._store.mark_failed(
                operation_id,
                error=SimpleError(
                    code=MANUAL_RECOVERY_REQUIRED_CODE,
                    message=message,
                    details={"reason": "startup_recovery"},
                    request_id=None,
                ),
            )
        except Exception:
            _LOGGER.exception("failed to persist manual recovery for operation %s", operation_id)
