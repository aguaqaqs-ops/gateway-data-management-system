"""Public repository identity value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Self

from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

_UUID_V7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_REF_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_PRINTABLE_ASCII_PATTERN = re.compile(r"^[\x21-\x7E]+$")

OPAQUE_MAX_BYTES = 1024
CURSOR_MIN_BYTES = 1
CURSOR_MAX_BYTES = 8192
REF_NAME_MAX_BYTES = 255
REF_SEGMENT_MAX_BYTES = 63


def _require_string(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must be string",
        )
    return value


def _validate_uuid_v7(value: object, *, label: str) -> str:
    wire = _require_string(value, label=label)
    if wire != wire.strip() or " " in wire:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must not contain whitespace",
        )
    if not _UUID_V7_PATTERN.fullmatch(wire):
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must be canonical lowercase UUIDv7",
        )
    return wire


def _require_printable_ascii(wire: str, *, label: str) -> None:
    if not _PRINTABLE_ASCII_PATTERN.fullmatch(wire):
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must be printable ASCII",
        )


def _validate_opaque(value: object, *, label: str, max_bytes: int = OPAQUE_MAX_BYTES) -> str:
    wire = _require_string(value, label=label)
    try:
        wire.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must be ASCII",
        ) from exc
    _require_printable_ascii(wire, label=label)
    encoded = wire.encode("ascii")
    if not encoded:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} must be non-empty",
        )
    if len(encoded) > max_bytes:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            f"{label} exceeds maximum length",
        )
    return wire


@dataclass(frozen=True, slots=True, eq=False)
class _IdentityBase:
    value: str

    def to_wire(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and self.value == other.value

    def __hash__(self) -> int:
        return hash((type(self), self.value))


@dataclass(frozen=True, slots=True, eq=False)
class RepositoryId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_uuid_v7(self.value, label="RepositoryId"))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_uuid_v7(value, label="RepositoryId"))


@dataclass(frozen=True, slots=True, eq=False)
class RepositoryOperationId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", _validate_uuid_v7(self.value, label="RepositoryOperationId")
        )

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_uuid_v7(value, label="RepositoryOperationId"))


@dataclass(frozen=True, slots=True, eq=False)
class ArtifactId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_uuid_v7(self.value, label="ArtifactId"))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_uuid_v7(value, label="ArtifactId"))


@dataclass(frozen=True, slots=True, eq=False)
class CallerIdentity(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_uuid_v7(self.value, label="CallerIdentity"))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_uuid_v7(value, label="CallerIdentity"))


@dataclass(frozen=True, slots=True, eq=False)
class RepositoryIncarnationId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", _validate_opaque(self.value, label="RepositoryIncarnationId")
        )

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_opaque(value, label="RepositoryIncarnationId"))


@dataclass(frozen=True, slots=True, eq=False)
class CommitId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_opaque(self.value, label="CommitId"))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_opaque(value, label="CommitId"))


@dataclass(frozen=True, slots=True, eq=False)
class IdempotencyKey(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_opaque(self.value, label="IdempotencyKey"))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_opaque(value, label="IdempotencyKey"))


@dataclass(frozen=True, slots=True, eq=False)
class CurrentTableGenerationId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", _validate_opaque(self.value, label="CurrentTableGenerationId")
        )

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_opaque(value, label="CurrentTableGenerationId"))


@dataclass(frozen=True, slots=True, eq=False)
class CurrentCatalogGenerationId(_IdentityBase):
    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", _validate_opaque(self.value, label="CurrentCatalogGenerationId")
        )

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_opaque(value, label="CurrentCatalogGenerationId"))


@dataclass(frozen=True, slots=True, eq=False)
class CursorToken(_IdentityBase):
    def __post_init__(self) -> None:
        wire = _require_string(self.value, label="CursorToken")
        try:
            wire.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "CursorToken must be ASCII",
            ) from exc
        _require_printable_ascii(wire, label="CursorToken")
        encoded = wire.encode("ascii")
        if len(encoded) < CURSOR_MIN_BYTES or len(encoded) > CURSOR_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "CursorToken length out of bounds",
            )
        object.__setattr__(self, "value", wire)

    @classmethod
    def from_wire(cls, value: object) -> Self:
        wire = _require_string(value, label="CursorToken")
        try:
            wire.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "CursorToken must be ASCII",
            ) from exc
        _require_printable_ascii(wire, label="CursorToken")
        encoded = wire.encode("ascii")
        if len(encoded) < CURSOR_MIN_BYTES or len(encoded) > CURSOR_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "CursorToken length out of bounds",
            )
        return cls(wire)


@dataclass(frozen=True, slots=True, eq=False)
class RefName(_IdentityBase):
    _RESERVED_SEGMENT_PREFIX: ClassVar[str] = "_"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _validate_ref_name_wire(self.value))

    @classmethod
    def from_wire(cls, value: object) -> Self:
        return cls(_validate_ref_name_wire(_require_string(value, label="RefName")))


def _validate_ref_name_wire(wire: str) -> str:
    if not wire:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            "RefName must be non-empty",
        )
    if wire.startswith("/") or wire.endswith("/") or "//" in wire:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            "RefName must not have empty segment",
        )
    try:
        wire.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            "RefName must be ASCII",
        ) from exc
    if len(wire.encode("ascii")) > REF_NAME_MAX_BYTES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.IDENTITY_INVALID,
            "RefName exceeds maximum length",
        )
    segments = wire.split("/")
    for segment in segments:
        if not segment:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName must not have empty segment",
            )
        if segment in {".", ".."}:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName segment is forbidden",
            )
        if "\\" in segment:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName must not contain backslash",
            )
        if any(ord(char) < 32 for char in segment):
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName must not contain control characters",
            )
        if len(segment.encode("ascii")) > REF_SEGMENT_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName segment exceeds maximum length",
            )
        if not _REF_SEGMENT_PATTERN.fullmatch(segment):
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName segment has invalid characters",
            )
        if segment.startswith(RefName._RESERVED_SEGMENT_PREFIX):
            raise RepositoryContractError(
                RepositoryContractErrorCode.IDENTITY_INVALID,
                "RefName uses reserved internal namespace",
            )
    return wire
