from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ...core import DiagnosticRecord
from ..flow_journey.models import FlowJourneyBenchmarkSummary
from ..history_compare.models import HistoryCompareBenchmarkSummary
from ..repository_import import RepositoryImportBenchmarkMachineProfile


class JourneyHistoryCompareSuiteStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _payload_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, set):
        return [_payload_value(item) for item in sorted(value, key=str)]
    if isinstance(value, StrEnum):
        return value.value
    return value


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
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer or None")
    return value


def _optional_summary(
    value: object,
    *,
    field_name: str,
) -> FlowJourneyBenchmarkSummary | HistoryCompareBenchmarkSummary | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping or None")
    if field_name == "flow_journey_summary":
        return FlowJourneyBenchmarkSummary.from_payload(value)
    if field_name == "history_compare_summary":
        return HistoryCompareBenchmarkSummary.from_payload(value)
    raise AssertionError(f"unsupported summary field: {field_name}")


@dataclass(frozen=True, slots=True)
class JourneyHistoryCompareSuiteSummary:
    run_id: str
    created_at: datetime
    machine_profile: RepositoryImportBenchmarkMachineProfile
    dataset_ids: tuple[str, ...]
    execution_order: tuple[str, ...]
    status: JourneyHistoryCompareSuiteStatus | str
    flow_journey_summary: FlowJourneyBenchmarkSummary | None = None
    history_compare_summary: HistoryCompareBenchmarkSummary | None = None
    journey_duration_ms: int | None = None
    history_compare_duration_ms: int | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(self.machine_profile, RepositoryImportBenchmarkMachineProfile):
            raise TypeError("machine_profile must be a RepositoryImportBenchmarkMachineProfile")
        if not isinstance(self.dataset_ids, tuple):
            object.__setattr__(self, "dataset_ids", tuple(self.dataset_ids))
        normalized_dataset_ids: list[str] = []
        seen_dataset_ids: set[str] = set()
        for dataset_id in self.dataset_ids:
            if not isinstance(dataset_id, str) or not dataset_id:
                raise ValueError("dataset_ids must contain non-empty strings")
            if dataset_id in seen_dataset_ids:
                continue
            seen_dataset_ids.add(dataset_id)
            normalized_dataset_ids.append(dataset_id)
        object.__setattr__(self, "dataset_ids", tuple(normalized_dataset_ids))
        if not isinstance(self.execution_order, tuple):
            object.__setattr__(self, "execution_order", tuple(self.execution_order))
        normalized_execution_order: list[str] = []
        for step in self.execution_order:
            if not isinstance(step, str) or not step:
                raise ValueError("execution_order must contain non-empty strings")
            normalized_execution_order.append(step)
        object.__setattr__(self, "execution_order", tuple(normalized_execution_order))
        object.__setattr__(self, "status", JourneyHistoryCompareSuiteStatus(self.status))
        if self.flow_journey_summary is not None and not isinstance(
            self.flow_journey_summary,
            FlowJourneyBenchmarkSummary,
        ):
            raise TypeError("flow_journey_summary must be a FlowJourneyBenchmarkSummary or None")
        if self.history_compare_summary is not None and not isinstance(
            self.history_compare_summary,
            HistoryCompareBenchmarkSummary,
        ):
            raise TypeError("history_compare_summary must be a HistoryCompareBenchmarkSummary or None")
        for field_name in ("journey_duration_ms", "history_compare_duration_ms"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.failure_stage is not None and (
            not isinstance(self.failure_stage, str) or not self.failure_stage
        ):
            raise ValueError("failure_stage must be a non-empty string or None")
        if self.failure_reason is not None and (
            not isinstance(self.failure_reason, str) or not self.failure_reason
        ):
            raise ValueError("failure_reason must be a non-empty string or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    @property
    def total_duration_ms(self) -> int:
        return sum(
            value
            for value in (self.journey_duration_ms, self.history_compare_duration_ms)
            if value is not None
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "machine_profile": self.machine_profile.to_payload(),
            "dataset_ids": list(self.dataset_ids),
            "execution_order": list(self.execution_order),
            "status": self.status.value,
            "flow_journey_summary": _payload_value(self.flow_journey_summary),
            "history_compare_summary": _payload_value(self.history_compare_summary),
            "journey_duration_ms": self.journey_duration_ms,
            "history_compare_duration_ms": self.history_compare_duration_ms,
            "total_duration_ms": self.total_duration_ms,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "JourneyHistoryCompareSuiteSummary":
        dataset_ids_payload = payload.get("dataset_ids", [])
        if dataset_ids_payload is None:
            dataset_ids_payload = []
        if not isinstance(dataset_ids_payload, Sequence):
            raise TypeError("dataset_ids payload must be a sequence")
        execution_order_payload = payload.get("execution_order", [])
        if execution_order_payload is None:
            execution_order_payload = []
        if not isinstance(execution_order_payload, Sequence):
            raise TypeError("execution_order payload must be a sequence")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, Sequence):
            raise TypeError("diagnostics payload must be a sequence")
        return cls(
            run_id=_required_str(payload, "run_id"),
            created_at=datetime.fromisoformat(_required_str(payload, "created_at")),
            machine_profile=RepositoryImportBenchmarkMachineProfile.from_payload(
                payload.get("machine_profile", {})
            ),
            dataset_ids=tuple(str(item) for item in dataset_ids_payload),
            execution_order=tuple(str(item) for item in execution_order_payload),
            status=_required_str(payload, "status"),
            flow_journey_summary=_optional_summary(
                payload.get("flow_journey_summary"),
                field_name="flow_journey_summary",
            ),
            history_compare_summary=_optional_summary(
                payload.get("history_compare_summary"),
                field_name="history_compare_summary",
            ),
            journey_duration_ms=_optional_int(
                payload.get("journey_duration_ms"),
                field_name="journey_duration_ms",
            ),
            history_compare_duration_ms=_optional_int(
                payload.get("history_compare_duration_ms"),
                field_name="history_compare_duration_ms",
            ),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                for diagnostic in diagnostics_payload
            ),
        )
