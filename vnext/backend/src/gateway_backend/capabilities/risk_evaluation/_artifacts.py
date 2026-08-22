"""Canonical Risk annotation artifacts and immutable closure validation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactStorePort,
    build_artifact_id,
    put_with_built_ref,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RISK_ANNOTATION_CLOSURE_MEDIA_TYPE,
    RISK_ANNOTATION_CONTRACT_VERSION,
    RISK_ANNOTATION_MANIFEST_MEDIA_TYPE,
    RISK_ANNOTATION_MEDIA_TYPE,
    RiskAnnotation,
    RiskAnnotationArtifact,
    RiskAnnotationClosure,
    RiskAnnotationClosureEntry,
    validate_risk_annotation_documents,
)


ANNOTATION_MEDIA_TYPE = RISK_ANNOTATION_MEDIA_TYPE
ANNOTATION_MANIFEST_MEDIA_TYPE = RISK_ANNOTATION_MANIFEST_MEDIA_TYPE
ANNOTATION_CLOSURE_MEDIA_TYPE = RISK_ANNOTATION_CLOSURE_MEDIA_TYPE


class RiskArtifactError(ValueError):
    """Risk artifact bytes, manifest or closure failed validation."""


def annotation_content_payload(
    table_name: str,
    annotations: Sequence[RiskAnnotation],
) -> dict[str, object]:
    return {
        "annotations": [item.to_document() for item in sorted(annotations, key=lambda item: item.annotation_id)],
        "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
        "table_name": table_name,
    }


def annotation_manifest_payload(
    *,
    table_name: str,
    annotation_count: int,
    content_digest: DigestRef,
) -> dict[str, object]:
    return {
        "annotation_count": annotation_count,
        "content_digest": content_digest.value,
        "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
        "record_format": "CANONICAL_JSON",
        "table_name": table_name,
    }


def publish_annotation_artifact(
    store: ArtifactStorePort,
    *,
    table_name: str,
    annotations: Sequence[RiskAnnotation],
    max_bytes: int,
) -> RiskAnnotationArtifact:
    content_bytes = canonicalize_json_value(annotation_content_payload(table_name, annotations))
    if len(content_bytes) > max_bytes:
        raise RiskArtifactError("risk annotation artifact exceeds table byte budget")
    content_digest = raw_blob_digest(content_bytes)
    manifest_bytes = canonicalize_json_value(
        annotation_manifest_payload(
            table_name=table_name,
            annotation_count=len(annotations),
            content_digest=content_digest,
        )
    )
    manifest_digest = raw_blob_digest(manifest_bytes)
    content_ref = put_with_built_ref(
        store,
        content_bytes,
        artifact_id=build_artifact_id("risk-annotation", f"content-{_digest_suffix(content_digest)}"),
        media_type=ANNOTATION_MEDIA_TYPE,
    )
    manifest_ref = put_with_built_ref(
        store,
        manifest_bytes,
        artifact_id=build_artifact_id("risk-annotation", f"manifest-{_digest_suffix(manifest_digest)}"),
        media_type=ANNOTATION_MANIFEST_MEDIA_TYPE,
    )
    artifact = RiskAnnotationArtifact(
        table_name=table_name,
        content_ref=content_ref,
        manifest_ref=manifest_ref,
        content_digest=content_digest,
        manifest_digest=manifest_digest,
        annotation_count=len(annotations),
    )
    _verify_annotation_artifact(store, artifact)
    return artifact


def closure_manifest_payload(
    *,
    comparison_digest: DigestRef,
    risk_evaluation_digest: DigestRef,
    entries: Sequence[RiskAnnotationClosureEntry],
) -> dict[str, object]:
    return {
        "comparison_digest": comparison_digest.value,
        "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
        "entries": [_closure_entry_payload(item) for item in sorted(entries, key=lambda item: item.table_name)],
        "risk_evaluation_digest": risk_evaluation_digest.value,
    }


def publish_annotation_closure(
    store: ArtifactStorePort,
    *,
    comparison_digest: DigestRef,
    risk_evaluation_digest: DigestRef,
    entries: Sequence[RiskAnnotationClosureEntry],
) -> RiskAnnotationClosure:
    ordered_entries = tuple(sorted(entries, key=lambda item: item.table_name))
    payload = closure_manifest_payload(
        comparison_digest=comparison_digest,
        risk_evaluation_digest=risk_evaluation_digest,
        entries=ordered_entries,
    )
    raw_bytes = canonicalize_json_value(payload)
    manifest_digest = raw_blob_digest(raw_bytes)
    closure_ref = put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=build_artifact_id("risk-annotation", f"closure-{_digest_suffix(manifest_digest)}"),
        media_type=ANNOTATION_CLOSURE_MEDIA_TYPE,
    )
    closure = RiskAnnotationClosure(
        comparison_digest=comparison_digest,
        risk_evaluation_digest=risk_evaluation_digest,
        entries=ordered_entries,
        closure_ref=closure_ref,
        closure_manifest_digest=manifest_digest,
    )
    validate_risk_annotation_closure(closure, store)
    return closure


def validate_risk_annotation_closure(
    closure: RiskAnnotationClosure,
    store: ArtifactStorePort,
) -> None:
    try:
        closure_bytes = store.locate(closure.closure_ref)
    except Exception as exc:
        raise RiskArtifactError("risk annotation closure cannot be located") from exc
    if raw_blob_digest(closure_bytes) != closure.closure_manifest_digest:
        raise RiskArtifactError("risk annotation closure digest mismatch")
    if canonicalize_json_value(_json_object(closure_bytes)) != closure_bytes:
        raise RiskArtifactError("risk annotation closure is not canonical JSON")
    expected_payload = closure_manifest_payload(
        comparison_digest=closure.comparison_digest,
        risk_evaluation_digest=closure.risk_evaluation_digest,
        entries=closure.entries,
    )
    if _json_object(closure_bytes) != expected_payload:
        raise RiskArtifactError("risk annotation closure payload mismatch")
    for entry in closure.entries:
        if entry.artifact is not None:
            _verify_annotation_artifact(store, entry.artifact)


def _verify_annotation_artifact(store: ArtifactStorePort, artifact: RiskAnnotationArtifact) -> None:
    try:
        content_bytes = store.locate(artifact.content_ref)
        manifest_bytes = store.locate(artifact.manifest_ref)
    except Exception as exc:
        raise RiskArtifactError("risk annotation artifact cannot be located") from exc
    if raw_blob_digest(content_bytes) != artifact.content_digest:
        raise RiskArtifactError("risk annotation content digest mismatch")
    if raw_blob_digest(manifest_bytes) != artifact.manifest_digest:
        raise RiskArtifactError("risk annotation manifest digest mismatch")
    try:
        validate_risk_annotation_documents(
            content_bytes,
            manifest_bytes,
            table_name=artifact.table_name,
            annotation_count=artifact.annotation_count,
            content_digest=artifact.content_digest,
        )
    except ValueError as exc:
        raise RiskArtifactError(str(exc)) from exc


def _closure_entry_payload(entry: RiskAnnotationClosureEntry) -> dict[str, object]:
    if entry.artifact is None:
        return {
            "annotation_count": entry.annotation_count,
            "manifest_digest": None,
            "no_record_reason_codes": [item.value for item in entry.no_record_reason_codes],
            "table_name": entry.table_name,
        }
    return {
        "annotation_count": entry.annotation_count,
        "content_digest": entry.artifact.content_digest.value,
        "manifest_digest": entry.artifact.manifest_digest.value,
        "no_record_reason_codes": [],
        "table_name": entry.table_name,
    }


def _json_object(raw_bytes: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw_bytes)
    except (TypeError, ValueError) as exc:
        raise RiskArtifactError("risk artifact is not JSON") from exc
    if type(value) is not dict:
        raise RiskArtifactError("risk artifact must be a JSON object")
    return cast(dict[str, object], value)


def _digest_suffix(digest: DigestRef) -> str:
    return digest.value.split(":", 1)[-1][:24]
