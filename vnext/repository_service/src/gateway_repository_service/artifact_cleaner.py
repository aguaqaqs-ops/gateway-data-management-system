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
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.artifact_broker import ArtifactBrokerError, get_artifact_broker
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
    STAGE_VICTIM,
    destroy_owned_bytes_and_reclaim_names,
    list_unlink_stage_dir_names,
    lock_unlink_stage_dir,
    normalize_unlink_stage_victim_via_fd,
    open_owned_ready_dir,
    open_owned_unlink_stage_dir,
    parse_any_recoverable_sidecar,
    parse_quarantine_name,
    parse_unlink_stage_dir_name,
    parse_unlink_verify_name,
    prove_size0_owned_name_terminal,
    reclaim_size0_owned_name,
    try_unlink_ready_artifact_with_recheck as try_unlink_ready_artifact_with_recheck,
    unlock_unlink_stage_dir,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)

_HEX32 = frozenset("0123456789abcdef")
_CLEANUP_CANDIDATE_PAGE_SIZE = 64

SidecarOutcome = Literal["absent", "success", "retain"]


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
        self._cleanup_cursor: tuple[str, UUID] | None = None

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
        self._gc_bytes_deleted_receipts()
        try:
            after_created_at: str | None = None
            after_artifact_id: UUID | None = None
            if self._cleanup_cursor is not None:
                after_created_at, after_artifact_id = self._cleanup_cursor
            candidates = self._mutation_store.list_artifacts_pending_byte_cleanup(
                limit=_CLEANUP_CANDIDATE_PAGE_SIZE,
                after_created_at=after_created_at,
                after_artifact_id=after_artifact_id,
            )
            if not candidates and self._cleanup_cursor is not None:
                self._cleanup_cursor = None
                candidates = self._mutation_store.list_artifacts_pending_byte_cleanup(
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
            return

        # Bounded keyset pagination (ADR 0011): SQL LIMIT, rotating cursor.
        sql_rows = len(candidates)
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
        if sql_rows < _CLEANUP_CANDIDATE_PAGE_SIZE:
            self._cleanup_cursor = None
        elif candidates:
            last = candidates[-1]
            if last.created_at is not None:
                self._cleanup_cursor = (last.created_at, last.artifact_id)
            else:
                self._cleanup_cursor = None

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
        intent_ids: dict[str, int | str] = {}

        def _stamp(dev: int, ino: int, generation: str) -> None:
            self._import_store.mark_artifact_bytes_deleted(
                artifact_id,
                deleted_at=self._deleted_at_stamp(),
                repository_id=repository_id,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )
            stamped["ok"] = True

        def _on_intent(dev: int, ino: int, generation: str) -> None:
            intent_ids["dev"] = dev
            intent_ids["ino"] = ino
            intent_ids["generation"] = generation
            self._import_store.begin_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at=self._deleted_at_stamp(),
                generation=generation,
            )

        def _on_clear_intent(dev: int, ino: int, generation: str) -> None:
            self._import_store.clear_artifact_bytes_delete_intent(
                artifact_id,
                repository_id=repository_id,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _on_clear_receipt(dev: int, ino: int, generation: str) -> None:
            self._import_store.clear_artifact_bytes_deleted_receipt(
                artifact_id,
                repository_id=repository_id,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
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
            on_clear_receipt=_on_clear_receipt,
            tombstone_budget=self._settings.artifact_tombstone_budget,
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
                parsed = parse_any_recoverable_sidecar(entry.name)
                if parsed is None:
                    continue
                inode, artifact_id, _generation, kind = parsed
                by_artifact.setdefault(artifact_id, []).append((entry.name, inode, kind))
            # Stage residuals first so sidecar/receipt paths never clear ownership
            # while a matching .unlink-stage-* victim still exists.
            self._recover_unlink_stage_dirs_for_ready(
                repository_id,
                ready_dir,
            )
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

    def _recover_unlink_stage_dirs_for_ready(
        self,
        repository_id: UUID,
        ready_dir: Path,
    ) -> None:
        del ready_dir  # path used only to reach owned ready_dir_fd
        try:
            ready_dir_fd = open_owned_ready_dir(self._layout, repository_id)
        except OwnedPathError:
            return
        except OSError:
            log_event(
                "artifact_cleanup",
                repository_id=repository_id,
                stage="quarantine",
                result="retained",
                cleanup_outcome="unknown_path_inventory",
                logger=_LOGGER,
            )
            return
        try:
            try:
                names = os.listdir(ready_dir_fd)
            except OSError:
                return
            stage_dirs: list[str] = []
            for entry_name in names:
                if parse_unlink_stage_dir_name(entry_name) is None:
                    continue
                stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, entry_name)
                if stage_dir_fd is None:
                    log_event(
                        "artifact_cleanup",
                        repository_id=repository_id,
                        stage="quarantine",
                        result="retained",
                        cleanup_outcome="unknown_path_inventory",
                        logger=_LOGGER,
                    )
                    continue
                try:
                    if not lock_unlink_stage_dir(stage_dir_fd):
                        continue
                    try:
                        # Do not normalize here — unknown/mismatched artifacts must
                        # remain byte-stable until lifecycle proves ownership.
                        stage_dirs.append(entry_name)
                    finally:
                        unlock_unlink_stage_dir(stage_dir_fd)
                finally:
                    os.close(stage_dir_fd)
            if not stage_dirs:
                return
            by_artifact: dict[UUID, list[str]] = {}
            for stage_name in stage_dirs:
                parsed = parse_unlink_stage_dir_name(stage_name)
                if parsed is None:
                    continue
                artifact_id, _token = parsed
                by_artifact.setdefault(artifact_id, []).append(stage_name)
            for artifact_id, stages in by_artifact.items():
                if self._stopping:
                    return
                try:
                    self._recover_artifact_unlink_stages(
                        repository_id,
                        artifact_id,
                        stage_names=stages,
                    )
                except Exception:
                    _LOGGER.exception(
                        "artifact unlink-stage recovery failed for artifact %s",
                        artifact_id,
                    )
        finally:
            os.close(ready_dir_fd)

    def _recover_artifact_unlink_stages(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        stage_names: list[str],
    ) -> None:
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
                return

            if lifecycle.bytes_deleted_at is not None:
                self._recover_stamped_unlink_stages(
                    ready_dir_fd,
                    repository_id,
                    artifact_id,
                    lifecycle=lifecycle,
                    stage_names=stage_names,
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
                return
            assert intent_dev is not None and intent_ino is not None and intent_generation is not None

            outcomes = [
                self._unlink_intent_unlink_stage_with_recheck(
                    ready_dir_fd,
                    stage_name,
                    expected_dev=int(intent_dev),
                    expected_ino=int(intent_ino),
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    generation=str(intent_generation),
                )
                for stage_name in stage_names
            ]
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
    ) -> None:
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
            return
        assert receipt_dev is not None and receipt_ino is not None and receipt_generation is not None
        retention_ok = self._retention_explains_deleted(
            lifecycle,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        outcomes: list[SidecarOutcome] = []
        for stage_name in stage_names:
            outcomes.append(
                self._unlink_stamped_unlink_stage_with_recheck(
                    ready_dir_fd,
                    stage_name,
                    expected_dev=int(receipt_dev),
                    expected_ino=int(receipt_ino),
                    repository_id=repository_id,
                    artifact_id=artifact_id,
                    retention_ok=retention_ok,
                    generation=str(receipt_generation),
                )
            )
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

    def _has_matching_sidecar_residual(
        self,
        ready_dir_fd: int,
        *,
        artifact_id: UUID,
        expected_ino: int,
        generation: str,
    ) -> bool:
        try:
            entries = os.listdir(ready_dir_fd)
        except OSError:
            return True
        for entry_name in entries:
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
        return False

    def _stage_dir_is_empty(self, ready_dir_fd: int, stage_name: str) -> bool:
        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            return False
        try:
            if not lock_unlink_stage_dir(stage_dir_fd):
                return False
            try:
                try:
                    names = os.listdir(stage_dir_fd)
                except OSError:
                    return False
                return not names
            finally:
                unlock_unlink_stage_dir(stage_dir_fd)
        finally:
            os.close(stage_dir_fd)

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
                    names = os.listdir(stage_dir_fd)
                except OSError:
                    return False
                if not names:
                    return True
                for name in names:
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

    def _list_artifact_unlink_stages(
        self,
        ready_dir_fd: int,
        artifact_id: UUID,
    ) -> list[str]:
        names: list[str] = []
        for stage_name in list_unlink_stage_dir_names(ready_dir_fd):
            parsed = parse_unlink_stage_dir_name(stage_name)
            if parsed is not None and parsed[0] == artifact_id:
                names.append(stage_name)
        return names

    def _staged_victim_path(self, stage_name: str) -> str:
        return f"{stage_name}/{STAGE_VICTIM}"

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
    ) -> SidecarOutcome:
        stage_dir_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
        if stage_dir_fd is None:
            return "retain"
        if not lock_unlink_stage_dir(stage_dir_fd):
            os.close(stage_dir_fd)
            return "retain"
        try:
            if not normalize_unlink_stage_victim_via_fd(
                stage_dir_fd,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
            ):
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
                        generation=generation,
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
            if not normalize_unlink_stage_victim_via_fd(
                stage_dir_fd,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
            ):
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
        generation: str,
    ) -> bool:
        """Publish held victim inode to exact ready via linkat (fd-stable).

        Idempotent for exact ready: an existing ready name that already holds the
        expected regular inode with full (non-truncated) size counts as success.
        Matching verify sidecars are diagnose-only and must not clear intent when
        ready is foreign/symlink/I/O (ADR 0011). Stage victim pathname may remain.
        Failure is fail-closed so callers retain intent.
        """

        from gateway_repository_service.upload_artifact.admission_pin import (
            verify_sidecar_name_for,
        )

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
        restore_names = [
            ready_name,
            verify_sidecar_name_for(
                inode=int(expected.st_ino),
                generation=generation,
                artifact_id=artifact_id,
                token="restore",
            ),
        ]
        open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        for restore_name in restore_names:
            is_ready_candidate = restore_name == ready_name
            fd: int | None = None
            try:
                fd = os.open(restore_name, open_flags, dir_fd=ready_dir_fd)
            except FileNotFoundError:
                try:
                    get_artifact_broker().link_from_fd(
                        ready_dir_fd, restore_name, victim_fd
                    )
                except FileExistsError:
                    continue
                except (OSError, ArtifactBrokerError):
                    continue
                try:
                    fd = os.open(restore_name, open_flags, dir_fd=ready_dir_fd)
                except OSError:
                    return False
            except OSError:
                # Symlink / I/O / permission: try next candidate.
                # ADR 0011: foreign/symlink/EIO on ready must not clear intent via verify.
                continue
            try:
                st = os.fstat(fd)
            except OSError:
                return False
            finally:
                if fd is not None:
                    os.close(fd)
            if not stat_module.S_ISREG(st.st_mode):
                continue
            if (st.st_dev, st.st_ino) != (expected.st_dev, expected.st_ino):
                continue
            if int(st.st_size) != expected_size:
                continue
            # Only exact ready name may clear intent (ADR 0011 restore freeze).
            if is_ready_candidate:
                return True
            # Matching verify is diagnose-only; keep searching / fail closed.
            continue
        return False

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
                get_artifact_broker().rename_noreplace(
                    ready_dir_fd, sidecar_name, ready_dir_fd, ready_name
                )
            except FileExistsError:
                return False
            except (OSError, ArtifactBrokerError):
                return False
            return True
        finally:
            self._unlock_sidecar(q_fd)

    def _gc_bytes_deleted_receipts(self) -> None:
        try:
            receipts = self._mutation_store.list_artifacts_with_bytes_deleted_receipt()
        except Exception:
            _LOGGER.exception("artifact cleaner failed to list receipt GC candidates")
            return
        for lifecycle in receipts:
            if self._stopping:
                return
            try:
                self._gc_one_bytes_deleted_receipt(lifecycle)
            except Exception:
                _LOGGER.exception(
                    "artifact receipt GC failed for artifact %s",
                    lifecycle.artifact_id,
                )

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
                entries = os.listdir(ready_dir_fd)
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
        """Reclaim size-0 q/d/verify tombs after c4df9d9 receipt-null stamps.

        Never forges a receipt. Non-zero / foreign / ino-mismatched names retain.
        """

        del repository_id
        if lifecycle.bytes_deleted_at is None or not retention_ok:
            return
        for sidecar_name, expected_ino, _kind in sidecars:
            parsed = parse_any_recoverable_sidecar(sidecar_name)
            if parsed is None:
                continue
            name_ino, parsed_artifact_id, _generation, _parsed_kind = parsed
            if parsed_artifact_id != artifact_id or int(name_ino) != int(expected_ino):
                continue
            self._reclaim_receipt_null_size0_entry(
                ready_dir_fd,
                sidecar_name,
                expected_ino=int(expected_ino),
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
        for stage_name in stage_names:
            parsed = parse_unlink_stage_dir_name(stage_name)
            if parsed is None or parsed[0] != artifact_id:
                continue
            stage_fd = open_owned_unlink_stage_dir(ready_dir_fd, stage_name)
            if stage_fd is None:
                continue
            reclaimed_any = False
            try:
                if not lock_unlink_stage_dir(stage_fd):
                    continue
                try:
                    try:
                        children = os.listdir(stage_fd)
                    except OSError:
                        continue
                    for child in children:
                        open_flags = (
                            os.O_RDONLY
                            | getattr(os, "O_NOFOLLOW", 0)
                            | getattr(os, "O_NONBLOCK", 0)
                        )
                        try:
                            child_fd = os.open(child, open_flags, dir_fd=stage_fd)
                        except FileNotFoundError:
                            continue
                        except OSError:
                            continue
                        try:
                            st = os.fstat(child_fd)
                        except OSError:
                            continue
                        finally:
                            os.close(child_fd)
                        if not stat_module.S_ISREG(st.st_mode) or int(st.st_size) != 0:
                            continue
                        if reclaim_size0_owned_name(
                            stage_fd,
                            child,
                            expected_dev=int(st.st_dev),
                            expected_ino=int(st.st_ino),
                            artifact_id=artifact_id,
                        ):
                            reclaimed_any = True
                finally:
                    unlock_unlink_stage_dir(stage_fd)
            finally:
                os.close(stage_fd)
            if reclaimed_any:
                get_artifact_broker().rmdir_if_empty(ready_dir_fd, stage_name)

    def _reclaim_receipt_null_size0_entry(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_ino: int,
    ) -> None:
        open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(name, open_flags, dir_fd=dir_fd)
        except FileNotFoundError:
            return
        except OSError:
            return
        try:
            st = os.fstat(fd)
        except OSError:
            return
        finally:
            os.close(fd)
        if not stat_module.S_ISREG(st.st_mode):
            return
        if int(st.st_ino) != int(expected_ino):
            return
        if int(st.st_size) != 0:
            return
        if not prove_size0_owned_name_terminal(
            dir_fd,
            name,
            expected_dev=int(st.st_dev),
            expected_ino=int(expected_ino),
        ):
            return
        reclaim_size0_owned_name(
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
            if (
                name.startswith(".deleting-")
                or name.startswith(".detach-")
                or name.startswith(".unlink-verify-")
                or name.startswith(".unlink-stage-")
            ):
                # Quarantine/detach/verify/stage sidecars are recovered separately; diagnose
                # malformed names that fail to parse.
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
