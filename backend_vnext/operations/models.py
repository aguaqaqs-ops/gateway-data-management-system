from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from ..core.digests import DigestRef, canonical_json_bytes
from ..core.diagnostics import DiagnosticRecord
from ..core.results import ResultRecord


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = _payload_value(value)
    return normalized


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Mapping):
        return _mapping_payload(value)
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return value


def _optional_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be an ISO 8601 string or None")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer or None")
    return value


def _optional_bool(value: object, *, field_name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool or None")
    return value


class OperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    READY = "READY"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class OperationStepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


class OperationKind(StrEnum):
    UPLOAD_PREVIEW = "UPLOAD_PREVIEW"
    PREVIEW_CACHE_COMPLETION = "PREVIEW_CACHE_COMPLETION"
    PRECOMMIT_WARMUP = "PRECOMMIT_WARMUP"
    SUBMISSION_REVIEW = "SUBMISSION_REVIEW"
    SUBMIT_FINALIZE = "SUBMIT_FINALIZE"
    HISTORY_COMPARE = "HISTORY_COMPARE"
    ARCHIVE_PROMOTE = "ARCHIVE_PROMOTE"


class OperationCallerType(StrEnum):
    DIRECT_RESPONSE_CALLER = "DIRECT_RESPONSE_CALLER"
    READ_ONLY_CALLER = "READ_ONLY_CALLER"
    WARMUP_CALLER = "WARMUP_CALLER"
    FINALIZE_WRITE_CALLER = "FINALIZE_WRITE_CALLER"


class OperationParallelPolicy(StrEnum):
    SERIAL = "SERIAL"
    FIXED_DUAL_SLOT = "FIXED_DUAL_SLOT"


@dataclass(frozen=True, slots=True)
class OperationStepPlan:
    step_name: str
    retryable: bool = False
    allow_parallel: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.step_name, str) or not self.step_name:
            raise ValueError("step_name must be a non-empty string")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a bool")
        if not isinstance(self.allow_parallel, bool):
            raise TypeError("allow_parallel must be a bool")

    def to_payload(self) -> dict[str, object]:
        return {
            "step_name": self.step_name,
            "retryable": self.retryable,
            "allow_parallel": self.allow_parallel,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "OperationStepPlan":
        return cls(
            step_name=_required_str(payload, "step_name"),
            retryable=_optional_bool(payload.get("retryable"), field_name="retryable"),
            allow_parallel=_optional_bool(
                payload.get("allow_parallel"),
                field_name="allow_parallel",
            ),
        )


@dataclass(frozen=True, slots=True)
class OperationStepRecord:
    step_sequence: int
    step_name: str
    status: OperationStepStatus | str
    retryable: bool = False
    allow_parallel: bool = False
    worker_id: str | None = None
    claim_token: str | None = None
    lease_expires_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: ResultRecord | None = None
    failure_summary: str | None = None
    ready_closure_digest: DigestRef | str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.step_sequence, int)
            or isinstance(self.step_sequence, bool)
            or self.step_sequence < 0
        ):
            raise ValueError("step_sequence must be a non-negative integer")
        if not isinstance(self.step_name, str) or not self.step_name:
            raise ValueError("step_name must be a non-empty string")
        object.__setattr__(self, "status", OperationStepStatus(self.status))
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a bool")
        if not isinstance(self.allow_parallel, bool):
            raise TypeError("allow_parallel must be a bool")
        for field_name in ("worker_id", "claim_token", "failure_summary"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in ("lease_expires_at", "started_at", "finished_at"):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, datetime):
                    raise TypeError(f"{field_name} must be a datetime or None")
                if value.tzinfo is None:
                    raise ValueError(f"{field_name} must be timezone-aware")
        if self.result is not None and not isinstance(self.result, ResultRecord):
            raise TypeError("result must be a ResultRecord or None")
        object.__setattr__(self, "ready_closure_digest", _optional_digest(self.ready_closure_digest))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")

    def to_payload(self) -> dict[str, object]:
        return {
            "step_sequence": self.step_sequence,
            "step_name": self.step_name,
            "status": self.status.value,
            "retryable": self.retryable,
            "allow_parallel": self.allow_parallel,
            "worker_id": self.worker_id,
            "claim_token": self.claim_token,
            "lease_expires_at": _payload_value(self.lease_expires_at),
            "started_at": _payload_value(self.started_at),
            "finished_at": _payload_value(self.finished_at),
            "result": None if self.result is None else self.result.to_payload(),
            "failure_summary": self.failure_summary,
            "ready_closure_digest": (
                None
                if self.ready_closure_digest is None
                else self.ready_closure_digest.to_payload()
            ),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "OperationStepRecord":
        result_payload = payload.get("result")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("diagnostics payload must be a list")
        if result_payload is not None and not isinstance(result_payload, Mapping):
            raise TypeError("result payload must be a mapping or null")
        return cls(
            step_sequence=_required_non_negative_int(payload, "step_sequence"),
            step_name=_required_str(payload, "step_name"),
            status=_required_str(payload, "status"),
            retryable=_optional_bool(payload.get("retryable"), field_name="retryable"),
            allow_parallel=_optional_bool(
                payload.get("allow_parallel"),
                field_name="allow_parallel",
            ),
            worker_id=_optional_str(payload.get("worker_id"), field_name="worker_id"),
            claim_token=_optional_str(payload.get("claim_token"), field_name="claim_token"),
            lease_expires_at=_optional_datetime(
                payload.get("lease_expires_at"),
                field_name="lease_expires_at",
            ),
            started_at=_optional_datetime(payload.get("started_at"), field_name="started_at"),
            finished_at=_optional_datetime(payload.get("finished_at"), field_name="finished_at"),
            result=(
                None
                if result_payload is None
                else ResultRecord.from_payload(result_payload)
            ),
            failure_summary=_optional_str(
                payload.get("failure_summary"),
                field_name="failure_summary",
            ),
            ready_closure_digest=_optional_digest(payload.get("ready_closure_digest")),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item) for item in diagnostics_payload
            ),
        )


