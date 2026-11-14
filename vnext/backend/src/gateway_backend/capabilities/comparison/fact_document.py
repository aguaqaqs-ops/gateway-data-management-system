"""Strict flow-neutral table facts shared by comparison cache and backend audit."""
from __future__ import annotations

from typing import Literal
from dataclasses import fields

from gateway_shared_kernel.jcs import canonicalize_json_value

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.capabilities.comparison.contracts import (
    OrderedStatus, OrderedTableProcessingMode, ReplayGuarantee,
    SchemaChangeSource, SchemaEvolution, ComparisonTableStatus, ComparisonTableFact,
)


class _Document(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SchemaDocument(_Document):
    before_only_columns: tuple[str, ...]
    current_only_columns: tuple[str, ...]
    selected_columns: tuple[str, ...]
    effective_compare_key_before: tuple[str, ...]
    effective_compare_key_current: tuple[str, ...]
    effective_compare_key_changed: bool
    incompatible_columns: tuple[str, ...]
    change_source: SchemaChangeSource | None
    schema_evolution: SchemaEvolution


class OrderedSummaryDocument(_Document):
    row_added_count: int = Field(ge=0)
    row_deleted_count: int = Field(ge=0)
    row_modified_count: int = Field(ge=0)
    row_moved_count: int = Field(ge=0)
    position_changed_count: int = Field(ge=0)
    degraded_count: int = Field(ge=0)


class BlankSummaryDocument(_Document):
    interval_inserted_count: int = Field(ge=0)
    interval_deleted_count: int = Field(ge=0)
    blank_changed_count: int = Field(ge=0)
    degraded_count: int = Field(ge=0)


class OrderedDocument(_Document):
    status: OrderedStatus
    ordered_summary: OrderedSummaryDocument
    records: tuple[()]
    before_ordered_digest: str | None
    current_ordered_digest: str | None
    replay_guarantee: ReplayGuarantee
    table_processing_mode: OrderedTableProcessingMode | None
    diagnostics: tuple[str, ...]
    contract_version: str
    policy_digest: str | None


class BlankDocument(_Document):
    status: OrderedStatus
    blank_summary: BlankSummaryDocument
    records: tuple[()]
    before_occupancy_digest: str | None
    current_occupancy_digest: str | None
    replay_guarantee: ReplayGuarantee
    diagnostics: tuple[str, ...]
    contract_version: str


class ComparisonTableFactDocument(_Document):
    status: ComparisonTableStatus
    schema_changes: SchemaDocument
    row_count_before: int | None = Field(ge=0)
    row_count_current: int | None = Field(ge=0)
    row_added_count: int = Field(ge=0)
    row_deleted_count: int = Field(ge=0)
    row_modified_count: int = Field(ge=0)
    suppressed_added_count: int = Field(ge=0)
    suppressed_deleted_count: int = Field(ge=0)
    records: tuple[()]
    diagnostics: tuple[str, ...]
    content_changed: bool
    shared_value_equality: Literal["BOUND_EMPTY_DESCRIPTORS", "NATIVE_SHARED_VALUES"] | None
    ordered_extension: OrderedDocument | None
    blank_extension: BlankDocument | None


def table_fact_document_bytes(fact: ComparisonTableFact) -> bytes:
    """Encode the small completed outcome; native Arrow owns all row details."""
    from gateway_backend.capabilities.comparison.task_input import semantic_value

    if (fact.records or (fact.ordered_extension is not None and fact.ordered_extension.records)
            or (fact.blank_extension is not None and fact.blank_extension.records)):
        raise ValueError("neutral table metadata cannot carry row records")
    removed = {"table_name", "before_descriptor", "current_descriptor", "table_fact_digest"}
    return canonicalize_json_value({field.name: semantic_value(getattr(fact, field.name))
        for field in fields(fact) if field.name not in removed})


def describe_table_fact(fact: ComparisonTableFact) -> ComparisonTableFactDocument:
    """Public immutable raw outcome for audit; no cache or artifact authority leaks."""
    return ComparisonTableFactDocument.model_validate_json(table_fact_document_bytes(fact))
