"""Application adapter for the control DB backed Snapshot Table export cache."""

from __future__ import annotations

from collections.abc import Callable
from typing import ContextManager

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTableArtifactCacheKey,
    SnapshotTableExportCachePort,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork


class ControlDbSnapshotTableExportCache(SnapshotTableExportCachePort):
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ContextManager[ControlDbUnitOfWork]],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def lookup_many(
        self,
        keys: tuple[SnapshotTableArtifactCacheKey, ...],
    ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.snapshot_table_export_cache.lookup_many(keys)

    def store_many(
        self,
        entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...],
    ) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.snapshot_table_export_cache.store_many(entries)

    def discard_many(self, keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.snapshot_table_export_cache.discard_many(keys)