@dataclass(frozen=True, slots=True)
class OperationPlan:
    operation_kind: OperationKind | str
    caller_type: OperationCallerType | str
    steps: tuple[OperationStepPlan, ...] = field(default_factory=tuple)
    request_payload: Mapping[str, object] = field(default_factory=dict)
    parallel_policy: OperationParallelPolicy | str = OperationParallelPolicy.SERIAL
    ready_closure_required: bool = True
    generation: str | None = None
    retry_of: str | None = None
    superseded_by: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_kind", OperationKind(self.operation_kind))
        object.__setattr__(self, "caller_type", OperationCallerType(self.caller_type))
        object.__setattr__(self, "parallel_policy", OperationParallelPolicy(self.parallel_policy))
        if not isinstance(self.ready_closure_required, bool):
            raise TypeError("ready_closure_required must be a bool")
        for field_name in ("generation", "retry_of", "superseded_by"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if not isinstance(self.request_payload, Mapping):
            raise TypeError("request_payload must be a mapping")
        object.__setattr__(self, "request_payload", _mapping_payload(self.request_payload))
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))
        normalized_steps: list[OperationStepPlan] = []
        for step in self.steps:
            if not isinstance(step, OperationStepPlan):
                raise TypeError("steps must contain OperationStepPlan values")
            normalized_steps.append(step)
        object.__setattr__(self, "steps", tuple(normalized_steps))
        if not self.steps:
            raise ValueError("steps must contain at least one step")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")

    def to_payload(self) -> dict[str, object]:
        return {
            "operation_kind": self.operation_kind.value,
            "caller_type": self.caller_type.value,
            "steps": [step.to_payload() for step in self.steps],
            "request_payload": _mapping_payload(self.request_payload),
            "parallel_policy": self.parallel_policy.value,
            "ready_closure_required": self.ready_closure_required,
            "generation": self.generation,
            "retry_of": self.retry_of,
            "superseded_by": self.superseded_by,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    def request_digest(self) -> DigestRef:
        return DigestRef.from_payload(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "OperationPlan":
        steps_payload = payload.get("steps", [])
        diagnostics_payload = payload.get("diagnostics", [])
        if steps_payload is None:
            steps_payload = []
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(steps_payload, list):
            raise TypeError("steps payload must be a list")
        if not isinstance(diagnostics_payload, list):
            raise TypeError("diagnostics payload must be a list")
        return cls(
            operation_kind=_required_str(payload, "operation_kind"),
            caller_type=_required_str(payload, "caller_type"),
            steps=tuple(OperationStepPlan.from_payload(item) for item in steps_payload),
            request_payload=_mapping_payload(_mapping_value(payload, "request_payload")),
            parallel_policy=_required_str(payload, "parallel_policy"),
            ready_closure_required=_optional_bool(
                payload.get("ready_closure_required"),
                field_name="ready_closure_required",
                default=True,
            ),
            generation=_optional_str(payload.get("generation"), field_name="generation"),
            retry_of=_optional_str(payload.get("retry_of"), field_name="retry_of"),
            superseded_by=_optional_str(payload.get("superseded_by"), field_name="superseded_by"),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item) for item in diagnostics_payload
            ),
        )


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    operation_kind: OperationKind | str
    caller_type: OperationCallerType | str
    status: OperationStatus | str
    steps: tuple[OperationStepRecord, ...] = field(default_factory=tuple)
    parallel_policy: OperationParallelPolicy | str = OperationParallelPolicy.SERIAL
    request_payload: Mapping[str, object] = field(default_factory=dict)
    request_digest: DigestRef | str | None = None
    operation_contract_version: str = "backend-vnext/operation/v1"
    generation: str | None = None
    retry_of: str | None = None
    superseded_by: str | None = None
    worker_id: str | None = None
    claim_token: str | None = None
    lease_expires_at: datetime | None = None
    failure_summary: str | None = None
    ready_closure_digest: DigestRef | str | None = None
    result: ResultRecord | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("operation_id must be a non-empty string")
        object.__setattr__(self, "operation_kind", OperationKind(self.operation_kind))
        object.__setattr__(self, "caller_type", OperationCallerType(self.caller_type))
        object.__setattr__(self, "status", OperationStatus(self.status))
        object.__setattr__(self, "parallel_policy", OperationParallelPolicy(self.parallel_policy))
        if not isinstance(self.operation_contract_version, str) or not self.operation_contract_version:
            raise ValueError("operation_contract_version must be a non-empty string")
        if not isinstance(self.request_payload, Mapping):
            raise TypeError("request_payload must be a mapping")
        object.__setattr__(self, "request_payload", _mapping_payload(self.request_payload))
        if self.request_digest is None:
            object.__setattr__(
                self,
                "request_digest",
                DigestRef.from_payload(self.request_payload),
            )
        else:
            object.__setattr__(self, "request_digest", _optional_digest(self.request_digest))
        for field_name in ("generation", "retry_of", "superseded_by", "worker_id", "claim_token", "failure_summary"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.lease_expires_at is not None:
            if not isinstance(self.lease_expires_at, datetime):
                raise TypeError("lease_expires_at must be a datetime or None")
            if self.lease_expires_at.tzinfo is None:
                raise ValueError("lease_expires_at must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if self.result is not None and not isinstance(self.result, ResultRecord):
            raise TypeError("result must be a ResultRecord or None")
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))
        normalized_steps: list[OperationStepRecord] = []
        seen_sequences: set[int] = set()
        for step in self.steps:
            if not isinstance(step, OperationStepRecord):
                raise TypeError("steps must contain OperationStepRecord values")
            if step.step_sequence in seen_sequences:
                raise ValueError("step sequences must be unique")
            seen_sequences.add(step.step_sequence)
            normalized_steps.append(step)
        normalized_steps.sort(key=lambda item: item.step_sequence)
        if normalized_steps and [step.step_sequence for step in normalized_steps] != list(range(len(normalized_steps))):
            raise ValueError("step sequences must be contiguous starting at zero")
        object.__setattr__(self, "steps", tuple(normalized_steps))
        object.__setattr__(self, "ready_closure_digest", _optional_digest(self.ready_closure_digest))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")

    def to_payload(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "operation_kind": self.operation_kind.value,
            "caller_type": self.caller_type.value,
            "status": self.status.value,
            "steps": [step.to_payload() for step in self.steps],
            "parallel_policy": self.parallel_policy.value,
            "request_payload": _mapping_payload(self.request_payload),
            "request_digest": self.request_digest.to_payload()
            if self.request_digest is not None
            else None,
            "operation_contract_version": self.operation_contract_version,
            "generation": self.generation,
            "retry_of": self.retry_of,
            "superseded_by": self.superseded_by,
            "worker_id": self.worker_id,
            "claim_token": self.claim_token,
            "lease_expires_at": _payload_value(self.lease_expires_at),
            "failure_summary": self.failure_summary,
            "ready_closure_digest": (
                None
                if self.ready_closure_digest is None
                else self.ready_closure_digest.to_payload()
            ),
            "result": None if self.result is None else self.result.to_payload(),
            "created_at": _payload_value(self.created_at),
            "updated_at": _payload_value(self.updated_at),
            "version": self.version,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    def payload_digest(self) -> DigestRef:
        return DigestRef.from_payload(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "OperationRecord":
        steps_payload = payload.get("steps", [])
        diagnostics_payload = payload.get("diagnostics", [])
        result_payload = payload.get("result")
        if steps_payload is None:
            steps_payload = []
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(steps_payload, list):
            raise TypeError("steps payload must be a list")
        if not isinstance(diagnostics_payload, list):
            raise TypeError("diagnostics payload must be a list")
        if result_payload is not None and not isinstance(result_payload, Mapping):
            raise TypeError("result payload must be a mapping or null")
        return cls(
            operation_id=_required_str(payload, "operation_id"),
            operation_kind=_required_str(payload, "operation_kind"),
            caller_type=_required_str(payload, "caller_type"),
            status=_required_str(payload, "status"),
            steps=tuple(OperationStepRecord.from_payload(item) for item in steps_payload),
            parallel_policy=_required_str(payload, "parallel_policy"),
            request_payload=_mapping_payload(_mapping_value(payload, "request_payload")),
            request_digest=_optional_digest(payload.get("request_digest")),
            operation_contract_version=_required_str(
                payload,
                "operation_contract_version",
            ),
            generation=_optional_str(payload.get("generation"), field_name="generation"),
            retry_of=_optional_str(payload.get("retry_of"), field_name="retry_of"),
            superseded_by=_optional_str(payload.get("superseded_by"), field_name="superseded_by"),
            worker_id=_optional_str(payload.get("worker_id"), field_name="worker_id"),
            claim_token=_optional_str(payload.get("claim_token"), field_name="claim_token"),
            lease_expires_at=_optional_datetime(
                payload.get("lease_expires_at"),
                field_name="lease_expires_at",
            ),
            failure_summary=_optional_str(
                payload.get("failure_summary"),
                field_name="failure_summary",
            ),
            ready_closure_digest=_optional_digest(payload.get("ready_closure_digest")),
            result=(
                None
                if result_payload is None
                else ResultRecord.from_payload(result_payload)
            ),
            created_at=_optional_datetime(payload.get("created_at"), field_name="created_at")
            or datetime.now(timezone.utc),
            updated_at=_optional_datetime(payload.get("updated_at"), field_name="updated_at")
            or datetime.now(timezone.utc),
            version=_required_positive_int(payload, "version"),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item) for item in diagnostics_payload
            ),
        )


def _mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return value


def _required_non_negative_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _required_positive_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TypeError(f"{field_name} must be a positive integer")
    return value
