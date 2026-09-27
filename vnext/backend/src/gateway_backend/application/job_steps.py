"""Shared operation step checkpoint helpers for job handlers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from gateway_backend.application.checkpoints import make_checkpoint_step_builder
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import OperationRecord, StepRecord


class ArtifactProtectionTransaction(Protocol):
    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> None: ...


def unique_artifact_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    unique: list[ArtifactRef] = []
    for ref in refs:
        if ref.artifact_id in seen:
            continue
        seen.add(ref.artifact_id)
        unique.append(ref)
    return tuple(unique)


def pinned_checkpoint_builder(
    *,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    intent: str,
    owner_kind: str,
    transaction: ArtifactProtectionTransaction | None,
    on_missing_transaction: Callable[[], None],
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    inner = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        candidate = inner(operation, step, transaction_now)
        if transaction is None:
            on_missing_transaction()
        else:
            transaction.set_artifact_protection(
                unique_artifact_refs((checkpoint_ref, *extra_refs)),
                owner_kind=owner_kind,
                owner_id=step.step_id,
                intent=intent,
            )
        return candidate

    return builder
