"""Filesystem roots and constants for conformance validation."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
VNEXT_ROOT = _PACKAGE_ROOT.parent
SCHEMA_ROOT = VNEXT_ROOT / "fixtures" / "schemas"
OWNER_REGISTRY_ROOT = SCHEMA_ROOT / "conformance" / "owners" / "v1"
GOVERNANCE_ROOT = SCHEMA_ROOT / "conformance" / "governance" / "v1"
SHARED_ROOT = VNEXT_ROOT / "fixtures" / "shared"
SCENARIO_DIGEST_VECTOR_ROOT = (
    VNEXT_ROOT / "fixtures" / "vectors" / "conformance" / "scenario-digest" / "v1"
)
FORMAL_SCENARIO_ROOT = VNEXT_ROOT / "fixtures" / "scenarios"

SCENARIO_MANIFEST_NAME = "scenario.yaml"
SCENARIO_MAX_BYTES = 1_048_576
SHARED_ASSET_MAX_BYTES = 5_242_880

SCHEMA_FILES = (
    "definitions-v1.schema.json",
    "scenario-manifest-v1.schema.json",
    "scenario-manifest-v2.schema.json",
    "golden-envelope-v1.schema.json",
    "harness-protocol-v1.schema.json",
    "runner-result-v1.schema.json",
    "run-evidence-v1.schema.json",
)

SCHEMA_ID_BY_FILE = {
    "definitions-v1.schema.json": "gateway-vnext.fixture-oracle.definitions.v1",
    "scenario-manifest-v1.schema.json": "gateway-vnext.fixture-oracle.scenario-manifest.v1",
    "scenario-manifest-v2.schema.json": "gateway-vnext.fixture-oracle.scenario-manifest.v2",
    "golden-envelope-v1.schema.json": "gateway-vnext.fixture-oracle.golden-envelope.v1",
    "harness-protocol-v1.schema.json": "gateway-vnext.fixture-oracle.harness-protocol.v1",
    "runner-result-v1.schema.json": "gateway-vnext.fixture-oracle.runner-result.v1",
    "run-evidence-v1.schema.json": "gateway-vnext.fixture-oracle.run-evidence.v1",
}

FORBIDDEN_PROTOCOL_FIELDS = frozenset(
    {
        "expected_payload",
        "golden_path",
        "golden_digest",
        "expected_content_digest",
        "golden",
        "expected_path",
    }
)
