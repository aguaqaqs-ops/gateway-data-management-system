"""Cooperative ready-bytes cleanup seam.

Worker, recovery/admin, and the background cleaner share this entry.
The protocol is: non-blocking inode flock (the same pin admission uses),
re-read durable eligibility in that critical section, dirfd-relative
``unlinkat`` of the exact UUID name, then stamp ``bytes_deleted_at``.
Eligible ``ENOENT`` is idempotent completion and stamps. The path does
not create sidecars, delete intent, receipt, residual rows, or tombstone
reservations. Callers keep eligibility pre-checks, private-ref/staging
cleanup, and cleaner housekeeping outside this function.
"""

from __future__ import annotations

import errno
import fcntl
import os
from collections.abc import Callable
from uuid import UUID

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStoreError, MutationStoreInvariantError
from gateway_repository_service.upload_artifact.admission_pin import (
    OwnedPathError,
    open_owned_ready_artifact,
)
from gateway_repository_service.versioned_import.models import ImportOperationStoreError
from gateway_repository_service.versioned_import.store import ImportOperationStore


def _unlink_ready_name(name: str, *, dir_fd: int) -> None:
    os.unlink(name, dir_fd=dir_fd)


def cleanup_ready_artifact_bytes(
    store: ImportOperationStore,
    layout: DurableLayout,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    ttl_seconds: int,
    deleted_at: str | None = None,
    recheck: Callable[[], bool] | None = None,
) -> str:
    """Delete owned ready bytes via pin, eligibility recheck, and dirfd unlink.

    Returns an outcome string: ``deleted``, ``busy``, ``ineligible``,
    ``unlink_failed``, or ``unsafe_path``. Eligible absence stamps
    ``bytes_deleted_at``. I/O errors do not stamp.
    """

    def _default_recheck() -> bool:
        return store.can_delete_artifact_bytes(
            artifact_id,
            ttl_seconds=ttl_seconds,
        )

    eligibility_check = recheck if recheck is not None else _default_recheck

    def _scope_matches() -> bool:
        try:
            lifecycle = store.mutation_store.get_artifact_lifecycle(artifact_id)
        except (ImportOperationStoreError, MutationStoreError, MutationStoreInvariantError):
            return False
        return lifecycle is not None and lifecycle.repository_id == repository_id

    def _pinned_eligible() -> bool:
        if not _scope_matches():
            return False
        return eligibility_check()

    def _try_stamp() -> bool:
        try:
            store.mark_artifact_bytes_deleted(
                artifact_id,
                deleted_at=deleted_at,
                repository_id=repository_id,
            )
        except (ImportOperationStoreError, MutationStoreError):
            return False
        return True

    def _stamp_if_eligible() -> str:
        if not _pinned_eligible():
            return "ineligible"
        if not _try_stamp():
            return "ineligible"
        return "deleted"

    file_fd = -1
    ready_dir_fd = -1
    locked = False
    try:
        try:
            file_fd, ready_dir_fd = open_owned_ready_artifact(
                layout,
                repository_id,
                artifact_id,
            )
        except OwnedPathError as exc:
            message = str(exc)
            if message == "ready artifact file is missing":
                return _stamp_if_eligible()
            if (
                "symlink" in message
                or "not a regular file" in message
                or "non-directory" in message
            ):
                return "unsafe_path"
            return "unlink_failed"

        try:
            fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        except OSError as exc:
            if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES}:
                return "busy"
            return "unlink_failed"
        locked = True

        if not _pinned_eligible():
            return "ineligible"

        try:
            _unlink_ready_name(artifact_id.hex, dir_fd=ready_dir_fd)
        except FileNotFoundError:
            pass
        except OSError:
            return "unlink_failed"

        if not _try_stamp():
            return "unlink_failed"
        return "deleted"
    finally:
        if locked and file_fd >= 0:
            try:
                fcntl.flock(file_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        if file_fd >= 0:
            os.close(file_fd)
        if ready_dir_fd >= 0:
            os.close(ready_dir_fd)
