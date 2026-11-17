"""Restart-scoped telemetry budgets, independent of business resource settings."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveBudget = Annotated[int, Field(gt=0, le=2**63 - 1)]


class StatisticsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_STATISTICS_", frozen=True)

    enabled: bool = True
    export_concurrency: int = Field(default=1, ge=1, le=1)
    sample_interval_seconds: float = Field(default=1, gt=0, le=3600)
    filesystem_interval_seconds: float = Field(default=60, gt=0, le=86400)
    storage_refresh_seconds: float = Field(default=600, gt=0, le=86400)
    rs_poll_seconds: float = Field(default=5, gt=0, le=3600)
    curve_retention_days: PositiveBudget = 7
    summary_retention_days: PositiveBudget = 90
    queue_max_items: PositiveBudget = 512
    queue_max_bytes: PositiveBudget = 4 * 1024 * 1024
    record_max_bytes: PositiveBudget = Field(default=16 * 1024, le=16 * 1024)
    write_batch_items: PositiveBudget = 128
    write_batch_bytes: PositiveBudget = 256 * 1024
    flush_seconds: float = Field(default=1, gt=0, le=60)
    sqlite_busy_timeout_ms: PositiveBudget = Field(default=50, le=1000)
    storage_page_size: PositiveBudget = Field(default=100, le=100)
    scan_slice_entries: PositiveBudget = 256
    scan_slice_ms: PositiveBudget = 50
    scan_total_entries: PositiveBudget = Field(default=10000, le=10000)
    scan_total_seconds: float = Field(default=2, gt=0, le=60)
    rs_ring_items: PositiveBudget = 4096
    rs_ring_bytes: PositiveBudget = 16 * 1024 * 1024
    rs_http_timeout_seconds: float = Field(default=2, gt=0, le=30)
    feed_page_items: PositiveBudget = Field(default=100, le=100)
    retention_batch_rows: PositiveBudget = 1000
    maintenance_seconds: float = Field(default=60, gt=0, le=3600)
    shutdown_flush_seconds: float = Field(default=1, gt=0, le=1)
    total_budget_bytes: PositiveBudget = Field(default=4 * 1024**3, ge=1024 * 1024)

    @model_validator(mode="after")
    def _coherent_budgets(self) -> Self:
        if self.record_max_bytes > min(self.queue_max_bytes, self.write_batch_bytes):
            raise ValueError("record budget exceeds queue or batch byte budget")
        if self.write_batch_items > self.queue_max_items:
            raise ValueError("batch item budget exceeds queue item budget")
        if self.write_batch_bytes > self.queue_max_bytes:
            raise ValueError("batch byte budget exceeds queue byte budget")
        return self

    @property
    def max_page_count(self) -> int:
        return self.total_budget_bytes // 2 // 4096

    @property
    def wal_soft_limit_bytes(self) -> int:
        return min(128 * 1024**2, self.total_budget_bytes // 16)


def statistics_database_path(metadata_root: Path) -> Path:
    if not metadata_root.is_absolute():
        raise ValueError("metadata root must be absolute")
    return metadata_root / "telemetry" / "statistics.sqlite3"
