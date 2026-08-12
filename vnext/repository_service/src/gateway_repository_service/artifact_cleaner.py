"""Runtime-owned artifact retention cleaner."""

from __future__ import annotations

import fcntl
import logging
import os
import stat as stat_module
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
    retention_explains_missing_ready_bytes,
)
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    MutationStore,
    MutationStoreInvariantError,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import (
    OwnedPathError,
    open_owned_ready_dir,
    parse_detach_name,
    parse_quarantine_name,
    try_unlink_ready_artifact_with_recheck as try_unlink_ready_artifact_with_recheck,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)

_HEX32 = frozenset("0123456789abcdef")


@runtime_checkable
class ArtifactCleanerLifecycle(Protocol):
    """Instance-scoped stop/join seam owned by ServiceRuntime."""

    def stop(self, *, timeout: float | None = None) -> None:
        """Stop and join cleaner work. Idempotent."""


class ArtifactCleanerShutdownError(RuntimeError):
    """Raised when the cleaner thread does not stop within the join timeout."""


class NoOpArtifactCleaner:
    """Default cleaner that performs no background work."""

    def stop(self, *, timeout: float | None = None) -> None:
        del timeout

    def notify(self) -> None:
        return None


class ArtifactCleaner:
    """Non-daemon retention cleaner with sticky wake and interval fallback."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        import_store: ImportOperationStore,
        mutation_store: MutationStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._import_store = import_store
        self._mutation_store = mutation_store or import_store.mutation_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._condition = threading.Condition()
        self._pending = False
        self._stopping = False
        self._started = False
        self._thread: threading.Thread | None = None
        self._stop_lock = threading.Lock()

    def start(self) -> None:
        with self._stop_lock:
            if self._started:
                return
            self._stopping = False
            self._pending = False
            thread = threading.Thread(
                target=self._run,
                name="artifact-cleaner",
                daemon=False,
            )
            self._thread = thread
            self._started = True
            thread.start()

    def notify(self) -> None:
        with self._condition:
            self._pending = True
            self._condition.notify_all()

    def stop(self, *, timeout: float | None = None) -> None:
        with self._stop_lock:
            thread = self._thread
            if thread is None:
                self._started = False
                return
            with self._condition:
                self._stopping = True
                self._pending = True
                self._condition.notify_all()
            join_timeout = timeout if timeout is not None else 30.0
            thread.join(timeout=join_timeout)
            if thread.is_alive():
                raise ArtifactCleanerShutdownError(
                    f"artifact cleaner thread did not stop within {join_timeout}s"
                )
            self._thread = None
            self._started = False

    def sweep_once(self) -> None:
        """Run one sweep synchronously (tests / startup-compatible probe)."""

        self._sweep()

    def _run(self) -> None:
        interval = float(self._settings.artifact_cleanup_interval_seconds)
        while True:
            try:
                self._sweep()
            except Exception:
                _LOGGER.exception("artifact cleaner sweep failed")
                log_event(
                    "artifact_cleanup",
                    stage="sweep",
                    result="error",
                    cleanup_outcome="sweep_exception",
                    logger=_LOGGER,
                )
            with self._condition:
                if self._stopping:
                    return
                if self._pending:
                    self._pending = False
                    continue
                self._condition.wait(timeout=max(interval, 0.0))
                if self._stopping:
                    return
                self._pending = False

    def _sweep(self) -> None:
        started = time.monotonic()
        self._inventory_owned_artifact_tree()
        self._recover_delete_quarantines()
        try:
            candidates = self._mutation_store.list_artifacts_pending_byte_cleanup()
        except Exception:
            _LOGGER.exception("artifact cleaner failed to list candidates")
            log_event(
                "artifact_cleanup",
                stage="list_candidates",
                result="error",
                cleanup_outcome="list_failed",
                logger=_LOGGER,
            )
            return

        for lifecycle in candidates:
            if self._stopping:
                return
            try:
                self._process_candidate(lifecycle.artifact_id, lifecycle.repository_id)
            except Exception:
                _LOGGER.exception(
                    "artifact cleaner failed for artifact %s",
                    lifecycle.artifact_id,
                )
                log_event(
                    "artifact_cleanup",
                    repository_id=lifecycle.repository_id,
                    artifact_id=lifecycle.artifact_id,
                    stage="candidate",
                    result="error",
                    cleanup_outcome="candidate_exception",
                    logger=_LOGGER,
                )

        duration_ms = int((time.monotonic() - started) * 1000)
        log_event(
            "artifact_cleanup",
            stage="sweep",
            duration_ms=duration_ms,
            result="completed",
            cleanup_outcome="sweep_completed",
            logger=_LOGGER,
        )

    def _process_candidate(self, artifact_id: UUID, repository_id: UUID) -> None:
        now = self._clock()
        decision = self._import_store.evaluate_artifact_bytes_deletion(
            artifact_id,
            now=now,
            ttl_seconds=self._settings.artifact_ttl_seconds,
        )
        if not decision.eligible:
            if decision.reason in {
                ArtifactBytesDeletionReason.ALREADY_DELETED,
                ArtifactBytesDeletionReason.PROTECTED,
                ArtifactBytesDeletionReason.TTL_NOT_ELAPSED,
            }:
                return
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="eligibility",
                result="retained",
                code=decision.reason.value,
                cleanup_outcome="fail_closed",
                logger=_LOGGER,
            )
            return

        expected = artifact_ready_path(self._layout, repository_id, artifact_id)
        path_kind = classify_ready_artifact_path(
            expected,
            expected=expected,
            artifact_id=artifact_id,
        )
        if path_kind == "absent":
            # Missing ready name without a verified delete in this call never mints a stamp.
            # Quarantine residuals are handled by _recover_delete_quarantines.
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="retained",
                code=decision.reason.value,
                cleanup_outcome="already_absent_unproven",
                logger=_LOGGER,
            )
            return
        if path_kind != "regular_file":
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="path_check",
                result="retained",
                code=path_kind,
                cleanup_outcome="unsafe_path",
                logger=_LOGGER,
            )
            return

        stamped = {"ok": False}
        intent_ids: dict[str, int] = {}

        def _stamp(dev: int, ino: int) -> None:
            self._import_store.mark_artifact_bytes_deleted(
                artifact_id,
                deleted_at=self._deleted_at_stamp(),
                repository_id=repository_id,
                expected_dev=dev,
                expected_ino=ino,
            )
            stamped["ok"] = True

        def _on_intent(dev: int, ino: int) -> None:
            intent_ids["dev"] = dev
            intent_ids["ino"] = ino
            self._import_store.begin_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at=self._deleted_at_stamp(),
            )

        def _on_clear_intent(dev: int, ino: int) -> None:
            self._import_store.clear_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                expected_dev=dev,
                expected_ino=ino,
            )

        outcome = try_unlink_ready_artifact_with_recheck(
            expected,
            recheck=lambda: self._still_eligible(artifact_id),
            layout=self._layout,
            repository_id=repository_id,
            artifact_id=artifact_id,
            on_deleted=_stamp,
            on_intent=_on_intent,
            on_clear_intent=_on_clear_intent,
        )
        if outcome == "deleted" and stamped["ok"]:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="deleted",
                code=decision.reason.value,
                cleanup_outcome="deleted",
                logger=_LOGGER,
            )
            return
        if outcome == "busy":
            cleanup_outcome = "lock_busy"
        elif outcome == "ineligible":
            cleanup_outcome = "eligibility_changed"
        elif outcome == "already_absent":
            cleanup_outcome = "already_absent_unproven"
        elif outcome in {"replaced", "intent_failed"}:
            cleanup_outcome = outcome
        else:
            cleanup_outcome = outcome
        log_event(
            "artifact_cleanup",
            repository_id=repository_id,
            artifact_id=artifact_id,
            stage="delete",
            result="retained",
            cleanup_outcome=cleanup_outcome,
            logger=_LOGGER,
        )

    def _deleted_at_stamp(self) -> str:
        return self._clock().astimezone(UTC).replace(microsecond=0).isoformat()

    def _recover_delete_quarantines(self) -> None:
        artifacts_root = self._layout.artifacts
        if not artifacts_root.is_dir():
            return
        try:
            repo_entries = list(artifacts_root.iterdir())
        except OSError:
            return
        for repo_entry in repo_entries:
            name = repo_entry.name
            if len(name) != 32 or any(ch not in _HEX32 for ch in name):
                continue
            try:
                repository_id = UUID(hex=name)
            except ValueError:
                continue
            ready_dir = repo_entry / "ready"
            if not ready_dir.is_dir():
                continue
            try:
                entries = list(ready_dir.iterdir())
            except OSError:
                continue
            by_artifact: dict[UUID, list[tuple[str, int, str]]] = {}
            for entry in entries:
                parsed = parse_quarantine_name(entry.name)
                kind = "quarantine"
                if parsed is None:
                    parsed = parse_detach_name(entry.name)
                    kind = "detach"
                if parsed is None:
                    continue
                inode, artifact_id = parsed
                by_artifact.setdefault(artifact_id, []).append((entry.name, inode, kind))
            for artifact_id, sidecars in by_artifact.items():
                if self._stopping:
                    return
                try:
                    self._recover_artifact_sidecars(
                        repository_id,
                        artifact_id,
                        sidecars=sidecars,
                    )
                except Exception:
                    _LOGGER.exception(
                        "artifact quarantine recovery failed for artifact %s",
                        artifact_id,
                    )

    def _recover_artifact_sidecars(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        sidecars: list[tuple[str, int, str]],
    ) -> None:
        """Recover all deleting/detach sidecars for one artifact under one intent."""

        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, repository_id)
        except OwnedPathError:
            return
        try:
            try:
                lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
            except (MutationStoreInvariantError, Exception):
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="poison_lifecycle_inventory",
                    logger=_LOGGER,
                )
                return
            if lifecycle is None or lifecycle.repository_id != repository_id:
                for name, _ino, _kind in sidecars:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                return

            intent_dev = lifecycle.bytes_delete_dev
            intent_ino = lifecycle.bytes_delete_ino
            intent_phase = lifecycle.bytes_delete_phase
            intent_present = (
                lifecycle.bytes_delete_intent_at is not None
                and intent_dev is not None
                and intent_ino is not None
                and intent_phase in {"quarantined", "detached"}
            )

            matching: list[tuple[str, int, str, os.stat_result]] = []
            for sidecar_name, expected_ino, kind in sidecars:
                verified = self._verify_sidecar_stat(
                    ready_dir_fd,
                    sidecar_name,
                    expected_ino=expected_ino,
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                )
                if verified is None:
                    continue
                q_stat = verified
                matches_intent = (
                    intent_present
                    and intent_dev is not None
                    and intent_ino is not None
                    and int(intent_dev) == int(q_stat.st_dev)
                    and int(intent_ino) == int(q_stat.st_ino)
                )
                if lifecycle.bytes_deleted_at is not None:
                    if intent_present and not matches_intent:
                        log_event(
                            "artifact_cleanup",
                            repository_id=repository_id,
                            artifact_id=artifact_id,
                            stage="quarantine",
                            result="retained",
                            cleanup_outcome="unknown_path_inventory",
                            logger=_LOGGER,
                        )
                        continue
                    if not self._retention_explains_deleted(
                        lifecycle,
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                    ):
                        log_event(
                            "artifact_cleanup",
                            repository_id=repository_id,
                            artifact_id=artifact_id,
                            stage="quarantine",
                            result="retained",
                            cleanup_outcome="fail_closed",
                            logger=_LOGGER,
                        )
                        continue
                    if self._unlink_sidecar_if_same_inode(
                        ready_dir_fd, sidecar_name, q_stat
                    ):
                        log_event(
                            "artifact_cleanup",
                            repository_id=repository_id,
                            artifact_id=artifact_id,
                            stage="quarantine",
                            result="deleted",
                            cleanup_outcome="quarantine_residual_unlinked",
                            logger=_LOGGER,
                        )
                    continue
                if not matches_intent:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                # Phase/sidecar consistency: detach phase expects detach name.
                if intent_phase == "detached" and kind == "quarantine":
                    pass  # both may exist mid-crash; still intent-matched
                matching.append((sidecar_name, expected_ino, kind, q_stat))

            if lifecycle.bytes_deleted_at is not None or not matching:
                return
            assert intent_dev is not None and intent_ino is not None

            ready_name = artifact_id.hex
            ready_stat: os.stat_result | None
            try:
                ready_stat = os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                ready_stat = None
            except OSError:
                return

            ready_same_inode = ready_stat is not None and (
                ready_stat.st_dev,
                ready_stat.st_ino,
            ) == (int(intent_dev), int(intent_ino))
            ready_absent = ready_stat is None
            ready_is_replacement = ready_stat is not None and not ready_same_inode

            decision = self._import_store.evaluate_artifact_bytes_deletion(
                artifact_id,
                now=self._clock(),
                ttl_seconds=self._settings.artifact_ttl_seconds,
            )

            if ready_is_replacement:
                # Never stamp when ready holds a different inode.
                for sidecar_name, _ino, _kind, q_stat in matching:
                    self._unlink_sidecar_if_same_inode(ready_dir_fd, sidecar_name, q_stat)
                self._clear_intent_best_effort(
                    artifact_id,
                    repository_id,
                    expected_dev=int(intent_dev),
                    expected_ino=int(intent_ino),
                )
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="quarantine_orphaned_dropped",
                    logger=_LOGGER,
                )
                return

            if decision.eligible and ready_absent:
                try:
                    self._import_store.mark_artifact_bytes_deleted(
                        artifact_id,
                        deleted_at=self._deleted_at_stamp(),
                        repository_id=repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                    )
                except Exception:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="stamp_failed",
                        logger=_LOGGER,
                    )
                    return
                for sidecar_name, _ino, _kind, q_stat in matching:
                    self._unlink_sidecar_if_same_inode(ready_dir_fd, sidecar_name, q_stat)
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="deleted",
                    cleanup_outcome="quarantine_completed",
                    logger=_LOGGER,
                )
                return

            if decision.eligible and ready_same_inode:
                # Leave to live helper / next sweep with flock on ready.
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="eligibility_changed",
                    logger=_LOGGER,
                )
                return

            # Ineligible: restore or drop all matching sidecars, then clear intent once.
            if ready_absent:
                restore_name = matching[0][0]
                try:
                    os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    try:
                        os.link(
                            restore_name,
                            ready_name,
                            src_dir_fd=ready_dir_fd,
                            dst_dir_fd=ready_dir_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError:
                        log_event(
                            "artifact_cleanup",
                            repository_id=repository_id,
                            artifact_id=artifact_id,
                            stage="quarantine",
                            result="retained",
                            cleanup_outcome="quarantine_restore_skipped",
                            logger=_LOGGER,
                        )
                        return
                    except OSError:
                        return
                    for sidecar_name, _ino, _kind, q_stat in matching:
                        self._unlink_sidecar_if_same_inode(
                            ready_dir_fd, sidecar_name, q_stat
                        )
                    self._clear_intent_best_effort(
                        artifact_id,
                        repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                    )
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="quarantine_restored",
                        logger=_LOGGER,
                    )
                    return
                except OSError:
                    return
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="quarantine_restore_skipped",
                    logger=_LOGGER,
                )
                return

            # ready_same_inode and ineligible: drop sidecars only.
            for sidecar_name, _ino, _kind, q_stat in matching:
                self._unlink_sidecar_if_same_inode(ready_dir_fd, sidecar_name, q_stat)
            self._clear_intent_best_effort(
                artifact_id,
                repository_id,
                expected_dev=int(intent_dev),
                expected_ino=int(intent_ino),
            )
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="quarantine",
                result="retained",
                cleanup_outcome="quarantine_hardlink_dropped",
                logger=_LOGGER,
            )
        finally:
            os.close(ready_dir_fd)

    def _verify_sidecar_stat(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> os.stat_result | None:
        open_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            open_flags |= nofollow
        q_fd: int | None = None
        try:
            try:
                q_fd = os.open(sidecar_name, open_flags, dir_fd=ready_dir_fd)
            except (FileNotFoundError, OSError):
                return None
            try:
                fcntl.flock(q_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="lock_busy",
                    logger=_LOGGER,
                )
                return None
            try:
                q_stat = os.fstat(q_fd)
            except OSError:
                return None
            if q_stat.st_ino != expected_ino or not stat_module.S_ISREG(q_stat.st_mode):
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="quarantine_inode_mismatch",
                    logger=_LOGGER,
                )
                return None
            return q_stat
        finally:
            if q_fd is not None:
                try:
                    fcntl.flock(q_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(q_fd)

    @staticmethod
    def _unlink_sidecar_if_same_inode(
        ready_dir_fd: int,
        sidecar_name: str,
        expected: os.stat_result,
    ) -> bool:
        try:
            live = os.stat(sidecar_name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if (live.st_dev, live.st_ino) != (expected.st_dev, expected.st_ino):
            return False
        try:
            os.unlink(sidecar_name, dir_fd=ready_dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def _clear_intent_best_effort(
        self,
        artifact_id: UUID,
        repository_id: UUID,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> None:
        try:
            self._import_store.clear_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
            )
        except Exception:
            pass

    def _retention_explains_deleted(
        self,
        lifecycle: ArtifactLifecycleRecord,
        *,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> bool:
        references = self._import_store.list_artifact_references(artifact_id)
        consumed_operation_artifact_id: UUID | None = None
        if lifecycle.consumed_by_operation_id is not None:
            operation = self._import_store.get_operation(
                repository_id,
                lifecycle.consumed_by_operation_id,
            )
            if operation is not None and operation.status == OperationStatus.SUCCEEDED:
                consumed_operation_artifact_id = operation.artifact_id
        return retention_explains_missing_ready_bytes(
            lifecycle=lifecycle,
            repository_id=repository_id,
            references=references,
            ttl_seconds=self._settings.artifact_ttl_seconds,
            now=self._clock(),
            consumed_operation_artifact_id=consumed_operation_artifact_id,
        )

    def _inventory_owned_artifact_tree(self) -> None:
        artifacts_root = self._layout.artifacts
        if not artifacts_root.is_dir():
            return
        try:
            repo_entries = list(artifacts_root.iterdir())
        except OSError:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="artifacts_root_unreadable",
                logger=_LOGGER,
            )
            return
        for repo_entry in repo_entries:
            name = repo_entry.name
            try:
                entry_stat = repo_entry.lstat()
            except OSError:
                log_event(
                    "artifact_cleanup",
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                continue
            if stat_module.S_ISLNK(entry_stat.st_mode) or not stat_module.S_ISDIR(
                entry_stat.st_mode
            ):
                log_event(
                    "artifact_cleanup",
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                continue
            if len(name) != 32 or any(ch not in _HEX32 for ch in name):
                log_event(
                    "artifact_cleanup",
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                continue
            try:
                repository_id = UUID(hex=name)
            except ValueError:
                log_event(
                    "artifact_cleanup",
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                continue
            owned = self._import_store.has_succeeded_create_repository(repository_id)
            if not owned:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
            for sub in ("ready", "staging"):
                self._inventory_directory_entries(
                    repository_id,
                    repo_entry / sub,
                    allow_staging_shape=(sub == "staging"),
                )

        staging_artifacts = self._layout.staging_artifacts
        if staging_artifacts.is_dir():
            self._inventory_directory_entries(
                None,
                staging_artifacts,
                allow_staging_shape=True,
            )

    def _inventory_directory_entries(
        self,
        repository_id: UUID | None,
        directory: Path,
        *,
        allow_staging_shape: bool,
    ) -> None:
        if not directory.is_dir():
            return
        try:
            entries = list(directory.iterdir())
        except OSError:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="path_check",
                result="retained",
                cleanup_outcome="ready_dir_unreadable",
                logger=_LOGGER,
            )
            return
        for entry in entries:
            name = entry.name
            if name.startswith(".deleting-") or name.startswith(".detach-"):
                # Quarantine/detach sidecars are recovered separately; diagnose
                # malformed names that fail to parse.
                parsed = (
                    parse_quarantine_name(name)
                    if name.startswith(".deleting-")
                    else parse_detach_name(name)
                )
                if parsed is None:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                continue
            if _is_exact_ready_name(name):
                try:
                    artifact_id = UUID(hex=name)
                except ValueError:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                try:
                    lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
                except MutationStoreInvariantError:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="poison_lifecycle_inventory",
                        logger=_LOGGER,
                    )
                    continue
                except Exception:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                if lifecycle is None or (
                    repository_id is not None and lifecycle.repository_id != repository_id
                ):
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                continue
            if allow_staging_shape and _is_staging_shape(name):
                left, _right = name.split(".", 1)
                try:
                    artifact_id = UUID(hex=left)
                except ValueError:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                try:
                    lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
                except MutationStoreInvariantError:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="poison_lifecycle_inventory",
                        logger=_LOGGER,
                    )
                    continue
                except Exception:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                if lifecycle is None or (
                    repository_id is not None and lifecycle.repository_id != repository_id
                ):
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                continue
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )

    def _still_eligible(self, artifact_id: UUID) -> bool:
        lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
        references = self._import_store.list_artifact_references(artifact_id)
        decision = decide_artifact_bytes_deletion(
            lifecycle=lifecycle,
            references=references,
            now=self._clock(),
            ttl_seconds=self._settings.artifact_ttl_seconds,
        )
        return decision.eligible


def _is_exact_ready_name(name: str) -> bool:
    return len(name) == 32 and all(ch in _HEX32 for ch in name)


def _is_staging_shape(name: str) -> bool:
    # Upload staging: <artifact_hex>.<12-hex-nonce>
    if "." not in name:
        return False
    left, right = name.split(".", 1)
    return _is_exact_ready_name(left) and len(right) == 12 and all(ch in _HEX32 for ch in right)


def classify_ready_artifact_path(
    path: Path,
    *,
    expected: Path,
    artifact_id: UUID | None = None,
) -> str:
    """Classify a candidate ready path without logging the raw path."""

    if path != expected:
        return "unexpected_path"
    if artifact_id is not None and path.name != artifact_id.hex:
        return "malformed_name"
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "stat_failed"
    try:
        if stat_module.S_ISLNK(path_stat.st_mode):
            return "symlink"
        if not stat_module.S_ISREG(path_stat.st_mode):
            return "not_regular_file"
    except (AttributeError, TypeError):
        return "stat_failed"
    name = path.name
    if len(name) != 32 or any(ch not in "0123456789abcdef" for ch in name):
        return "malformed_name"
    return "regular_file"
