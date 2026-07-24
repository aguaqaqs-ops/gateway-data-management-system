"""Test helpers for building scenario fixtures with valid digests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_shared_kernel import raw_blob_digest

from gateway_conformance.owner.validate import (
    compute_owner_content_digest,
    compute_structured_asset_content_digest,
)
from gateway_conformance.scenario.closure import load_scenario_closure
from gateway_conformance.scenario.digest import compute_fixture_content_digest, compute_input_digest


def _binding(
    binding_id: str = "subject",
    owner: str = "test-capability",
    contract_id: str = "gateway-vnext.test-contract",
) -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "owner": owner,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
    }


def _schema_for_kind(kind: str) -> tuple[str, Any]:
    if kind == "structured":
        return "gateway-vnext.test-result.v1", {"status": "ok"}
    if kind == "recovery":
        return "gateway-vnext.test-recovery.v1", {"checkpoints": ["ok"]}
    if kind == "artifact":
        return "gateway-vnext.test-artifact.v1", {"artifact": True}
    raise ValueError(f"unsupported kind: {kind}")


def _golden_envelope(
    expectation_id: str = "result",
    *,
    kind: str = "structured",
    value: Any | None = None,
) -> dict[str, Any]:
    schema_id, default_value = _schema_for_kind(kind)
    payload_value = value if value is not None else default_value
    contract_binding = {
        "owner": "test-capability",
        "contract_id": "gateway-vnext.test-contract",
        "semantic_version": "1.0.0",
    }
    content_digest = compute_owner_content_digest(
        payload_value,
        owner=str(contract_binding["owner"]),
        contract_id=str(contract_binding["contract_id"]),
        semantic_version=str(contract_binding["semantic_version"]),
        schema_id=schema_id,
        schema_version=1,
    )
    comparison = {
        "structured": "exact-canonical",
        "recovery": "recovery-checkpoints",
        "artifact": "artifact-closure",
    }[kind]
    payload: dict[str, Any]
    if kind == "artifact":
        payload = {
            "storage": "closure",
            "value": {
                "content_digest": content_digest,
                "manifest": payload_value,
            },
        }
    else:
        payload = {"storage": "inline", "value": payload_value}
    return {
        "golden_envelope_schema_version": 1,
        "expectation_id": expectation_id,
        "kind": kind,
        "contract_binding": contract_binding,
        "payload_descriptor": {
            "media_type": "application/json",
            "schema_id": schema_id,
            "schema_version": 1,
            "canonical_encoding_version": 1,
            "comparison_mode": comparison,
        },
        "content_digest": content_digest,
        "payload": payload,
    }


def base_manifest(
    *,
    track: str = "data",
    subject_name: str = "test-capability",
    scenario_suffix: str = "minimal",
    kind: str = "structured",
    include_fault: bool = False,
) -> tuple[dict[str, Any], bytes]:
    scenario_id = f"{track}.{subject_name}.{scenario_suffix}"
    manifest: dict[str, Any] = {
        "manifest_schema_version": 1,
        "scenario_id": scenario_id,
        "track": track,
        "subject": {"kind": "capability", "name": subject_name},
        "description": "Synthetic test scenario.",
        "provenance": {"kind": "HANDCRAFTED"},
        "contract_bindings": [_binding()],
        "canonical_encoding_version": 1,
        "input_assets": [],
        "stimulus": {
            "contract_binding_id": "subject",
            "payload": {"storage": "inline", "value": {"action": "run"}},
        },
        "input_digest": "sha256:" + "0" * 64,
        "fixture_content_digest": "sha256:" + "0" * 64,
        "expected": [],
        "required_profiles": ["reference"],
        "legacy_classification": "NOT_APPLICABLE",
    }
    envelope = _golden_envelope(kind=kind)
    golden_bytes = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    manifest["expected"] = [
        {
            "expectation_id": "result",
            "kind": kind,
            "path": "expected/result.golden.json",
            "size_bytes": len(golden_bytes),
            "raw_sha256": raw_blob_digest(golden_bytes).value,
            "contract_binding": envelope["contract_binding"],
            "content_digest": envelope["content_digest"],
        }
    ]
    if include_fault:
        manifest["fault"] = {
            "contract_binding_id": "subject",
            "target": "primary",
            "boundary": "network",
            "action": "timeout",
            "occurrence": 1,
        }
        manifest["recovery_trigger"] = {
            "contract_binding_id": "subject",
            "kind": "restart",
            "repetitions": 1,
        }
    return manifest, golden_bytes


def write_scenario_tree(root: Path, manifest: dict[str, Any], *, golden_bytes: bytes) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "expected").mkdir(exist_ok=True)
    (root / "expected" / "result.golden.json").write_bytes(golden_bytes)

    yaml_text = _manifest_to_yaml(manifest)
    (root / "scenario.yaml").write_text(yaml_text, encoding="utf-8")

    closure = load_scenario_closure(root)
    manifest["input_digest"] = compute_input_digest(manifest, closure.assets)
    manifest["fixture_content_digest"] = compute_fixture_content_digest(closure)
    yaml_text = _manifest_to_yaml(manifest)
    (root / "scenario.yaml").write_text(yaml_text, encoding="utf-8")


def _manifest_to_yaml(manifest: dict[str, Any]) -> str:
    version = int(manifest["manifest_schema_version"])
    lines = [f"manifest_schema_version: {version}"]
    lines.append(f"scenario_id: {manifest['scenario_id']}")
    lines.append(f"track: {manifest['track']}")
    lines.append("subject:")
    lines.append(f"  kind: {manifest['subject']['kind']}")
    lines.append(f"  name: {manifest['subject']['name']}")
    lines.append(f"description: {manifest['description']}")
    lines.append("provenance:")
    provenance = manifest["provenance"]
    lines.append(f"  kind: {provenance['kind']}")
    if provenance["kind"] == "SANITIZED_REGRESSION":
        lines.append(f"  source_reference: {json.dumps(str(provenance['source_reference']))}")
        lines.append("  sanitization_policy:")
        lines.append(f"    policy_id: {provenance['sanitization_policy']['policy_id']}")
        lines.append(f"    version: {provenance['sanitization_policy']['version']}")
        lines.append("  approval:")
        lines.append(f"    authority: {provenance['approval']['authority']}")
        lines.append(f"    reference: {json.dumps(str(provenance['approval']['reference']))}")
    lines.append("contract_bindings:")
    for binding in manifest["contract_bindings"]:
        lines.append(f"  - binding_id: {binding['binding_id']}")
        lines.append(f"    owner: {binding['owner']}")
        lines.append(f"    contract_id: {binding['contract_id']}")
        lines.append(f"    semantic_version: {binding['semantic_version']}")
    lines.append("canonical_encoding_version: 1")
    lines.append("input_assets:")
    if manifest["input_assets"]:
        for asset in manifest["input_assets"]:
            lines.append(f"  - logical_name: {asset['logical_name']}")
            if "path" in asset:
                lines.append(f"    path: {asset['path']}")
            else:
                lines.append(f"    ref: {asset['ref']}")
            lines.append(f"    media_type: {asset['media_type']}")
            lines.append(f"    size_bytes: {asset['size_bytes']}")
            lines.append(f"    raw_sha256: {asset['raw_sha256']}")
            if asset.get("content_binding") is not None:
                binding = asset["content_binding"]
                lines.append("    content_binding:")
                lines.append(f"      contract_binding_id: {binding['contract_binding_id']}")
                lines.append(f"      schema_id: {binding['schema_id']}")
                lines.append(f"      schema_version: {binding['schema_version']}")
                if binding.get("canonical_encoding_version") is not None:
                    lines.append(
                        f"      canonical_encoding_version: {binding['canonical_encoding_version']}"
                    )
                lines.append(f"    content_digest: {asset['content_digest']}")
    else:
        lines.append("  []")
    owner_closure = manifest.get("owner_closure_assets")
    if owner_closure is not None:
        lines.append("owner_closure_assets:")
        for asset in owner_closure:
            lines.append(f"  - logical_name: {asset['logical_name']}")
            lines.append(f"    path: {asset['path']}")
            lines.append(f"    media_type: {asset['media_type']}")
            lines.append(f"    size_bytes: {asset['size_bytes']}")
            lines.append(f"    raw_sha256: {asset['raw_sha256']}")
    lines.append("stimulus:")
    stimulus = manifest["stimulus"]
    lines.append(f"  contract_binding_id: {stimulus['contract_binding_id']}")
    lines.append("  payload:")
    payload = stimulus["payload"]
    storage = str(payload["storage"])
    lines.append(f"    storage: {storage}")
    if storage == "inline":
        value_json = json.dumps(payload["value"], separators=(",", ":"), ensure_ascii=False)
        lines.append(f"    value: {value_json}")
    elif storage == "asset-ref":
        lines.append(f"    logical_name: {payload['logical_name']}")
    else:
        raise ValueError(f"unsupported stimulus storage in test helper: {storage}")
    if "fault" in manifest:
        fault = manifest["fault"]
        lines.append("fault:")
        lines.append(f"  contract_binding_id: {fault['contract_binding_id']}")
        lines.append(f"  target: {fault['target']}")
        lines.append(f"  boundary: {fault['boundary']}")
        lines.append(f"  action: {fault['action']}")
        lines.append(f"  occurrence: {fault['occurrence']}")
        if "parameters" in fault:
            lines.append(
                f"  parameters: {json.dumps(fault['parameters'], separators=(',', ':'), ensure_ascii=False)}"
            )
        recovery = manifest["recovery_trigger"]
        lines.append("recovery_trigger:")
        lines.append(f"  contract_binding_id: {recovery['contract_binding_id']}")
        lines.append(f"  kind: {recovery['kind']}")
        lines.append(f"  repetitions: {recovery['repetitions']}")
        if "parameters" in recovery:
            lines.append(
                "  parameters: "
                f"{json.dumps(recovery['parameters'], separators=(',', ':'), ensure_ascii=False)}"
            )
    lines.append(f"input_digest: {manifest['input_digest']}")
    lines.append(f"fixture_content_digest: {manifest['fixture_content_digest']}")
    lines.append("expected:")
    for entry in manifest["expected"]:
        lines.append(f"  - expectation_id: {entry['expectation_id']}")
        lines.append(f"    kind: {entry['kind']}")
        lines.append(f"    path: {entry['path']}")
        lines.append(f"    size_bytes: {entry['size_bytes']}")
        lines.append(f"    raw_sha256: {entry['raw_sha256']}")
        lines.append("    contract_binding:")
        lines.append(f"      owner: {entry['contract_binding']['owner']}")
        lines.append(f"      contract_id: {entry['contract_binding']['contract_id']}")
        lines.append(f"      semantic_version: {entry['contract_binding']['semantic_version']}")
        lines.append(f"    content_digest: {entry['content_digest']}")
    lines.append("required_profiles:")
    for profile in manifest["required_profiles"]:
        lines.append(f"  - {profile}")
    lines.append(f"legacy_classification: {manifest['legacy_classification']}")
    return "\n".join(lines) + "\n"


def build_valid_data_scenario(root: Path) -> dict[str, Any]:
    manifest, golden_bytes = base_manifest(track="data")
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest


def build_valid_command_scenario(root: Path) -> dict[str, Any]:
    manifest, golden_bytes = base_manifest(track="command", scenario_suffix="submit")
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest


def build_valid_recovery_scenario(root: Path) -> dict[str, Any]:
    manifest, golden_bytes = base_manifest(
        track="recovery",
        scenario_suffix="timeout-success",
        kind="recovery",
        include_fault=True,
    )
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest


def structured_input_asset(
    *,
    logical_name: str = "table",
    relative_path: str = "input/table.json",
    value: Any | None = None,
    shared_logical_name: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    payload_value = value if value is not None else {"rows": [{"id": 1}]}
    payload = json.dumps(payload_value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    contract_binding = {
        "owner": "test-capability",
        "contract_id": "gateway-vnext.test-contract",
        "semantic_version": "1.0.0",
    }
    content_binding = {
        "contract_binding_id": "subject",
        "schema_id": "gateway-vnext.test-table.v1",
        "schema_version": 1,
        "canonical_encoding_version": 1,
    }
    content_digest = compute_structured_asset_content_digest(
        payload,
        content_binding=content_binding,
        contract_binding=contract_binding,
    )
    raw_sha256 = raw_blob_digest(payload).value
    asset: dict[str, Any] = {
        "logical_name": logical_name,
        "media_type": "application/json",
        "size_bytes": len(payload),
        "raw_sha256": raw_sha256,
        "content_binding": content_binding,
        "content_digest": content_digest,
    }
    if shared_logical_name is not None:
        digest_hex = raw_sha256.removeprefix("sha256:")
        asset["ref"] = f"sha256/{digest_hex}/{shared_logical_name}"
    else:
        asset["path"] = relative_path
    return payload, asset


def build_valid_structured_input_scenario(root: Path) -> dict[str, Any]:
    manifest, golden_bytes = base_manifest(scenario_suffix="structured-input")
    payload, asset = structured_input_asset()
    manifest["input_assets"] = [asset]
    root.mkdir(parents=True, exist_ok=True)
    (root / "input").mkdir()
    (root / asset["path"]).write_bytes(payload)
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest


def ensure_shared_structured_asset(
    shared_root: Path,
    *,
    shared_logical_name: str = "table-json",
) -> tuple[bytes, dict[str, Any]]:
    payload, asset = structured_input_asset(shared_logical_name=shared_logical_name)
    digest_hex = str(asset["raw_sha256"]).removeprefix("sha256:")
    asset_dir = shared_root / "sha256" / digest_hex
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / shared_logical_name).write_bytes(payload)
    return payload, asset


def build_valid_shared_structured_input_scenario(
    root: Path,
    *,
    shared_root: Path,
) -> dict[str, Any]:
    _payload, asset = ensure_shared_structured_asset(shared_root)
    manifest, golden_bytes = base_manifest(scenario_suffix="shared-structured-input")
    manifest["input_assets"] = [asset]
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest


def build_valid_owner_closure_v2_scenario(root: Path) -> dict[str, Any]:
    manifest, golden_bytes = base_manifest(scenario_suffix="owner-closure-v2")
    manifest["manifest_schema_version"] = 2
    input_bytes = b"owner-closure-v2-input"
    owner_bytes = b'{"anchor":true}'
    manifest["input_assets"] = [
        {
            "logical_name": "payload",
            "path": "input/payload.bin",
            "media_type": "application/octet-stream",
            "size_bytes": len(input_bytes),
            "raw_sha256": raw_blob_digest(input_bytes).value,
        }
    ]
    manifest["owner_closure_assets"] = [
        {
            "logical_name": "oracle-anchor",
            "path": "input/oracle-anchor.json",
            "media_type": "application/json",
            "size_bytes": len(owner_bytes),
            "raw_sha256": raw_blob_digest(owner_bytes).value,
        }
    ]
    root.mkdir(parents=True, exist_ok=True)
    (root / "input").mkdir(exist_ok=True)
    (root / "input" / "payload.bin").write_bytes(input_bytes)
    (root / "input" / "oracle-anchor.json").write_bytes(owner_bytes)
    write_scenario_tree(root, manifest, golden_bytes=golden_bytes)
    return manifest
