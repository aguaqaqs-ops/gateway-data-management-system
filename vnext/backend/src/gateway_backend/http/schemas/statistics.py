"""Public statistics DTOs; units and limits are part of schema version 1."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Generic, Literal, Self, TypeVar

from pydantic import Field, field_validator, model_validator

from gateway_repository_contracts.statistics import Counter, Identifier, ObservationQuality, Reason, Role, StatisticsModel, StorageValues
from gateway_backend.statistics.models import ExecutionSummary, StorageRecord, WriteRecord

T = TypeVar("T")


class StatisticsQuery(StatisticsModel):
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=10000)] | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    export: bool = False
    format: Literal["json", "csv"] = "json"

    @field_validator('limit', 'max_points', 'attempt_count', 'claim_version', mode='before', check_fields=False)
    @classmethod
    def _http_integer(cls, value: object) -> object:
        if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 19:
            return int(value)
        return value

    @property
    def is_export(self) -> bool:
        return self.export or self.format == "csv"

    @property
    def effective_limit(self) -> int:
        return self.limit if self.limit is not None else (1000 if self.is_export else 100)

    @model_validator(mode="after")
    def _valid_query(self) -> Self:
        for value in (self.from_, self.to):
            if value is not None and (value.utcoffset() is None or value.utcoffset() != timedelta(0)):
                raise ValueError("statistics timestamps must be UTC")
        if self.from_ is not None and self.to is not None:
            if not self.from_ < self.to or self.to - self.from_ > timedelta(days=90):
                raise ValueError("statistics range must be positive and at most 90 days")
        if self.effective_limit > (10000 if self.is_export else 500):
            raise ValueError("statistics page limit exceeded")
        if self.cursor is not None and len(self.cursor.encode("utf-8")) > 2048:
            raise ValueError("statistics cursor exceeds byte budget")
        return self


class ResourceQuery(StatisticsQuery):
    max_points: Annotated[int, Field(strict=True, ge=1, le=2000)] = 600

    @model_validator(mode="after")
    def _resource_range(self) -> Self:
        if self.from_ is not None and self.to is not None and self.to - self.from_ > timedelta(hours=6):
            raise ValueError("resource range must be at most six hours")
        return self


class OperationResourceQuery(ResourceQuery):
    step_id: Identifier
    attempt_count: Counter
    claim_version: Counter | None = None


class GroupResourceQuery(ResourceQuery):
    role: Role
    process_instance_id: Identifier


class StatisticsPage(StatisticsModel, Generic[T]):
    schema_version: Literal[1] = 1
    generated_at_us: Counter
    window_start_us: Counter | None = None
    window_end_us: Counter | None = None
    coverage_start_us: Counter | None = None
    coverage_end_us: Counter | None = None
    quality: Literal["available", "partial", "unavailable"]
    reason: Reason | None = None
    next_cursor: str | None = Field(default=None, max_length=2048)
    items: tuple[T, ...] = Field(default=(), max_length=10000)
    units: Literal["bytes,count,utc_microseconds,duration_milliseconds,cpu_microseconds"] = "bytes,count,utc_microseconds,duration_milliseconds,cpu_microseconds"


class BucketValue(StatisticsModel):
    avg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max: Counter | None = None
    count: Counter


class ResourceBucket(StatisticsModel):
    bucket_start_us: Counter
    bucket_end_us: Counter
    cpu_time_us: BucketValue
    rss_bytes: BucketValue
    cgroup_bytes: BucketValue
    read_bytes: BucketValue
    write_bytes: BucketValue


class ResourceSeries(ObservationQuality):
    role: Role
    process_instance_id: Identifier
    step_id: Identifier | None = None
    attempt_count: Counter | None = None
    claim_version: Counter | None = None
    window_start_us: Counter
    window_end_us: Counter
    bucket_width_us: Counter
    points: tuple[ResourceBucket, ...] = Field(default=(), max_length=2000)


class CollectionHealth(ObservationQuality):
    enabled: bool
    dropped_count: Counter = 0


class GroupStorageItem(StorageValues):
    service_owner: Literal["backend", "repository_service"]
    generated_at_us: Counter


class CurrentProcess(StatisticsModel):
    role: Role
    process_instance_id: Identifier


class GroupStatistics(StatisticsModel):
    schema_version: Literal[1] = 1
    environment_id: Identifier
    group_id: Identifier
    generated_at_us: Counter
    storage: tuple[GroupStorageItem, ...] = Field(default=(), max_length=500)
    current_instances: tuple[CurrentProcess, ...] = Field(default=(), max_length=3)
    health: CollectionHealth


StoragePage = StatisticsPage[StorageRecord]
ExecutionPage = StatisticsPage[ExecutionSummary]
WritePage = StatisticsPage[WriteRecord]
ResourcePage = StatisticsPage[ResourceSeries]
