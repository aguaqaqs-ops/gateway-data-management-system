from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..core.digests import DigestRef
from .models import ArchiveCandidateRecord, WorkspaceArchiveConfirmationRecord


class ArchiveExecuteCommandProtocol(Protocol):
    batch_id: str
    expected_base_main_hash: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    workspace_confirmation_set_hash: str
    candidate_set_hash: str
    override_reason: str | None


def normalize_candidate_ids(candidate_ids: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate_id in candidate_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        normalized.append(candidate_id)
    return tuple(normalized)


def compute_workspace_confirmation_set_hash(
    confirmations: tuple[WorkspaceArchiveConfirmationRecord, ...],
) -> str:
    payload = [
        {
            "confirmation_id": confirmation.confirmation_id,
            "batch_id": confirmation.batch_id,
            "workspace_id": confirmation.workspace_id,
            "status": confirmation.status.value,
            "archive_candidate_id": confirmation.archive_candidate_id,
            "reason": confirmation.reason,
        }
        for confirmation in confirmations
    ]
    return DigestRef.from_payload(payload).hex_digest


def compute_candidate_set_hash(candidates: Sequence[ArchiveCandidateRecord]) -> str:
    payload = [
        {
            "candidate_id": candidate.candidate_id,
            "batch_id": candidate.batch_id,
            "workspace_id": candidate.workspace_id,
            "source_kind": candidate.source_kind.value,
            "role": candidate.role.value,
            "status": candidate.status.value,
            "source_submission_id": candidate.source_submission_id,
            "override_reason": candidate.override_reason,
            "selected_for_archive": candidate.selected_for_archive,
        }
        for candidate in sorted(candidates, key=lambda item: item.candidate_id)
    ]
    return DigestRef.from_payload(payload).hex_digest


def compute_command_payload_hash(command: ArchiveExecuteCommandProtocol) -> str:
    return DigestRef.from_payload(
        {
            "batch_id": command.batch_id,
            "expected_base_main_hash": command.expected_base_main_hash,
            "selected_modified_candidate_id": command.selected_modified_candidate_id,
            "selected_initial_candidate_ids": list(command.selected_initial_candidate_ids),
            "workspace_confirmation_set_hash": command.workspace_confirmation_set_hash,
            "candidate_set_hash": command.candidate_set_hash,
            "override_reason": command.override_reason,
        }
    ).hex_digest
