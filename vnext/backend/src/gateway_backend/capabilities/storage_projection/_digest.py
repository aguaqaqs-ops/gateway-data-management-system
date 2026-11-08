"""Small schema, view and manifest digests owned by Storage Projection."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView

MANIFEST_DIGEST_PREFIX = b"gateway-vnext:canonicalization-manifest:v1\0"
def compute_storage_rule_digest(view: StorageRuleView) -> DigestRef:
    payload = {
        "canonical_key_columns": list(view.canonical_key_columns),
        "canonical_key_policy": view.canonical_key_policy.value,
        "canonical_table": view.canonical_table,
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in view.dropped_columns
        ],
        "ordered_policy": view.ordered_policy.value,
        "retained_columns": list(view.retained_columns),
        "structural_columns": list(view.structural_columns),
    }
    return _sha256_jcs(payload)


def compute_schema_digest(
    *,
    columns: Sequence[Mapping[str, object]],
    primary_key: Sequence[str],
) -> DigestRef:
    payload = {
        "columns": [dict(column) for column in columns],
        "primary_key": list(primary_key),
    }
    return _sha256_jcs(payload)


def compute_manifest_digest(manifest: CanonicalizationManifest) -> DigestRef:
    payload = canonicalize_json_value(manifest_document(manifest))
    return DigestRef.from_raw_digest(hashlib.sha256(MANIFEST_DIGEST_PREFIX + payload).digest())


def manifest_document(manifest: CanonicalizationManifest) -> dict[str, Any]:
    return {
        "contract_version": manifest.contract_version,
        "ruleset_digest": manifest.ruleset_digest.value,
        "ruleset_id": manifest.ruleset_id,
        "ruleset_version": manifest.ruleset_version,
        "source_artifact_digest": manifest.source_artifact_digest.value,
        "storage_projection_version": manifest.storage_projection_version,
        "tables": [_manifest_table_document(table) for table in manifest.tables],
    }


def _manifest_table_document(table: CanonicalizationManifestTable) -> dict[str, Any]:
    return {
        "canonical_key_columns": list(table.canonical_key_columns),
        "canonical_key_policy": table.canonical_key_policy.value,
        "canonical_row_count": table.canonical_row_count,
        "canonical_schema_digest": _optional_digest(table.canonical_schema_digest),
        "content_digest": _optional_digest(table.content_digest),
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in table.dropped_columns
        ],
        "gid_pseudo_count": table.gid_pseudo_count,
        "gid_real_count": table.gid_real_count,
        "name": table.name,
        "ordered_policy": table.ordered_policy.value,
        "retained_columns": list(table.retained_columns),
        "source_row_count": table.source_row_count,
        "source_schema_digest": _optional_digest(table.source_schema_digest),
        "structural_columns": list(table.structural_columns),
    }


def _optional_digest(digest: DigestRef | None) -> str | None:
    if digest is None:
        return None
    return digest.value


def _sha256_jcs(payload: Mapping[str, object]) -> DigestRef:
    return DigestRef.from_raw_digest(hashlib.sha256(canonicalize_json_value(dict(payload))).digest())


