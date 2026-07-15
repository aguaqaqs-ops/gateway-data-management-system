from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from .versions import BUSINESS_PROJECTION_CONTRACT_VERSION


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _normalize_rows(rows: tuple[Mapping[str, object], ...]) -> tuple[Mapping[str, object], ...]:
    normalized: list[Mapping[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("rows must contain mappings")
        normalized.append(_mapping_payload(row))
    return tuple(normalized)


def _normalize_str_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, tuple):
        values = tuple(values)
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError("tuple values must be non-empty strings")
        normalized.append(canonical_identifier(value))
    return tuple(normalized)


class BusinessProjectionKind(StrEnum):
    FORWARD_CHANNELS = "FORWARD_CHANNELS"
    SECONDARY_DEVICES = "SECONDARY_DEVICES"
    COMMUNICATION_PROTOCOLS = "COMMUNICATION_PROTOCOLS"
    GLOBAL_PARAMETERS = "GLOBAL_PARAMETERS"
    UNPARSED_TABLES = "UNPARSED_TABLES"


@dataclass(frozen=True, slots=True)
class BusinessProjectionTable:
    table_name: str
    columns: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    display_name: str | None = None
    rows_loaded: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "columns", _normalize_str_tuple(self.columns))
        object.__setattr__(self, "rows", _normalize_rows(tuple(self.rows)))
        if self.display_name is not None and not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string or None")
        if not isinstance(self.rows_loaded, bool):
            raise TypeError("rows_loaded must be a bool")

    @property
    def table_id(self) -> str:
        return self.table_name


@dataclass(frozen=True, slots=True)
class BusinessProjectionInput:
    before_tables: tuple[BusinessProjectionTable, ...] = field(default_factory=tuple)
    current_tables: tuple[BusinessProjectionTable, ...] = field(default_factory=tuple)
    surface_table_names: tuple[str, ...] = field(default_factory=tuple)
    projection_contract_version: str = BUSINESS_PROJECTION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.projection_contract_version, str) or not self.projection_contract_version:
            raise ValueError("projection_contract_version must be a non-empty string")
        object.__setattr__(self, "before_tables", tuple(self.before_tables))
        object.__setattr__(self, "current_tables", tuple(self.current_tables))
        for field_name in ("before_tables", "current_tables"):
            for table in getattr(self, field_name):
                if not isinstance(table, BusinessProjectionTable):
                    raise TypeError(f"{field_name} must contain BusinessProjectionTable values")
        object.__setattr__(self, "surface_table_names", _normalize_str_tuple(self.surface_table_names))


@dataclass(frozen=True, slots=True)
class BusinessProjectionArtifact:
    projection_kind: BusinessProjectionKind | str
    projection_id: str
    payload: Mapping[str, object]
    projection_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_kind", BusinessProjectionKind(self.projection_kind))
        if not isinstance(self.projection_id, str) or not self.projection_id:
            raise ValueError("projection_id must be a non-empty string")
        object.__setattr__(self, "payload", _mapping_payload(self.payload))
        if self.projection_digest is None:
            object.__setattr__(self, "projection_digest", DigestRef.from_payload(self.payload))
        elif not isinstance(self.projection_digest, DigestRef):
            object.__setattr__(self, "projection_digest", DigestRef.parse(str(self.projection_digest)))

    def to_payload(self) -> dict[str, object]:
        return {
            "projection_kind": self.projection_kind.value,
            "projection_id": self.projection_id,
            "projection_digest": self.projection_digest.to_payload(),
            "payload": _mapping_payload(self.payload),
        }


@dataclass(frozen=True, slots=True)
class BusinessProjectionResult:
    projections: tuple[BusinessProjectionArtifact, ...]
    consumed_table_names: tuple[str, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    summary: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "projections", tuple(self.projections))
        for projection in self.projections:
            if not isinstance(projection, BusinessProjectionArtifact):
                raise TypeError("projections must contain BusinessProjectionArtifact values")
        object.__setattr__(self, "consumed_table_names", _normalize_str_tuple(self.consumed_table_names))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
        object.__setattr__(self, "summary", _mapping_payload(self.summary))

    def projection_for_kind(self, kind: BusinessProjectionKind | str) -> BusinessProjectionArtifact:
        projection_kind = BusinessProjectionKind(kind)
        for projection in self.projections:
            if projection.projection_kind is projection_kind:
                return projection
        raise KeyError(projection_kind.value)


__all__ = [
    "BusinessProjectionArtifact",
    "BusinessProjectionInput",
    "BusinessProjectionKind",
    "BusinessProjectionResult",
    "BusinessProjectionTable",
]
