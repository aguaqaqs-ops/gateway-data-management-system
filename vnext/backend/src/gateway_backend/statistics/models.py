"""Typed telemetry records. A claim version identifies one execution window."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from gateway_repository_contracts.statistics import (
    Counter,
    Identifier,
    ObservationQuality,
    ResourceValues,
    StatisticsModel,
    StorageValues,
    WriteValues,
)

METRICS_MAX_BYTES = 12 * 1024
RECORD_MAX_BYTES = 16 * 1024
TABLE_LIMIT = 100


class InputShape(StatisticsModel):
    table_count: Counter | None = None
    total_rows: Counter | None = None
    max_table_rows: Counter | None = None
    sql_bytes: Counter | None = None
    changed_tables: Counter | None = None
    changed_rows: Counter | None = None
    ordered_table_rows: Counter | None = None


class StageDurations(StatisticsModel):
    parse: Counter | None = None
    materialize: Counter | None = None
    compare: Counter | None = None
    risk: Counter | None = None
    export: Counter | None = None
    bundle: Counter | None = None
    rs_import: Counter | None = None
    finalize: Counter | None = None


class CacheCounts(StatisticsModel):
    canonical: Counter | None = None
    comparison: Counter | None = None
    risk_candidate: Counter | None = None
    snapshot_export: Counter | None = None


class TableMetric(StatisticsModel):
    pair_id: Identifier | None = None
    table_name: Annotated[str, Field(min_length=1, max_length=256)]
    comparison_mode: Identifier | None = None
    before_rows: Counter | None = None
    after_rows: Counter | None = None
    changed_rows: Counter | None = None

    @model_validator(mode="after")
    def _bounded_name(self) -> Self:
        if len(self.table_name.encode("utf-8")) > 256:
            raise ValueError("table name exceeds UTF-8 byte budget")
        return self


class ExecutionMetrics(StatisticsModel):
    input_shape: InputShape = Field(default_factory=InputShape)
    stage_duration_ms: StageDurations = Field(default_factory=StageDurations)
    cache_lookups: CacheCounts = Field(default_factory=CacheCounts)
    cache_hits: CacheCounts = Field(default_factory=CacheCounts)
    tables: tuple[TableMetric, ...] = Field(default=(), max_length=TABLE_LIMIT)
    tables_total: Counter | None = None
    tables_truncated: bool = False

    @model_validator(mode="after")
    def _bounded_metrics(self) -> Self:
        if self.tables_total is not None:
            if self.tables_total < len(self.tables):
                raise ValueError("tables_total is smaller than retained tables")
            if self.tables_total > len(self.tables) and not self.tables_truncated:
                raise ValueError("omitted table metrics require tables_truncated")
        for name in CacheCounts.model_fields:
            lookups = getattr(self.cache_lookups, name)
            hits = getattr(self.cache_hits, name)
            if lookups is not None and hits is not None and hits > lookups:
                raise ValueError("cache hits exceed lookups")
        if len(self.model_dump_json().encode("utf-8")) > METRICS_MAX_BYTES:
            raise ValueError("execution metrics exceed byte budget")
        return self


class StatisticsIdentity(StatisticsModel):
    environment_id: Identifier
    group_id: Identifier


class StorageRecord(StorageValues, StatisticsIdentity):
    source_event_id: Identifier
    repository_id: Identifier | None = None
    service_owner: Literal["backend", "repository_service"]
    generated_at_us: Counter

    @model_validator(mode="after")
    def _filesystem_is_shared(self) -> Self:
        if self.category == "filesystem" and self.repository_id is not None:
            raise ValueError("filesystem capacity has no repository owner")
        return self


class ExecutionSummary(ObservationQuality, StatisticsIdentity):
    operation_id: Identifier
    step_id: Identifier
    claim_version: Counter
    attempt_count: Counter
    process_instance_id: Identifier
    worker_id: Identifier
    repository_id: Identifier | None = None
    submit_attempt_id: Identifier | None = None
    started_at_us: Counter | None = None
    ended_at_us: Counter | None = None
    duration_ms: Counter | None = None
    recorded_at_us: Counter
    observed_outcome: Literal["succeeded", "failed", "cancelled", "unknown"] = "unknown"
    cpu_time_us: Counter | None = None
    rss_peak_bytes: Counter | None = None
    cgroup_peak_bytes: Counter | None = None
    read_bytes: Counter | None = None
    write_bytes: Counter | None = None
    scratch_peak_bytes: Counter | None = None
    revision: Identifier | None = None
    config_digest: Identifier | None = None
    rules_digest: Identifier | None = None
    input_digest: Identifier | None = None
    metrics: ExecutionMetrics | None = None

    @model_validator(mode="after")
    def _bounded_record(self) -> Self:
        if len(self.model_dump_json().encode("utf-8")) > RECORD_MAX_BYTES:
            raise ValueError("execution summary exceeds byte budget")
        return self


class ResourceRecord(ResourceValues, StatisticsIdentity):
    source_event_id: Identifier
    operation_id: Identifier | None = None
    step_id: Identifier | None = None
    attempt_count: Counter | None = None
    claim_version: Counter | None = None

    @model_validator(mode="after")
    def _complete_window_key(self) -> Self:
        key = (self.operation_id, self.step_id, self.attempt_count, self.claim_version)
        if any(value is not None for value in key) and any(value is None for value in key):
            raise ValueError("resource window key must be complete")
        return self


class WriteRecord(WriteValues, StatisticsIdentity):
    observation_id: Identifier
    repository_id: Identifier
    operation_id: Identifier | None = None
    submission_id: Identifier | None = None
    recorded_at_us: Counter
