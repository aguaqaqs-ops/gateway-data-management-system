"""Comparison storage-facts document codecs owned by comparison."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison.contracts import ComparisonStorageFacts
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
)
from gateway_backend.document_fields import document_string, document_string_tuple


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
    if type(raw) is not list:
        raise ValueError("storage_facts must be a list")
    facts: list[ComparisonStorageFacts] = []
    expected_keys = {
        "canonical_table",
        "source_schema_digest",
        "canonical_schema_digest",
        "raw_content_digest",
        "storage_projection_version",
        "canonical_key_policy",
        "ordered_policy",
        "dropped_columns",
        "structural_columns",
        "retained_columns",
        "canonical_key_columns",
        "storage_rule_digest",
    }
    for item in raw:
        if type(item) is not dict or set(item) != expected_keys:
            raise ValueError("storage fact document fields are invalid")
        dropped_raw = item["dropped_columns"]
        if type(dropped_raw) is not list:
            raise ValueError("dropped_columns must be a list")
        dropped: list[DroppedColumn] = []
        for dropped_item in dropped_raw:
            if type(dropped_item) is not dict or set(dropped_item) != {"name", "reason"}:
                raise ValueError("dropped column fields are invalid")
            dropped.append(
                DroppedColumn(
                    name=document_string(dropped_item, "name"),
                    reason=document_string(dropped_item, "reason"),
                )
            )
        canonical_table = document_string(item, "canonical_table")
        key_policy = CanonicalKeyPolicy(document_string(item, "canonical_key_policy"))
        ordered_policy = OrderedPolicy(document_string(item, "ordered_policy"))
        storage_rule_digest_raw = item["storage_rule_digest"]
        if storage_rule_digest_raw is not None and type(storage_rule_digest_raw) is not str:
            raise ValueError("storage_rule_digest must be a string or null")
        view = StorageRuleView(
            canonical_table=canonical_table,
            canonical_key_policy=key_policy,
            ordered_policy=ordered_policy,
            dropped_columns=tuple(dropped),
            structural_columns=document_string_tuple(item, "structural_columns"),
            retained_columns=document_string_tuple(item, "retained_columns"),
            canonical_key_columns=document_string_tuple(item, "canonical_key_columns"),
            storage_rule_digest=(
                None if storage_rule_digest_raw is None else DigestRef(storage_rule_digest_raw)
            ),
        )
        canonical_schema_raw = item["canonical_schema_digest"]
        if canonical_schema_raw is not None and type(canonical_schema_raw) is not str:
            raise ValueError("canonical_schema_digest must be a string or null")
        raw_content_digest = item["raw_content_digest"]
        if raw_content_digest is not None and type(raw_content_digest) is not str:
            raise ValueError("raw_content_digest must be a string or null")
        storage_projection_raw = item["storage_projection_version"]
        if storage_projection_raw is not None and type(storage_projection_raw) is not str:
            raise ValueError("storage_projection_version must be a string or null")
        facts.append(
            ComparisonStorageFacts(
                storage_rule_view=view,
                source_schema_digest=DigestRef(document_string(item, "source_schema_digest")),
                canonical_schema_digest=(
                    None if canonical_schema_raw is None else DigestRef(canonical_schema_raw)
                ),
                raw_content_digest=(
                    None if raw_content_digest is None else DigestRef(raw_content_digest)
                ),
                storage_projection_version=storage_projection_raw,
            )
        )
    return tuple(facts)


__all__ = [
    "storage_facts_from_documents",
    "storage_facts_to_documents",
]
