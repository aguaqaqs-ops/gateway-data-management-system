"""Read-only telemetry boundary, independent of HTTP and business authority."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from gateway_repository_contracts.statistics import Role

from gateway_backend.statistics.models import ExecutionSummary, ResourceRecord, StatisticsIdentity, StorageRecord, WriteRecord


CollectionKind = Literal['storage', 'storage_history', 'writes', 'executions']


class StatisticsReadError(Exception):
    def __init__(self, reason: Literal['unavailable', 'invalid_cursor', 'budget_exceeded', 'select_claim']) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ReadRequest:
    kind: CollectionKind
    owner_id: str
    start_us: int
    end_us: int
    limit: int
    cursor: str | None = None


@dataclass(frozen=True)
class ReadPage:
    items: tuple[StorageRecord | WriteRecord | ExecutionSummary, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ResourceRequest:
    start_us: int
    end_us: int
    operation_id: str | None = None
    step_id: str | None = None
    attempt_count: int | None = None
    claim_version: int | None = None
    role: str | None = None
    process_instance_id: str | None = None


@dataclass(frozen=True)
class ResourceRead:
    samples: tuple[ResourceRecord, ...]
    windows: tuple[ExecutionSummary, ...] = ()


@dataclass(frozen=True)
class GroupRead:
    storage: tuple[StorageRecord, ...]
    instances: tuple[tuple[Role, str], ...]


class StatisticsReader(Protocol):
    identity: StatisticsIdentity

    def read(self, request: ReadRequest) -> ReadPage: ...
    def resources(self, request: ResourceRequest) -> ResourceRead: ...
    def group(self, start_us: int, end_us: int) -> GroupRead: ...
