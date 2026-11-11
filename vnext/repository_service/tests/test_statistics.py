"""Disposable feed, finite filesystem observations and asynchronous import cutoffs."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gateway_repository_contracts.statistics import (
    RepositoryStorageObservation, StatisticsFeedQuery, StorageValues, WriteObservation,
)
from gateway_repository_service.app import create_app
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.storage_roots import RepositoryRoots
from gateway_repository_service.statistics import ObservationRing, RepositoryStatistics, ScanResult, scan_repository


def _observation() -> RepositoryStorageObservation:
    return RepositoryStorageObservation(repository_id=uuid4(), payload=StorageValues(category='repository',
        object_count=0, logical_bytes=0, allocated_bytes=0, window_end_us=1))


def test_ring_budgets_reset_truncation_and_updates() -> None:
    ring = ObservationRing('e', 'g', max_items=2, max_bytes=10000)
    observation_id = uuid4()
    ring.append(_observation(), observation_id=observation_id)
    ring.append(_observation(), observation_id=observation_id)
    page = ring.read(StatisticsFeedQuery(limit=1))
    assert len(page.records) == 1
    next_page = ring.read(StatisticsFeedQuery(instance_id=page.instance_id, after_sequence=1))
    assert next_page.records[0].observation_id == observation_id
    assert next_page.records[0].sequence == 2
    ring.append(_observation())
    page = ring.read(StatisticsFeedQuery(instance_id='old-process'))
    assert page.reset and page.truncated and page.dropped_count == 1
    assert len(page.records) == 2
    tiny = ObservationRing('e', 'g', max_bytes=1)
    tiny.append(_observation())
    assert tiny.read(StatisticsFeedQuery()).dropped_count == 1


@pytest.mark.parametrize(('before_bytes', 'after_bytes'), [(10, 40), (40, 10), (0, 0)])
def test_complete_async_windows_produce_signed_differences(tmp_path: Path, before_bytes: int, after_bytes: int) -> None:
    scans: list[ScanResult] = [ScanResult(1, 2, 1, 2, 1, before_bytes, before_bytes, True),
                               ScanResult(5, 6, 5, 6, 1, after_bytes, after_bytes, True)]
    calls: list[Path] = []
    def scanner(path: Path) -> Iterator[ScanResult | None]:
        calls.append(path)
        yield scans.pop(0)
    now = [3.0]
    ring = ObservationRing('e', 'g')
    statistics = RepositoryStatistics(DurableLayout(RepositoryRoots.under(tmp_path)), ring,
        scanner=scanner, clock=lambda: now[0], outcome=lambda _r, _o: ('succeeded', 'commit-after'))
    window = statistics.begin(uuid4(), uuid4(), 'commit-before')
    assert calls == []  # business callback did not start or wait for a scan
    assert statistics.collect_one()
    statistics.mutation(window)
    now[0] = 4
    statistics.end(window)
    assert len(calls) == 1
    assert statistics.collect_one()
    page = ring.read(StatisticsFeedQuery())
    assert len(page.records) == 2
    assert page.records[0].observation_id == page.records[1].observation_id
    value = page.records[-1].observation
    assert isinstance(value, WriteObservation)
    assert value.payload.logical_net_change_bytes == after_bytes - before_bytes
    assert value.payload.allocated_net_change_bytes == after_bytes - before_bytes
    assert value.payload.after_commit == 'commit-after'
    assert value.payload.quality == 'available'


@pytest.mark.parametrize('fault', ['late_before', 'truncated_before', 'early_after', 'interference', 'failure_before_mutation'])
def test_incomplete_or_overlapping_windows_never_invent_delta(tmp_path: Path, fault: str) -> None:
    before = ScanResult(1, 2, 1, 2 if fault != 'late_before' else 4, 1, 10, 10,
                        fault != 'truncated_before', 'budget_exceeded' if fault == 'truncated_before' else None)
    after = ScanResult(5, 6, 2 if fault == 'early_after' else 5, 6, 1, 20, 20, True)
    results = [before, after]
    def scanner(_path: Path) -> Iterator[ScanResult | None]:
        yield results.pop(0)
    now = [3.0]
    ring = ObservationRing('e', 'g')
    statistics = RepositoryStatistics(DurableLayout(RepositoryRoots.under(tmp_path)), ring,
                                      scanner=scanner, clock=lambda: now[0])
    repository = uuid4()
    window = statistics.begin(repository, uuid4(), None)
    statistics.collect_one()
    if fault != 'failure_before_mutation':
        statistics.mutation(window)
    now[0] = 4
    statistics.end(window)
    if fault == 'interference':
        statistics.begin(repository, uuid4(), None)
    statistics.collect_one()
    observation = ring.read(StatisticsFeedQuery()).records[-1].observation
    assert isinstance(observation, WriteObservation)
    assert observation.payload.logical_net_change_bytes is None
    assert observation.payload.quality == 'partial'


@pytest.mark.parametrize('fault', ['none', 'budget', 'link', 'missing'])
def test_fd_scanner_is_bounded_and_does_not_follow_links(tmp_path: Path, fault: str) -> None:
    directory = tmp_path / 'repository'
    directory.mkdir()
    (directory / 'first').write_bytes(b'abc')
    nested = directory / 'nested'
    nested.mkdir()
    (nested / 'second').write_bytes(b'ab')
    if fault == 'link':
        (directory / 'link').symlink_to(tmp_path)
    results = list(scan_repository(directory if fault != 'missing' else tmp_path / 'missing',
        max_entries=1 if fault == 'budget' else 100, slice_entries=1))
    value = results[-1]
    assert value is not None
    if fault == 'none':
        assert value.complete and value.objects == 2 and value.logical == 5
        assert len(results) > 1
    else:
        assert not value.complete and value.logical is None and value.allocated is None


def test_feed_http_is_authenticated_and_read_only() -> None:
    app = create_app(RepositoryServiceSettings(profile='test', bearer_token='token'), enable_lifecycle=False)
    ring = ObservationRing('e', 'g')
    ring.append(_observation())
    app.state.statistics_ring = ring
    with TestClient(app) as client:
        assert client.get('/v1/statistics/observations').status_code == 401
        headers = {'Authorization': 'Bearer token'}
        response = client.get('/v1/statistics/observations', headers=headers)
        assert response.status_code == 200
        assert len(response.json()['records']) == 1
        assert client.get('/v1/statistics/observations?limit=101', headers=headers).status_code == 422
        assert len(ring.read(StatisticsFeedQuery()).records) == 1
