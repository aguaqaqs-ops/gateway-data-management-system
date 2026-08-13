"""Cooperative ready-bytes cleanup seam.

Worker, recovery/admin, and the background cleaner share this entry. The current
implementation still adapts to the owned unlink protocol (sidecar / intent /
receipt). Callers keep eligibility pre-checks, private-ref/staging cleanup, and
cleaner housekeeping outside this function.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.upload_artifact.admission_pin import (
    artifact_residual_sink,
    try_unlink_ready_artifact_with_recheck as try_unlink_ready_artifact_with_recheck,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore


def cleanup_ready_artifact_bytes(
    store: ImportOperationStore,
    layout: DurableLayout,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    ttl_seconds: int,
    tombstone_budget: int,
    deleted_at: str | None = None,
    recheck: Callable[[], bool] | None = None,
) -> str:
    """Delete owned ready bytes via the current unlink protocol.

    Returns the underlying unlink outcome string. Eligible ``ENOENT`` does not
    stamp ``bytes_deleted_at``; that remains a Step B behavior change.
    """

    def _default_recheck() -> bool:
        return store.can_delete_artifact_bytes(
            artifact_id,
            ttl_seconds=ttl_seconds,
        )

    eligibility_check = recheck if recheck is not None else _default_recheck

    def _stamp(dev: int, ino: int, generation: str) -> None:
        store.mark_artifact_bytes_deleted(
            artifact_id,
            deleted_at=deleted_at,
            repository_id=repository_id,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _on_intent(dev: int, ino: int, generation: str) -> None:
        store.begin_artifact_bytes_delete_intent(
            artifact_id,
            repository_id=repository_id,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at=deleted_at,
            generation=generation,
        )

    def _on_clear_intent(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_delete_intent(
            artifact_id,
            repository_id=repository_id,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _on_clear_receipt(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_deleted_receipt(
            artifact_id,
            repository_id=repository_id,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _on_residual(
        kind: str,
        name: str,
        parent_name: str,
        dev: int,
        ino: int,
        generation: str | None,
    ) -> None:
        store.insert_artifact_residual(
            artifact_id,
            repository_id=repository_id,
            kind=kind,
            name=name,
            parent_name=parent_name,
            dev=dev,
            ino=ino,
            generation=generation,
            created_at=deleted_at,
        )

    ready_path = artifact_ready_path(layout, repository_id, artifact_id)
    with artifact_residual_sink(_on_residual):
        return try_unlink_ready_artifact_with_recheck(
            ready_path,
            recheck=eligibility_check,
            layout=layout,
            repository_id=repository_id,
            artifact_id=artifact_id,
            on_deleted=_stamp,
            on_intent=_on_intent,
            on_clear_intent=_on_clear_intent,
            on_clear_receipt=_on_clear_receipt,
            tombstone_budget=tombstone_budget,
        )
