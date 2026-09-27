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
        if type(self.empty) is not bool:
            raise ValueError("empty must be bool")
        if type(self.composite_logic_source_digest) is not DigestRef:
            raise ValueError("composite_logic_source_digest must be DigestRef")
        if self.empty:
            if self.document_content_digest is not None:
                raise ValueError("EMPTY source forbids document_content_digest")
            if self.composite_logic_source_digest != EMPTY_COMPOSITE_LOGIC_DIGEST:
                raise ValueError("EMPTY source must use the stable EMPTY digest")
            return
        if type(self.document_content_digest) is not DigestRef:
            raise ValueError("non-empty source requires document_content_digest")
        if self.composite_logic_source_digest != self.document_content_digest:
            raise ValueError("non-empty source digest must equal document_content_digest")


def empty_composite_logic_source() -> CompositeLogicSource:
    return CompositeLogicSource(
        empty=True,
        composite_logic_source_digest=EMPTY_COMPOSITE_LOGIC_DIGEST,
    )


def present_composite_logic_source(document_utf8: bytes) -> CompositeLogicSource:
    if type(document_utf8) is not bytes:
        raise ValueError("document_utf8 must be bytes")
    digest = raw_blob_digest(document_utf8)
    return CompositeLogicSource(
        empty=False,
        composite_logic_source_digest=digest,
        document_content_digest=digest,
    )


@dataclass(frozen=True, slots=True)
class PointNode:
    name: str

    def __post_init__(self) -> None:
        if type(self.name) is not str:
            raise ValueError("name must be a string")


@dataclass(frozen=True, slots=True)
class DigitalNode:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError("value must be a string")


