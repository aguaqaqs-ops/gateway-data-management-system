"""Comparison storage-facts document codecs owned by comparison."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef
from pydantic import BaseModel, ConfigDict, TypeAdapter

from gateway_backend.capabilities.comparison.contracts import ComparisonStorageFacts
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
)


class _StrictDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _DroppedColumnDocument(_StrictDocument):
    name: str
    reason: str


class _StorageFactDocument(_StrictDocument):
    canonical_table: str
    source_schema_digest: str
    canonical_schema_digest: str | None
    raw_content_digest: str | None
    storage_projection_version: str | None
    canonical_key_policy: str
    ordered_policy: str
    dropped_columns: list[_DroppedColumnDocument]
    structural_columns: list[str]
    retained_columns: list[str]
    canonical_key_columns: list[str]
    storage_rule_digest: str | None


_STORAGE_FACTS_ADAPTER = TypeAdapter(list[_StorageFactDocument])


def storage_facts_to_documents(
    facts: tuple[ComparisonStorageFacts, ...],
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for fact in facts:
        view = fact.storage_rule_view
        documents.append(
            {
                "canonical_table": view.canonical_table,
                "source_schema_digest": fact.source_schema_digest.value,
                "canonical_schema_digest": (
                    None
                    if fact.canonical_schema_digest is None
                    else fact.canonical_schema_digest.value
                ),
                "raw_content_digest": (
                    None if fact.raw_content_digest is None else fact.raw_content_digest.value
                ),
                "storage_projection_version": fact.storage_projection_version,
                "canonical_key_policy": view.canonical_key_policy.value,
                "ordered_policy": view.ordered_policy.value,
                "dropped_columns": [
                    {"name": item.name, "reason": item.reason} for item in view.dropped_columns
                ],
                "structural_columns": list(view.structural_columns),
                "retained_columns": list(view.retained_columns),
                "canonical_key_columns": list(view.canonical_key_columns),
                "storage_rule_digest": (
                    None if view.storage_rule_digest is None else view.storage_rule_digest.value
                ),
            }
        )
    return documents


def storage_facts_from_documents(raw: object) -> tuple[ComparisonStorageFacts, ...]:
    docs = _STORAGE_FACTS_ADAPTER.validate_python(raw, strict=True)
    return tuple(
        ComparisonStorageFacts(
            storage_rule_view=StorageRuleView(
                canonical_table=d.canonical_table,
                canonical_key_policy=CanonicalKeyPolicy(d.canonical_key_policy),
                ordered_policy=OrderedPolicy(d.ordered_policy),
                dropped_columns=tuple(DroppedColumn(c.name, c.reason) for c in d.dropped_columns),
                structural_columns=tuple(d.structural_columns),
                retained_columns=tuple(d.retained_columns),
                canonical_key_columns=tuple(d.canonical_key_columns),
                storage_rule_digest=(
                    None if d.storage_rule_digest is None else DigestRef(d.storage_rule_digest)
                ),
            ),
            source_schema_digest=DigestRef(d.source_schema_digest),
            canonical_schema_digest=(
                None if d.canonical_schema_digest is None else DigestRef(d.canonical_schema_digest)
            ),
            raw_content_digest=(
                None if d.raw_content_digest is None else DigestRef(d.raw_content_digest)
            ),
            storage_projection_version=d.storage_projection_version,
        )
        for d in docs
    )


__all__ = [
    "storage_facts_from_documents",
    "storage_facts_to_documents",
]
