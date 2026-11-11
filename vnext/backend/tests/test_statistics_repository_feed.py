from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from gateway_backend.infrastructure.statistics.repository_feed import RepositoryFeedPoller
from gateway_backend.statistics.models import ResourceRecord, StatisticsIdentity, StorageRecord, WriteRecord
from gateway_repository_contracts.statistics import (
    StatisticsFeedQuery, StatisticsFeedRecord, StatisticsFeedResponse, WriteObservation, WriteValues,
)


class Feed:
    def __init__(self, records: tuple[StatisticsFeedRecord, ...]) -> None:
        self.records = records
        self.queries: list[StatisticsFeedQuery] = []

    async def get_statistics_observations(self, query: StatisticsFeedQuery) -> StatisticsFeedResponse:
        self.queries.append(query)
        return StatisticsFeedResponse(instance_id='process', oldest_sequence=1, next_sequence=3,
            dropped_count=0, records=self.records if query.after_sequence == 0 else ())


@pytest.mark.asyncio
async def test_poller_preserves_updates_identity_and_window_values() -> None:
    repository, operation, observation = uuid4(), uuid4(), uuid4()
    base = WriteValues(rs_operation_id=operation, process_instance_id='process', quality='partial', reason='not_collected')
    complete = base.model_copy(update=dict(before_logical_bytes=20, after_logical_bytes=10,
                                          logical_net_change_bytes=-10, quality='available', reason=None))
    records = tuple(StatisticsFeedRecord(observation_id=observation, sequence=index + 1,
        instance_id='process', environment_id='e', group_id='g', generated_at_us=index + 10,
        observation=WriteObservation(repository_id=repository, payload=value)) for index, value in enumerate((base, complete)))
    feed = Feed(records)
    saved: list[StorageRecord | WriteRecord | ResourceRecord] = []
    def offer(value: StorageRecord | WriteRecord | ResourceRecord) -> bool:
        saved.append(value)
        return True
    poller = RepositoryFeedPoller(feed, StatisticsIdentity(environment_id='e', group_id='g'), offer)
    await poller.poll()
    assert poller.reason is None and poller.after_sequence == 2
    assert len(saved) == 2
    assert cast(WriteRecord, saved[1]).observation_id == str(observation)
    assert cast(WriteRecord, saved[1]).logical_net_change_bytes == -10
    await poller.poll()
    assert feed.queries[1].instance_id == 'process' and feed.queries[1].after_sequence == 2
    assert len(saved) == 2
    bad = RepositoryFeedPoller(feed, StatisticsIdentity(environment_id='other', group_id='g'), offer)
    await bad.poll()
    assert bad.reason == 'collection_failed' and bad.after_sequence == 0