@dataclass(frozen=True, slots=True)
class ExpressNode:
    operator: str
    children: tuple[AstNode, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        if type(self.operator) is not str:
            raise ValueError("operator must be a string")
        if self.name is not None and type(self.name) is not str:
            raise ValueError("name must be a string or None")
        if type(self.children) is not tuple:
            raise ValueError("children must be a tuple")
        for child in self.children:
            if not isinstance(child, (ExpressNode, PointNode, DigitalNode)):
                raise ValueError("children must contain AST nodes")


AstNode = ExpressNode | PointNode | DigitalNode


@dataclass(frozen=True, slots=True)
class NamedFormula:
    name: str
    ast: ExpressNode
    formula_digest: DigestRef
    formula_ast_json: str

    def __post_init__(self) -> None:
        if type(self.name) is not str or self.name == "":
            raise ValueError("name must be a non-empty string")
        if type(self.ast) is not ExpressNode:
            raise ValueError("ast must be ExpressNode")
        if type(self.formula_digest) is not DigestRef:
            raise ValueError("formula_digest must be DigestRef")
        if type(self.formula_ast_json) is not str or self.formula_ast_json == "":
            raise ValueError("formula_ast_json must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SpecialDevice:
    gid: int
    dev_addr: int
    description: str

    def __post_init__(self) -> None:
        if type(self.gid) is not int:
            raise ValueError("gid must be int")
        if type(self.dev_addr) is not int:
            raise ValueError("dev_addr must be int")
        if type(self.description) is not str:
            raise ValueError("description must be a string")


@dataclass(frozen=True, slots=True)
class SpecialPointFact:
    source_table: str
    point_gid: int
    dev_addr: int
    point_name: str
    payload: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        if type(self.source_table) is not str or self.source_table == "":
            raise ValueError("source_table must be a non-empty string")
        if type(self.point_gid) is not int:
            raise ValueError("point_gid must be int")
        if type(self.dev_addr) is not int:
            raise ValueError("dev_addr must be int")
        if type(self.point_name) is not str:
            raise ValueError("point_name must be a string")
        if type(self.payload) is not tuple:
            raise ValueError("payload must be a tuple")
        seen: set[str] = set()
        for item in self.payload:
            if type(item) is not tuple or len(item) != 2:
                raise ValueError("payload must contain (name, value) pairs")
            name, _value = item
            if type(name) is not str or name == "":
                raise ValueError("payload names must be non-empty strings")
            if name in seen:
                raise ValueError("payload names must be unique")
            seen.add(name)


@dataclass(frozen=True, slots=True)
class SpecialDeviceCatalog:
    devices: tuple[SpecialDevice, ...]
    points: tuple[SpecialPointFact, ...]

    def __post_init__(self) -> None:
        if type(self.devices) is not tuple:
            raise ValueError("devices must be a tuple")
        for device in self.devices:
            if type(device) is not SpecialDevice:
                raise ValueError("devices must contain SpecialDevice")
        if type(self.points) is not tuple:
            raise ValueError("points must be a tuple")
        for point in self.points:
            if type(point) is not SpecialPointFact:
                raise ValueError("points must contain SpecialPointFact")


def empty_special_device_catalog() -> SpecialDeviceCatalog:
    return SpecialDeviceCatalog(devices=(), points=())


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
        if type(self.source_table) is not str or self.source_table == "":
            raise ValueError("source_table must be a non-empty string")
        if type(self.point_gid) is not int:
            raise ValueError("point_gid must be int")
        if type(self.dev_addr) is not int:
            raise ValueError("dev_addr must be int")
        if type(self.device_gid) is not int:
            raise ValueError("device_gid must be int")
        if type(self.point_name) is not str:
            raise ValueError("point_name must be a string")
        if type(self.point_payload_json) is not str or self.point_payload_json == "":
            raise ValueError("point_payload_json must be a non-empty string")
        if self.formula_digest is not None and (
            type(self.formula_digest) is not str or self.formula_digest == ""
        ):
            raise ValueError("formula_digest must be a non-empty string or None")
        if self.formula_ast_json is not None and (
            type(self.formula_ast_json) is not str or self.formula_ast_json == ""
        ):
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
        if type(self.code) is not CompositeDiagnosticCode:
            raise ValueError("code must be CompositeDiagnosticCode")
        if type(self.severity) is not CompositeDiagnosticSeverity:
            raise ValueError("severity must be CompositeDiagnosticSeverity")
        if type(self.message) is not str or self.message == "":
            raise ValueError("message must be a non-empty string")
        if len(self.message.encode(_UTF8)) > RESOURCE_BUDGETS.max_diagnostic_message_bytes:
            raise ValueError("message exceeds max diagnostic bytes")
        if self.table is not None and (type(self.table) is not str or self.table == ""):
            raise ValueError("table must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class CompositeSignalRequest:
    logic: CompositeLogicSource
    catalog: SpecialDeviceCatalog
    context: ParserInvocationContext
    xml: XmlParseResult | None = None

    def __post_init__(self) -> None:
        if type(self.logic) is not CompositeLogicSource:
            raise ValueError("logic must be CompositeLogicSource")
        if type(self.catalog) is not SpecialDeviceCatalog:
            raise ValueError("catalog must be SpecialDeviceCatalog")
        if type(self.context) is not ParserInvocationContext:
            raise ValueError("context must be ParserInvocationContext")
        if self.logic.empty:
            if self.xml is not None:
                raise ValueError("EMPTY source forbids an XML document result")
            return
        if type(self.xml) is not XmlParseResult:
            raise ValueError("non-empty source requires an XML document result")


@dataclass(frozen=True, slots=True)
class CompositeSignalResult:
    status: CompositeSignalStatus
    diagnostics: tuple[CompositeDiagnostic, ...]
    rows: tuple[CompositeSignalPointRow, ...] = ()
    formulas: tuple[NamedFormula, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not CompositeSignalStatus:
            raise ValueError("status must be CompositeSignalStatus")
        if type(self.diagnostics) is not tuple:
            raise ValueError("diagnostics must be a tuple")
        if len(self.diagnostics) > RESOURCE_BUDGETS.max_diagnostics:
            raise ValueError("diagnostics exceed max_diagnostics")
        for diagnostic in self.diagnostics:
            if type(diagnostic) is not CompositeDiagnostic:
                raise ValueError("diagnostics must contain CompositeDiagnostic")
        if type(self.rows) is not tuple:
            raise ValueError("rows must be a tuple")
        for row in self.rows:
            if type(row) is not CompositeSignalPointRow:
                raise ValueError("rows must contain CompositeSignalPointRow")
        if type(self.formulas) is not tuple:
            raise ValueError("formulas must be a tuple")
        for formula in self.formulas:
            if type(formula) is not NamedFormula:
                raise ValueError("formulas must contain NamedFormula")
        if self.status is CompositeSignalStatus.FAILED:
            if self.rows or self.formulas:
                raise ValueError("FAILED must not publish derived rows or formulas")
            if not self.diagnostics:
                raise ValueError("FAILED requires diagnostics")
            return
        if self.diagnostics:
            raise ValueError("COMPLETE forbids diagnostics")

