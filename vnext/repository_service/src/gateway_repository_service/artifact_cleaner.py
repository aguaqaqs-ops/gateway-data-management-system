"""Runtime-owned artifact retention cleaner."""

from __future__ import annotations

import logging
import os
import stat as stat_module
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable
from uuid import UUID

from gateway_repository_service import artifact_cleanup
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
)
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import (
    MutationStore,
    MutationStoreInvariantError,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)

_HEX32 = frozenset("0123456789abcdef")
_CLEANUP_CANDIDATE_PAGE_SIZE = 64
_HOUSEKEEPING_ENTRY_BUDGET = 64
_T = TypeVar("_T")


class _HousekeepingBudget:
    """Per-sweep entry cap for bounded diagnostic inventory."""

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


@dataclass
class _BilledScan:
    truncated: bool = False


def _billed_iter(
    raw: Iterator[_T],
    budget: _HousekeepingBudget,
    scan: _BilledScan,
) -> Iterator[_T]:
    """Yield dirents only after the shared budget still has room.

    Checks ``remaining`` before pulling the next name so a 64-entry cap
    cannot observe a 65th scandir yield.
    """

    while True:
        if budget.remaining() <= 0:
            scan.truncated = True
            return
        try:
            item = next(raw)
        except StopIteration:
            return
        if not budget.consume():
            scan.truncated = True
            return
        yield item


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
        before_sweep: Callable[[], None] | None = None,
    ) -> None:
        self._before_sweep = before_sweep
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
        while not admitted():
            deleted = self._sweep(housekeeping=True)
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
        if self._before_sweep is not None:
            self._before_sweep()
        with self._condition:
            restart = self._restart_cursor
            self._restart_cursor = False
        if restart:
            self._cleanup_cursor = None
        started = time.monotonic()
        if housekeeping:
            budget = _HousekeepingBudget(_HOUSEKEEPING_ENTRY_BUDGET)
            self._inventory_owned_artifact_tree(budget)
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

    def _inventory_owned_artifact_tree(self, budget: _HousekeepingBudget) -> None:
        artifacts_root = self._layout.artifacts
        if not artifacts_root.is_dir():
            return
        truncated = False
        try:
            with os.scandir(artifacts_root) as entries:
                scan = _BilledScan()
                for entry in _billed_iter(iter(entries), budget, scan):
                    if self._inventory_one_artifacts_entry(entry, budget):
                        truncated = True
                        break
                    if budget.remaining() <= 0:
                        truncated = True
                        break
                if scan.truncated:
                    truncated = True
        except OSError:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="artifacts_root_unreadable",
                logger=_LOGGER,
            )
            return
        if not truncated and budget.remaining():
            staging_artifacts = self._layout.staging_artifacts
            if staging_artifacts.is_dir():
                truncated = self._inventory_directory_entries(
                    None,
                    staging_artifacts,
                    allow_staging_shape=True,
                    budget=budget,
                )
        if truncated:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="inventory_truncated",
                logger=_LOGGER,
            )

    def _inventory_one_artifacts_entry(
        self,
        entry: os.DirEntry[str],
        budget: _HousekeepingBudget,
    ) -> bool:
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
                return False
        except OSError:
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return False
        if len(name) != 32 or any(ch not in _HEX32 for ch in name):
            log_event(
                "artifact_cleanup",
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return False
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
            return False
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
            if self._inventory_directory_entries(
                repository_id,
                Path(entry.path) / sub,
                allow_staging_shape=(sub == "staging"),
                budget=budget,
            ):
                return True
        return False

    def _inventory_directory_entries(
        self,
        repository_id: UUID | None,
        directory: Path,
        *,
        allow_staging_shape: bool,
        budget: _HousekeepingBudget,
    ) -> bool:
        try:
            dir_st = directory.lstat()
        except OSError:
            return False
        if stat_module.S_ISLNK(dir_st.st_mode) or not stat_module.S_ISDIR(dir_st.st_mode):
            return False
        try:
            with os.scandir(directory) as entries:
                scan = _BilledScan()
                for entry in _billed_iter(iter(entries), budget, scan):
                    name = entry.name
                    if _is_exact_ready_name(name):
                        self._diagnose_known_shape(repository_id, name)
                        continue
                    if allow_staging_shape and _is_staging_shape(name):
                        left, _right = name.split(".", 1)
                        self._diagnose_known_shape(repository_id, left)
                        continue
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        stage="path_check",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                if scan.truncated:
                    return True
        except OSError:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="path_check",
                result="retained",
                cleanup_outcome="ready_dir_unreadable",
                logger=_LOGGER,
            )
            return False
        return False

    def _diagnose_known_shape(self, repository_id: UUID | None, artifact_hex: str) -> None:
        try:
            artifact_id = UUID(hex=artifact_hex)
        except ValueError:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="path_check",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return
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
            return
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
            return
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
