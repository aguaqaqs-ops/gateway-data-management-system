#!/usr/bin/env python3
"""Write WP5 R3 formal scenario tree (offline; not invoked by pytest).

Single offline reproduction (conformance env: ruamel + gateway_compute):

  cd vnext/conformance
  uv sync --locked --offline --extra writer --reinstall-package gateway-compute-python
  uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py

Optional flat base directory (appends data/canonical-row-hashes/mixed-scalars automatically):

  uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py --output-dir /tmp/wp5-r3-formal
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import pyarrow as pa

VNEXT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "data.canonical-row-hashes.mixed-scalars"
SCENARIO_REL_DIR = Path("data") / "canonical-row-hashes" / "mixed-scalars"
FORMAL_SCENARIO_ROOT = (
    VNEXT_ROOT
    / "fixtures"
    / "scenarios"
    / "data"
    / "canonical-row-hashes"
    / "mixed-scalars"
)

PUBLISHED_INPUT_DIGEST = (
    "sha256:3f3bc9791793bb3cb435eb75e0c566064026012a82e3866803acd8702892d995"
)
PUBLISHED_FIXTURE_DIGEST = (
    "sha256:1f7361b145cc9c353b3ada8577123de4d632936ebf7ebfde0e496220869aaf09"
)
PUBLISHED_TABLE_RAW_SHA256 = (
    "sha256:1b4586a017ccde6ed136feab26e3e835f5198dcb5dbfa8644c34c8d5664d600f"
)
PUBLISHED_ANCHOR_RAW_SHA256 = (
    "sha256:e1eea51ea97b70ae0f12d9ec0df8c1cd946f3cafe83baf702342c886efd4280d"
)

REQUEST_VALUE = {
    "request_schema_version": 1,
    "contract_binding": {
        "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
        "semantic_version": "1.0.0",
    },
    "canonical_encoding_version": 1,
    "arrow_mapping_schema_version": 1,
    "declared_table_schema": {
        "fields": [
            {
                "name": "z_label",
                "nullable": True,
                "semantic_type": {"kind": "string"},
            },
            {
                "name": "a_id",
                "nullable": False,
                "semantic_type": {"kind": "signed-integer", "bits": 32},
            },
            {
                "name": "m_flag",
                "nullable": True,
                "semantic_type": {"kind": "boolean"},
            },
            {
                "name": "amount",
                "nullable": False,
                "semantic_type": {"kind": "decimal", "precision": 10, "scale": 2},
            },
        ]
    },
}


def _build_batch() -> pa.RecordBatch:
    schema = pa.schema(
        [
            pa.field("z_label", pa.string(), nullable=True),
            pa.field("a_id", pa.int32(), nullable=False),
            pa.field("m_flag", pa.bool_(), nullable=True),
            pa.field("amount", pa.decimal128(10, 2), nullable=False),
        ]
    )
    z_label = pa.array(["beta", "alpha", "beta"], type=pa.string())
    a_id = pa.array([2, 1, 2], type=pa.int32())
    m_flag = pa.array([True, None, True], type=pa.bool_())
    amount = pa.array(
        [
            pa.scalar(Decimal("12.50"), type=pa.decimal128(10, 2)),
            pa.scalar(Decimal("-3.00"), type=pa.decimal128(10, 2)),
            pa.scalar(Decimal("12.50"), type=pa.decimal128(10, 2)),
        ]
    )
    return pa.record_batch([z_label, a_id, m_flag, amount], schema=schema)


def _manifest_to_yaml(manifest: dict) -> str:
    version = int(manifest["manifest_schema_version"])
    lines = [f"manifest_schema_version: {version}"]
    lines.append("scenario_id: data.canonical-row-hashes.mixed-scalars")
    lines.append("track: data")
    lines.append("subject:")
    lines.append("  kind: capability")
    lines.append("  name: canonical-row-hashes")
    lines.append(
        "description: Handcrafted mixed-scalar canonical row-hash oracle scenario for Phase 1."
    )
    lines.append("provenance:")
    lines.append("  kind: HANDCRAFTED")
    lines.append("contract_bindings:")
    lines.append("  - binding_id: subject")
    lines.append("    owner: canonical-row-hash-capability")
    lines.append("    contract_id: gateway-vnext.canonical-row-hash-compute-boundary")
    lines.append("    semantic_version: 1.0.0")
    lines.append("canonical_encoding_version: 1")
    lines.append("input_assets:")
    for asset in manifest["input_assets"]:
        lines.append(f"  - logical_name: {asset['logical_name']}")
        lines.append(f"    path: {asset['path']}")
        lines.append(f"    media_type: {asset['media_type']}")
        lines.append(f"    size_bytes: {asset['size_bytes']}")
        lines.append(f"    raw_sha256: {asset['raw_sha256']}")
    lines.append("owner_closure_assets:")
    for asset in manifest.get("owner_closure_assets", []):
        lines.append(f"  - logical_name: {asset['logical_name']}")
        lines.append(f"    path: {asset['path']}")
        lines.append(f"    media_type: {asset['media_type']}")
        lines.append(f"    size_bytes: {asset['size_bytes']}")
        lines.append(f"    raw_sha256: {asset['raw_sha256']}")
    lines.append("stimulus:")
    lines.append("  contract_binding_id: subject")
    lines.append("  payload:")
    lines.append("    storage: inline")
    value_json = json.dumps(manifest["stimulus"]["payload"]["value"], separators=(",", ":"))
    lines.append(f"    value: {value_json}")
    lines.append(f"input_digest: {manifest['input_digest']}")
    lines.append(f"fixture_content_digest: {manifest['fixture_content_digest']}")
    lines.append("expected:")
    entry = manifest["expected"][0]
    lines.append(f"  - expectation_id: {entry['expectation_id']}")
    lines.append(f"    kind: {entry['kind']}")
    lines.append(f"    path: {entry['path']}")
    lines.append(f"    size_bytes: {entry['size_bytes']}")
    lines.append(f"    raw_sha256: {entry['raw_sha256']}")
    lines.append("    contract_binding:")
    binding = entry["contract_binding"]
    lines.append(f"      owner: {binding['owner']}")
    lines.append(f"      contract_id: {binding['contract_id']}")
    lines.append(f"      semantic_version: {binding['semantic_version']}")
    lines.append(f"    content_digest: {entry['content_digest']}")
    lines.append("required_profiles:")
    for profile in manifest["required_profiles"]:
        lines.append(f"  - {profile}")
    lines.append(f"legacy_classification: {manifest['legacy_classification']}")
    return "\n".join(lines) + "\n"


_WRITER_UV_HINT = """\
gateway_compute is not installed. Run from vnext/conformance:

  uv sync --locked --offline --extra writer --reinstall-package gateway-compute-python
  uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py
