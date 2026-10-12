"""Shared operation step checkpoint helpers for job handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.application.checkpoints import make_checkpoint_step_builder
from gateway_backend.operations.contracts import OperationRecord, StepRecord


class ArtifactProtectionTransaction(Protocol):
    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool: ...


def pinned_checkpoint_builder(
    *,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    owner_kind: str,
    intent: str,
    active_transaction: Callable[[], ArtifactProtectionTransaction | None],
    transaction_missing: Callable[[], Exception],
    deduplicate_refs: bool = True,
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    inner = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        candidate = inner(operation, step, transaction_now)
        transaction = active_transaction()
        if transaction is None:
            raise transaction_missing()
        refs = (checkpoint_ref, *extra_refs)
        if deduplicate_refs:
            refs = unique_artifact_refs(refs)
        transaction.set_artifact_protection(
            refs,
            owner_kind=owner_kind,
            owner_id=step.step_id,
            intent=intent,
        )
        return candidate

    return builder


def unique_artifact_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    unique: list[ArtifactRef] = []
    for ref in refs:
        if ref.artifact_id in seen:
            continue
        seen.add(ref.artifact_id)
        unique.append(ref)
    return tuple(unique)


def successor_step_id(
    operation_id: str,
    step_name: str,
    suffix_by_step: Mapping[str, str],
) -> str:
    try:
        suffix = suffix_by_step[step_name]
    except KeyError:
        raise ValueError(f"unknown step_name: {step_name}") from None
    return f"{operation_id}-step-{suffix}"


__all__ = ["pinned_checkpoint_builder", "successor_step_id", "unique_artifact_refs"]
