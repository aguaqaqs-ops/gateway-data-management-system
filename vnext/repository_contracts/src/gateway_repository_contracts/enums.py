"""Closed cross-capability base enumerations for repository contracts."""

from __future__ import annotations

from enum import StrEnum

from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode


class FailureCategory(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    STATE_CONFLICT = "STATE_CONFLICT"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class RecoveryAction(StrEnum):
    RETRY_COMMAND = "RETRY_COMMAND"
    RETRY_SAME_OPERATION = "RETRY_SAME_OPERATION"
    RECONCILE_SAME_OPERATION = "RECONCILE_SAME_OPERATION"
    NEW_USER_INPUT = "NEW_USER_INPUT"
    OPERATOR_INTERVENTION = "OPERATOR_INTERVENTION"
    NO_RETRY = "NO_RETRY"


class EffectClassification(StrEnum):
    NOT_APPLIED = "NOT_APPLIED"
    UNKNOWN = "UNKNOWN"
    APPLIED = "APPLIED"
    NONE = "NONE"


class StreamFrameFamily(StrEnum):
    STREAM_HEADER = "STREAM_HEADER"
    ARROW_BATCH = "ARROW_BATCH"
    CHECKPOINT = "CHECKPOINT"
    STREAM_END = "STREAM_END"
    STREAM_ERROR = "STREAM_ERROR"


class StoreKind(StrEnum):
    VERSIONED = "VERSIONED"
    CURRENT = "CURRENT"


FAILURE_CATEGORIES: frozenset[FailureCategory] = frozenset(FailureCategory)
RECOVERY_ACTIONS: frozenset[RecoveryAction] = frozenset(RecoveryAction)
EFFECT_CLASSIFICATIONS: frozenset[EffectClassification] = frozenset(EffectClassification)
STREAM_FRAME_FAMILIES: frozenset[StreamFrameFamily] = frozenset(StreamFrameFamily)


def parse_failure_category(value: object) -> FailureCategory:
    return _parse_enum(value, FailureCategory, label="category")


def parse_recovery_action(value: object) -> RecoveryAction:
    return _parse_enum(value, RecoveryAction, label="recovery")


def parse_effect_classification(value: object) -> EffectClassification:
    return _parse_enum(value, EffectClassification, label="effect")


def parse_stream_frame_family(value: object) -> StreamFrameFamily:
    return _parse_enum(value, StreamFrameFamily, label="frame_family")


def parse_store_kind(value: object) -> StoreKind:
    return _parse_enum(value, StoreKind, label="store_kind")


def _parse_enum[T: StrEnum](value: object, enum_type: type[T], *, label: str) -> T:
    if type(value) is not str:
        raise RepositoryContractError(
            RepositoryContractErrorCode.ENUM_UNKNOWN,
            f"{label} must be string",
        )
    try:
        return enum_type(value)
    except ValueError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.ENUM_UNKNOWN,
            f"unknown {label}",
        ) from exc
