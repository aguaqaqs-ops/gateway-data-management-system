"""Finite, disposable telemetry threads; independent of business readiness."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from gateway_repository_service.statistics import (
    ObservationRing, RepositoryStatistics, filesystem_capacity, sample_resources, scan_repository,
)

if TYPE_CHECKING:
    from gateway_repository_service.layout import DurableLayout
    from gateway_repository_service.mutation_store import MutationStore
    from gateway_repository_service.settings import RepositoryServiceSettings
    from gateway_repository_service.versioned_import.store import ImportOperationStore


class StatisticsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='GATEWAY_STATISTICS_', frozen=True)
    enabled: bool = True
    sample_interval_seconds: float = Field(default=1, gt=0, le=3600)
    filesystem_interval_seconds: float = Field(default=60, gt=0, le=86400)
    storage_refresh_seconds: float = Field(default=600, gt=0, le=86400)
    rs_ring_items: int = Field(default=4096, gt=0, le=100000)
    rs_ring_bytes: int = Field(default=16 * 1024**2, gt=0, le=128 * 1024**2)
    queue_max_items: int = Field(default=512, gt=0, le=10000)
    storage_page_size: int = Field(default=100, gt=0, le=100)
    scan_slice_entries: int = Field(default=256, gt=0, le=10000)
    scan_slice_ms: int = Field(default=50, gt=0, le=1000)
    scan_total_entries: int = Field(default=10000, gt=0, le=10000)
    scan_total_seconds: float = Field(default=2, gt=0, le=60)


class StatisticsLifecycle:
    def __init__(self, settings: RepositoryServiceSettings, layout: DurableLayout,
                 mutations: MutationStore, imports: ImportOperationStore) -> None:
        try:
            self.config = StatisticsConfig()
        except ValueError:
            logging.getLogger(__name__).warning('statistics disabled reason=invalid_configuration')
            self.config = StatisticsConfig.model_construct(enabled=False)
        config = self.config
        deployment = settings.deployment_config
        self.ring = ObservationRing(deployment.storage.environment_id if deployment else 'test',
            deployment.storage.group_id if deployment else 'test',
            max_items=config.rs_ring_items, max_bytes=config.rs_ring_bytes)
        self.roots = ({name: (Path(root.path), root.filesystem_id)
                       for name, root in deployment.storage.roots.items() if name.startswith('rs-')}
                      if deployment else {})
        self.statistics = RepositoryStatistics(layout, self.ring, max_pending=config.queue_max_items,
            outcome=imports.observe_statistics_outcome,
            scanner=lambda path: scan_repository(path, max_entries=config.scan_total_entries,
                max_seconds=config.scan_total_seconds, slice_entries=config.scan_slice_entries,
                slice_seconds=config.scan_slice_ms / 1000))
        self.mutations = mutations
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.dropped = 0

    def start(self) -> None:
        if not self.config.enabled:
            return
        self.statistics.start()
        for target in (self._resources, self._storage):
            try:
                thread = threading.Thread(target=target, name='rs-statistics-periodic', daemon=True)
                thread.start()
                self._threads.append(thread)
            except Exception:
                self.dropped += 1

    def _resources(self) -> None:
        next_sample = next_capacity = 0.0
        while not self._stop.is_set():
            now = monotonic()
            if now >= next_sample:
                next_sample = now + self.config.sample_interval_seconds
                try:
                    sample_resources(self.ring)
                except Exception:
                    self.dropped += 1
            if now >= next_capacity:
                next_capacity = now + self.config.filesystem_interval_seconds
                try:
                    filesystem_capacity(self.ring, self.roots)
                except Exception:
                    self.dropped += 1
            self._stop.wait(min(self.config.sample_interval_seconds, .1))

    def _storage(self) -> None:
        cursor = 0
        cycle_start = monotonic()
        while not self._stop.is_set():
            try:
                rows = self.mutations.page_succeeded_repositories(after_effect_id=cursor,
                    limit=self.config.storage_page_size)
                if not rows:
                    cursor = 0
                    self._stop.wait(max(.1, cycle_start + self.config.storage_refresh_seconds - monotonic()))
                    cycle_start = monotonic()
                    continue
                for effect_id, repository_id in rows:
                    if self._stop.is_set():
                        return
                    cursor = effect_id
                    self.statistics.collect_repository(repository_id)
            except Exception:
                self.dropped += 1
                self._stop.wait(60)
            self._stop.wait(.01)

    def close(self) -> None:
        self._stop.set()
        # Interrupt yielding periodic scans before the business DB closes.
        deadline = monotonic() + 1
        self.statistics.close(timeout=max(0, deadline - monotonic()))
        for thread in self._threads:
            thread.join(timeout=max(0, deadline - monotonic()))
