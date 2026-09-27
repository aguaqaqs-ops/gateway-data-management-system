"""Helpers for composite-signal tests. Not a production materializer."""

from __future__ import annotations

from pathlib import Path

from gateway_backend.capabilities.composite_signal import materialize_composite_signal
from gateway_backend.capabilities.composite_signal.contracts import (
    SPECIAL_DEV_ADDR,
    SPECIAL_DEVICE_DESCRIPTION,
    CompositeLogicSource,
    CompositeSignalRequest,
    CompositeSignalResult,
    SpecialDevice,
    SpecialDeviceCatalog,
    SpecialPointFact,
    empty_composite_logic_source,
    empty_special_device_catalog,
    present_composite_logic_source,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    XmlParseResult,
)
from tests.support.table_access_xml import parse_xml_text

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "composite-signal"


def load_text(relative_path: str) -> str:
    return (FIXTURE_ROOT / relative_path).read_text(encoding="utf-8")


def special_catalog(
    *,
    point_names: tuple[str, ...] = ("top",),
    include_device: bool = True,
    extra_devices: tuple[SpecialDevice, ...] = (),
) -> SpecialDeviceCatalog:
    devices = extra_devices
    if include_device:
        devices = (
            SpecialDevice(gid=1, dev_addr=SPECIAL_DEV_ADDR, description=SPECIAL_DEVICE_DESCRIPTION),
            *extra_devices,
        )
    points = tuple(
        SpecialPointFact(
            source_table="device_st",
            point_gid=index + 1,
            dev_addr=SPECIAL_DEV_ADDR,
            point_name=name,
            payload=(
                ("dev_addr", SPECIAL_DEV_ADDR),
                ("gid", index + 1),
                ("name", name),
            ),
        )
        for index, name in enumerate(point_names)
    )
    return SpecialDeviceCatalog(devices=devices, points=points)


def materialize_logic(
    xml: str | bytes | XmlParseResult | None = None,
    *,
    catalog: SpecialDeviceCatalog | None = None,
    context: ParserInvocationContext | None = None,
    empty: bool = False,
    logic: CompositeLogicSource | None = None,
) -> CompositeSignalResult:
    invocation = context or ParserInvocationContext(NeverCancel())
    document: XmlParseResult | None
    if empty:
        source = logic or empty_composite_logic_source()
        document = None
    elif isinstance(xml, XmlParseResult):
        source = logic or present_composite_logic_source(b"<Logic_Set></Logic_Set>")
        document = xml
    elif xml is None:
        raise ValueError("xml is required unless empty=True")
    else:
        data = xml.encode("utf-8") if isinstance(xml, str) else xml
        source = logic or present_composite_logic_source(data)
        document = parse_xml_text(data)
    return materialize_composite_signal(
        CompositeSignalRequest(
            logic=source,
            catalog=catalog if catalog is not None else empty_special_device_catalog(),
            context=invocation,
            xml=document,
        )
    )
