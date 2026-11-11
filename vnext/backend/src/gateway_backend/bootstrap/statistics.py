"""Best-effort process telemetry lifecycle; never a business readiness dependency."""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from time import monotonic

from gateway_repository_client import RepositoryClient

from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.http.schemas.statistics import CollectionHealth
from gateway_backend.http.statistics import StatisticsHttpDependencies
from gateway_backend.infrastructure.statistics.collection import BufferedTelemetrySink
from gateway_backend.infrastructure.statistics.queries import SQLiteStatisticsReader
from gateway_backend.infrastructure.statistics.repository_feed import RepositoryFeedPoller
from gateway_backend.infrastructure.statistics.sqlite_store import SQLiteStatisticsStore
from gateway_backend.infrastructure.statistics.storage import DeviceStorageCollector, StorageCandidates, filesystem_capacity
from gateway_backend.bootstrap.storage_layout import local_store_from_config
from gateway_backend.statistics.config import StatisticsConfig, statistics_database_path
from gateway_backend.statistics.models import StatisticsIdentity

_LOG = logging.getLogger(__name__)


def load_statistics_config() -> StatisticsConfig:
    try:
        return StatisticsConfig()
    except ValueError:
        _LOG.warning('statistics disabled reason=invalid_configuration')
        return StatisticsConfig.model_construct(enabled=False)


def build_statistics_sink(deployment: DeploymentConfig, role: str) -> BufferedTelemetrySink:
    config = load_statistics_config()
    identity = StatisticsIdentity(environment_id=deployment.storage.environment_id, group_id=deployment.storage.group_id)
    path = statistics_database_path(Path(deployment.storage.roots['be-metadata'].path))
    return BufferedTelemetrySink(SQLiteStatisticsStore(path, identity, config), identity, config,
        role=role, config_digest=deployment.resources.digest)


class BackendStatistics:
    def __init__(self, deployment: DeploymentConfig, control_db: Path, base_url: str, token: str) -> None:
        self.sink = build_statistics_sink(deployment, 'backend')
        self.config = self.sink.config
        self.collector = DeviceStorageCollector(StorageCandidates(control_db, self.config),
            local_store_from_config(deployment), self.sink.identity, self.sink.offer, self.config)
        self.poller = RepositoryFeedPoller(RepositoryClient(base_url=base_url, bearer_token=token,
            timeout_seconds=self.config.rs_http_timeout_seconds), self.sink.identity, self.sink.offer,
            timeout_seconds=self.config.rs_http_timeout_seconds)
        self.roots = {name: (Path(root.path), root.filesystem_id) for name, root in deployment.storage.roots.items()
                      if name.startswith('be-')}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.collection_failures = 0
        self.http = StatisticsHttpDependencies(SQLiteStatisticsReader(self.sink.store.path, self.sink.identity,
            available=lambda: self.config.enabled and self.sink.health.available),
            dropped_count=lambda: self.sink.health.dropped + self.poller.dropped_count + self.collection_failures,
            health=self.health, sample_interval_seconds=self.config.sample_interval_seconds)

    def health(self) -> CollectionHealth:
        reason = self.sink.health.reason or self.poller.reason
        return CollectionHealth(enabled=self.config.enabled,
            dropped_count=self.sink.health.dropped + self.poller.dropped_count + self.collection_failures,
            quality='available' if reason is None else 'partial' if self.sink.health.available else 'unavailable',
            reason=reason)

    def start(self) -> None:
        self.sink.start()
        if self.config.enabled and self._thread is None:
            try:
                self._thread = threading.Thread(target=self._run, name='backend-statistics', daemon=True)
                self._thread.start()
            except Exception:
                self.collection_failures += 1

    def _run(self) -> None:
        next_storage = next_capacity = next_poll = 0.0
        while not self._stop.is_set():
            now = monotonic()
            if now >= next_storage:
                try:
                    complete = self.collector.collect_next()
                    next_storage = now + (self.config.storage_refresh_seconds if complete else .01)
                except Exception:
                    self.collection_failures += 1
                    next_storage = now + self.config.maintenance_seconds
            if self._stop.is_set():
                break
            if now >= next_capacity:
                next_capacity = now + self.config.filesystem_interval_seconds
                try:
                    for record in filesystem_capacity(self.sink.identity, self.roots):
                        self.sink.offer(record)
                except Exception:
                    self.collection_failures += 1
            if now >= next_poll:
                next_poll = now + self.config.rs_poll_seconds
                asyncio.run(self.poller.poll())
            self._stop.wait(.05)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.config.shutdown_flush_seconds)
        self.sink.close()
