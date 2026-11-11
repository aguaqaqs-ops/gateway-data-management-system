"""Backend-owned consumer vectors from the real presentation fixture generator."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.capabilities.business_navigation.contracts import validate_diagnostics, validate_navigation
from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata
from gateway_backend.capabilities.row_location.producer import LOCATOR_SCHEMA

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures/golden/presentation/be-b/v1"
MANIFEST: dict[str, Any] = json.loads((GOLDEN / "manifest.json").read_bytes())
SCENARIOS = tuple(item["scenario"] for item in MANIFEST["scenarios"])
CODE_INVENTORY: dict[str, Any] = json.loads((Path(__file__).resolve().parents[2] / "fixtures/presentation-inputs/diagnostic-codes.json").read_bytes())


def _load(kind: str, scenario: str) -> list[dict[str, Any]]:
    relative = f"{kind}/{scenario}.json"
    raw = (GOLDEN / relative).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST["files"][relative]
    document: list[dict[str, Any]] = json.loads(raw)
    assert canonicalize_json_value(document) == raw
    return document


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_generated_five_class_presentation_vectors_are_mutually_bound(scenario: str) -> None:
    surfaces = {item["pair_id"]: item for item in _load("surface", scenario)}
    navigations = {item["pair_id"]: item for item in _load("navigation", scenario)}
    diagnostics = {item["pair_id"]: item for item in _load("navigation-diagnostics", scenario)}
    assert surfaces.keys() == navigations.keys() == diagnostics.keys()
    for pair_id, vector in surfaces.items():
        surface = vector["document"]
        assert surface["surface_contract_version"] == "backend-vnext/comparison-surface/v4"
        payload = vector["semantic_preimage"]
        assert raw_blob_digest(canonicalize_json_value(payload)).value == vector["surface_digest"]
        assert vector["surface_digest"] == surface["surface_digest"] == vector["physical_variant_digest"]
        assert all("table_refs" not in table and "row_locator_ref" not in table for table in payload["_tables"])
        published_codes = set(surface["diagnostics"]["diagnostics_summary"])
        published_codes.update(surface["view"]["diagnostics_summary"])
        for table in surface["tables"]:
            published_codes.update(table["diagnostics"]["diagnostics_summary"])
        assert published_codes <= set(CODE_INVENTORY["surface_summary_codes"])
        table_ids = frozenset(table["table_id"] for table in surface["tables"])
        navigation = validate_navigation(navigations[pair_id]["document"],
            replacement=surface["comparison_mode"] == "DATASET_REPLACEMENT")
        diagnostic = diagnostics[pair_id]["document"]
        if diagnostic is not None:
            validate_diagnostics(diagnostic, navigation, table_ids)
        projections = [p for p in surface["projections"] if p["projection_kind"] == "BUSINESS_NAVIGATION"]
        assert len(projections) == 1
        assert projections[0]["projection_digest"] == raw_blob_digest(canonicalize_json_value(navigation)).value
        for table in surface["tables"]:
            columns = table["columns"]
            assert [c["name"] for c in columns] == sorted({c["name"] for c in columns}, key=lambda value: value.encode())
            assert sorted(c["display_order"] for c in columns) == list(range(len(columns)))
            for side in ("before", "current", "browse"):
                assert (table["table_refs"][side + "_table_ref"] is None) == (table["table_content_bindings"][side] is None)
    for vector in _load("row-location", scenario):
        raw = base64.b64decode(vector["parquet_base64"], validate=True)
        assert raw_blob_digest(raw).value == vector["raw_sha256"]
        file = pq.ParquetFile(pa.BufferReader(raw))
        assert file.schema_arrow.equals(LOCATOR_SCHEMA, check_metadata=True)
        rows = file.read().to_pylist()
        assert [{**row, "row_identity": row["row_identity"].hex()} for row in rows] == vector["rows"]
        assert [row["row_identity"] for row in rows] == sorted({row["row_identity"] for row in rows})
        table = next(t for t in surfaces[vector["pair_id"]]["document"]["tables"] if t["table_id"] == vector["table_id"])
        for row in rows:
            for side in ("before", "current"):
                index = row[side + "_row_index"]
                context = row[side + "_filter_context_json"]
                if index is not None:
                    assert context is None
                    assert 0 <= index < table["table_content_bindings"][side]["row_count"]
    for vector in _load("bundle", scenario):
        history = scenario in {"history-three-nodes", "schema-keyless"}
        for index, item in enumerate(vector["manifest"]["inputs"]):
            assert item["snapshot_digest"] is None and item["display_metadata"] == {}
            assert item["display_name"] == (f"node-{index}" if history else item["role"].capitalize())
            if history:
                assert item["role"] == f"fixture-history-ref-{index}"
        transport = read_bundle_transport_metadata(canonicalize_json_value(vector["manifest"]))
        assert transport.expected_closure_bytes == canonicalize_json_value(vector["artifact_closure"])
    if scenario == "comment-only":
        result = next(item for item in MANIFEST["scenarios"] if item["scenario"] == scenario)["submit_result"]
        assert result["code"] == "NO_CANONICAL_CHANGE"
        assert result["write_transactions"] == result["repository_main_calls"] == 0
        assert result["baseline_canonical_state_digest"] == result["modified_canonical_state_digest"]
