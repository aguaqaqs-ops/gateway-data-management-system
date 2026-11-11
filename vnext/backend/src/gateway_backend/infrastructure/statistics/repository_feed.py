"""Background-only disposable RS feed polling into the bounded local sink."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from gateway_repository_contracts.statistics import (
    FilesystemCapacityObservation, RepositoryStorageObservation, ResourceObservation,
    StatisticsFeedQuery, StatisticsFeedResponse, WriteObservation,
)
from gateway_backend.statistics.models import ResourceRecord, StatisticsIdentity, StorageRecord, WriteRecord


class StatisticsFeedClient(Protocol):
    async def get_statistics_observations(self, query: StatisticsFeedQuery) -> StatisticsFeedResponse: ...


class RepositoryFeedPoller:
    def __init__(self, client: StatisticsFeedClient, identity: StatisticsIdentity,
                 offer: Callable[[StorageRecord | WriteRecord | ResourceRecord], bool], *, timeout_seconds: float = 2,
                 page_items: int = 100) -> None:
        self.client, self.identity, self.offer, self.timeout = client, identity, offer, timeout_seconds
        self.page_items = page_items
        self.instance_id: str | None = None
        self.after_sequence = 0
        self.dropped_count = 0
        self.reason: str | None = 'not_collected'

    async def poll(self) -> None:
        """One page per tick bounds work even if producer outpaces the backend."""
        try:
            page = await asyncio.wait_for(self.client.get_statistics_observations(
                StatisticsFeedQuery(instance_id=self.instance_id, after_sequence=self.after_sequence, limit=self.page_items)), self.timeout)
            if page.reset or page.truncated:
                self.reason = 'retention'
            else:
                self.reason = None
            reset = self.instance_id != page.instance_id
            self.instance_id = page.instance_id
            if reset:
                self.after_sequence = 0
            self.dropped_count = page.dropped_count
            for record in page.records:
                if (record.environment_id != self.identity.environment_id or record.group_id != self.identity.group_id):
                    raise ValueError('statistics feed identity mismatch')
                value = record.observation
                fields = self.identity.model_dump()
                event_id = str(record.observation_id)
                if isinstance(value, (RepositoryStorageObservation, FilesystemCapacityObservation)):
                    accepted = self.offer(StorageRecord(**fields, **value.payload.model_dump(),
                        source_event_id=event_id, service_owner='repository_service',
                        repository_id=str(value.repository_id) if value.repository_id else None,
                        generated_at_us=record.generated_at_us))
                elif isinstance(value, WriteObservation):
                    accepted = self.offer(WriteRecord(**fields, **value.payload.model_dump(),
                        repository_id=str(value.repository_id), observation_id=event_id, recorded_at_us=record.generated_at_us))
                elif isinstance(value, ResourceObservation):
                    accepted = self.offer(ResourceRecord(**fields, **value.payload.model_dump(), source_event_id=event_id))
                else:
                    raise ValueError('invalid statistics observation')
                if not accepted:
                    self.reason = 'budget_exceeded'
                # Delivery is explicitly disposable; no acknowledgment/reliable retry protocol.
                self.after_sequence = record.sequence
            if not page.records:
                self.after_sequence = max(0, page.next_sequence - 1)
        except Exception:
            self.reason = 'collection_failed'
