"""Runtime-owned artifact retention cleaner."""

from __future__ import annotations

import fcntl
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
)
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)


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
            self._pending = True
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
                    # Sticky wake consumed: resweep immediately without sleeping.
                    self._pending = False
                    continue
                self._condition.wait(timeout=max(interval, 0.0))
                if self._stopping:
                    return
                # Timeout fallback or wake: clear sticky bit and loop for next sweep.
                self._pending = False

    def _sweep(self) -> None:
        started = time.monotonic()
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

        ready_path = artifact_ready_path(self._layout, repository_id, artifact_id)
        path_kind = classify_ready_artifact_path(ready_path, expected=ready_path)
        if path_kind == "absent":
            self._import_store.mark_artifact_bytes_deleted(artifact_id)
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="deleted",
                code=decision.reason.value,
                cleanup_outcome="already_absent_recorded",
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

        outcome = try_unlink_ready_artifact_with_recheck(
            ready_path,
            recheck=lambda: self._still_eligible(artifact_id),
        )
        if outcome == "busy":
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="retained",
                cleanup_outcome="lock_busy",
                logger=_LOGGER,
            )
            return
        if outcome == "ineligible":
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="retained",
                cleanup_outcome="eligibility_changed",
                logger=_LOGGER,
            )
            return
        if outcome == "unlink_failed":
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="retained",
                cleanup_outcome="unlink_failed",
                logger=_LOGGER,
            )
            return
        if outcome in {"deleted", "already_absent"}:
            if ready_path.exists():
                log_event(
                    "artifact_cleanup",
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    stage="delete",
                    result="retained",
                    cleanup_outcome="still_present_after_unlink",
                    logger=_LOGGER,
                )
                return
            self._import_store.mark_artifact_bytes_deleted(artifact_id)
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                artifact_id=artifact_id,
                stage="delete",
                result="deleted",
                code=decision.reason.value,
                cleanup_outcome=outcome,
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


def classify_ready_artifact_path(path: Path, *, expected: Path) -> str:
    """Classify a candidate ready path without logging the raw path."""

    try:
        if path.resolve(strict=False) != expected.resolve(strict=False):
            return "unexpected_path"
    except OSError:
        return "unresolvable"
    if not path.exists():
        return "absent"
    try:
        if path.is_symlink():
            return "symlink"
        if not path.is_file():
            return "not_regular_file"
    except OSError:
        return "stat_failed"
    name = path.name
    if len(name) != 32 or any(ch not in "0123456789abcdef" for ch in name):
        return "malformed_name"
    return "regular_file"


def try_unlink_ready_artifact_with_recheck(
    ready_path: Path,
    *,
    recheck: Callable[[], bool],
) -> str:
    """Acquire admission flock, recheck eligibility, then unlink when safe."""

    try:
        fd = os.open(ready_path, os.O_RDONLY)
    except FileNotFoundError:
        return "already_absent"
    except OSError:
        return "unlink_failed"
    try:
        os.set_inheritable(fd, False)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        try:
            if not recheck():
                return "ineligible"
            try:
                ready_path.unlink()
            except FileNotFoundError:
                return "already_absent"
            except OSError:
                return "unlink_failed"
            return "deleted"
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)