"""


def _resolve_scenario_root(base: Path) -> Path:
    base = base.resolve()
    if len(base.parts) >= 3:
        tail = Path(base.parts[-3]) / base.parts[-2] / base.name
        if tail == SCENARIO_REL_DIR:
            return base
    resolved = base / SCENARIO_REL_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _ensure_writer_import_paths() -> None:
    conf_src = VNEXT_ROOT / "conformance" / "src"
    if str(conf_src) not in sys.path:
        sys.path.insert(0, str(conf_src))
    try:
        import gateway_compute  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(_WRITER_UV_HINT) from exc


def _write_tree(scenario_root: Path) -> dict[str, str]:
    _ensure_writer_import_paths()
    from gateway_compute import canonical_row_hashes_v1
    from gateway_shared_kernel import raw_blob_digest
    from gateway_shared_kernel.jcs import canonicalize_json_value

    from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
    from gateway_conformance.owner.validate import (
        compute_golden_content_digest,
        compute_owner_content_digest,
    )
    from gateway_conformance.scenario.closure import load_scenario_closure
    from gateway_conformance.scenario.digest import (
        compute_fixture_content_digest,
        compute_input_digest,
    )
    from gateway_conformance.scenario.validate import validate_scenario

    batch = _build_batch()
    request_jcs = canonicalize_json_value(REQUEST_VALUE)
    _output, result_jcs = canonical_row_hashes_v1(request_jcs, batch)
    result_value = json.loads(result_jcs.decode())

    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, batch.schema) as writer:
        writer.write_batch(batch)
    ipc_bytes = bytes(sink.getvalue().to_pybytes())

    fields = REQUEST_VALUE["declared_table_schema"]["fields"]
    row_count, raw_content_digest, sorted_hashes = compute_table_content_identity(
        ipc_bytes, fields
    )
    anchor_payload = {
        "anchor_schema_version": 1,
        "scenario_id": SCENARIO_ID,
        "row_count": row_count,
        "raw_content_digest": raw_content_digest,
        "sorted_row_hashes_hex": [item.hex() for item in sorted_hashes],
    }
    anchor_bytes = (json.dumps(anchor_payload, indent=2) + "\n").encode("utf-8")

    contract_binding = {
        "owner": "canonical-row-hash-capability",
        "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
        "semantic_version": "1.0.0",
    }
    content_digest = compute_owner_content_digest(
        result_value,
        owner=str(contract_binding["owner"]),
        contract_id=str(contract_binding["contract_id"]),
        semantic_version=str(contract_binding["semantic_version"]),
        schema_id="gateway-vnext.canonical-table-result.v1",
        schema_version=1,
    )
    envelope = {
        "golden_envelope_schema_version": 1,
        "expectation_id": "row-hashes",
        "kind": "structured",
        "contract_binding": contract_binding,
        "payload_descriptor": {
            "media_type": "application/json",
            "schema_id": "gateway-vnext.canonical-table-result.v1",
            "schema_version": 1,
            "canonical_encoding_version": 1,
            "comparison_mode": "exact-canonical",
        },
        "content_digest": content_digest,
        "payload": {"storage": "inline", "value": result_value},
    }
    assert compute_golden_content_digest(envelope) == content_digest
    golden_bytes = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    manifest: dict = {
        "manifest_schema_version": 2,
        "scenario_id": SCENARIO_ID,
        "track": "data",
        "subject": {"kind": "capability", "name": "canonical-row-hashes"},
        "description": (
            "Handcrafted mixed-scalar canonical row-hash oracle scenario for Phase 1."
        ),
        "provenance": {"kind": "HANDCRAFTED"},
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "canonical-row-hash-capability",
                "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
                "semantic_version": "1.0.0",
            }
        ],
        "canonical_encoding_version": 1,
        "input_assets": [
            {
                "logical_name": "table-stream",
                "path": "input/table.arrow-stream",
                "media_type": "application/vnd.apache.arrow.stream",
                "size_bytes": len(ipc_bytes),
                "raw_sha256": raw_blob_digest(ipc_bytes).value,
            }
        ],
        "owner_closure_assets": [
            {
                "logical_name": "row-hash-oracle-anchor",
                "path": "input/row-hash-oracle-anchor.json",
                "media_type": "application/json",
                "size_bytes": len(anchor_bytes),
                "raw_sha256": raw_blob_digest(anchor_bytes).value,
            }
        ],
        "stimulus": {
            "contract_binding_id": "subject",
            "payload": {"storage": "inline", "value": REQUEST_VALUE},
        },
        "input_digest": "sha256:" + "0" * 64,
        "fixture_content_digest": "sha256:" + "0" * 64,
        "expected": [
            {
                "expectation_id": "row-hashes",
                "kind": "structured",
                "path": "expected/row-hashes.golden.json",
                "size_bytes": len(golden_bytes),
                "raw_sha256": raw_blob_digest(golden_bytes).value,
                "contract_binding": contract_binding,
                "content_digest": content_digest,
            }
        ],
        "required_profiles": ["integration", "provider-matrix", "reference"],
        "legacy_classification": "NOT_APPLICABLE",
    }

    scenario_root.mkdir(parents=True, exist_ok=True)
    (scenario_root / "input").mkdir(exist_ok=True)
    (scenario_root / "expected").mkdir(exist_ok=True)
    (scenario_root / "input" / "table.arrow-stream").write_bytes(ipc_bytes)
    (scenario_root / "input" / "row-hash-oracle-anchor.json").write_bytes(anchor_bytes)
    (scenario_root / "expected" / "row-hashes.golden.json").write_bytes(golden_bytes)
    (scenario_root / "scenario.yaml").write_text(_manifest_to_yaml(manifest), encoding="utf-8")

    closure = load_scenario_closure(scenario_root)
    manifest["input_digest"] = compute_input_digest(manifest, closure.assets)
    manifest["fixture_content_digest"] = compute_fixture_content_digest(closure)
    (scenario_root / "scenario.yaml").write_text(_manifest_to_yaml(manifest), encoding="utf-8")

    validate_scenario(scenario_root)
    return {
        "input_digest": str(manifest["input_digest"]),
        "fixture_content_digest": str(manifest["fixture_content_digest"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Author WP5 R3 formal scenario (offline).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Base output directory; scenario files are written under "
            "data/canonical-row-hashes/mixed-scalars (appended when missing). "
            "Default: temporary directory with the same layout."
        ),
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help=f"Copy validated tree to {FORMAL_SCENARIO_ROOT} after validation.",
    )
    args = parser.parse_args()

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.output_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="wp5-r3-scenario-")
        output_base = Path(temp_dir.name)
    else:
        output_base = args.output_dir.expanduser().resolve()

    scenario_root = _resolve_scenario_root(output_base)

    digests = _write_tree(scenario_root)
    print(f"wrote scenario to {scenario_root}")
    print("input_digest:", digests["input_digest"])
    print("fixture_content_digest:", digests["fixture_content_digest"])

    if args.install:
        from gateway_conformance.scenario.closure import load_scenario_closure
        from gateway_shared_kernel import raw_blob_digest

        if scenario_root == FORMAL_SCENARIO_ROOT.resolve():
            raise SystemExit("refusing --install when output-dir is already the formal tree")
        if digests["input_digest"] != PUBLISHED_INPUT_DIGEST:
            raise SystemExit(
                f"input_digest mismatch: got {digests['input_digest']}, "
                f"expected {PUBLISHED_INPUT_DIGEST}"
            )
        if digests["fixture_content_digest"] != PUBLISHED_FIXTURE_DIGEST:
            raise SystemExit(
                f"fixture_content_digest mismatch: got {digests['fixture_content_digest']}, "
                f"expected {PUBLISHED_FIXTURE_DIGEST}"
            )
        closure = load_scenario_closure(scenario_root)
        table_asset = closure.assets["table-stream"]
        anchor_asset = closure.owner_closure_assets["row-hash-oracle-anchor"]

        if raw_blob_digest(table_asset.raw).value != PUBLISHED_TABLE_RAW_SHA256:
            raise SystemExit("table-stream raw_sha256 mismatch against published identity")
        if raw_blob_digest(anchor_asset.raw).value != PUBLISHED_ANCHOR_RAW_SHA256:
            raise SystemExit("oracle anchor raw_sha256 mismatch against published identity")
        if FORMAL_SCENARIO_ROOT.exists():
            shutil.rmtree(FORMAL_SCENARIO_ROOT)
        shutil.copytree(scenario_root, FORMAL_SCENARIO_ROOT)
        print(f"installed to {FORMAL_SCENARIO_ROOT}")

    if temp_dir is not None:
        temp_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
