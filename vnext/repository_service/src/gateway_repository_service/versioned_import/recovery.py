"""Startup reconciliation for interrupted Versioned import operations."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import OperationStatus, SimpleError, VersionedImportResult

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    ImportOperationExecutionContext,
    ImportPackageRejected,
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
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._store = store
        self._provider_factory = provider_factory

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
        if not self._artifact_is_valid(context, artifact_path):
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

        manifest_digest = self._resolve_manifest_digest(context)
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
        self._cleanup_succeeded_residuals_for_context(context, provider, inspection.candidate)
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

        if isinstance(inspection, MarkerInspectionZero):
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
                verification_policy=context.verification_policy,
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
            self._cleanup_succeeded_residuals_for_context(context, provider, candidate)
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
            self._cleanup_succeeded_residuals_for_context(context, provider, candidate)
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
        self._cleanup_succeeded_residuals_for_context(
            context,
            provider,
            operation.result.commit_id,
        )
        return True

    def _cleanup_succeeded_residuals_for_context(
        self,
        context: ImportOperationExecutionContext,
        provider: VersionedImportProvider,
        candidate: str,
    ) -> None:
        try:
            provider.delete_private_ref(context.private_ref_name, expected_candidate=candidate)
        except Exception:
            _LOGGER.exception(
                "failed to delete private ref during recovery cleanup for %s",
                context.operation_id,
            )
        self._cleanup_staging(context.operation_id)
        artifact_path = artifact_ready_path(
            self._layout,
            context.repository_id,
            context.artifact_id,
        )
        try:
            if self._store.can_delete_artifact_bytes(context.artifact_id) and artifact_path.is_file():
                artifact_path.unlink()
                self._store.mark_artifact_bytes_deleted(context.artifact_id)
        except Exception:
            _LOGGER.exception(
                "failed to delete artifact bytes during recovery cleanup for %s",
                context.operation_id,
            )

    def _cleanup_staging(self, operation_id: UUID) -> None:
        staging_dir = self._layout.staging_artifacts / f"import-{operation_id.hex}"
        if not staging_dir.exists():
            return
        try:
            shutil.rmtree(staging_dir)
        except OSError:
            _LOGGER.exception("failed to remove import staging for operation %s", operation_id)

    def _artifact_is_valid(
        self,
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
        staging_dir = self._layout.staging_artifacts / f"import-{context.operation_id.hex}-probe"
        try:
            validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self._settings,
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
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    _LOGGER.exception(
                        "failed to remove artifact probe staging for operation %s",
                        context.operation_id,
                    )

    def _resolve_manifest_digest(
        self,
        context: ImportOperationExecutionContext,
    ) -> str | None:
        stored = self._store.get_operation(context.repository_id, context.operation_id)
        if stored is not None and stored.canonicalization_manifest_digest is not None:
            return stored.canonicalization_manifest_digest
        artifact_path = artifact_ready_path(
            self._layout,
            context.repository_id,
            context.artifact_id,
        )
        staging_dir = self._layout.staging_artifacts / f"import-{context.operation_id.hex}-digest"
        try:
            package = validate_and_extract_import_package(
                artifact_path=artifact_path,
                expected_size_bytes=context.artifact_size_bytes,
                expected_raw_sha256=context.artifact_raw_sha256,
                staging_dir=staging_dir,
                settings=self._settings,
            )
            return package.manifest.canonicalization_manifest_digest
        except Exception:
            return None
        finally:
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    _LOGGER.exception(
                        "failed to remove digest staging for operation %s",
                        context.operation_id,
                    )

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
