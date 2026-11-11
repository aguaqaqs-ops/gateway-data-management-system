from __future__ import annotations

import httpx
import pytest

from gateway_repository_client import RepositoryClient, RepositoryProtocolError
from gateway_repository_contracts.statistics import StatisticsFeedQuery


@pytest.mark.asyncio
async def test_statistics_client_preserves_cursor_and_authentication() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers['Authorization'] == 'Bearer token'
        assert request.url.params['after_sequence'] == '3'
        return httpx.Response(200, json=dict(instance_id='instance', oldest_sequence=4,
            next_sequence=4, dropped_count=0, records=[]))
    client = RepositoryClient(base_url='http://repository.test', bearer_token='token',
                              transport=httpx.MockTransport(handler))
    page = await client.get_statistics_observations(StatisticsFeedQuery(instance_id='instance', after_sequence=3))
    assert page.next_sequence == 4


@pytest.mark.asyncio
async def test_statistics_client_rejects_oversized_body_without_retry() -> None:
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b' ' * (1024 * 1024 + 1))
    client = RepositoryClient(base_url='http://repository.test', bearer_token='token',
                              transport=httpx.MockTransport(handler))
    with pytest.raises(RepositoryProtocolError):
        await client.get_statistics_observations(StatisticsFeedQuery())
    assert len(calls) == 1
