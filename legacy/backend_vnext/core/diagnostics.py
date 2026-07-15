from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeAlias


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("diagnostic details keys must be strings")
        normalized[key] = value
    return normalized


@dataclass(frozen=True, slots=True)
class DiagnosticRecord:
    code: str
    message: str
    phase: str | None = None
    severity: str = "INFO"
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("diagnostic code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("diagnostic message must be a non-empty string")
        if self.phase is not None and not isinstance(self.phase, str):
            raise TypeError("diagnostic phase must be a string or None")
        if not isinstance(self.severity, str) or not self.severity:
            raise ValueError("diagnostic severity must be a non-empty string")
        object.__setattr__(self, "details", _mapping_payload(self.details))

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "phase": self.phase,
            "severity": self.severity,
            "details": _mapping_payload(self.details),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "DiagnosticRecord":
        severity_value = payload.get("severity", "INFO")
        if severity_value is None:
            severity_value = "INFO"
        return cls(
            code=_required_str(payload, "code"),
            message=_required_str(payload, "message"),
            phase=_optional_str(payload.get("phase"), field_name="phase"),
            severity=_required_str(
                {"severity": severity_value},
                "severity",
            ),
            details=_mapping_payload(_mapping_value(payload, "details")),
        )


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)
    retryable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("error code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("error message must be a non-empty string")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a bool")
        object.__setattr__(self, "details", _mapping_payload(self.details))

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": _mapping_payload(self.details),
            "retryable": self.retryable,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ErrorRecord":
        retryable_value = payload.get("retryable", False)
        if retryable_value is None:
            retryable_value = False
        if not isinstance(retryable_value, bool):
            raise TypeError("retryable must be a bool")
        return cls(
            code=_required_str(payload, "code"),
            message=_required_str(payload, "message"),
            details=_mapping_payload(_mapping_value(payload, "details")),
            retryable=retryable_value,
        )


def _mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return value


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None")
    return value


Diagnostics: TypeAlias = tuple[DiagnosticRecord, ...]
Error: TypeAlias = ErrorRecord
