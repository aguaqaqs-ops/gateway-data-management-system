"""Bounded, read-only Repository Service statistics feed (schema version 1).

These observations are disposable telemetry, never an import acknowledgment.
All timestamps are UTC microseconds and counters are bytes unless named otherwise.
"""
from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Counter = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
SignedCounter = Annotated[int, Field(strict=True, ge=-(2**63), le=2**63 - 1)]
Identifier = Annotated[str, Field(min_length=1, max_length=255)]
Quality = Literal["available", "partial", "unavailable"]
Reason = Literal[
    "disabled", "not_collected", "counter_unavailable", "counter_reset",
    "interference", "budget_exceeded", "retention", "collection_failed",
]
Role = Literal["backend", "worker", "repository_service"]
Category = Literal[
    "repository", "durable", "canonical", "comparison", "export", "scratch",
    "metadata", "public", "unknown", "filesystem",
]


class StatisticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservationQuality(StatisticsModel):
    quality: Quality = "available"
    reason: Reason | None = None


class StorageValues(ObservationQuality):
    category: Category
    object_count: Counter | None = None
    logical_bytes: Counter | None = None
    allocated_bytes: Counter | None = None
    unverified_reference_bytes: Counter | None = None
    filesystem_id: Identifier | None = None
    total_bytes: Counter | None = None
    available_bytes: Counter | None = None
    available_inodes: Counter | None = None
    window_start_us: Counter | None = None
    window_end_us: Counter


class ResourceValues(ObservationQuality):
    role: Role
    process_instance_id: Identifier
    sampled_at_us: Counter
    cpu_time_us: Counter | None = None
    rss_bytes: Counter | None = None
    cgroup_bytes: Counter | None = None
    read_bytes: Counter | None = None
    write_bytes: Counter | None = None


class WriteValues(ObservationQuality):
    rs_operation_id: UUID
    process_instance_id: Identifier
    before_commit: Identifier | None = None
    after_commit: Identifier | None = None
    before_start_us: Counter | None = None
    before_end_us: Counter | None = None
    after_start_us: Counter | None = None
    after_end_us: Counter | None = None
    before_logical_bytes: Counter | None = None
    after_logical_bytes: Counter | None = None
    before_allocated_bytes: Counter | None = None
    after_allocated_bytes: Counter | None = None
    logical_net_change_bytes: SignedCounter | None = None
    allocated_net_change_bytes: SignedCounter | None = None
    observed_outcome: Literal["succeeded", "failed", "unknown"] = "unknown"


class RepositoryStorageObservation(StatisticsModel):
    kind: Literal["repository_storage"] = "repository_storage"
    repository_id: UUID
    payload: StorageValues


class FilesystemCapacityObservation(StatisticsModel):
    kind: Literal["filesystem_capacity"] = "filesystem_capacity"
    repository_id: None = None
    payload: StorageValues

    @model_validator(mode="after")
    def _filesystem_category(self) -> Self:
        if self.payload.category != "filesystem":
            raise ValueError("filesystem capacity requires filesystem category")
        return self


class ResourceObservation(StatisticsModel):
    kind: Literal["resource"] = "resource"
    repository_id: None = None
    payload: ResourceValues


class WriteObservation(StatisticsModel):
    kind: Literal["write"] = "write"
    repository_id: UUID
    payload: WriteValues


Observation = Annotated[
    RepositoryStorageObservation | FilesystemCapacityObservation | ResourceObservation | WriteObservation,
    Field(discriminator="kind"),
]


class StatisticsFeedQuery(StatisticsModel):
    instance_id: Identifier | None = None
    after_sequence: Counter = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 100


class StatisticsFeedRecord(StatisticsModel):
    observation_id: UUID
    sequence: Counter
    instance_id: Identifier
    environment_id: Identifier
    group_id: Identifier
    generated_at_us: Counter
    observation: Observation

    @model_validator(mode="after")
    def _bounded_record(self) -> Self:
        if len(self.model_dump_json().encode("utf-8")) > 16 * 1024:
            raise ValueError("statistics record exceeds byte budget")
        return self


class StatisticsFeedResponse(StatisticsModel):
    schema_version: Literal[1] = 1
    instance_id: Identifier
    oldest_sequence: Counter
    next_sequence: Counter
    dropped_count: Counter
    reset: bool = False
    truncated: bool = False
    coverage_start_us: Counter | None = None
    coverage_end_us: Counter | None = None
    records: tuple[StatisticsFeedRecord, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def _valid_page(self) -> Self:
        if self.oldest_sequence > self.next_sequence:
            raise ValueError("invalid sequence bounds")
        previous = -1
        for record in self.records:
            if (record.instance_id != self.instance_id or record.sequence <= previous
                    or not self.oldest_sequence <= record.sequence < self.next_sequence):
                raise ValueError("invalid feed record sequence or instance")
            previous = record.sequence
        if len(self.model_dump_json().encode("utf-8")) > 1024 * 1024:
            raise ValueError("statistics feed exceeds byte budget")
        return self
