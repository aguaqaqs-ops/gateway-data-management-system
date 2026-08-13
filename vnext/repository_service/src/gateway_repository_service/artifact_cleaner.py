"""Runtime-owned artifact retention cleaner."""

from __future__ import annotations

import fcntl
import logging
import os
import stat as stat_module
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service import artifact_cleanup
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
    retention_explains_missing_ready_bytes,
)
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    ArtifactResidualRecord,
    MutationStore,
    MutationStoreInvariantError,
)
from gateway_repository_service.publication import renameat2_noreplace
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import (
    OwnedPathError,
    STAGE_VICTIM,
    StageDirStatus,
    destroy_owned_bytes_and_reclaim_names,
    link_from_fd,
    lock_unlink_stage_dir,
    lookup_unlink_stage_dir,
    NormalizeVictimStatus,
    normalize_unlink_stage_victim_via_fd,
    open_owned_ready_dir,
    open_owned_unlink_stage_dir,
    parse_any_recoverable_sidecar,
    parse_quarantine_name,
    parse_unlink_stage_dir_name,
    parse_unlink_verify_name,
    prove_size0_owned_name_terminal,
    reclaim_size0_owned_name,
    reclaim_stage_dir,
    rmdir_if_empty,
    scandir_dir_fd_names,
    unlink_if_match,
    unlock_unlink_stage_dir,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)

_HEX32 = frozenset("0123456789abcdef")
_CLEANUP_CANDIDATE_PAGE_SIZE = 64
_HOUSEKEEPING_ENTRY_BUDGET = 64


