"""Deterministic Bundle assembly and final artifact closure."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    artifact_ref_from_dict,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.bundle_assembly._digest import (
    closure_bytes,
    closure_digest,
    compute_bundle_digest,
    manifest_bytes,
    manifest_semantic_payload,
)
from gateway_backend.capabilities.bundle_assembly._refs import (
    collect_surface_refs,
    validate_bundle_ref,
)
from gateway_backend.capabilities.bundle_assembly.contracts import (
    BUNDLE_CLOSURE_MEDIA_TYPE,
    BUNDLE_CONTRACT_VERSION,
    BUNDLE_MANIFEST_MEDIA_TYPE,
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleArtifactManifest,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleAssemblyPolicy,
    BundleAssemblyResult,
    BundleAssemblyStatus,
    BundleClosureEntry,
    BundlePair,
    BundlePairFailure,
    BundlePairInput,
    BundleProfile,
    BundleSummary,
    ComparisonBundle,
)
from gateway_backend.capabilities.surface_assembly import (
    compute_surface_digest,
    rewrite_surface_refs,
    validate_surface,
)
from gateway_backend.capabilities.surface_assembly.contracts import (
    ComparisonSurface,
    SurfaceAssemblyStatus,
)


class BundleAssemblyError(ValueError):
    """Bundle input, closure or publication failed validation."""


class BundleCancelled(Exception):
    """Bundle assembly was cancelled before its publication boundary."""


@dataclass(frozen=True, slots=True)
class _PlannedArtifact:
    source_ref: ArtifactRef
    final_ref: ArtifactRef
    raw_bytes: bytes
    binding: BundleArtifactBinding


@dataclass(frozen=True, slots=True)
class _PublishedPair:
    pair: BundlePair
    surface: ComparisonSurface
    surface_bytes: bytes
    surface_ref: ArtifactRef


def assemble_bundle(
    request: BundleAssemblyInput,
    *,
    source_store: ArtifactStorePort,
    destination_store: ArtifactStorePort | None = None,
    policy: BundleAssemblyPolicy | None = None,
    context: BundleAssemblyContext | None = None,
) -> BundleAssemblyResult:
    """Assemble a replayable bundle without exposing a partial final closure."""

    if type(request) is not BundleAssemblyInput:
        raise TypeError("request must be BundleAssemblyInput")
    limits = policy or request.artifact_policy or BundleAssemblyPolicy()
    control = context or BundleAssemblyContext()
    target_store = source_store if destination_store is None else destination_store
    started = monotonic()

    def checkpoint() -> None:
        control.checkpoint()
        if control.cancel_requested():
            raise BundleCancelled
        if monotonic() - started > limits.max_bundle_wall_time_seconds:
            raise BundleAssemblyError("BUNDLE_WALL_TIME_EXCEEDED")

    try:
        checkpoint()
        _validate_shape(request)
        active_pairs, failures = _select_pairs(request.pairs)
        required_failures = tuple(item for item in failures if item.required)
        if required_failures:
            raise BundleAssemblyError(_failure_message(required_failures))

        bindings = _collect_bindings(active_pairs, request.shared_artifacts)
        source_by_ref = {item.source_ref: item for item in bindings}
        for pair_input, surface in active_pairs:
            checkpoint()
            surface_refs = collect_surface_refs(surface)
            missing = [ref for ref in surface_refs if ref not in source_by_ref]
            if missing:
                raise BundleAssemblyError(
                    f"PAIR_{pair_input.pair_id}_MISSING_CLOSURE_REFS:{len(missing)}"
                )

        planned_by_source = _plan_artifacts(bindings, source_store, checkpoint)
        replacement_map = {item.source_ref: item.final_ref for item in planned_by_source.values()}
        published_pairs = _rewrite_pairs(
            active_pairs,
            replacement_map,
            checkpoint,
        )

        generated: list[_PlannedArtifact] = list(planned_by_source.values())
        used_paths = {item.logical_path for item in bindings}
        for published in published_pairs:
            surface_binding = BundleArtifactBinding(
                source_ref=published.surface_ref,
                logical_path=f"pairs/{published.pair.pair_id}/comparison-surface.json",
                kind=BundleArtifactKind.SURFACE,
                pair_id=published.pair.pair_id,
            )
            if surface_binding.logical_path in used_paths:
                raise BundleAssemblyError("SURFACE_LOGICAL_PATH_COLLISION")
            used_paths.add(surface_binding.logical_path)
            generated.append(
                _PlannedArtifact(
                    source_ref=published.surface_ref,
                    final_ref=published.surface_ref,
                    raw_bytes=published.surface_bytes,
                    binding=surface_binding,
                )
            )

        generated = _deduplicate_generated(generated)
        closure = _closure_manifest(generated)
        status = BundleAssemblyStatus.DEGRADED if failures else BundleAssemblyStatus.READY
        diagnostics = tuple(
            sorted(
                message
                for failure in failures
                for message in failure.diagnostics
            )
        )
        pairs = tuple(item.pair for item in published_pairs)
        bundle_digest = compute_bundle_digest(
            profile=request.bundle_profile,
            status=status,
            inputs=request.inputs,
            pairs=pairs,
            failed_pairs=failures,
            closure=closure,
            diagnostics=diagnostics,
        )
        semantic_manifest_digest = raw_blob_digest(
            canonicalize_json_value(
                manifest_semantic_payload(
                    profile=request.bundle_profile,
                    status=status,
                    inputs=request.inputs,
                    pairs=pairs,
                    failed_pairs=failures,
                    closure=closure,
                    diagnostics=diagnostics,
                )
            )
        )
        closure_manifest_digest = closure_digest(closure)
        manifest_raw = manifest_bytes(
            profile=request.bundle_profile,
            status=status,
            inputs=request.inputs,
            pairs=pairs,
            failed_pairs=failures,
            closure=closure,
            closure_manifest_digest=closure_manifest_digest,
            bundle_digest=bundle_digest,
            diagnostics=diagnostics,
        )
        closure_raw = closure_bytes(
            bundle_digest=bundle_digest,
            closure=closure,
            manifest_digest=semantic_manifest_digest,
        )
        if len(manifest_raw) > limits.max_bundle_manifest_json_bytes:
            raise BundleAssemblyError("BUNDLE_MANIFEST_JSON_BUDGET_EXCEEDED")
        if len(closure_raw) > limits.max_bundle_closure_json_bytes:
            raise BundleAssemblyError("BUNDLE_CLOSURE_JSON_BUDGET_EXCEEDED")

        checkpoint()
        final_artifacts = [
            (item.raw_bytes, item.final_ref)
            for item in generated
        ]
        for raw_bytes, ref in final_artifacts:
            target_store.put(raw_bytes, ref)
            _verify_store_bytes(target_store, ref, raw_bytes)
        closure_ref = put_with_built_ref(
            target_store,
            closure_raw,
            artifact_id=_bundle_artifact_id("closure", closure_raw),
            media_type=BUNDLE_CLOSURE_MEDIA_TYPE,
        )
        manifest_ref = put_with_built_ref(
            target_store,
            manifest_raw,
            artifact_id=_bundle_artifact_id("manifest", manifest_raw),
            media_type=BUNDLE_MANIFEST_MEDIA_TYPE,
        )
        _verify_store_bytes(target_store, closure_ref, closure_raw)
        _verify_store_bytes(target_store, manifest_ref, manifest_raw)
        checkpoint()

        summary = BundleSummary(
            pair_count=len(request.pairs),
            published_pair_count=len(pairs),
            degraded_pair_count=len(failures),
            artifact_count=len(generated),
            diagnostics_count=len(diagnostics),
        )
        bundle = ComparisonBundle(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_digest=bundle_digest,
            bundle_id=_bundle_id(bundle_digest),
            bundle_profile=request.bundle_profile,
            status=status,
            inputs=request.inputs,
            pairs=pairs,
            failed_pairs=failures,
            summary=summary,
            manifest_ref=manifest_ref,
            artifact_closure_ref=closure_ref,
            diagnostics=diagnostics,
        )
        validate_bundle(bundle, target_store)
        return BundleAssemblyResult(
            status=status,
            bundle=bundle,
            manifest_ref=manifest_ref,
            artifact_closure_ref=closure_ref,
            referenced_artifacts=tuple(
                sorted(
                    {item.final_ref for item in generated} | {manifest_ref, closure_ref},
                    key=lambda ref: (ref.artifact_id, ref.raw_sha256.value),
                )
            ),
            diagnostics=diagnostics,
        )
    except BundleCancelled:
        return BundleAssemblyResult(
            status=BundleAssemblyStatus.CANCELLED,
            diagnostics=("BUNDLE_ASSEMBLY_CANCELLED",),
        )
    except Exception as exc:
        return BundleAssemblyResult(
            status=BundleAssemblyStatus.FAILED,
            diagnostics=(str(exc) or type(exc).__name__,),
        )


def validate_bundle(bundle: ComparisonBundle, store: ArtifactStorePort) -> None:
    if type(bundle) is not ComparisonBundle:
        raise TypeError("bundle must be ComparisonBundle")
    manifest_raw = store.locate(bundle.manifest_ref)
    closure_raw = store.locate(bundle.artifact_closure_ref)
    if raw_blob_digest(manifest_raw) != bundle.manifest_ref.raw_sha256:
        raise BundleAssemblyError("BUNDLE_MANIFEST_REF_DIGEST_MISMATCH")
    if raw_blob_digest(closure_raw) != bundle.artifact_closure_ref.raw_sha256:
        raise BundleAssemblyError("BUNDLE_CLOSURE_REF_DIGEST_MISMATCH")
    manifest = _json_object(manifest_raw, "bundle manifest")
    closure_document = _json_object(closure_raw, "bundle closure")
    _require_exact_keys(
        manifest,
        {
            "bundle_contract_version",
            "bundle_digest",
            "bundle_profile",
            "closure",
            "closure_entries",
            "closure_manifest_digest",
            "diagnostics",
            "failed_pairs",
            "inputs",
            "pairs",
            "status",
        },
        "BUNDLE_MANIFEST_FIELDS_INVALID",
    )
    _require_exact_keys(
        closure_document,
        {
            "bundle_contract_version",
            "bundle_digest",
            "bundle_manifest_digest",
            "closure_entries",
            "entries",
        },
        "BUNDLE_CLOSURE_FIELDS_INVALID",
    )
    if canonicalize_json_value(manifest) != manifest_raw:
        raise BundleAssemblyError("BUNDLE_MANIFEST_NOT_CANONICAL")
    if canonicalize_json_value(closure_document) != closure_raw:
        raise BundleAssemblyError("BUNDLE_CLOSURE_NOT_CANONICAL")
    entries = _entries_from_document(closure_document)
    closure = BundleArtifactManifest(entries=entries)
    manifest_entries = _entries_from_document(manifest)
    if manifest_entries != entries:
        raise BundleAssemblyError("BUNDLE_MANIFEST_CLOSURE_ENTRIES_MISMATCH")
    if manifest.get("bundle_contract_version") != BUNDLE_CONTRACT_VERSION:
        raise BundleAssemblyError("BUNDLE_MANIFEST_CONTRACT_VERSION_MISMATCH")
    if closure_document.get("bundle_contract_version") != BUNDLE_CONTRACT_VERSION:
        raise BundleAssemblyError("BUNDLE_CLOSURE_CONTRACT_VERSION_MISMATCH")
    if manifest.get("bundle_profile") != bundle.bundle_profile.value:
        raise BundleAssemblyError("BUNDLE_MANIFEST_PROFILE_MISMATCH")
    if manifest.get("status") != bundle.status.value:
        raise BundleAssemblyError("BUNDLE_MANIFEST_STATUS_MISMATCH")
    for entry in entries:
        validate_bundle_ref(entry.artifact_ref, label="final closure artifact ref")
        raw = store.locate(entry.artifact_ref)
        _verify_store_bytes(store, entry.artifact_ref, raw)
    expected_closure_digest = closure_digest(closure)
    if manifest.get("closure_manifest_digest") != expected_closure_digest.value:
        raise BundleAssemblyError("BUNDLE_CLOSURE_MANIFEST_DIGEST_MISMATCH")
    if closure_document.get("bundle_digest") != bundle.bundle_digest.value:
        raise BundleAssemblyError("BUNDLE_CLOSURE_BUNDLE_DIGEST_MISMATCH")
    expected_digest = compute_bundle_digest(
        profile=bundle.bundle_profile,
        status=bundle.status,
        inputs=bundle.inputs,
        pairs=bundle.pairs,
        failed_pairs=bundle.failed_pairs,
        closure=closure,
        diagnostics=bundle.diagnostics,
    )
    if expected_digest != bundle.bundle_digest:
        raise BundleAssemblyError("BUNDLE_DIGEST_MISMATCH")
    if manifest.get("bundle_digest") != bundle.bundle_digest.value:
        raise BundleAssemblyError("BUNDLE_MANIFEST_BUNDLE_DIGEST_MISMATCH")
    expected_manifest_payload = manifest_semantic_payload(
        profile=bundle.bundle_profile,
        status=bundle.status,
        inputs=bundle.inputs,
        pairs=bundle.pairs,
        failed_pairs=bundle.failed_pairs,
        closure=closure,
        diagnostics=bundle.diagnostics,
    )
    if any(manifest.get(key) != value for key, value in expected_manifest_payload.items()):
        raise BundleAssemblyError("BUNDLE_MANIFEST_SEMANTIC_PAYLOAD_MISMATCH")
    expected_manifest_digest = raw_blob_digest(
        canonicalize_json_value(expected_manifest_payload)
    )
    if closure_document.get("bundle_manifest_digest") != expected_manifest_digest.value:
        raise BundleAssemblyError("BUNDLE_CLOSURE_MANIFEST_DIGEST_MISMATCH")
    entry_refs = {entry.artifact_ref for entry in entries}
    for pair in bundle.pairs:
        if pair.surface_ref not in entry_refs:
            raise BundleAssemblyError("BUNDLE_SURFACE_MISSING_FROM_CLOSURE")
        surface_raw = store.locate(pair.surface_ref)
        surface_document = _json_object(surface_raw, "surface artifact")
        if surface_document.get("surface_digest") != pair.surface_digest.value:
            raise BundleAssemblyError("BUNDLE_SURFACE_DIGEST_LINK_MISMATCH")
        if surface_document.get("comparison_digest") != pair.comparison_digest.value:
            raise BundleAssemblyError("BUNDLE_SURFACE_COMPARISON_LINK_MISMATCH")


def _validate_shape(request: BundleAssemblyInput) -> None:
    indexes = {item.input_index for item in request.inputs}
    if request.bundle_profile is BundleProfile.SINGLE_PAIR and len(request.pairs) != 1:
        raise BundleAssemblyError("SINGLE_PAIR_REQUIRES_ONE_PAIR")
    if request.bundle_profile is BundleProfile.MULTI_PAIR and len(request.pairs) < 2:
        raise BundleAssemblyError("MULTI_PAIR_REQUIRES_AT_LEAST_TWO_PAIRS")
    if not request.inputs:
        raise BundleAssemblyError("BUNDLE_REQUIRES_INPUTS")
    for pair in request.pairs:
        if pair.before_input_index not in indexes or pair.current_input_index not in indexes:
            raise BundleAssemblyError(f"PAIR_{pair.pair_id}_INPUT_INDEX_MISSING")


def _select_pairs(
    pairs: Iterable[BundlePairInput],
) -> tuple[tuple[tuple[BundlePairInput, ComparisonSurface], ...], tuple[BundlePairFailure, ...]]:
    active: list[tuple[BundlePairInput, ComparisonSurface]] = []
    failures: list[BundlePairFailure] = []
    for pair in pairs:
        result = pair.surface_result
        if result.status is SurfaceAssemblyStatus.CANCELLED:
            raise BundleCancelled
        if result.status is not SurfaceAssemblyStatus.READY or result.surface is None:
            failure = BundlePairFailure(
                pair_id=pair.pair_id,
                required=pair.required,
                diagnostics=tuple(result.diagnostics) or ("SURFACE_NOT_READY",),
            )
            failures.append(failure)
            continue
        active.append((pair, result.surface))
    return tuple(active), tuple(sorted(failures, key=lambda item: item.pair_id))


def _failure_message(failures: Iterable[BundlePairFailure]) -> str:
    return "REQUIRED_PAIR_FAILURE:" + ",".join(item.pair_id for item in failures)


def _collect_bindings(
    active_pairs: Iterable[tuple[BundlePairInput, ComparisonSurface]],
    shared: BundleArtifactClosure,
) -> tuple[BundleArtifactBinding, ...]:
    candidates: list[BundleArtifactBinding] = list(shared.entries)
    for pair, _surface in active_pairs:
        for binding in pair.surface_artifact_closure.entries:
            if binding.shared:
                raise BundleAssemblyError("PAIR_CLOSURE_CANNOT_DECLARE_SHARED_ARTIFACT")
            if binding.pair_id != pair.pair_id:
                raise BundleAssemblyError(f"PAIR_{pair.pair_id}_CLOSURE_SCOPE_MISMATCH")
            candidates.append(binding)
    by_source: dict[ArtifactRef, BundleArtifactBinding] = {}
    by_path: dict[str, BundleArtifactBinding] = {}
    for binding in candidates:
        validate_bundle_ref(binding.source_ref, label="source artifact ref")
        if binding.shared and not binding.logical_path.startswith("shared/"):
            raise BundleAssemblyError("SHARED_ARTIFACT_PATH_MUST_BE_SHARED")
        if binding.pair_id is not None and not binding.logical_path.startswith(
            f"pairs/{binding.pair_id}/"
        ):
            raise BundleAssemblyError("PAIR_ARTIFACT_PATH_SCOPE_MISMATCH")
        previous_source = by_source.get(binding.source_ref)
        if previous_source is not None:
            if previous_source.kind is BundleArtifactKind.SNAPSHOT_TABLE and binding.kind is BundleArtifactKind.SNAPSHOT_TABLE:
                shared_binding = replace(
                    previous_source,
                    logical_path=f"shared/snapshot-tables/{binding.source_ref.raw_sha256.value.removeprefix('sha256:')}.parquet",
                    pair_id=None,
                    shared=True,
                )
                by_source[binding.source_ref] = shared_binding
                by_path[shared_binding.logical_path] = shared_binding
                continue
            if previous_source != binding:
                raise BundleAssemblyError("DUPLICATE_SOURCE_ARTIFACT_REF")
            continue
        previous_path = by_path.get(binding.logical_path)
        if previous_path is not None and previous_path.source_ref != binding.source_ref:
            raise BundleAssemblyError("DUPLICATE_LOGICAL_ARTIFACT_PATH")
        by_source[binding.source_ref] = binding
        by_path[binding.logical_path] = binding
    snapshot_groups: dict[tuple[str, int, str], list[ArtifactRef]] = {}
    for source_ref, binding in by_source.items():
        if binding.kind is BundleArtifactKind.SNAPSHOT_TABLE:
            key = (source_ref.media_type, source_ref.size_bytes, source_ref.raw_sha256.value)
            snapshot_groups.setdefault(key, []).append(source_ref)
    for source_refs in snapshot_groups.values():
        if len(source_refs) < 2:
            continue
        first = by_source[source_refs[0]]
        shared_binding = replace(
            first,
            logical_path=f"shared/snapshot-tables/{source_refs[0].raw_sha256.value.removeprefix('sha256:')}.parquet",
            pair_id=None,
            shared=True,
        )
        for source_ref in source_refs:
            by_source[source_ref] = replace(shared_binding, source_ref=source_ref)
    return tuple(
        sorted(
            by_source.values(),
            key=lambda item: (item.logical_path, item.kind.value, item.source_ref.artifact_id),
        )
    )


def _plan_artifacts(
    bindings: Iterable[BundleArtifactBinding],
    store: ArtifactStorePort,
    checkpoint: Any,
) -> dict[ArtifactRef, _PlannedArtifact]:
    binding_by_source = {item.source_ref: item for item in bindings}
    planned: dict[ArtifactRef, _PlannedArtifact] = {}
    visiting: set[ArtifactRef] = set()

    def plan(source_ref: ArtifactRef) -> _PlannedArtifact:
        if source_ref in planned:
            return planned[source_ref]
        if source_ref in visiting:
            raise BundleAssemblyError("ARTIFACT_REF_DEPENDENCY_CYCLE")
        visiting.add(source_ref)
        checkpoint()
        try:
            raw = store.locate(source_ref)
        except Exception as exc:
            raise BundleAssemblyError("SOURCE_ARTIFACT_NOT_FOUND") from exc
        _verify_store_bytes(store, source_ref, raw)
        rewritten = raw
        if _is_json_ref_bearing(source_ref):
            value = _json_object_or_value(raw)
            if canonicalize_json_value(value) != raw:
                raise BundleAssemblyError("SOURCE_JSON_NOT_CANONICAL")
            dependencies = _embedded_refs(value)
            for dependency in dependencies:
                if dependency not in binding_by_source:
                    raise BundleAssemblyError("EMBEDDED_ARTIFACT_REF_MISSING_FROM_CLOSURE")
                plan(dependency)
            rewritten_value = _rewrite_embedded_refs(value, planned)
            rewritten = canonicalize_json_value(rewritten_value)
        final_ref = _build_final_ref(source_ref, rewritten)
        binding = binding_by_source[source_ref]
        item = _PlannedArtifact(
            source_ref=source_ref,
            final_ref=final_ref,
            raw_bytes=rewritten,
            binding=binding,
        )
        planned[source_ref] = item
        visiting.remove(source_ref)
        return item

    for binding in bindings:
        plan(binding.source_ref)
    return planned


def _rewrite_pairs(
    active_pairs: Iterable[tuple[BundlePairInput, ComparisonSurface]],
    replacements: Mapping[ArtifactRef, ArtifactRef],
    checkpoint: Any,
) -> tuple[_PublishedPair, ...]:
    result: list[_PublishedPair] = []
    for pair_input, source_surface in active_pairs:
        checkpoint()
        validate_surface(source_surface)
        surface = rewrite_surface_refs(source_surface, replacements)
        surface = replace(surface, surface_digest=compute_surface_digest(surface))
        validate_surface(surface)
        surface_bytes = canonicalize_json_value(surface.to_document())
        surface_ref = _build_final_ref(
            ArtifactRef(
                artifact_id=f"surface-source-{surface.surface_digest.value.removeprefix('sha256:')}",
                media_type="application/json",
                size_bytes=len(surface_bytes),
                raw_sha256=raw_blob_digest(surface_bytes),
            ),
            surface_bytes,
        )
        summary = tuple(
            sorted(
                (key, str(value))
                for key, value in surface.summary.to_document().items()
            )
        )
        result.append(
            _PublishedPair(
                pair=BundlePair(
                    pair_id=pair_input.pair_id,
                    before_input_index=pair_input.before_input_index,
                    current_input_index=pair_input.current_input_index,
                    surface_ref=surface_ref,
                    surface_digest=surface.surface_digest,
                    comparison_digest=surface.comparison_digest,
                    risk_evaluation_digest=surface.risk_evaluation_digest,
                    summary=summary,
                ),
                surface=surface,
                surface_bytes=surface_bytes,
                surface_ref=surface_ref,
            )
        )
    return tuple(sorted(result, key=lambda item: item.pair.pair_id))


def _closure_manifest(generated: Iterable[_PlannedArtifact]) -> BundleArtifactManifest:
    entries = tuple(
        BundleClosureEntry(
            logical_path=item.binding.logical_path,
            artifact_ref=item.final_ref,
            kind=item.binding.kind,
            size_bytes=item.final_ref.size_bytes,
            raw_sha256=item.final_ref.raw_sha256,
            pair_id=item.binding.pair_id,
            table_name=item.binding.table_name,
            shared=item.binding.shared,
        )
        for item in generated
    )
    return BundleArtifactManifest(entries=entries)


def _deduplicate_generated(generated: Iterable[_PlannedArtifact]) -> list[_PlannedArtifact]:
    by_path: dict[str, _PlannedArtifact] = {}
    for item in generated:
        previous = by_path.get(item.binding.logical_path)
        if previous is not None:
            if previous.final_ref != item.final_ref or previous.binding.kind is not item.binding.kind:
                raise BundleAssemblyError("DUPLICATE_FINAL_LOGICAL_PATH")
            continue
        by_path[item.binding.logical_path] = item
    return list(by_path.values())


def _is_json_ref_bearing(ref: ArtifactRef) -> bool:
    return "json" in ref.media_type.casefold()


def _json_object(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise BundleAssemblyError(f"{label}_NOT_JSON") from exc
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise BundleAssemblyError(f"{label}_MUST_BE_OBJECT")
    return value


def _json_object_or_value(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except Exception as exc:
        raise BundleAssemblyError("JSON_ARTIFACT_NOT_JSON") from exc


def _require_exact_keys(
    document: dict[str, object], expected: set[str], error: str
) -> None:
    if set(document) != expected:
        raise BundleAssemblyError(error)


def _embedded_refs(value: object) -> tuple[ArtifactRef, ...]:
    found: list[ArtifactRef] = []
    if isinstance(value, dict):
        if set(value) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}:
            try:
                found.append(artifact_ref_from_dict(value))
            except Exception as exc:
                raise BundleAssemblyError("EMBEDDED_ARTIFACT_REF_INVALID") from exc
            return tuple(found)
        for item in value.values():
            found.extend(_embedded_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_embedded_refs(item))
    return tuple(dict.fromkeys(found))


def _rewrite_embedded_refs(value: object, planned: Mapping[ArtifactRef, _PlannedArtifact]) -> object:
    if isinstance(value, dict):
        if set(value) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}:
            source_ref = artifact_ref_from_dict(value)
            return {
                "artifact_id": planned[source_ref].final_ref.artifact_id,
                "media_type": planned[source_ref].final_ref.media_type,
                "size_bytes": planned[source_ref].final_ref.size_bytes,
                "raw_sha256": planned[source_ref].final_ref.raw_sha256.value,
            }
        return {key: _rewrite_embedded_refs(item, planned) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_embedded_refs(item, planned) for item in value]
    return value


def _build_final_ref(source_ref: ArtifactRef, raw_bytes: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=_bundle_artifact_id("artifact", raw_bytes, media_type=source_ref.media_type),
        media_type=source_ref.media_type,
        size_bytes=len(raw_bytes),
        raw_sha256=raw_blob_digest(raw_bytes),
    )


def _bundle_artifact_id(kind: str, raw_bytes: bytes, *, media_type: str = "application/octet-stream") -> str:
    identity_digest = raw_blob_digest(
        canonicalize_json_value(
            {
                "kind": kind,
                "media_type": media_type,
                "raw_sha256": raw_blob_digest(raw_bytes).value,
                "size_bytes": len(raw_bytes),
            }
        )
    )
    return build_artifact_id("bundle", f"{kind}-{identity_digest.value.removeprefix('sha256:')}")


def _bundle_id(bundle_digest: DigestRef) -> str:
    return f"bundle-{bundle_digest.value.removeprefix('sha256:')}"


def _verify_store_bytes(store: ArtifactStorePort, ref: ArtifactRef, raw: bytes) -> None:
    if len(raw) != ref.size_bytes or raw_blob_digest(raw) != ref.raw_sha256:
        raise BundleAssemblyError("ARTIFACT_INTEGRITY_MISMATCH")
    located = store.locate(ref)
    if located != raw:
        raise BundleAssemblyError("ARTIFACT_CHANGED_DURING_PUBLICATION")


def _entries_from_document(document: dict[str, object]) -> tuple[BundleClosureEntry, ...]:
    raw_entries = document.get("closure_entries")
    if type(raw_entries) is not list:
        raise BundleAssemblyError("BUNDLE_CLOSURE_ENTRIES_MISSING")
    result: list[BundleClosureEntry] = []
    for raw_entry in raw_entries:
        if type(raw_entry) is not dict:
            raise BundleAssemblyError("BUNDLE_CLOSURE_ENTRY_INVALID")
        if set(raw_entry) != {
            "artifact_ref",
            "kind",
            "logical_path",
            "pair_id",
            "raw_sha256",
            "shared",
            "size_bytes",
            "table_name",
        }:
            raise BundleAssemblyError("BUNDLE_CLOSURE_ENTRY_INVALID")
        ref_payload = raw_entry.get("artifact_ref")
        if type(ref_payload) is not dict:
            raise BundleAssemblyError("BUNDLE_CLOSURE_REF_INVALID")
        try:
            ref = artifact_ref_from_dict(ref_payload)
            kind = BundleArtifactKind(raw_entry["kind"])
            raw_sha256 = DigestRef(raw_entry["raw_sha256"])
            result.append(
                BundleClosureEntry(
                    logical_path=raw_entry["logical_path"],
                    artifact_ref=ref,
                    kind=kind,
                    size_bytes=raw_entry["size_bytes"],
                    raw_sha256=raw_sha256,
                    pair_id=raw_entry.get("pair_id"),
                    table_name=raw_entry.get("table_name"),
                    shared=raw_entry["shared"],
                )
            )
        except Exception as exc:
            raise BundleAssemblyError("BUNDLE_CLOSURE_ENTRY_INVALID") from exc
    return tuple(result)
