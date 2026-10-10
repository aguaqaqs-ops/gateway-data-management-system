"""Public surface of the Composite Signal capability."""

from gateway_backend.capabilities.composite_signal.contracts import (
    COMPOSITE_SIGNAL_CONTRACT_VERSION,
    COMPOSITE_SIGNAL_POINT_KEY,
    COMPOSITE_SIGNAL_POINT_TABLE,
    DEVICE_TABLE,
    EMPTY_COMPOSITE_LOGIC_DIGEST,
    EMPTY_COMPOSITE_LOGIC_MARKER_BYTES,
    SPECIAL_DEV_ADDR,
    SPECIAL_DEVICE_DESCRIPTION,
    SPECIAL_POINT_TABLES,
    CompositeDiagnostic,
    CompositeDiagnosticCode,
    CompositeDiagnosticSeverity,
    CompositeLogicSource,
    CompositeSignalPointRow,
    CompositeSignalRequest,
    CompositeSignalResult,
    CompositeSignalStatus,
    DigitalNode,
    ExpressNode,
    NamedFormula,
    PointNode,
    SpecialDevice,
    SpecialDeviceCatalog,
    SpecialPointFact,
    empty_composite_logic_source,
    empty_special_device_catalog,
    present_composite_logic_source,
)


def materialize_composite_signal(request: CompositeSignalRequest) -> CompositeSignalResult:
    from gateway_backend.capabilities.composite_signal.materialize import (
        materialize_composite_signal as _impl,
    )

    return _impl(request)


__all__ = [
    "COMPOSITE_SIGNAL_CONTRACT_VERSION",
    "COMPOSITE_SIGNAL_POINT_KEY",
    "COMPOSITE_SIGNAL_POINT_TABLE",
    "DEVICE_TABLE",
    "EMPTY_COMPOSITE_LOGIC_DIGEST",
    "EMPTY_COMPOSITE_LOGIC_MARKER_BYTES",
    "SPECIAL_DEV_ADDR",
    "SPECIAL_DEVICE_DESCRIPTION",
    "SPECIAL_POINT_TABLES",
    "CompositeDiagnostic",
    "CompositeDiagnosticCode",
    "CompositeDiagnosticSeverity",
    "CompositeLogicSource",
    "CompositeSignalPointRow",
    "CompositeSignalRequest",
    "CompositeSignalResult",
    "CompositeSignalStatus",
    "DigitalNode",
    "ExpressNode",
    "NamedFormula",
    "PointNode",
    "SpecialDevice",
    "SpecialDeviceCatalog",
    "SpecialPointFact",
    "empty_composite_logic_source",
    "empty_special_device_catalog",
    "materialize_composite_signal",
    "present_composite_logic_source",
]