class _HousekeepingBudget:
    """Shared per-sweep cap for inventory, leftover recovery, and receipt/residual GC."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def consume(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def _scandir_names(dir_fd: int) -> Iterator[str]:
    """Stream directory names from an owned fd without a full listdir."""

    yield from scandir_dir_fd_names(dir_fd)


SidecarOutcome = Literal["absent", "success", "retain", "paused"]


class SidecarLockResult(Enum):
    LOCKED = "locked"
    ABSENT = "absent"
    BUSY = "busy"
    MISMATCH = "mismatch"
    IO_ERROR = "io_error"


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
        self._cleanup_cursor: int | None = None
        self._restart_cursor = False
        self._inventory_after_repo: str | None = None
        self._inventory_after_sub: str | None = None
        self._inventory_after_name: str | None = None
        self._recover_after_repo: str | None = None
        self._recover_after_name: str | None = None
        self._recover_after_stage_child: str | None = None
        self._normalize_match_count = 0
        self._normalize_match_name: str | None = None
        self._paused_stage_child: str | None = None
        self._defer_recover_once = False
        self._receipt_after_artifact_id: str | None = None
        self._residual_after_id: int | None = None

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
            self._restart_cursor = True
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

    def reclaim_until_disk_admission(self, *, admitted: Callable[[], bool]) -> None:
        """Page eligible cleanup until disk admission passes or a cycle deletes nothing."""

        with self._condition:
            self._cleanup_cursor = None
            self._restart_cursor = False
        cycle_deleted = 0
        first = True
        while not admitted():
            deleted = self._sweep(housekeeping=first)
            first = False
            cycle_deleted += deleted
            if self._cleanup_cursor is None:
                if cycle_deleted == 0:
                    return
                cycle_deleted = 0

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

    def _sweep(self, *, housekeeping: bool = True) -> int:
        with self._condition:
            restart = self._restart_cursor
            self._restart_cursor = False
        if restart:
            self._cleanup_cursor = None
        started = time.monotonic()
        if housekeeping:
            budget = _HousekeepingBudget(_HOUSEKEEPING_ENTRY_BUDGET)
            self._inventory_owned_artifact_tree(budget)
            if self._defer_recover_once:
                self._defer_recover_once = False
                self._gc_bytes_deleted_receipts(budget)
                self._reclaim_durable_residuals(budget)
                self._recover_delete_quarantines(budget)
            else:
                self._recover_delete_quarantines(budget)
                if budget.remaining() <= 0:
                    self._defer_recover_once = True
                self._gc_bytes_deleted_receipts(budget)
                self._reclaim_durable_residuals(budget)
            log_event(
                "artifact_cleanup",
                stage="housekeeping",
                result="completed",
                cleanup_outcome="housekeeping_bounded",
                capacity=_HOUSEKEEPING_ENTRY_BUDGET,
                in_use=budget.used,
                logger=_LOGGER,
            )
        try:
            after_seq: int | None = None
            if self._cleanup_cursor is not None:
                after_seq = self._cleanup_cursor
            page = self._mutation_store.list_artifacts_pending_byte_cleanup(
                limit=_CLEANUP_CANDIDATE_PAGE_SIZE,
                after_cleanup_seq=after_seq,
            )
            if page.scanned == 0 and self._cleanup_cursor is not None:
                self._cleanup_cursor = None
                page = self._mutation_store.list_artifacts_pending_byte_cleanup(
                    limit=_CLEANUP_CANDIDATE_PAGE_SIZE,
                )
        except Exception:
            _LOGGER.exception("artifact cleaner failed to list candidates")
            log_event(
                "artifact_cleanup",
                stage="list_candidates",
                result="error",
                cleanup_outcome="list_failed",
                logger=_LOGGER,
            )
            return 0

        # Bounded keyset pagination: advance by the last raw SQL row, including poison.
        deleted = 0
        candidates = page.records
        for lifecycle in candidates:
            if self._stopping:
                return deleted
            try:
                if self._process_candidate(lifecycle.artifact_id, lifecycle.repository_id):
                    deleted += 1
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
        sql_rows = page.scanned
        if sql_rows < _CLEANUP_CANDIDATE_PAGE_SIZE:
            self._cleanup_cursor = None
        elif page.cursor_cleanup_seq is not None:
            next_seq = int(page.cursor_cleanup_seq)
            if after_seq is not None and next_seq <= after_seq:
                log_event(
                    "artifact_cleanup",
                    stage="list_candidates",
                    result="skipped",
                    cleanup_outcome="repeated_cleanup_cursor",
                    logger=_LOGGER,
                )
                next_seq = after_seq + 1
            self._cleanup_cursor = next_seq
        elif after_seq is not None:
            self._cleanup_cursor = after_seq + 1
        else:
            self._cleanup_cursor = 1

        duration_ms = int((time.monotonic() - started) * 1000)
        log_event(
            "artifact_cleanup",
            stage="sweep",
            duration_ms=duration_ms,
            result="completed",
            cleanup_outcome="sweep_completed",
            capacity=_CLEANUP_CANDIDATE_PAGE_SIZE,
            in_use=sql_rows,
            logger=_LOGGER,
        )
        return deleted

    def _process_candidate(self, artifact_id: UUID, repository_id: UUID) -> bool:
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
                return False
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
            return False

        expected = artifact_ready_path(self._layout, repository_id, artifact_id)
        path_kind = classify_ready_artifact_path(
            expected,
            expected=expected,
            artifact_id=artifact_id,
        )
        if path_kind not in {"regular_file", "absent"}:
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
            return False

        if self._artifact_has_parseable_leftovers(repository_id, artifact_id):
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="retained",
                cleanup_outcome="leftover_pending",
                logger=_LOGGER,
            )
            return False

        outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
            self._import_store,
            self._layout,
            repository_id=repository_id,
            artifact_id=artifact_id,
            ttl_seconds=self._settings.artifact_ttl_seconds,
            deleted_at=self._deleted_at_stamp(),
            recheck=lambda: self._still_eligible(artifact_id, repository_id),
        )
        if outcome == "deleted":
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
            return True
        if outcome == "busy":
            cleanup_outcome = "lock_busy"
        elif outcome == "ineligible":
            cleanup_outcome = "eligibility_changed"
        elif outcome == "already_absent":
            cleanup_outcome = "already_absent"
        elif outcome in {"replaced", "intent_failed", "unsafe_path"}:
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
        return False

    def _deleted_at_stamp(self) -> str:
        return self._clock().astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _leftover_file_flags() -> int:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            flags |= nofollow
        return flags

    def _should_converge_eligible_leftover(self, artifact_id: UUID) -> bool:
        try:
            lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
        except (MutationStoreInvariantError, Exception):
            return False
        if lifecycle is None:
            return False
        if lifecycle.bytes_deleted_at is not None:
            return self._retention_explains_deleted(
                lifecycle,
                repository_id=lifecycle.repository_id,
                artifact_id=artifact_id,
            )
        decision = self._import_store.evaluate_artifact_bytes_deletion(
            artifact_id,
            now=self._clock(),
            ttl_seconds=self._settings.artifact_ttl_seconds,
        )
        return decision.eligible

    def _artifact_has_parseable_leftovers(
        self,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> bool:
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, repository_id)
        except OwnedPathError:
            return False
        except OSError:
            return True
        try:
            try:
                for name in scandir_dir_fd_names(ready_dir_fd):
                    parsed = parse_any_recoverable_sidecar(name)
                    if parsed is not None and parsed[1] == artifact_id:
                        return True
                    stage = parse_unlink_stage_dir_name(name)
                    if stage is not None and stage[0] == artifact_id:
                        return True
            except OSError:
                return True
        finally:
            os.close(ready_dir_fd)
        return False

    def _dirfd_unlink_regular_leftover(
        self,
        ready_dir_fd: int,
        name: str,
        *,
        expected_ino: int | None = None,
    ) -> bool:
        """Unlink a parseable leftover regular file. True means gone or absent."""

        try:
            fd = os.open(name, self._leftover_file_flags(), dir_fd=ready_dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        try:
            try:
                st = os.fstat(fd)
            except OSError:
                return False
            if not stat_module.S_ISREG(st.st_mode):
                return False
            if expected_ino is not None and int(st.st_ino) != int(expected_ino):
                return False
        finally:
            os.close(fd)
        try:
            os.unlink(name, dir_fd=ready_dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _is_known_unlink_stage_child(name: str) -> bool:
        return name == STAGE_VICTIM or name.startswith("final-") or name.startswith("doom-")

    def _dirfd_remove_unlink_stage(
        self,
        ready_dir_fd: int,
        stage_name: str,
        budget: _HousekeepingBudget,
    ) -> tuple[bool, str | None]:
        """Unlink known leftover stage children immediately, then rmdir.

        Returns ``(removed, last_child)``. ``last_child`` is set when the shared
        budget pauses mid-stage so the next sweep can re-enter the same stage.
        Unknown / non-regular children stop the walk without rmdir or stamp.
        """

        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            try:
                os.stat(stage_name, dir_fd=ready_dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                return True, None
            except OSError:
                return False, None
            return False, None
        if not lock_unlink_stage_dir(stage_dir_fd):
            os.close(stage_dir_fd)
            return False, None
        last_child: str | None = None
        paused = False
        try:
            try:
                for child in _scandir_names(stage_dir_fd):
                    if not budget.consume():
                        paused = True
                        break
                    last_child = child
                    if not self._is_known_unlink_stage_child(child):
                        return False, None
                    try:
                        child_fd = os.open(
                            child, self._leftover_file_flags(), dir_fd=stage_dir_fd
                        )
                    except FileNotFoundError:
                        continue
                    except OSError:
                        return False, None
                    try:
                        st = os.fstat(child_fd)
                    except OSError:
                        return False, None
                    finally:
                        os.close(child_fd)
                    if not stat_module.S_ISREG(st.st_mode):
                        return False, None
                    if not self._dirfd_unlink_regular_leftover(stage_dir_fd, child):
                        return False, None
            except OSError:
                return False, None
        finally:
            unlock_unlink_stage_dir(stage_dir_fd)
            os.close(stage_dir_fd)
        if paused:
            return False, last_child if last_child is not None else ""
        if rmdir_if_empty(ready_dir_fd, stage_name):
            return True, None
        return False, None

    def _clear_leftover_residuals(self, artifact_id: UUID, names: set[str]) -> None:
        if not names:
            return
        try:
            page = self._import_store.list_artifact_residuals(artifact_id=artifact_id)
        except Exception:
            return
        for row in page.records:
            if row.name not in names and row.parent_name not in names:
                continue
            try:
                self._import_store.clear_artifact_residual(
                    residual_id=row.residual_id,
                    expected_dev=row.dev,
                    expected_ino=row.ino,
                )
            except Exception:
                continue

    def _collect_parseable_leftover_ids(
        self,
        ready_dir_fd: int,
        budget: _HousekeepingBudget,
    ) -> set[UUID] | None:
        found: set[UUID] = set()
        try:
            for name in _scandir_names(ready_dir_fd):
                if not budget.consume():
                    return None
                parsed = parse_any_recoverable_sidecar(name)
                if parsed is not None:
                    found.add(parsed[1])
                    continue
                stage = parse_unlink_stage_dir_name(name)
                if stage is not None:
                    found.add(stage[0])
        except OSError:
            return None
        return found

    def _stamp_eligible_leftover_if_needed(
        self,
        ready_dir_fd: int,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        leftovers_present: bool | None = None,
    ) -> bool:
        lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
        if lifecycle is None or lifecycle.bytes_deleted_at is not None:
            return True
        try:
            os.stat(artifact_id.hex, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        else:
            # Exact UUID still present; candidate/facade unlinks and stamps.
            return True
        if leftovers_present is None:
            leftovers_present = self._artifact_has_parseable_leftovers(
                repository_id, artifact_id
            )
        if leftovers_present:
            return False
        try:
            self._import_store.mark_artifact_bytes_deleted(
                artifact_id,
                deleted_at=self._deleted_at_stamp(),
                repository_id=repository_id,
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
            return False
        log_event(
            "artifact_cleanup",
            repository_id=repository_id,
            artifact_id=artifact_id,
            stage="quarantine",
            result="deleted",
            cleanup_outcome="leftover_unlinked",
            logger=_LOGGER,
        )
        return True

    def _converge_eligible_leftover_sidecars(
        self,
        ready_dir_fd: int,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        sidecars: list[tuple[str, int, str]],
    ) -> None:
        cleared: set[str] = set()
        for name, ino, _kind in sidecars:
            if self._dirfd_unlink_regular_leftover(
                ready_dir_fd, name, expected_ino=ino
            ):
                cleared.add(name)
            else:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unlink_failed",
                    logger=_LOGGER,
                )
        self._clear_leftover_residuals(artifact_id, cleared)

    def _converge_eligible_leftover_stages(
        self,
        ready_dir_fd: int,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        stage_names: list[str],
        budget: _HousekeepingBudget,
    ) -> tuple[bool, str | None]:
        cleared: set[str] = set()
        paused_child: str | None = None
        for stage_name in stage_names:
            removed, last_child = self._dirfd_remove_unlink_stage(
                ready_dir_fd, stage_name, budget
            )
            if removed:
                cleared.add(stage_name)
                continue
            if last_child is not None:
                paused_child = last_child
                break
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="quarantine",
                result="retained",
                cleanup_outcome="unlink_failed",
                logger=_LOGGER,
            )
        self._clear_leftover_residuals(artifact_id, cleared)
        if paused_child is not None:
            return True, paused_child
        return False, None

    def _recover_delete_quarantines(self, budget: _HousekeepingBudget) -> None:
        artifacts_root = self._layout.artifacts
        if not artifacts_root.is_dir():
            return
        after_repo = self._recover_after_repo
        after_name = self._recover_after_name
        after_child = self._recover_after_stage_child
        skipping_repo = after_repo is not None
        last_repo: str | None = None
        last_name: str | None = None
        last_child: str | None = None
        exhausted = False
        try:
            with os.scandir(artifacts_root) as entries:
                for entry in entries:
                    name = entry.name
                    resume = False
                    if skipping_repo:
                        if name != after_repo:
                            continue
                        skipping_repo = False
                        resume = True
                    if len(name) != 32 or any(ch not in _HEX32 for ch in name):
                        continue
                    try:
                        repository_id = UUID(hex=name)
                    except ValueError:
                        continue
                    try:
                        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    page_exhausted, page_last, page_child = self._recover_one_ready_dir(
                        repository_id,
                        budget,
                        after_name=after_name if resume else None,
                        after_stage_child=after_child if resume else None,
                    )
                    last_repo = name
                    if page_exhausted:
                        last_name = page_last
                        last_child = page_child
                        exhausted = True
                        break
                    after_name = None
                    after_child = None
                    if self._stopping:
                        exhausted = True
                        last_name = page_last
                        last_child = page_child
                        break
        except OSError:
            return
        if exhausted:
            self._recover_after_repo = last_repo
            self._recover_after_name = last_name
            self._recover_after_stage_child = last_child
        else:
            self._recover_after_repo = None
            self._recover_after_name = None
            self._recover_after_stage_child = None
            self._normalize_match_count = 0
            self._normalize_match_name = None

    def _recover_one_ready_dir(
        self,
        repository_id: UUID,
        budget: _HousekeepingBudget,
        *,
        after_name: str | None,
        after_stage_child: str | None,
    ) -> tuple[bool, str | None, str | None]:
        if budget.remaining() <= 0:
            return True, after_name, after_stage_child
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, repository_id)
        except OwnedPathError:
            return False, None, None
        processed_ids: set[UUID] = set()
        try:
            skipping = after_name is not None
            resume_stage = after_stage_child is not None
            last: str | None = None
            try:
                for ready_name in _scandir_names(ready_dir_fd):
                    if skipping:
                        if not budget.consume():
                            return True, None, None
                        if ready_name != after_name:
                            continue
                        skipping = False
                        if not resume_stage:
                            continue
                    elif not budget.consume():
                        return True, None, None
                    last = ready_name
                    parsed = parse_any_recoverable_sidecar(ready_name)
                    if parsed is not None:
                        processed_ids.add(parsed[1])
                    stage = parse_unlink_stage_dir_name(ready_name)
                    if stage is not None:
                        processed_ids.add(stage[0])
                    try:
                        paused, paused_child = self._recover_one_ready_entry(
                            repository_id,
                            ready_name,
                            budget,
                            after_stage_child=(
                                after_stage_child if resume_stage else None
                            ),
                        )
                    except Exception:
                        _LOGGER.exception(
                            "artifact leftover recovery failed for repository %s",
                            repository_id,
                        )
                        paused = False
                        paused_child = None
                    resume_stage = False
                    after_stage_child = None
                    if paused:
                        return True, last, paused_child
                    self._normalize_match_count = 0
                    self._normalize_match_name = None
                    if self._stopping:
                        return True, last, None
            except OSError:
                return False, None, None
            if skipping:
                return False, None, None
            if processed_ids:
                leftover_ids = self._collect_parseable_leftover_ids(ready_dir_fd, budget)
                if leftover_ids is not None:
                    for artifact_id in processed_ids:
                        self._stamp_eligible_leftover_if_needed(
                            ready_dir_fd,
                            repository_id,
                            artifact_id,
                            leftovers_present=artifact_id in leftover_ids,
                        )
            return False, None, None
        finally:
            os.close(ready_dir_fd)

    def _recover_one_ready_entry(
        self,
        repository_id: UUID,
        ready_name: str,
        budget: _HousekeepingBudget,
        *,
        after_stage_child: str | None = None,
    ) -> tuple[bool, str | None]:
        parsed = parse_any_recoverable_sidecar(ready_name)
        if parsed is not None:
            inode, artifact_id, _generation, kind = parsed
            self._recover_artifact_sidecars(
                repository_id,
                artifact_id,
                sidecars=[(ready_name, inode, kind)],
            )
            return False, None
        stage = parse_unlink_stage_dir_name(ready_name)
        if stage is None:
            return False, None
        artifact_id, _token = stage
        return self._recover_artifact_unlink_stages(
            repository_id,
            artifact_id,
            stage_names=[ready_name],
            budget=budget,
            after_stage_child=after_stage_child,
        )

    def _recover_artifact_unlink_stages(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        stage_names: list[str],
        budget: _HousekeepingBudget,
        after_stage_child: str | None = None,
    ) -> tuple[bool, str | None]:
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, repository_id)
        except OwnedPathError:
            return False, None
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
                return False, None
            if lifecycle is None or lifecycle.repository_id != repository_id:
                for _stage_name in stage_names:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                return False, None

            if self._should_converge_eligible_leftover(artifact_id):
                return self._converge_eligible_leftover_stages(
                    ready_dir_fd,
                    repository_id,
                    artifact_id,
                    stage_names=stage_names,
                    budget=budget,
                )

            if lifecycle.bytes_deleted_at is not None:
                return self._recover_stamped_unlink_stages(
                    ready_dir_fd,
                    repository_id,
                    artifact_id,
                    lifecycle=lifecycle,
                    stage_names=stage_names,
                    budget=budget,
                    after_stage_child=after_stage_child,
                )

            intent_dev = lifecycle.bytes_delete_dev
            intent_ino = lifecycle.bytes_delete_ino
            intent_generation = lifecycle.bytes_delete_generation
            intent_present = (
                lifecycle.bytes_delete_intent_at is not None
                and intent_dev is not None
                and intent_ino is not None
                and intent_generation is not None
                and lifecycle.bytes_delete_phase in {"quarantined", "detached"}
            )
            if not intent_present:
                for _stage_name in stage_names:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                return False, None
            assert intent_dev is not None and intent_ino is not None and intent_generation is not None

            outcomes: list[SidecarOutcome] = []
            resume_child = after_stage_child
            for stage_name in stage_names:
                outcome = self._unlink_intent_unlink_stage_with_recheck(
                    ready_dir_fd,
                    stage_name,
                    expected_dev=int(intent_dev),
                    expected_ino=int(intent_ino),
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    generation=str(intent_generation),
                    budget=budget,
                    after_stage_child=resume_child,
                )
                resume_child = None
                if outcome == "paused":
                    return True, self._paused_stage_child
                outcomes.append(outcome)
            # Stamp-first clears intent; clear receipt only when public names absent.
            if self._all_sidecars_cleared(outcomes) and not self._has_matching_sidecar_residual(
                ready_dir_fd,
                artifact_id=artifact_id,
                expected_ino=int(intent_ino),
                generation=str(intent_generation),
            ):
                self._clear_receipt_best_effort(
                    artifact_id,
                    repository_id,
                    expected_dev=int(intent_dev),
                    expected_ino=int(intent_ino),
                    expected_generation=str(intent_generation),
                )
            return False, None
        finally:
            os.close(ready_dir_fd)

    def _recover_stamped_unlink_stages(
        self,
        ready_dir_fd: int,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        lifecycle: ArtifactLifecycleRecord,
        stage_names: list[str],
        budget: _HousekeepingBudget,
        after_stage_child: str | None = None,
    ) -> tuple[bool, str | None]:
        receipt_dev = lifecycle.bytes_deleted_receipt_dev
        receipt_ino = lifecycle.bytes_deleted_receipt_ino
        receipt_generation = lifecycle.bytes_deleted_receipt_generation
        receipt_present = (
            receipt_dev is not None
            and receipt_ino is not None
            and receipt_generation is not None
        )
        if not receipt_present:
            self._reclaim_receipt_null_size0_stages(
                ready_dir_fd,
                repository_id=repository_id,
                artifact_id=artifact_id,
                lifecycle=lifecycle,
                stage_names=stage_names,
            )
            return False, None
        assert receipt_dev is not None and receipt_ino is not None and receipt_generation is not None
        retention_ok = self._retention_explains_deleted(
            lifecycle,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        outcomes: list[SidecarOutcome] = []
        resume_child = after_stage_child
        for stage_name in stage_names:
            outcome = self._unlink_stamped_unlink_stage_with_recheck(
                ready_dir_fd,
                stage_name,
                expected_dev=int(receipt_dev),
                expected_ino=int(receipt_ino),
                repository_id=repository_id,
                artifact_id=artifact_id,
                retention_ok=retention_ok,
                generation=str(receipt_generation),
                budget=budget,
                after_stage_child=resume_child,
            )
            resume_child = None
            if outcome == "paused":
                return True, self._paused_stage_child
            outcomes.append(outcome)
        if self._all_sidecars_cleared(outcomes) and not self._has_matching_sidecar_residual(
            ready_dir_fd,
            artifact_id=artifact_id,
            expected_ino=int(receipt_ino),
            generation=str(receipt_generation),
        ):
            self._clear_receipt_best_effort(
                artifact_id,
                repository_id,
                expected_dev=int(receipt_dev),
                expected_ino=int(receipt_ino),
                expected_generation=str(receipt_generation),
            )
        return False, None

    def _has_matching_sidecar_residual(
        self,
        ready_dir_fd: int,
        *,
        artifact_id: UUID,
        expected_ino: int,
        generation: str,
    ) -> bool:
        try:
            for entry_name in _scandir_names(ready_dir_fd):
                parsed_stage = parse_unlink_stage_dir_name(entry_name)
                if parsed_stage is not None and parsed_stage[0] == artifact_id:
                    # Empty stages or owned size-0 victims do not block clear.
                    # Non-empty owned content still blocks.
                    if self._stage_dir_is_terminal_or_empty(
                        ready_dir_fd,
                        entry_name,
                        expected_ino=expected_ino,
                    ):
                        continue
                    return True
                parsed = parse_any_recoverable_sidecar(entry_name)
                if parsed is None:
                    continue
                inode, parsed_artifact_id, parsed_generation, _kind = parsed
                if parsed_artifact_id != artifact_id:
                    continue
                if parsed_generation == generation and inode == expected_ino:
                    # Round16: owned size-0 tombstones are terminal; do not block.
                    if self._ready_entry_is_size0_owned_tombstone(
                        ready_dir_fd,
                        entry_name,
                        expected_ino=expected_ino,
                    ):
                        continue
                    return True
        except OSError:
            return True
        return False

    def _stage_dir_is_terminal_or_empty(
        self,
        ready_dir_fd: int,
        stage_name: str,
        *,
        expected_ino: int,
    ) -> bool:
        """True when stage is empty or every child is owned size-0 of expected_ino."""

        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            return False
        try:
            if not lock_unlink_stage_dir(stage_dir_fd):
                return False
            try:
                try:
                    for name in _scandir_names(stage_dir_fd):
                        try:
                            fd = os.open(
                                name,
                                os.O_RDONLY
                                | getattr(os, "O_NOFOLLOW", 0)
                                | getattr(os, "O_NONBLOCK", 0),
                                dir_fd=stage_dir_fd,
                            )
                        except OSError:
                            return False
                        try:
                            st = os.fstat(fd)
                        except OSError:
                            return False
                        finally:
                            os.close(fd)
                        if not stat_module.S_ISREG(st.st_mode):
                            return False
                        if int(st.st_ino) != int(expected_ino) or int(st.st_size) != 0:
                            return False
                    return True
                except OSError:
                    return False
            finally:
                unlock_unlink_stage_dir(stage_dir_fd)
        finally:
            os.close(stage_dir_fd)

    def _ready_entry_is_size0_owned_tombstone(
        self,
        ready_dir_fd: int,
        entry_name: str,
        *,
        expected_ino: int,
    ) -> bool:
        try:
            fd = os.open(
                entry_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                dir_fd=ready_dir_fd,
            )
        except OSError:
            return False
        try:
            st = os.fstat(fd)
        except OSError:
            return False
        finally:
            os.close(fd)
        return (
            stat_module.S_ISREG(st.st_mode)
            and int(st.st_ino) == int(expected_ino)
            and int(st.st_size) == 0
        )

    def _staged_victim_path(self, stage_name: str) -> str:
        return f"{stage_name}/{STAGE_VICTIM}"

    def _normalize_unlink_stage_victim(
        self,
        stage_dir_fd: int,
        *,
        expected_dev: int,
        expected_ino: int,
        budget: _HousekeepingBudget,
        after_stage_child: str | None,
    ) -> SidecarOutcome:
        result = normalize_unlink_stage_victim_via_fd(
            stage_dir_fd,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            consume=budget.consume,
            after_child=after_stage_child,
            match_count=(
                self._normalize_match_count if after_stage_child is not None else 0
            ),
            match_name=(
                self._normalize_match_name if after_stage_child is not None else None
            ),
        )
        if result.status is NormalizeVictimStatus.PAUSED:
            self._normalize_match_count = result.match_count
            self._normalize_match_name = result.match_name
            self._paused_stage_child = result.last_child
            return "paused"
        self._normalize_match_count = 0
        self._normalize_match_name = None
        self._paused_stage_child = None
        if result.status is NormalizeVictimStatus.SUCCESS:
            return "success"
        return "retain"

    def _unlink_intent_unlink_stage_with_recheck(
        self,
        ready_dir_fd: int,
        stage_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
        generation: str,
        budget: _HousekeepingBudget,
        after_stage_child: str | None = None,
    ) -> SidecarOutcome:
        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            return "retain"
        if not lock_unlink_stage_dir(stage_dir_fd):
            os.close(stage_dir_fd)
            return "retain"
        try:
            normalized = self._normalize_unlink_stage_victim(
                stage_dir_fd,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
                budget=budget,
                after_stage_child=after_stage_child,
            )
            if normalized == "paused":
                return "paused"
            if normalized != "success":
                return "retain"
            victim_path = self._staged_victim_path(stage_name)
            lock_result, q_fd, q_stat = self._lock_sidecar(
                ready_dir_fd,
                victim_path,
                expected_ino=expected_ino,
                repository_id=repository_id,
                artifact_id=artifact_id,
            )
            if lock_result == SidecarLockResult.ABSENT:
                return "absent"
            if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
                return "retain"
            try:
                try:
                    lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
                except (MutationStoreInvariantError, Exception):
                    return "retain"
                if lifecycle is None or lifecycle.repository_id != repository_id:
                    return "retain"
                intent_dev = lifecycle.bytes_delete_dev
                intent_ino = lifecycle.bytes_delete_ino
                intent_generation = lifecycle.bytes_delete_generation
                matches_intent = (
                    lifecycle.bytes_delete_intent_at is not None
                    and intent_dev is not None
                    and intent_ino is not None
                    and intent_generation is not None
                    and lifecycle.bytes_delete_phase in {"quarantined", "detached"}
                    and int(intent_dev) == int(q_stat.st_dev)
                    and int(intent_ino) == int(q_stat.st_ino)
                    and generation == intent_generation
                )
                if not matches_intent:
                    return "retain"
                assert intent_dev is not None and intent_ino is not None and intent_generation is not None

                # Stamp-first: eligibility + CAS stamp before any truncate.
                decision = self._import_store.evaluate_artifact_bytes_deletion(
                    artifact_id,
                    now=self._clock(),
                    ttl_seconds=self._settings.artifact_ttl_seconds,
                )
                if not decision.eligible:
                    restored = self._restore_staged_victim_to_ready(
                        ready_dir_fd,
                        victim_fd=q_fd,
                        expected=q_stat,
                        artifact_id=artifact_id,
                    )
                    if restored:
                        self._clear_intent_best_effort(
                            artifact_id,
                            repository_id,
                            expected_dev=int(intent_dev),
                            expected_ino=int(intent_ino),
                            expected_generation=str(intent_generation),
                        )
                        log_event(
                            "artifact_cleanup",
                            repository_id=repository_id,
                            artifact_id=artifact_id,
                            stage="quarantine",
                            result="retained",
                            cleanup_outcome="unlink_stage_restored_ineligible",
                            logger=_LOGGER,
                        )
                        return "success"
                    return "retain"
                try:
                    self._import_store.mark_artifact_bytes_deleted(
                        artifact_id,
                        deleted_at=self._deleted_at_stamp(),
                        repository_id=repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                        expected_generation=str(intent_generation),
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
                    return "retain"

                unlinked = destroy_owned_bytes_and_reclaim_names(
                    ready_dir_fd,
                    q_fd,
                    q_stat,
                    [],
                    artifact_id=artifact_id,
                    generation=generation,
                    held_stage_dir_fd=stage_dir_fd,
                    held_stage_name=stage_name,
                )
                if unlinked:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="deleted",
                        cleanup_outcome="unlink_stage_residual_unlinked",
                        logger=_LOGGER,
                    )
                    return "success"
                return "retain"
            finally:
                self._unlock_sidecar(q_fd)
        finally:
            unlock_unlink_stage_dir(stage_dir_fd)
            os.close(stage_dir_fd)

    def _unlink_stamped_unlink_stage_with_recheck(
        self,
        ready_dir_fd: int,
        stage_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
        retention_ok: bool,
        generation: str | None,
        budget: _HousekeepingBudget,
        after_stage_child: str | None = None,
    ) -> SidecarOutcome:
        if generation is None:
            return "retain"
        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            return "retain"
        if not lock_unlink_stage_dir(stage_dir_fd):
            os.close(stage_dir_fd)
            return "retain"
        try:
            normalized = self._normalize_unlink_stage_victim(
                stage_dir_fd,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
                budget=budget,
                after_stage_child=after_stage_child,
            )
            if normalized == "paused":
                return "paused"
            if normalized != "success":
                return "retain"
            victim_path = self._staged_victim_path(stage_name)
            lock_result, q_fd, q_stat = self._lock_sidecar(
                ready_dir_fd,
                victim_path,
                expected_ino=expected_ino,
                repository_id=repository_id,
                artifact_id=artifact_id,
            )
            if lock_result == SidecarLockResult.ABSENT:
                return "absent"
            if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
                return "retain"
            try:
                try:
                    lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
                except (MutationStoreInvariantError, Exception):
                    return "retain"
                if lifecycle is None or lifecycle.repository_id != repository_id:
                    return "retain"
                receipt_dev = lifecycle.bytes_deleted_receipt_dev
                receipt_ino = lifecycle.bytes_deleted_receipt_ino
                receipt_generation = lifecycle.bytes_deleted_receipt_generation
                matches_receipt = (
                    lifecycle.bytes_deleted_at is not None
                    and receipt_dev is not None
                    and receipt_ino is not None
                    and receipt_generation is not None
                    and int(receipt_dev) == int(q_stat.st_dev)
                    and int(receipt_ino) == int(q_stat.st_ino)
                    and generation == receipt_generation
                )
                if not matches_receipt or not retention_ok:
                    return "retain"
                unlinked = destroy_owned_bytes_and_reclaim_names(
                    ready_dir_fd,
                    q_fd,
                    q_stat,
                    [],
                    artifact_id=artifact_id,
                    generation=generation,
                    held_stage_dir_fd=stage_dir_fd,
                    held_stage_name=stage_name,
                )
                if unlinked:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        stage="quarantine",
                        result="deleted",
                        cleanup_outcome="unlink_stage_residual_unlinked",
                        logger=_LOGGER,
                    )
                    return "success"
                return "retain"
            finally:
                self._unlock_sidecar(q_fd)
        finally:
            unlock_unlink_stage_dir(stage_dir_fd)
            os.close(stage_dir_fd)

    def _restore_staged_victim_to_ready(
        self,
        ready_dir_fd: int,
        *,
        victim_fd: int,
        expected: os.stat_result,
        artifact_id: UUID,
    ) -> bool:
        """Publish held victim inode to exact ready via linkat (fd-stable).

        Idempotent for exact ready: an existing ready name that already holds the
        expected regular inode with full (non-truncated) size counts as success.
        Symlink, foreign inode, or I/O failure retains the leftover stage victim.
        """

        try:
            live = os.fstat(victim_fd)
        except OSError:
            return False
        if (live.st_dev, live.st_ino) != (expected.st_dev, expected.st_ino):
            return False
        if int(live.st_size) == 0:
            # Truncated victim is not a valid ineligible restore source.
            return False
        expected_size = int(expected.st_size)

        ready_name = artifact_id.hex
        open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd: int | None = None
        try:
            fd = os.open(ready_name, open_flags, dir_fd=ready_dir_fd)
        except FileNotFoundError:
            try:
                link_from_fd(ready_dir_fd, ready_name, victim_fd)
            except (FileExistsError, OSError):
                return False
            try:
                fd = os.open(ready_name, open_flags, dir_fd=ready_dir_fd)
            except OSError:
                return False
        except OSError:
            return False
        try:
            st = os.fstat(fd)
        except OSError:
            return False
        finally:
            if fd is not None:
                os.close(fd)
        if not stat_module.S_ISREG(st.st_mode):
            return False
        if (st.st_dev, st.st_ino) != (expected.st_dev, expected.st_ino):
            return False
        if int(st.st_size) != expected_size:
            return False
        return True

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
                for _name, _ino, _kind in sidecars:
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

            if self._should_converge_eligible_leftover(artifact_id):
                self._converge_eligible_leftover_sidecars(
                    ready_dir_fd,
                    repository_id,
                    artifact_id,
                    sidecars=sidecars,
                )
                return

            if lifecycle.bytes_deleted_at is not None:
                self._recover_stamped_residual_sidecars(
                    ready_dir_fd,
                    repository_id,
                    artifact_id,
                    lifecycle=lifecycle,
                    sidecars=sidecars,
                )
                return

            intent_dev = lifecycle.bytes_delete_dev
            intent_ino = lifecycle.bytes_delete_ino
            intent_generation = lifecycle.bytes_delete_generation
            intent_present = (
                lifecycle.bytes_delete_intent_at is not None
                and intent_dev is not None
                and intent_ino is not None
                and intent_generation is not None
                and lifecycle.bytes_delete_phase in {"quarantined", "detached"}
            )
            if not intent_present:
                for _name, _ino, _kind in sidecars:
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
            assert intent_dev is not None and intent_ino is not None and intent_generation is not None

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
                outcomes = [
                    self._unlink_intent_sidecar_with_recheck(
                        ready_dir_fd,
                        sidecar_name,
                        expected_ino=expected_ino,
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                    )
                    for sidecar_name, expected_ino, _kind in sidecars
                ]
                if self._may_clear_ownership(
                    ready_dir_fd,
                    outcomes,
                    artifact_id=artifact_id,
                    expected_ino=int(intent_ino),
                    generation=str(intent_generation),
                ):
                    self._clear_intent_best_effort(
                        artifact_id,
                        repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                        expected_generation=str(intent_generation),
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
                        expected_generation=str(intent_generation),
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
                outcomes = [
                    self._unlink_stamped_sidecar_with_recheck(
                        ready_dir_fd,
                        sidecar_name,
                        expected_ino=expected_ino,
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                        retention_ok=True,
                    )
                    for sidecar_name, expected_ino, _kind in sidecars
                ]
                if self._may_clear_ownership(
                    ready_dir_fd,
                    outcomes,
                    artifact_id=artifact_id,
                    expected_ino=int(intent_ino),
                    generation=str(intent_generation),
                ):
                    self._clear_receipt_best_effort(
                        artifact_id,
                        repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                        expected_generation=str(intent_generation),
                    )
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

            if ready_absent:
                # Prefer detach→ready so leftover is at most one quarantine hardlink.
                # Falling back to quarantine leaves at most one detach diagnose.
                restore_sidecar = next(
                    (item for item in sidecars if item[2] == "detach"),
                    next(
                        (item for item in sidecars if item[2] == "quarantine"),
                        sidecars[0],
                    ),
                )
                restore_name = restore_sidecar[0]
                try:
                    os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    restored = self._restore_ready_from_sidecar_with_recheck(
                        ready_dir_fd,
                        restore_name,
                        ready_name=ready_name,
                        expected_ino=restore_sidecar[1],
                        repository_id=repository_id,
                        artifact_id=artifact_id,
                    )
                    if not restored:
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
                    # Ready restored with full payload. Remaining same-inode
                    # sidecars are diagnose-only; never pathname-unlink them.
                    self._clear_intent_best_effort(
                        artifact_id,
                        repository_id,
                        expected_dev=int(intent_dev),
                        expected_ino=int(intent_ino),
                        expected_generation=str(intent_generation),
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

            outcomes = [
                self._unlink_intent_sidecar_with_recheck(
                    ready_dir_fd,
                    sidecar_name,
                    expected_ino=expected_ino,
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                )
                for sidecar_name, expected_ino, _kind in sidecars
            ]
            if self._may_clear_ownership(
                ready_dir_fd,
                outcomes,
                artifact_id=artifact_id,
                expected_ino=int(intent_ino),
                generation=str(intent_generation),
            ):
                self._clear_intent_best_effort(
                    artifact_id,
                    repository_id,
                    expected_dev=int(intent_dev),
                    expected_ino=int(intent_ino),
                    expected_generation=str(intent_generation),
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

    def _recover_stamped_residual_sidecars(
        self,
        ready_dir_fd: int,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        lifecycle: ArtifactLifecycleRecord,
        sidecars: list[tuple[str, int, str]],
    ) -> None:
        """Unlink stamped residuals only when they match residual receipt under flock."""

        receipt_dev = lifecycle.bytes_deleted_receipt_dev
        receipt_ino = lifecycle.bytes_deleted_receipt_ino
        receipt_generation = lifecycle.bytes_deleted_receipt_generation
        receipt_present = (
            receipt_dev is not None
            and receipt_ino is not None
            and receipt_generation is not None
        )
        retention_ok = self._retention_explains_deleted(
            lifecycle,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if not receipt_present:
            self._reclaim_receipt_null_size0_sidecars(
                ready_dir_fd,
                repository_id=repository_id,
                artifact_id=artifact_id,
                lifecycle=lifecycle,
                sidecars=sidecars,
                retention_ok=retention_ok,
            )
            return
        outcomes: list[SidecarOutcome] = []

        for sidecar_name, expected_ino, _kind in sidecars:
            outcomes.append(
                self._unlink_stamped_sidecar_with_recheck(
                    ready_dir_fd,
                    sidecar_name,
                    expected_ino=expected_ino,
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    retention_ok=retention_ok,
                )
            )

        if (
            receipt_present
            and receipt_dev is not None
            and receipt_ino is not None
            and receipt_generation is not None
            and self._may_clear_ownership(
                ready_dir_fd,
                outcomes,
                artifact_id=artifact_id,
                expected_ino=int(receipt_ino),
                generation=str(receipt_generation),
            )
        ):
            self._clear_receipt_best_effort(
                artifact_id,
                repository_id,
                expected_dev=int(receipt_dev),
                expected_ino=int(receipt_ino),
                expected_generation=str(receipt_generation),
            )

    @staticmethod
    def _all_sidecars_cleared(outcomes: list[SidecarOutcome]) -> bool:
        return bool(outcomes) and all(outcome in {"absent", "success"} for outcome in outcomes)

    def _may_clear_ownership(
        self,
        ready_dir_fd: int,
        outcomes: list[SidecarOutcome],
        *,
        artifact_id: UUID,
        expected_ino: int,
        generation: str,
    ) -> bool:
        return self._all_sidecars_cleared(outcomes) and not self._has_matching_sidecar_residual(
            ready_dir_fd,
            artifact_id=artifact_id,
            expected_ino=expected_ino,
            generation=generation,
        )

    def _parse_sidecar_generation(self, sidecar_name: str) -> str | None:
        parsed = parse_any_recoverable_sidecar(sidecar_name)
        if parsed is None:
            return None
        return parsed[2]

    def _unlink_intent_sidecar_with_recheck(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> SidecarOutcome:
        lock_result, q_fd, q_stat = self._lock_sidecar(
            ready_dir_fd,
            sidecar_name,
            expected_ino=expected_ino,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if lock_result == SidecarLockResult.ABSENT:
            return "absent"
        if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
            return "retain"
        try:
            try:
                lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
            except (MutationStoreInvariantError, Exception):
                return "retain"
            if lifecycle is None or lifecycle.repository_id != repository_id:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return "retain"
            intent_dev = lifecycle.bytes_delete_dev
            intent_ino = lifecycle.bytes_delete_ino
            intent_generation = lifecycle.bytes_delete_generation
            sidecar_generation = self._parse_sidecar_generation(sidecar_name)
            if sidecar_generation is None:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return "retain"
            matches_intent = (
                lifecycle.bytes_delete_intent_at is not None
                and intent_dev is not None
                and intent_ino is not None
                and intent_generation is not None
                and lifecycle.bytes_delete_phase in {"quarantined", "detached"}
                and int(intent_dev) == int(q_stat.st_dev)
                and int(intent_ino) == int(q_stat.st_ino)
                and sidecar_generation == intent_generation
            )
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
                return "retain"
            unlinked = self._unlink_locked_sidecar(
                ready_dir_fd,
                sidecar_name,
                q_fd,
                q_stat,
                artifact_id=artifact_id,
                generation=sidecar_generation,
            )
            if unlinked:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="deleted",
                    cleanup_outcome="quarantine_residual_unlinked",
                    logger=_LOGGER,
                )
                return "success"
            return "retain"
        finally:
            self._unlock_sidecar(q_fd)

    def _unlink_stamped_sidecar_with_recheck(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
        retention_ok: bool,
    ) -> SidecarOutcome:
        lock_result, q_fd, q_stat = self._lock_sidecar(
            ready_dir_fd,
            sidecar_name,
            expected_ino=expected_ino,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if lock_result == SidecarLockResult.ABSENT:
            return "absent"
        if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
            return "retain"
        try:
            try:
                lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
            except (MutationStoreInvariantError, Exception):
                return "retain"
            if lifecycle is None or lifecycle.repository_id != repository_id:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return "retain"
            receipt_dev = lifecycle.bytes_deleted_receipt_dev
            receipt_ino = lifecycle.bytes_deleted_receipt_ino
            receipt_generation = lifecycle.bytes_deleted_receipt_generation
            sidecar_generation = self._parse_sidecar_generation(sidecar_name)
            if sidecar_generation is None:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return "retain"
            matches_receipt = (
                lifecycle.bytes_deleted_at is not None
                and receipt_dev is not None
                and receipt_ino is not None
                and receipt_generation is not None
                and int(receipt_dev) == int(q_stat.st_dev)
                and int(receipt_ino) == int(q_stat.st_ino)
                and sidecar_generation == receipt_generation
            )
            if not matches_receipt:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return "retain"
            if not retention_ok:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="retained",
                    cleanup_outcome="fail_closed",
                    logger=_LOGGER,
                )
                return "retain"
            unlinked = self._unlink_locked_sidecar(
                ready_dir_fd,
                sidecar_name,
                q_fd,
                q_stat,
                artifact_id=artifact_id,
                generation=sidecar_generation,
            )
            if unlinked:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="quarantine",
                    result="deleted",
                    cleanup_outcome="quarantine_residual_unlinked",
                    logger=_LOGGER,
                )
                return "success"
            return "retain"
        finally:
            self._unlock_sidecar(q_fd)

    def _restore_ready_from_sidecar_with_recheck(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        ready_name: str,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> bool:
        lock_result, q_fd, q_stat = self._lock_sidecar(
            ready_dir_fd,
            sidecar_name,
            expected_ino=expected_ino,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
            return False
        try:
            try:
                lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
            except (MutationStoreInvariantError, Exception):
                return False
            if lifecycle is None or lifecycle.repository_id != repository_id:
                return False
            intent_dev = lifecycle.bytes_delete_dev
            intent_ino = lifecycle.bytes_delete_ino
            intent_generation = lifecycle.bytes_delete_generation
            sidecar_generation = self._parse_sidecar_generation(sidecar_name)
            if sidecar_generation is None:
                return False
            matches_intent = (
                lifecycle.bytes_delete_intent_at is not None
                and intent_dev is not None
                and intent_ino is not None
                and intent_generation is not None
                and lifecycle.bytes_delete_phase in {"quarantined", "detached"}
                and int(intent_dev) == int(q_stat.st_dev)
                and int(intent_ino) == int(q_stat.st_ino)
                and sidecar_generation == intent_generation
            )
            if not matches_intent:
                return False
            try:
                renameat2_noreplace(
                    ready_dir_fd, sidecar_name, ready_dir_fd, ready_name
                )
            except FileExistsError:
                return False
            except OSError:
                return False
            return True
        finally:
            self._unlock_sidecar(q_fd)

    def _gc_bytes_deleted_receipts(self, budget: _HousekeepingBudget) -> None:
        remaining = budget.remaining()
        if remaining <= 0:
            return
        try:
            page = self._mutation_store.list_artifacts_with_bytes_deleted_receipt(
                limit=remaining,
                after_artifact_id=self._receipt_after_artifact_id,
            )
        except Exception:
            _LOGGER.exception("artifact cleaner failed to list receipt GC candidates")
            return
        if page.scanned == 0:
            self._receipt_after_artifact_id = None
            return
        for _ in range(page.scanned):
            if not budget.consume():
                break
        for lifecycle in page.records:
            if self._stopping:
                break
            try:
                self._gc_one_bytes_deleted_receipt(lifecycle)
            except Exception:
                _LOGGER.exception(
                    "artifact receipt GC failed for artifact %s",
                    lifecycle.artifact_id,
                )
        self._receipt_after_artifact_id = page.cursor_artifact_id

    def _gc_one_bytes_deleted_receipt(self, lifecycle: ArtifactLifecycleRecord) -> None:
        receipt_generation = lifecycle.bytes_deleted_receipt_generation
        receipt_dev = lifecycle.bytes_deleted_receipt_dev
        receipt_ino = lifecycle.bytes_deleted_receipt_ino
        if (
            receipt_generation is None
            or receipt_dev is None
            or receipt_ino is None
        ):
            return
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, lifecycle.repository_id)
        except OwnedPathError:
            return
        try:
            try:
                entries = _scandir_names(ready_dir_fd)
            except OSError:
                return
            has_blocking_residual = False
            for entry_name in entries:
                parsed_stage = parse_unlink_stage_dir_name(entry_name)
                if parsed_stage is not None and parsed_stage[0] == lifecycle.artifact_id:
                    if self._stage_dir_is_terminal_or_empty(
                        ready_dir_fd,
                        entry_name,
                        expected_ino=int(receipt_ino),
                    ):
                        continue
                    # Non-empty / unreadable stage blocks receipt GC.
                    return
                parsed = parse_any_recoverable_sidecar(entry_name)
                if parsed is None:
                    continue
                inode, parsed_artifact_id, parsed_generation, _kind = parsed
                if parsed_artifact_id != lifecycle.artifact_id:
                    continue
                if (
                    parsed_generation == receipt_generation
                    and inode == int(receipt_ino)
                ):
                    if self._ready_entry_is_size0_owned_tombstone(
                        ready_dir_fd,
                        entry_name,
                        expected_ino=int(receipt_ino),
                    ):
                        continue
                    has_blocking_residual = True
                    break
            if has_blocking_residual:
                return
            self._clear_receipt_best_effort(
                lifecycle.artifact_id,
                lifecycle.repository_id,
                expected_dev=int(receipt_dev),
                expected_ino=int(receipt_ino),
                expected_generation=str(receipt_generation),
            )
        finally:
            os.close(ready_dir_fd)

    def _lock_sidecar(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> tuple[SidecarLockResult, int | None, os.stat_result | None]:
        """Open + LOCK_NB + fstat. On LOCKED success caller must `_unlock_sidecar`."""

        open_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            open_flags |= nofollow
        q_fd: int | None = None
        try:
            q_fd = os.open(sidecar_name, open_flags, dir_fd=ready_dir_fd)
        except FileNotFoundError:
            return SidecarLockResult.ABSENT, None, None
        except OSError:
            return SidecarLockResult.IO_ERROR, None, None
        try:
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
                os.close(q_fd)
                return SidecarLockResult.BUSY, None, None
            except OSError:
                os.close(q_fd)
                return SidecarLockResult.IO_ERROR, None, None
            try:
                q_stat = os.fstat(q_fd)
            except OSError:
                self._unlock_sidecar(q_fd)
                return SidecarLockResult.IO_ERROR, None, None
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
                self._unlock_sidecar(q_fd)
                return SidecarLockResult.MISMATCH, None, None
            return SidecarLockResult.LOCKED, q_fd, q_stat
        except Exception:
            if q_fd is not None:
                self._unlock_sidecar(q_fd)
            raise

    @staticmethod
    def _unlock_sidecar(q_fd: int) -> None:
        try:
            fcntl.flock(q_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(q_fd)
        except OSError:
            pass

    def _unlink_locked_sidecar(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        q_fd: int,
        expected: os.stat_result,
        *,
        artifact_id: UUID,
        generation: str | None,
    ) -> bool:
        """Destroy a locked sidecar via fd-truncate + size-0 reclaim.

        When the ready name still holds the same inode with non-zero content,
        retain the sidecar as a diagnose tombstone (never pathname-unlink).
        """

        if generation is None:
            return False
        ready_name = artifact_id.hex
        try:
            ready_stat = os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            ready_stat = None
        except OSError:
            ready_stat = None
        if (
            ready_stat is not None
            and (ready_stat.st_dev, ready_stat.st_ino) == (expected.st_dev, expected.st_ino)
            and int(ready_stat.st_size) > 0
        ):
            # Diagnose-only: ready still exposes full package bytes.
            return False
        return destroy_owned_bytes_and_reclaim_names(
            ready_dir_fd,
            q_fd,
            expected,
            [sidecar_name],
            artifact_id=artifact_id,
            generation=generation,
        )

    def _unlink_sidecar_if_same_inode(
        self,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> bool:
        """Open+flock+fstat match then rename-verify-unlink while holding flock."""

        parsed = parse_any_recoverable_sidecar(sidecar_name)
        if parsed is None:
            return False
        _inode, _parsed_artifact_id, generation, _kind = parsed
        if generation is None:
            return False

        lock_result, q_fd, q_stat = self._lock_sidecar(
            ready_dir_fd,
            sidecar_name,
            expected_ino=expected_ino,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if lock_result == SidecarLockResult.ABSENT:
            return True
        if lock_result != SidecarLockResult.LOCKED or q_fd is None or q_stat is None:
            return False
        try:
            if (int(q_stat.st_dev), int(q_stat.st_ino)) != (
                int(expected_dev),
                int(expected_ino),
            ):
                return False
            return self._unlink_locked_sidecar(
                ready_dir_fd,
                sidecar_name,
                q_fd,
                q_stat,
                artifact_id=artifact_id,
                generation=generation,
            )
        finally:
            self._unlock_sidecar(q_fd)

    def _clear_receipt_best_effort(
        self,
        artifact_id: UUID,
        repository_id: UUID,
        *,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        try:
            self._import_store.clear_artifact_bytes_deleted_receipt(
                artifact_id,
                repository_id=repository_id,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
                expected_generation=expected_generation,
            )
        except Exception:
            pass

    def _clear_intent_best_effort(
        self,
        artifact_id: UUID,
        repository_id: UUID,
        *,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        try:
            self._import_store.clear_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
                expected_generation=expected_generation,
            )
        except Exception:
            pass

    def _reclaim_receipt_null_size0_sidecars(
        self,
        ready_dir_fd: int,
        *,
        repository_id: UUID,
        artifact_id: UUID,
        lifecycle: ArtifactLifecycleRecord,
        sidecars: list[tuple[str, int, str]],
        retention_ok: bool,
    ) -> None:
        if lifecycle.bytes_deleted_at is None or not retention_ok:
            return
        kind_map = {"quarantine": "deleting", "detach": "detach", "unlink_verify": "verify"}
        proofs = {
            (row.kind, row.name): row
            for row in self._import_store.list_artifact_residuals(artifact_id=artifact_id).records
            if row.kind in {"deleting", "detach", "verify"}
        }
        for sidecar_name, expected_ino, kind in sidecars:
            parsed = parse_any_recoverable_sidecar(sidecar_name)
            if parsed is None:
                continue
            name_ino, parsed_artifact_id, name_generation, _parsed_kind = parsed
            if parsed_artifact_id != artifact_id or int(name_ino) != int(expected_ino):
                continue
            proof = proofs.get((kind_map.get(kind, kind), sidecar_name))
            if proof is None:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="receipt_null",
                    result="retained",
                    cleanup_outcome="missing_residual_proof",
                    logger=_LOGGER,
                )
                continue
            if int(name_ino) != int(proof.ino):
                continue
            if (
                proof.generation is not None
                and name_generation is not None
                and name_generation != proof.generation
            ):
                continue
            if self._reclaim_receipt_null_size0_entry(
                ready_dir_fd,
                sidecar_name,
                expected_ino=int(proof.ino),
                expected_dev=int(proof.dev),
            ):
                self._import_store.clear_artifact_residual(
                    residual_id=proof.residual_id,
                    expected_dev=int(proof.dev),
                    expected_ino=int(proof.ino),
                )

    def _reclaim_receipt_null_size0_stages(
        self,
        ready_dir_fd: int,
        *,
        repository_id: UUID,
        artifact_id: UUID,
        lifecycle: ArtifactLifecycleRecord,
        stage_names: list[str],
    ) -> None:
        if lifecycle.bytes_deleted_at is None:
            return
        if not self._retention_explains_deleted(
            lifecycle,
            repository_id=repository_id,
            artifact_id=artifact_id,
        ):
            return
        residuals = self._import_store.list_artifact_residuals(artifact_id=artifact_id).records
        stage_proofs = {row.name: row for row in residuals if row.kind == "stage"}
        child_proofs = [row for row in residuals if row.kind == "stage_child"]
        for stage_name in stage_names:
            parsed = parse_unlink_stage_dir_name(stage_name)
            if parsed is None or parsed[0] != artifact_id:
                continue
            proof = stage_proofs.get(stage_name)
            if proof is None:
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="receipt_null",
                    result="retained",
                    cleanup_outcome="missing_residual_proof",
                    logger=_LOGGER,
                )
                continue
            children = [
                (row.name, int(row.dev), int(row.ino))
                for row in child_proofs
                if row.parent_name == stage_name
            ]
            if reclaim_stage_dir(
                ready_dir_fd, stage_name, children=children
            ):
                self._import_store.clear_artifact_residual(
                    residual_id=proof.residual_id,
                    expected_dev=int(proof.dev),
                    expected_ino=int(proof.ino),
                )
                for row in child_proofs:
                    if row.parent_name == stage_name:
                        self._import_store.clear_artifact_residual(
                            residual_id=row.residual_id,
                            expected_dev=int(row.dev),
                            expected_ino=int(row.ino),
                        )

    def _reclaim_durable_residuals(self, budget: _HousekeepingBudget) -> None:
        remaining = budget.remaining()
        if remaining <= 0:
            return
        if self._stopping:
            return
        page = self._import_store.list_artifact_residuals(
            limit=remaining, after_residual_id=self._residual_after_id
        )
        if page.scanned == 0:
            self._residual_after_id = None
            return
        last_id: int | None = None
        for row in page.records:
            if not budget.consume():
                break
            last_id = row.residual_id
            try:
                self._reclaim_one_residual(row)
            except Exception:
                _LOGGER.exception(
                    "artifact residual reclaim failed for %s", row.residual_id
                )
        self._residual_after_id = last_id if last_id is not None else page.cursor_residual_id

    def _reclaim_one_residual(self, row: ArtifactResidualRecord) -> None:
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, row.repository_id)
        except OwnedPathError:
            return
        try:
            if self._residual_name_absent(ready_dir_fd, row):
                self._import_store.clear_artifact_residual(
                    residual_id=row.residual_id,
                    expected_dev=int(row.dev),
                    expected_ino=int(row.ino),
                )
                return
            lifecycle = self._mutation_store.get_artifact_lifecycle(row.artifact_id)
            active_intent = (
                lifecycle is not None
                and lifecycle.bytes_deleted_at is None
                and lifecycle.bytes_delete_intent_at is not None
            )
            if active_intent:
                return
            if not self._residual_is_size0(ready_dir_fd, row):
                return
            if row.kind == "stage_child":
                lookup = lookup_unlink_stage_dir(ready_dir_fd, row.parent_name)
                if lookup.status is StageDirStatus.ABSENT:
                    self._import_store.clear_artifact_residual(
                        residual_id=row.residual_id,
                        expected_dev=int(row.dev),
                        expected_ino=int(row.ino),
                    )
                    return
                if lookup.status is not StageDirStatus.OPENED or lookup.fd is None:
                    return
                stage_fd = lookup.fd
                try:
                    if unlink_if_match(
                        stage_fd,
                        row.name,
                        expected_dev=int(row.dev),
                        expected_ino=int(row.ino),
                    ):
                        self._import_store.clear_artifact_residual(
                            residual_id=row.residual_id,
                            expected_dev=int(row.dev),
                            expected_ino=int(row.ino),
                        )
                finally:
                    os.close(stage_fd)
                return
            if row.kind == "stage":
                children = [
                    (child.name, int(child.dev), int(child.ino))
                    for child in self._import_store.list_artifact_residuals(
                        artifact_id=row.artifact_id
                    ).records
                    if child.kind == "stage_child" and child.parent_name == row.name
                ]
                if reclaim_stage_dir(
                    ready_dir_fd, row.name, children=children
                ):
                    self._import_store.clear_artifact_residual(
                        residual_id=row.residual_id,
                        expected_dev=int(row.dev),
                        expected_ino=int(row.ino),
                    )
                return
            if unlink_if_match(
                ready_dir_fd,
                row.name,
                expected_dev=int(row.dev),
                expected_ino=int(row.ino),
            ):
                self._import_store.clear_artifact_residual(
                    residual_id=row.residual_id,
                    expected_dev=int(row.dev),
                    expected_ino=int(row.ino),
                )
        finally:
            os.close(ready_dir_fd)

    def _residual_name_absent(self, ready_dir_fd: int, row: ArtifactResidualRecord) -> bool:
        if row.kind == "stage_child":
            lookup = lookup_unlink_stage_dir(ready_dir_fd, row.parent_name)
            if lookup.status is not StageDirStatus.OPENED or lookup.fd is None:
                return lookup.status is StageDirStatus.ABSENT
            stage_fd = lookup.fd
            try:
                os.stat(row.name, dir_fd=stage_fd, follow_symlinks=False)
            except FileNotFoundError:
                return True
            except OSError:
                return False
            finally:
                os.close(stage_fd)
            return False
        try:
            os.stat(row.name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return False

    def _residual_is_size0(self, ready_dir_fd: int, row: ArtifactResidualRecord) -> bool:
        dir_fd = ready_dir_fd
        stage_fd: int | None = None
        if row.kind == "stage_child":
            lookup = lookup_unlink_stage_dir(ready_dir_fd, row.parent_name)
            if lookup.status is not StageDirStatus.OPENED or lookup.fd is None:
                return False
            stage_fd = lookup.fd
            dir_fd = stage_fd
        try:
            st = os.stat(row.name, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        finally:
            if stage_fd is not None:
                os.close(stage_fd)
        return int(st.st_size) == 0

    def _reclaim_receipt_null_size0_entry(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_ino: int,
        expected_dev: int | None = None,
    ) -> bool:
        open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(name, open_flags, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        try:
            st = os.fstat(fd)
        except OSError:
            return False
        finally:
            os.close(fd)
        if not stat_module.S_ISREG(st.st_mode):
            return False
        if int(st.st_ino) != int(expected_ino):
            return False
        if expected_dev is not None and int(st.st_dev) != int(expected_dev):
            return False
        if int(st.st_size) != 0:
            return False
        if not prove_size0_owned_name_terminal(
            dir_fd,
            name,
            expected_dev=int(st.st_dev),
            expected_ino=int(expected_ino),
        ):
            return False
        return reclaim_size0_owned_name(
            dir_fd,
            name,
            expected_dev=int(st.st_dev),
            expected_ino=int(expected_ino),
        )

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

    def _inventory_owned_artifact_tree(self, budget: _HousekeepingBudget) -> None:
        artifacts_root = self._layout.artifacts
        if not artifacts_root.is_dir():
            return
        after_repo = self._inventory_after_repo
        after_sub = self._inventory_after_sub
        after_name = self._inventory_after_name
        skipping_repo = after_repo is not None
        last_repo: str | None = None
        last_sub: str | None = None
        last_entry: str | None = None
        exhausted = False
        try:
            with os.scandir(artifacts_root) as entries:
                for entry in entries:
                    name = entry.name
                    resume_inside = False
                    if skipping_repo:
                        if name != after_repo:
                            continue
                        skipping_repo = False
                        if after_sub is None:
                            continue
                        resume_inside = True
                    if not resume_inside:
                        if not budget.consume():
                            exhausted = True
                            break
                        last_repo = name
                        last_sub = None
                        last_entry = None
                    else:
                        last_repo = name
                    inner_exhausted, inner_sub, inner_name = self._inventory_one_artifacts_entry(
                        entry,
                        budget,
                        after_sub=after_sub if resume_inside else None,
                        after_name=after_name if resume_inside else None,
                    )
                    if inner_exhausted:
                        last_sub = inner_sub
                        last_entry = inner_name
                        exhausted = True
                        break
                    if not budget.remaining():
                        exhausted = True
                        break
                    after_sub = None
                    after_name = None
        except OSError:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="artifacts_root_unreadable",
                logger=_LOGGER,
            )
            return
        if not exhausted and budget.remaining():
            staging_artifacts = self._layout.staging_artifacts
            if staging_artifacts.is_dir():
                self._inventory_directory_entries(
                    None,
                    staging_artifacts,
                    allow_staging_shape=True,
                    budget=budget,
                    after_name=None,
                )
        if exhausted:
            self._inventory_after_repo = last_repo
            self._inventory_after_sub = last_sub
            self._inventory_after_name = last_entry
        else:
            self._inventory_after_repo = None
            self._inventory_after_sub = None
            self._inventory_after_name = None

    def _inventory_one_artifacts_entry(
        self,
        entry: os.DirEntry[str],
        budget: _HousekeepingBudget,
        *,
        after_sub: str | None,
        after_name: str | None,
    ) -> tuple[bool, str | None, str | None]:
        name = entry.name
        try:
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                log_event(
                    "artifact_cleanup",
                    stage="path_check",
                    result="retained",
                    cleanup_outcome="unknown_path_inventory",
                    logger=_LOGGER,
                )
                return False, None, None
        except OSError:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return False, None, None
        if len(name) != 32 or any(ch not in _HEX32 for ch in name):
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return False, None, None
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
            return False, None, None
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
        skipping_sub = after_sub is not None
        for sub in ("ready", "staging"):
            if skipping_sub:
                if sub != after_sub:
                    continue
                skipping_sub = False
            sub_exhausted, sub_last = self._inventory_directory_entries(
                repository_id,
                Path(entry.path) / sub,
                allow_staging_shape=(sub == "staging"),
                budget=budget,
                after_name=after_name if sub == after_sub else None,
            )
            after_name = None
            if sub_exhausted:
                return True, sub, sub_last
        return False, None, None

    def _inventory_directory_entries(
        self,
        repository_id: UUID | None,
        directory: Path,
        *,
        allow_staging_shape: bool,
        budget: _HousekeepingBudget,
        after_name: str | None,
    ) -> tuple[bool, str | None]:
        try:
            dir_st = directory.lstat()
        except OSError:
            return False, None
        if stat_module.S_ISLNK(dir_st.st_mode) or not stat_module.S_ISDIR(dir_st.st_mode):
            return False, None
        skipping = after_name is not None
        last: str | None = None
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    name = entry.name
                    if skipping:
                        if name == after_name:
                            skipping = False
                        continue
                    if not budget.consume():
                        return True, last
                    last = name
                    if (
                        name.startswith(".deleting-")
                        or name.startswith(".detach-")
                        or name.startswith(".unlink-verify-")
                        or name.startswith(".unlink-stage-")
                    ):
                        if name.startswith(".unlink-verify-"):
                            malformed = parse_unlink_verify_name(name) is None
                        elif name.startswith(".unlink-stage-"):
                            malformed = parse_unlink_stage_dir_name(name) is None
                        elif name.startswith(".deleting-"):
                            malformed = parse_quarantine_name(name) is None
                        else:
                            malformed = parse_any_recoverable_sidecar(name) is None
                        if malformed:
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
                            lifecycle = self._mutation_store.get_artifact_lifecycle(
                                artifact_id
                            )
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
                            repository_id is not None
                            and lifecycle.repository_id != repository_id
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
                            lifecycle = self._mutation_store.get_artifact_lifecycle(
                                artifact_id
                            )
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
                            repository_id is not None
                            and lifecycle.repository_id != repository_id
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
        except OSError:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="path_check",
                result="retained",
                cleanup_outcome="ready_dir_unreadable",
                logger=_LOGGER,
            )
            return False, None
        return False, None

    def _still_eligible(self, artifact_id: UUID, repository_id: UUID) -> bool:
        lifecycle = self._mutation_store.get_artifact_lifecycle(artifact_id)
        if lifecycle is None or lifecycle.repository_id != repository_id:
            return False
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
