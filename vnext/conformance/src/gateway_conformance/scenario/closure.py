"""Scenario filesystem closure validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gateway_shared_kernel import raw_blob_digest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import (
    SCENARIO_MANIFEST_NAME,
    SCENARIO_MAX_BYTES,
    SHARED_ASSET_MAX_BYTES,
    SHARED_ROOT,
)
from gateway_conformance.sanitize import relative_label
from gateway_conformance.schemas import validate_golden_envelope
from gateway_conformance.secure_io import SecureRoot
from gateway_conformance.scenario.identity import assert_lower_kebab
from gateway_conformance.strict_json import loads_strict_json_bytes


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    logical_name: str
    relative_path: str
    raw: bytes
    media_type: str
    structured: bool
    content_digest: str | None


@dataclass(frozen=True, slots=True)
class ScenarioClosure:
    root: Path
    manifest: dict[str, Any]
    declared_paths: dict[str, bytes]
    assets: dict[str, ResolvedAsset]
    owner_closure_assets: dict[str, ResolvedAsset]
    golden_envelopes: dict[str, dict[str, Any]]


def validate_posix_relative_path(path: str, *, label: str) -> None:
    if path.startswith("/"):
        raise ConformanceValidationError(f"{label} must not be absolute")
    if "\\" in path:
        raise ConformanceValidationError(f"{label} must use POSIX separators")
    if ".." in Path(path).parts:
        raise ConformanceValidationError(f"{label} must not contain parent segments")


def shared_ref_to_relative(ref: str) -> tuple[str, str]:
    parts = ref.split("/")
    if len(parts) != 3 or parts[0] != "sha256":
        raise ConformanceValidationError("shared asset ref must be sha256/<digest>/<logical-name>")
    digest_hex, logical_name = parts[1], parts[2]
    if len(digest_hex) != 64 or any(ch not in "0123456789abcdef" for ch in digest_hex):
        raise ConformanceValidationError("shared asset ref digest must be lowercase hex")
    assert_lower_kebab(logical_name, label="shared asset logical name")
    relative = f"sha256/{digest_hex}/{logical_name}"
    return relative, digest_hex


def _assert_shared_ref_matches_raw(ref: str, raw_sha256: str) -> None:
    _, digest_hex = shared_ref_to_relative(ref)
    expected = raw_sha256.removeprefix("sha256:")
    if digest_hex != expected:
        raise ConformanceValidationError("shared asset ref digest must match raw_sha256")


def load_scenario_closure(root: Path) -> ScenarioClosure:
    requested = Path(root).expanduser()
    with SecureRoot.open_path(requested, label="scenario root") as scenario_root:
        return _load_scenario_closure_with_root(requested, scenario_root)


def _load_scenario_closure_with_root(requested: Path, scenario_root: SecureRoot) -> ScenarioClosure:
    from gateway_conformance.strict_yaml import loads_strict_yaml_bytes

    manifest_raw = scenario_root.read_regular_file(
        SCENARIO_MANIFEST_NAME,
        label=SCENARIO_MANIFEST_NAME,
        max_bytes=SCENARIO_MAX_BYTES,
    )
    scenario_root.assert_path_unchanged()
    manifest = loads_strict_yaml_bytes(manifest_raw)

    declared_paths: dict[str, bytes] = {SCENARIO_MANIFEST_NAME: manifest_raw}
    local_paths: dict[str, bytes] = {SCENARIO_MANIFEST_NAME: manifest_raw}
    assets: dict[str, ResolvedAsset] = {}
    seen_closure_paths: set[str] = set()
    shared_root: SecureRoot | None = None

    try:
        for asset in manifest["input_assets"]:
            logical_name = str(asset["logical_name"])
            if "path" in asset:
                scenario_root.assert_path_unchanged()
                rel = str(asset["path"])
                validate_posix_relative_path(rel, label=f"input_assets[{logical_name}].path")
                label = relative_label(requested, requested / rel)
                raw = scenario_root.read_regular_file(
                    rel, label=label, max_bytes=SCENARIO_MAX_BYTES
                )
                if rel in seen_closure_paths:
                    raise ConformanceValidationError(f"duplicate declared closure path: {rel}")
                seen_closure_paths.add(rel)
                declared_paths[rel] = raw
                local_paths[rel] = raw
            else:
                if shared_root is None:
                    shared_root = SecureRoot.open_path(SHARED_ROOT, label="shared asset root")
                ref = str(asset["ref"])
                _assert_shared_ref_matches_raw(ref, str(asset["raw_sha256"]))
                rel, _digest_hex = shared_ref_to_relative(ref)
                raw = shared_root.read_regular_file(
                    rel, label=ref, max_bytes=SHARED_ASSET_MAX_BYTES
                )
                if rel in seen_closure_paths:
                    raise ConformanceValidationError(f"duplicate declared closure path: {rel}")
                seen_closure_paths.add(rel)
                # Shared assets participate in identity maps but not local size budget.
                declared_paths[rel] = raw

            expected_size = int(asset["size_bytes"])
            expected_hash = str(asset["raw_sha256"])
            if len(raw) != expected_size:
                raise ConformanceValidationError(f"input asset {logical_name} size_bytes mismatch")
            if raw_blob_digest(raw).value != expected_hash:
                raise ConformanceValidationError(f"input asset {logical_name} raw_sha256 mismatch")

            structured = asset.get("content_binding") is not None
            declared_content_digest: str | None = None
            if structured:
                content_binding = asset["content_binding"]
                if content_binding.get("canonical_encoding_version") != 1:
                    raise ConformanceValidationError(
                        f"input asset {logical_name} requires canonical_encoding_version 1"
                    )
                declared_content_digest = str(asset["content_digest"])
                binding_id = str(content_binding["contract_binding_id"])
                contract_binding = next(
                    item
                    for item in manifest["contract_bindings"]
                    if str(item["binding_id"]) == binding_id
                )
                from gateway_conformance.owner.validate import (
                    compute_structured_asset_content_digest,
                )

                computed_content_digest = compute_structured_asset_content_digest(
                    raw,
                    content_binding=content_binding,
                    contract_binding=contract_binding,
                )
                if declared_content_digest != computed_content_digest:
                    raise ConformanceValidationError(
                        f"input asset {logical_name} content_digest mismatch"
                    )

            assets[logical_name] = ResolvedAsset(
                logical_name=logical_name,
                relative_path=rel,
                raw=raw,
                media_type=str(asset["media_type"]),
                structured=structured,
                content_digest=declared_content_digest,
            )
    finally:
        if shared_root is not None:
            shared_root.close()

    owner_closure_assets: dict[str, ResolvedAsset] = {}
    for asset in manifest.get("owner_closure_assets", []):
        logical_name = str(asset["logical_name"])
        if "path" not in asset:
            raise ConformanceValidationError("owner_closure_assets must use scenario-local path")
        if asset.get("content_binding") is not None:
            raise ConformanceValidationError("owner_closure_asset must not declare content_binding")
        scenario_root.assert_path_unchanged()
        rel = str(asset["path"])
        validate_posix_relative_path(rel, label=f"owner_closure_assets[{logical_name}].path")
        label = relative_label(requested, requested / rel)
        raw = scenario_root.read_regular_file(rel, label=label, max_bytes=SCENARIO_MAX_BYTES)
        if rel in seen_closure_paths:
            raise ConformanceValidationError(f"duplicate declared closure path: {rel}")
        seen_closure_paths.add(rel)
        declared_paths[rel] = raw
        local_paths[rel] = raw
        expected_size = int(asset["size_bytes"])
        expected_hash = str(asset["raw_sha256"])
        if len(raw) != expected_size:
            raise ConformanceValidationError(
                f"owner closure asset {logical_name} size_bytes mismatch"
            )
        if raw_blob_digest(raw).value != expected_hash:
            raise ConformanceValidationError(
                f"owner closure asset {logical_name} raw_sha256 mismatch"
            )
        owner_closure_assets[logical_name] = ResolvedAsset(
            logical_name=logical_name,
            relative_path=rel,
            raw=raw,
            media_type=str(asset["media_type"]),
            structured=False,
            content_digest=None,
        )

    golden_envelopes: dict[str, dict[str, Any]] = {}
    for entry in manifest["expected"]:
        scenario_root.assert_path_unchanged()
        expectation_id = str(entry["expectation_id"])
        rel = str(entry["path"])
        validate_posix_relative_path(rel, label=f"expected[{expectation_id}].path")
        if rel in seen_closure_paths:
            raise ConformanceValidationError(f"duplicate declared closure path: {rel}")
        seen_closure_paths.add(rel)
        label = relative_label(requested, requested / rel)
        raw = scenario_root.read_regular_file(rel, label=label, max_bytes=SCENARIO_MAX_BYTES)
        declared_paths[rel] = raw
        local_paths[rel] = raw
        expected_size = int(entry["size_bytes"])
        expected_hash = str(entry["raw_sha256"])
        if len(raw) != expected_size:
            raise ConformanceValidationError(f"expected asset {expectation_id} size_bytes mismatch")
        if raw_blob_digest(raw).value != expected_hash:
            raise ConformanceValidationError(f"expected asset {expectation_id} raw_sha256 mismatch")
        try:
            envelope = loads_strict_json_bytes(raw)
        except ConformanceValidationError as exc:
            raise ConformanceValidationError(
                f"expected asset {expectation_id} is not valid strict JSON"
            ) from exc
        validate_golden_envelope(envelope)
        golden_envelopes[expectation_id] = envelope

    scenario_root.assert_path_unchanged()
    _assert_no_undeclared_files(scenario_root, local_paths)
    total_bytes = sum(len(data) for data in local_paths.values())
    if total_bytes > SCENARIO_MAX_BYTES:
        raise ConformanceValidationError("scenario closure exceeds 1 MiB limit")

    return ScenarioClosure(
        root=requested,
        manifest=manifest,
        declared_paths=declared_paths,
        assets=assets,
        owner_closure_assets=owner_closure_assets,
        golden_envelopes=golden_envelopes,
    )


def _assert_no_undeclared_files(scenario_root: SecureRoot, local_paths: dict[str, bytes]) -> None:
    allowed_dirs = frozenset({"input", "expected"})
    declared_set = set(local_paths.keys())

    for rel in scenario_root.iter_regular_files():
        if rel not in declared_set:
            raise ConformanceValidationError(f"undeclared file in scenario closure: {rel}")

    for entry in scenario_root.iter_top_level_names():
        if entry == SCENARIO_MANIFEST_NAME:
            continue
        if entry in allowed_dirs:
            continue
        raise ConformanceValidationError(f"undeclared top-level entry: {entry}")
