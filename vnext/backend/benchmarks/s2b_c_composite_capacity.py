"""Supplement existing t4 FULL facts with actual XML/AST/composite consumers only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pyarrow as pa
from gateway_compute._native import _parse_sql_native

from s2b_c_capacity import BUSINESS, read_input, sample_memory

from gateway_backend.capabilities.composite_signal import (
    CompositeSignalRequest, CompositeSignalStatus, materialize_composite_signal, present_composite_logic_source,
)
from gateway_backend.capabilities.snapshot_materialization.compose import _derived_table
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy, MaterializationStage
from gateway_backend.capabilities.snapshot_materialization.native import catalog_from_arrow_result, filter_arrow_catalog
from gateway_backend.capabilities.table_access import parse_xml
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION, NeverCancel, ParseStatus, ParserInvocationContext, XmlParseRequest, XmlSourceInput,
)
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("supplemental output must be new")
    retained: list[Any] = []
    reports = []
    memory = [sample_memory("start")]
    for side in ("v1", "v2"):
        package, sql, report = read_input("rd-t4-d-" + side)
        with tarfile.open(fileobj=io.BytesIO(package), mode="r:gz") as archive:
            member = next(item for item in archive.getmembers() if item.name.lstrip("/") == "comps/logic/logics.xml")
            if not member.isfile() or member.size > 64 * 1024**2:
                raise ValueError("XML member exceeds owning quota")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("XML member is missing")
            with source:
                xml_bytes = source.read(member.size + 1)
            if len(xml_bytes) != member.size:
                raise ValueError("XML length differs from fixed member header")
        parsed = _parse_sql_native(sql, NeverCancel(), None, 1)
        if parsed.get("kind") != "result" or parsed.get("status") != "COMPLETE":
            raise RuntimeError("existing SQL did not parse completely")
        metadata = {}
        arrays = []
        for table in parsed["tables"]:
            with table["arrow_stream"] as stream:
                array = stream.read_all()
            arrays.append(array)
            table["arrow_stream"] = pa.RecordBatchReader.from_batches(array.schema, array.to_batches())
            metadata[table["canonical_name"]] = table
        filtered = filter_arrow_catalog(metadata, cancel_probe=NeverCancel(), budgets=BUSINESS, deadline_monotonic=None, pool_threads=1)
        catalog = catalog_from_arrow_result(filtered, budgets=BUSINESS, cancel_probe=NeverCancel(), deadline_monotonic=None)
        for table in parsed["tables"]:
            table["arrow_stream"].close()
        logic = present_composite_logic_source(xml_bytes)
        digest = logic.document_content_digest
        assert digest is not None
        context = ParserInvocationContext(NeverCancel())
        xml = parse_xml(XmlParseRequest(
            source=XmlSourceInput(document_content_digest=digest, xml_source_digest=digest,
                parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION, encoding="utf-8", source_size_bytes=len(xml_bytes)),
            xml_utf8=xml_bytes, context=context,
        ))
        if xml.status is not ParseStatus.COMPLETE:
            raise RuntimeError("actual XML parser did not complete")
        composite = materialize_composite_signal(CompositeSignalRequest(logic=logic, catalog=catalog, context=context, xml=xml))
        if composite.status is not CompositeSignalStatus.COMPLETE:
            raise RuntimeError("actual composite consumer did not complete")
        _, derived = _derived_table(composite.rows, MaterializationStage.FINAL, TABLE_RULESET_VERSION, MaterializationPolicy.READERS_REQUIRED)
        retained.append((package, sql, xml_bytes, arrays, catalog, xml, composite, derived))
        report.update({
            "xml_sha256": hashlib.sha256(xml_bytes).hexdigest(), "xml_events": len(xml.events),
            "filtered_devices": len(catalog.devices), "filtered_points": len(catalog.points),
            "formulas": len(composite.formulas), "derived_rows": len(composite.rows),
            "formula_ast_json_utf8_bytes": sum(len(formula.formula_ast_json.encode()) for formula in composite.formulas),
            "derived_point_payload_utf8_bytes": sum(len(row.point_payload_json.encode()) for row in composite.rows),
        })
        reports.append(report)
        memory.append(sample_memory(side + "-XML-AST-composite-retained"))
    result = {"scope": "same fixed t4 pair; parser/filter/XML/AST/composite/derived-row consumers; no projection/IPC/store/operation", "inputs": reports, "memory": memory}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(), "memory": memory[-1]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
