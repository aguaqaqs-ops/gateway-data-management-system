"""Identity-projection CanonicalizationManifest assembler.

Outer digest algorithm (Canonical Storage §4):

    SHA256(b"gateway-vnext:canonicalization-manifest:v1\\0" || RFC8785-JCS(document))

``canonicalization-manifest`` is a Storage Projection domain prefix, not a
Shared Kernel DigestKind. Child schema/content digests are raw SHA-256 of the
canonical payloads (``sha256:`` + lowercase hex), not new DigestKind values.

Table content cells are DDL-order length-prefixed frames from
``canonicalization_cells.encode_row_cells``. Keyed tables use the caller's
primary-key order. Keyless tables hash an unordered multiset of those row
frames (sorted by unsigned bytes, duplicates retained). This path never calls
the Shared Kernel row encoder.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.canonicalization_cells import encode_row_cells

CONTRACT_VERSION = "3.0.0"
STORAGE_PROJECTION_VERSION = "1"
IDENTITY_RULESET_ID = "gateway-vnext.identity-sql-dump"
IDENTITY_RULESET_VERSION = "1"
CANONICALIZATION_MANIFEST_PREFIX = b"gateway-vnext:canonicalization-manifest:v1\0"
REPOSITORY_IMPORT_MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
PACKAGE_VERSION = 1

_IDENTITY_RULESET_BODY: dict[str, object] = {
    "drop_from_storage": False,
    "id": IDENTITY_RULESET_ID,
    "source_equals_canonical": True,
    "version": IDENTITY_RULESET_VERSION,
}


class CanonicalizationManifestError(ValueError):
    """Raised when identity-projection assembly fails closed."""


@dataclass(frozen=True, slots=True)
class ManifestColumn:
    name: str
    sql_type: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class AssembledTable:
    name: str
    columns: tuple[ManifestColumn, ...]
    primary_key: tuple[str, ...]
    row_count: int
    schema_digest: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class AssembledCanonicalization:
    source_artifact_digest: str
    ruleset_digest: str
    document: dict[str, object]
    digest: str
    tables: tuple[AssembledTable, ...]


def sha256_digest_ref(payload: bytes) -> str:
    if type(payload) is not bytes:
        raise CanonicalizationManifestError("digest payload must be bytes")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def identity_ruleset_digest() -> str:
    return sha256_digest_ref(canonicalize_json_value(_IDENTITY_RULESET_BODY))


def table_schema_payload(
    columns: Sequence[ManifestColumn],
    primary_key: Sequence[str],
) -> dict[str, object]:
    return {
        "columns": [
            {
                "name": column.name,
                "nullable": column.nullable,
                "sql_type": column.sql_type,
            }
            for column in columns
        ],
        "primary_key": list(primary_key),
    }


def table_schema_digest(
    columns: Sequence[ManifestColumn],
    primary_key: Sequence[str],
) -> str:
    payload = table_schema_payload(columns, primary_key)
    return sha256_digest_ref(canonicalize_json_value(payload))


def table_content_digest(
    columns: Sequence[ManifestColumn],
    rows: Iterable[Sequence[object]],
    *,
    expected_row_count: int,
    unordered: bool = False,
) -> str:
    sql_types = tuple(column.sql_type for column in columns)
    if not unordered:
        hasher = hashlib.sha256()
        observed = 0
        for row in rows:
            hasher.update(encode_row_cells(sql_types, row))
            observed += 1
        if observed != expected_row_count:
            raise CanonicalizationManifestError(
                f"content row count {observed} does not match catalog {expected_row_count}"
            )
        return "sha256:" + hasher.hexdigest()
    frames: list[bytes] = []
    for row in rows:
        frames.append(encode_row_cells(sql_types, row))
    if len(frames) != expected_row_count:
        raise CanonicalizationManifestError(
            f"content row count {len(frames)} does not match catalog {expected_row_count}"
        )
    frames.sort()
    hasher = hashlib.sha256()
    for frame in frames:
        hasher.update(frame)
    return "sha256:" + hasher.hexdigest()


def assemble_identity_canonicalization(
    *,
    source_artifact_digest: str,
    tables: Sequence[AssembledTable],
) -> AssembledCanonicalization:
    if not source_artifact_digest.startswith("sha256:"):
        raise CanonicalizationManifestError("source_artifact_digest must be sha256 hex")
    ordered = tuple(sorted(tables, key=lambda table: table.name.encode("utf-8")))
    seen: set[bytes] = set()
    table_documents: list[dict[str, object]] = []
    for table in ordered:
        name_bytes = table.name.encode("utf-8")
        if name_bytes in seen:
            raise CanonicalizationManifestError(f"duplicate table name {table.name!r}")
        seen.add(name_bytes)
        table_documents.append(_table_document(table))
    ruleset_digest = identity_ruleset_digest()
    document: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "ruleset_digest": ruleset_digest,
        "ruleset_id": IDENTITY_RULESET_ID,
        "ruleset_version": IDENTITY_RULESET_VERSION,
        "source_artifact_digest": source_artifact_digest,
        "storage_projection_version": STORAGE_PROJECTION_VERSION,
        "tables": table_documents,
    }
    digest = canonicalization_manifest_digest(document)
    return AssembledCanonicalization(
        source_artifact_digest=source_artifact_digest,
        ruleset_digest=ruleset_digest,
        document=document,
        digest=digest,
        tables=ordered,
    )


def canonicalization_manifest_digest(document: Mapping[str, object]) -> str:
    if "manifest_digest" in document:
        raise CanonicalizationManifestError("preimage must not include manifest_digest")
    preimage = CANONICALIZATION_MANIFEST_PREFIX + canonicalize_json_value(dict(document))
    return sha256_digest_ref(preimage)


def durable_canonicalization_manifest(assembled: AssembledCanonicalization) -> dict[str, object]:
    payload = dict(assembled.document)
    payload["manifest_digest"] = assembled.digest
    return payload


def repository_import_manifest(assembled: AssembledCanonicalization) -> dict[str, object]:
    tables: list[dict[str, object]] = []
    for table in assembled.tables:
        tables.append(
            {
                "name": table.name,
                "row_count": table.row_count,
                "schema": {
                    "columns": [
                        {
                            "name": column.name,
                            "nullable": column.nullable,
                            "sql_type": column.sql_type,
                        }
                        for column in table.columns
                    ],
                    "primary_key": list(table.primary_key),
                },
            }
        )
    return {
        "canonicalization_manifest_digest": assembled.digest,
        "package_version": PACKAGE_VERSION,
        "tables": tables,
    }


def _table_document(table: AssembledTable) -> dict[str, object]:
    retained = [column.name for column in table.columns]
    return {
        "canonical_content_digest": table.content_digest,
        "canonical_primary_key": list(table.primary_key),
        "canonical_row_count": table.row_count,
        "canonical_schema_digest": table.schema_digest,
        "dropped_columns": [],
        "retained_columns": retained,
        "source_row_count": table.row_count,
        "source_schema_digest": table.schema_digest,
        "structural_columns": [],
        "table_name": table.name,
    }
