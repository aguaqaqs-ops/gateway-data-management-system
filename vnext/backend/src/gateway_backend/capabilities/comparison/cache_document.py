"""Strict persisted neutral fact document; Arrow row views have their own owner."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.capabilities.comparison.contracts import (
    OrderedStatus, OrderedTableProcessingMode, ReplayGuarantee,
    SchemaChangeSource, SchemaEvolution, ComparisonTableStatus,
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


class NeutralFactDocument(_Document):
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
