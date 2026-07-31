"""Problem Details and FailureDescriptor contract models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from collections.abc import Mapping

from gateway_repository_contracts._json import (
    JSONValue,
    decode_wire_mapping,
    freeze_json_value,
    materialize_json_value,
    require_mapping_keys,
)
from gateway_repository_contracts.enums import (
    EffectClassification,
    FailureCategory,
    RecoveryAction,
    parse_effect_classification,
    parse_failure_category,
    parse_recovery_action,
)
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_SCHEMA_VERSION = 1
DIAGNOSTIC_REF_MAX_COUNT = 32
_FORBIDDEN_SCAN_MAX_DEPTH = 32

_FAILURE_KEYS = frozenset(
    {
        "code",
        "category",
        "phase",
        "recovery",
        "effect",
        "message",
        "details",
        "diagnostic_refs",
    }
)
_PROBLEM_KEYS = frozenset(
    {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "failure",
        "request_id",
        "wire_schema_version",
    }
)
_FAILURE_REQUIRED_KEYS = _FAILURE_KEYS - {"diagnostic_refs"}
_FORBIDDEN_SERIALIZATION_KEYS = frozenset(
    {
        "stack",
        "stacktrace",
        "traceback",
        "path",
        "host_path",
        "filesystem_path",
        "server_path",
        "dolt_command",
        "sqlite_path",
        "credential",
        "secret",
        "token",
    }
)


def _require_non_empty_string(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be non-empty string",
        )
    return value


def _require_int(value: object, *, label: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_BOOL_AS_INT
            if isinstance(value, bool)
            else RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be integer",
        )
    return value


def _require_failure_category(value: object) -> FailureCategory:
    if isinstance(value, FailureCategory):
        return value
    return parse_failure_category(value)


def _require_recovery_action(value: object) -> RecoveryAction:
    if isinstance(value, RecoveryAction):
        return value
    return parse_recovery_action(value)


def _require_effect_classification(value: object) -> EffectClassification:
    if isinstance(value, EffectClassification):
        return value
    return parse_effect_classification(value)


def _normalize_diagnostic_refs(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if type(value) is list:
        items: tuple[object, ...] | list[object] = value
    elif type(value) is tuple:
        items = value
    else:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "diagnostic_refs must be array",
        )
    refs: list[str] = []
    seen: set[str] = set()
    for item in items:
        ref = _require_non_empty_string(item, label="diagnostic_refs item")
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    refs.sort()
    if len(refs) > DIAGNOSTIC_REF_MAX_COUNT:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "diagnostic_refs exceeds maximum count",
        )
    return tuple(refs)


def _scan_forbidden_fields(value: object, *, depth: int = 0) -> None:
    if depth > _FORBIDDEN_SCAN_MAX_DEPTH:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "forbidden field scan exceeded maximum depth",
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is str and key in _FORBIDDEN_SERIALIZATION_KEYS:
                raise RepositoryContractError(
                    RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                    "forbidden field in problem payload",
                )
            _scan_forbidden_fields(item, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _scan_forbidden_fields(item, depth=depth + 1)


@dataclass(frozen=True, slots=True)
class FailureDescriptor:
    code: str
    category: FailureCategory
    phase: str
    recovery: RecoveryAction
    effect: EffectClassification
    message: str
    details: JSONValue
    diagnostic_refs: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_non_empty_string(self.code, label="code"))
        object.__setattr__(self, "category", _require_failure_category(self.category))
        object.__setattr__(self, "phase", _require_non_empty_string(self.phase, label="phase"))
        object.__setattr__(self, "recovery", _require_recovery_action(self.recovery))
        object.__setattr__(self, "effect", _require_effect_classification(self.effect))
        object.__setattr__(
            self, "message", _require_non_empty_string(self.message, label="message")
        )
        frozen_details = freeze_json_value(self.details)
        object.__setattr__(self, "details", frozen_details)
        refs = _normalize_diagnostic_refs(self.diagnostic_refs)
        object.__setattr__(self, "diagnostic_refs", refs)

    def to_wire_dict(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "code": self.code,
            "category": self.category.value,
            "phase": self.phase,
            "recovery": self.recovery.value,
            "effect": self.effect.value,
            "message": self.message,
            "details": materialize_json_value(self.details),
        }
        if self.diagnostic_refs is not None:
            payload["diagnostic_refs"] = list(self.diagnostic_refs)
        _scan_forbidden_fields(payload)
        return payload

    @classmethod
    def from_wire_dict(
        cls,
        value: object,
        *,
        ignore_unknown_fields: bool = True,
    ) -> Self:
        mapping = decode_wire_mapping(
            value,
            allowed_keys=_FAILURE_KEYS,
            label="failure",
            ignore_unknown=ignore_unknown_fields,
        )
        require_mapping_keys(mapping, _FAILURE_REQUIRED_KEYS, label="failure")
        _scan_forbidden_fields(mapping)
        return cls(
            code=_require_non_empty_string(mapping["code"], label="code"),
            category=parse_failure_category(mapping["category"]),
            phase=_require_non_empty_string(mapping["phase"], label="phase"),
            recovery=parse_recovery_action(mapping["recovery"]),
            effect=parse_effect_classification(mapping["effect"]),
            message=_require_non_empty_string(mapping["message"], label="message"),
            details=freeze_json_value(mapping["details"]),
            diagnostic_refs=_normalize_diagnostic_refs(mapping.get("diagnostic_refs")),
        )


@dataclass(frozen=True, slots=True)
class RepositoryProblemDetails:
    type: str
    title: str
    status: int
    detail: str
    instance: str
    failure: FailureDescriptor
    request_id: str
    wire_schema_version: int

    _WIRE_KEYS: ClassVar[frozenset[str]] = _PROBLEM_KEYS

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _require_non_empty_string(self.type, label="type"))
        object.__setattr__(self, "title", _require_non_empty_string(self.title, label="title"))
        object.__setattr__(self, "status", _require_int(self.status, label="status"))
        object.__setattr__(self, "detail", _require_non_empty_string(self.detail, label="detail"))
        object.__setattr__(
            self, "instance", _require_non_empty_string(self.instance, label="instance")
        )
        if not isinstance(self.failure, FailureDescriptor):
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "failure must be FailureDescriptor",
            )
        object.__setattr__(
            self, "request_id", _require_non_empty_string(self.request_id, label="request_id")
        )
        version = _require_int(self.wire_schema_version, label="wire_schema_version")
        if version != PROBLEM_SCHEMA_VERSION:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISMATCH,
                "wire_schema_version mismatch",
            )
        object.__setattr__(self, "wire_schema_version", version)

    def to_wire_dict(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "instance": self.instance,
            "failure": self.failure.to_wire_dict(),
            "request_id": self.request_id,
            "wire_schema_version": self.wire_schema_version,
        }
        _scan_forbidden_fields(payload)
        return payload

    @classmethod
    def from_wire_dict(
        cls,
        value: object,
        *,
        ignore_unknown_fields: bool = True,
    ) -> Self:
        mapping = decode_wire_mapping(
            value,
            allowed_keys=cls._WIRE_KEYS,
            label="problem",
            ignore_unknown=ignore_unknown_fields,
        )
        require_mapping_keys(mapping, cls._WIRE_KEYS, label="problem")
        _scan_forbidden_fields(mapping)
        wire_schema_version = _require_int(
            mapping["wire_schema_version"], label="wire_schema_version"
        )
        if wire_schema_version != PROBLEM_SCHEMA_VERSION:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISMATCH,
                "wire_schema_version mismatch",
            )
        return cls(
            type=_require_non_empty_string(mapping["type"], label="type"),
            title=_require_non_empty_string(mapping["title"], label="title"),
            status=_require_int(mapping["status"], label="status"),
            detail=_require_non_empty_string(mapping["detail"], label="detail"),
            instance=_require_non_empty_string(mapping["instance"], label="instance"),
            failure=FailureDescriptor.from_wire_dict(
                mapping["failure"],
                ignore_unknown_fields=ignore_unknown_fields,
            ),
            request_id=_require_non_empty_string(mapping["request_id"], label="request_id"),
            wire_schema_version=wire_schema_version,
        )

    @classmethod
    def assert_no_forbidden_fields(cls, payload: dict[str, object]) -> None:
        _scan_forbidden_fields(payload)
