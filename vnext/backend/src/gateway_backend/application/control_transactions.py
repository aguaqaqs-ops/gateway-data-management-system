"""Shared control-database session protocols for HTTP and application layers."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.store import OperationStore


class ReadOnlySubmissionReader(Protocol):
    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None: ...

    def get_submission(self, submission_id: str) -> Submission | None: ...


class ControlDbSession(Protocol):
    @property
    def operations(self) -> OperationStore: ...

    @property
    def submission(self) -> ReadOnlySubmissionReader: ...


ControlDbUnitOfWorkFactory = Callable[[], AbstractContextManager[ControlDbSession]]


class ReadOnlyOperationReader(Protocol):
    def get_operation(self, operation_id: str) -> OperationRecord: ...

    def get_step(self, step_id: str) -> StepRecord: ...
