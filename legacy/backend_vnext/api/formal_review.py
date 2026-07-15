from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from fastapi import status

from .formal_state_store import VNextFormalStateStore


@dataclass(frozen=True)
class FormalReviewRequest:
    submission_id: str
    actor_id: str
    action: str
    reason: str | None = None
    idempotency_key: str | None = None


class FormalReviewContractError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)


class FormalReviewService:
    def __init__(self, *, store: VNextFormalStateStore) -> None:
        self.store = store

    def apply(self, request: FormalReviewRequest) -> dict[str, object]:
        store_action = _store_action(request.action)
        before = self.store.get_submission(request.submission_id)
        if before is None:
            raise FormalReviewContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="SUBMISSION_NOT_FOUND",
                message="Submission not found.",
                details={"submission_id": request.submission_id},
            )
        try:
            submission, workspace = self.store.review_submission(
                submission_id=request.submission_id,
                actor_id=request.actor_id,
                action=store_action,
            )
        except KeyError as exc:
            raise FormalReviewContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="SUBMISSION_NOT_FOUND",
                message="Submission or workspace not found.",
                details={"submission_id": request.submission_id},
            ) from exc
        except ValueError as exc:
            raise FormalReviewContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUBMISSION_REVIEW_STATE_CONFLICT",
                message=str(exc),
                details={"submission_id": request.submission_id, "action": request.action},
            ) from exc

        now = datetime.now(timezone.utc).isoformat()
        changed = before.get("status") != submission.get("status")
        return {
            "action_id": _action_id(request),
            "action_kind": "SUBMISSION_REVIEW",
            "status": "READY",
            "ready_result": {
                "submission": submission,
                "workspace": workspace,
                "action": request.action,
                "changed": changed,
            },
            "error": None,
            "diagnostics": [],
            "submitted_at": now,
            "updated_at": now,
        }


def _store_action(action: str) -> str:
    normalized = action.strip().upper().replace("-", "_")
    mapping = {
        "START_REVIEW": "start-review",
        "APPROVE": "approve",
        "REJECT": "reject",
        "WITHDRAW": "withdraw",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise FormalReviewContractError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="Unsupported submission review action.",
            details={"action": action},
        ) from exc


def _action_id(request: FormalReviewRequest) -> str:
    if request.idempotency_key is not None and request.idempotency_key.strip() != "":
        return f"action:submission-review:{request.idempotency_key.strip()}"
    return f"action:submission-review:{uuid.uuid4().hex}"
