"""Public contracts owned by the Composite Signal capability.

Owner: Composite Signal capability
Authority: docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-handoff.md

S3 owns the EMPTY source identity marker, business AST, special-device
catalog DTO, and composite_signal_point derived rows. Downstream consumers
may import this module only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    ParserInvocationContext,
    XmlParseResult,
)

COMPOSITE_SIGNAL_CONTRACT_VERSION = 1
COMPOSITE_SIGNAL_POINT_TABLE = "composite_signal_point"
COMPOSITE_SIGNAL_POINT_KEY = ("source_table", "point_gid")
SPECIAL_DEV_ADDR = 65532
SPECIAL_DEVICE_DESCRIPTION = "复合信号虚装置"
DEVICE_TABLE = "device"
SPECIAL_POINT_TABLES = (
    "device_st",
    "device_mx",
    "device_co",
    "device_sg",
    "device_sp",
    "device_cnt",
    "device_sn",
    "device_tap",
    "device_other",
    "device_disturb",
)
EMPTY_COMPOSITE_LOGIC_MARKER_BYTES = b"gateway-vnext:composite-logic-empty:v1"
EMPTY_COMPOSITE_LOGIC_DIGEST = raw_blob_digest(EMPTY_COMPOSITE_LOGIC_MARKER_BYTES)
_UTF8 = "utf-8"


class CompositeSignalStatus(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class CompositeDiagnosticSeverity(StrEnum):
    ERROR = "ERROR"


class CompositeDiagnosticCode(StrEnum):
    XML_DOCUMENT_FAILED = "XML_DOCUMENT_FAILED"
    INVALID_ROOT = "INVALID_ROOT"
    UNKNOWN_ELEMENT = "UNKNOWN_ELEMENT"
    UNKNOWN_ATTRIBUTE = "UNKNOWN_ATTRIBUTE"
    MISSING_ATTRIBUTE = "MISSING_ATTRIBUTE"
    EMPTY_TOP_LEVEL_NAME = "EMPTY_TOP_LEVEL_NAME"
    UNEXPECTED_TEXT = "UNEXPECTED_TEXT"
    DUPLICATE_TOP_LEVEL_FORMULA = "DUPLICATE_TOP_LEVEL_FORMULA"
    DUPLICATE_SPECIAL_POINT_NAME = "DUPLICATE_SPECIAL_POINT_NAME"
    ORPHAN_FORMULA = "ORPHAN_FORMULA"
    SPECIAL_DEVICE_IDENTITY_INVALID = "SPECIAL_DEVICE_IDENTITY_INVALID"
    CATALOG_UNAVAILABLE = "CATALOG_UNAVAILABLE"
    MATERIALIZATION_CANCELLED = "MATERIALIZATION_CANCELLED"
    MATERIALIZATION_TIMEOUT = "MATERIALIZATION_TIMEOUT"


@dataclass(frozen=True, slots=True)
class CompositeLogicSource:
    empty: bool
    composite_logic_source_digest: DigestRef
    document_content_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        if self.empty:
            if self.document_content_digest is not None:
                raise ValueError("EMPTY source forbids document_content_digest")
            if self.composite_logic_source_digest != EMPTY_COMPOSITE_LOGIC_DIGEST:
                raise ValueError("EMPTY source must use the stable EMPTY digest")
            return
        if self.document_content_digest is None:
            raise ValueError("non-empty source requires document_content_digest")
        if self.composite_logic_source_digest != self.document_content_digest:
            raise ValueError("non-empty source digest must equal document_content_digest")


def empty_composite_logic_source() -> CompositeLogicSource:
    return CompositeLogicSource(
        empty=True,
        composite_logic_source_digest=EMPTY_COMPOSITE_LOGIC_DIGEST,
    )


def present_composite_logic_source(document_utf8: bytes) -> CompositeLogicSource:
    digest = raw_blob_digest(document_utf8)
    return CompositeLogicSource(
        empty=False,
        composite_logic_source_digest=digest,
        document_content_digest=digest,
    )


@dataclass(frozen=True, slots=True)
class PointNode:
    name: str


@dataclass(frozen=True, slots=True)
class DigitalNode:
    value: str


@dataclass(frozen=True, slots=True)
class ExpressNode:
    operator: str
    children: tuple[AstNode, ...]
    name: str | None = None


AstNode = ExpressNode | PointNode | DigitalNode


@dataclass(frozen=True, slots=True)
class NamedFormula:
    name: str
    ast: ExpressNode
    formula_digest: DigestRef
    formula_ast_json: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be a non-empty string")
        if not self.formula_ast_json:
            raise ValueError("formula_ast_json must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SpecialDevice:
    gid: int
    dev_addr: int
    description: str


@dataclass(frozen=True, slots=True)
class SpecialPointFact:
    source_table: str
    point_gid: int
    dev_addr: int
    point_name: str
    payload: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.source_table:
            raise ValueError("source_table must be a non-empty string")
        seen: set[str] = set()
        for name, _value in self.payload:
            if not name:
                raise ValueError("payload names must be non-empty strings")
            if name in seen:
                raise ValueError("payload names must be unique")
            seen.add(name)


@dataclass(frozen=True, slots=True)
class SpecialDeviceCatalog:
    devices: tuple[SpecialDevice, ...]
    points: tuple[SpecialPointFact, ...]
    source_device_row_count: int

    def __post_init__(self) -> None:
        if self.source_device_row_count < 0:
            raise ValueError("source_device_row_count must be a non-negative int")
        if len(self.devices) > self.source_device_row_count:
            raise ValueError("devices cannot exceed source_device_row_count")


def empty_special_device_catalog() -> SpecialDeviceCatalog:
    return SpecialDeviceCatalog(devices=(), points=(), source_device_row_count=0)


@dataclass(frozen=True, slots=True)
class CompositeSignalPointRow:
    source_table: str
    point_gid: int
    dev_addr: int
    device_gid: int
    point_name: str
    point_payload_json: str
    formula_digest: str | None
    formula_ast_json: str | None

    def __post_init__(self) -> None:
        if not self.source_table:
            raise ValueError("source_table must be a non-empty string")
        if not self.point_payload_json:
            raise ValueError("point_payload_json must be a non-empty string")
        if self.formula_digest is not None and not self.formula_digest:
            raise ValueError("formula_digest must be a non-empty string or None")
        if self.formula_ast_json is not None and not self.formula_ast_json:
            raise ValueError("formula_ast_json must be a non-empty string or None")
        if (self.formula_digest is None) != (self.formula_ast_json is None):
            raise ValueError("formula_digest and formula_ast_json must be both set or both None")


@dataclass(frozen=True, slots=True)
class CompositeDiagnostic:
    code: CompositeDiagnosticCode
    severity: CompositeDiagnosticSeverity
    message: str
    table: str | None = None

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode(_UTF8)) > RESOURCE_BUDGETS.max_diagnostic_message_bytes:
            raise ValueError("message exceeds max diagnostic bytes")
        if self.table is not None and not self.table:
            raise ValueError("table must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class CompositeSignalRequest:
    logic: CompositeLogicSource
    catalog: SpecialDeviceCatalog
    context: ParserInvocationContext
    xml: XmlParseResult | None = None

    def __post_init__(self) -> None:
        if self.logic.empty:
            if self.xml is not None:
                raise ValueError("EMPTY source forbids an XML document result")
            return
        if self.xml is None:
            raise ValueError("non-empty source requires an XML document result")


@dataclass(frozen=True, slots=True)
class CompositeSignalResult:
    status: CompositeSignalStatus
    diagnostics: tuple[CompositeDiagnostic, ...]
    rows: tuple[CompositeSignalPointRow, ...] = ()
    formulas: tuple[NamedFormula, ...] = ()

    def __post_init__(self) -> None:
        if len(self.diagnostics) > RESOURCE_BUDGETS.max_diagnostics:
            raise ValueError("diagnostics exceed max_diagnostics")
        if self.status is CompositeSignalStatus.FAILED:
            if self.rows or self.formulas:
                raise ValueError("FAILED must not publish derived rows or formulas")
            if not self.diagnostics:
                raise ValueError("FAILED requires diagnostics")
            return
        if self.diagnostics:
            raise ValueError("COMPLETE forbids diagnostics")
