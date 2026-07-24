"""Scenario input and fixture content digest computation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from gateway_shared_kernel import DigestKind, raw_blob_digest, semantic_digest
from gateway_shared_kernel.framing import encode_collection
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.types import CollectionSemantics

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.closure import ResolvedAsset, ScenarioClosure


def _digest_ref_to_raw(digest_ref: str) -> bytes:
    if not digest_ref.startswith("sha256:"):
        raise ConformanceValidationError("content_digest must be sha256 wire form")
    return bytes.fromhex(digest_ref.removeprefix("sha256:"))


def _content_binding_projection(asset: dict[str, Any]) -> dict[str, Any]:
    binding = asset["content_binding"]
    projected = {
        "contract_binding_id": binding["contract_binding_id"],
        "schema_id": binding["schema_id"],
        "schema_version": binding["schema_version"],
    }
    if binding.get("canonical_encoding_version") is not None:
        projected["canonical_encoding_version"] = binding["canonical_encoding_version"]
    return projected


def _manifest_projection_for_fixture(manifest: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(manifest)
    projected.pop("input_digest", None)
    projected.pop("fixture_content_digest", None)
    assets = []
    for asset in projected["input_assets"]:
        item = dict(asset)
        if item.get("content_binding") is not None:
            item.pop("size_bytes", None)
            item.pop("raw_sha256", None)
        assets.append(item)
    projected["input_assets"] = assets
    expected = []
    for entry in projected["expected"]:
        item = dict(entry)
        item.pop("size_bytes", None)
        item.pop("raw_sha256", None)
        expected.append(item)
    projected["expected"] = expected
    return projected


def _input_projection(manifest: dict[str, Any], assets: dict[str, ResolvedAsset]) -> dict[str, Any]:
    referenced_bindings = {str(manifest["stimulus"]["contract_binding_id"])}
    if "fault" in manifest:
        referenced_bindings.add(str(manifest["fault"]["contract_binding_id"]))
    if "recovery_trigger" in manifest:
        referenced_bindings.add(str(manifest["recovery_trigger"]["contract_binding_id"]))

    bindings = [
        item
        for item in manifest["contract_bindings"]
        if str(item["binding_id"]) in referenced_bindings
    ]
    input_assets = []
    for asset in manifest["input_assets"]:
        logical_name = str(asset["logical_name"])
        resolved = assets[logical_name]
        item: dict[str, Any] = {"logical_name": logical_name}
        if resolved.structured:
            item["content_binding"] = _content_binding_projection(asset)
            item["content_digest"] = resolved.content_digest
        else:
            item["raw_identity"] = raw_blob_digest(resolved.raw).value
        input_assets.append(item)
    payload: dict[str, Any] = {
        "contract_bindings": bindings,
        "stimulus": manifest["stimulus"],
        "input_assets": input_assets,
    }
    if "fault" in manifest:
        payload["fault"] = manifest["fault"]
    if "recovery_trigger" in manifest:
        payload["recovery_trigger"] = manifest["recovery_trigger"]
    return payload


def _closure_entries(closure: ScenarioClosure) -> list[tuple[bytes, bytes]]:
    expected_paths = {str(item["path"]) for item in closure.manifest["expected"]}
    assets_by_path = {asset.relative_path: asset for asset in closure.assets.values()}

    entries: list[tuple[bytes, bytes]] = []
    for rel_path, raw in sorted(
        closure.declared_paths.items(), key=lambda item: item[0].encode("utf-8")
    ):
        if rel_path == "scenario.yaml" or rel_path in expected_paths:
            continue
        resolved = assets_by_path.get(rel_path)
        if resolved is not None and resolved.structured:
            if resolved.content_digest is None:
                raise ConformanceValidationError(
                    f"structured asset at {rel_path} missing content_digest"
                )
            identity = _digest_ref_to_raw(resolved.content_digest)
        else:
            identity = raw_blob_digest(raw).raw_digest
        entries.append((rel_path.encode("utf-8"), identity))

    for expectation_id, envelope in closure.golden_envelopes.items():
        rel = next(
            str(item["path"])
            for item in closure.manifest["expected"]
            if str(item["expectation_id"]) == expectation_id
        )
        entries.append((rel.encode("utf-8"), _digest_ref_to_raw(str(envelope["content_digest"]))))
    return entries


def _digest_from_projection(
    projection: dict[str, Any], entries: list[tuple[bytes, bytes]], *, kind: DigestKind
) -> str:
    manifest_bytes = canonicalize_json_value(projection)
    keyed_entries: list[tuple[bytes, bytes]] = [(b"manifest", manifest_bytes)]
    keyed_entries.extend(entries)
    collection = encode_collection(CollectionSemantics.KEYED_COLLECTION, entries=keyed_entries)
    return semantic_digest(kind, collection.collection_frame).digest_ref.value


def compute_input_digest(manifest: dict[str, Any], assets: dict[str, ResolvedAsset]) -> str:
    projection = _input_projection(manifest, assets)
    return _digest_from_projection(projection, [], kind=DigestKind.SCENARIO_INPUT)


def compute_fixture_content_digest(closure: ScenarioClosure) -> str:
    manifest_projection = _manifest_projection_for_fixture(closure.manifest)
    entries = _closure_entries(closure)
    return _digest_from_projection(
        manifest_projection,
        entries,
        kind=DigestKind.SCENARIO_FIXTURE,
    )


def assert_digest_closure(closure: ScenarioClosure) -> None:
    manifest = closure.manifest
    computed_input = compute_input_digest(manifest, closure.assets)
    if str(manifest["input_digest"]) != computed_input:
        raise ConformanceValidationError("input_digest mismatch")
    computed_fixture = compute_fixture_content_digest(closure)
    if str(manifest["fixture_content_digest"]) != computed_fixture:
        raise ConformanceValidationError("fixture_content_digest mismatch")
