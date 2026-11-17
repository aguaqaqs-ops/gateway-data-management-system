"""Telemetry identity, bounded payload, query and schema contract barriers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from gateway_backend.domain.workspace.errors import PermissionDenied
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.application.statistics_queries import assert_statistics_group_permission
from gateway_backend.http.schemas.statistics import GroupStorageItem, ResourceQuery, StatisticsQuery
from gateway_backend.infrastructure.statistics.schema import SCHEMA_SQL, SCHEMA_VERSION
from gateway_backend.statistics.config import StatisticsConfig, statistics_database_path
from gateway_backend.statistics.models import (
    CacheCounts,
    ExecutionMetrics,
    InputShape,
    ResourceRecord,
    TableMetric,
)


@pytest.mark.parametrize(
    "field,value",
    [("total_rows", -1), ("sql_bytes", True), ("table_count", 1.5), ("max_table_rows", 2**63)],
)
def test_input_shape_rejects_invalid_counters(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        InputShape.model_validate({field: value})


def test_metrics_distinguish_missing_and_zero_and_bound_table_names() -> None:
    metrics = ExecutionMetrics(input_shape=InputShape(total_rows=0))
    assert metrics.input_shape.total_rows == 0
    assert metrics.input_shape.sql_bytes is None
    assert metrics.cache_hits.canonical is None
    with pytest.raises(ValidationError):
        TableMetric(table_name="表" * 86)
    with pytest.raises(ValidationError):
        ExecutionMetrics(tables=(TableMetric(table_name="t"),) * 101)
    with pytest.raises(ValidationError):
        ExecutionMetrics(tables=(TableMetric(table_name="t"),), tables_total=2)
    with pytest.raises(ValidationError):
        ExecutionMetrics(
            cache_lookups=CacheCounts(comparison=0), cache_hits=CacheCounts(comparison=1)
        )
    with pytest.raises(ValidationError):
        ExecutionMetrics(tables=tuple(TableMetric(table_name="a" * 256) for _ in range(100)))


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 501},
        {"limit": 10001, "export": True},
        {"cursor": "表" * 700},
        {"from": "2026-01-01T00:00:00Z", "to": "2026-05-01T00:00:00Z"},
        {"from": "2026-01-01T00:00:00", "to": "2026-01-02T00:00:00Z"},
    ],
)
def test_statistics_query_rejects_unbounded_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StatisticsQuery.model_validate(payload)


def test_export_and_resource_budgets() -> None:
    assert StatisticsQuery().effective_limit == 100
    assert StatisticsQuery(format="csv").is_export
    assert StatisticsQuery(format="csv").effective_limit == 1000
    with pytest.raises(ValidationError):
        ResourceQuery.model_validate({"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T07:00:00Z"})
    with pytest.raises(ValidationError):
        ResourceQuery(max_points=2001)
    with pytest.raises(ValidationError):
        GroupStorageItem.model_validate(
            {
                "category": "canonical",
                "window_end_us": 1,
                "generated_at_us": 1,
                "service_owner": "backend",
                "repository_id": "secret",
            }
        )


def test_group_permission_is_separate_from_workspace_and_recovery() -> None:
    identity = IdentityContext(
        actor_id="operator",
        gateway_device_external_key="device",
        business_project_id="project",
        permissions=frozenset({"statistics_read_group"}),
    )
    assert_statistics_group_permission(identity)
    with pytest.raises(PermissionDenied):
        assert_permission(identity, "workspace_read")
    with pytest.raises(PermissionDenied):
        assert_statistics_group_permission(
            IdentityContext(
                actor_id="user",
                gateway_device_external_key="device",
                business_project_id="project",
                permissions=frozenset({"workspace_read"}),
            )
        )


def test_resource_window_requires_all_existing_identity_parts() -> None:
    base = dict(
        environment_id="env",
        group_id="g",
        role="worker",
        process_instance_id="p",
        source_event_id="event",
        sampled_at_us=1,
    )
    with pytest.raises(ValidationError):
        ResourceRecord.model_validate({**base, "operation_id": "op"})
    resource = ResourceRecord.model_validate(
        {**base, "operation_id": "op", "step_id": "s", "attempt_count": 1, "claim_version": 4}
    )
    assert resource.claim_version == 4


def test_baseline_preserves_distinct_claims_and_signed_net_change() -> None:
    with sqlite3.connect(":memory:") as db:
        db.executescript(SCHEMA_SQL)
        assert db.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        for claim in (3, 8):
            db.execute(
                "INSERT INTO execution_summaries(environment_id,group_id,operation_id,step_id,claim_version,attempt_count,process_instance_id,worker_id,recorded_at_us,observed_outcome,quality) VALUES ('e','g','op','s',?,1,'p','w',7,'unknown','partial')",
                (claim,),
            )
        assert db.execute("SELECT count(*) FROM execution_summaries").fetchone() == (2,)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE execution_summaries SET recorded_at_us=NULL")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "UPDATE execution_summaries SET metrics_json=?", ('{"x":"' + "a" * 13000 + '"}',)
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO storage_observations(source_event_id,environment_id,group_id,service_owner,category,window_end_us,generated_at_us,quality) VALUES ('f','e','g','backend','filesystem',1,1,'unavailable')"
            )
        indices = {row[1] for row in db.execute("PRAGMA index_list(resource_samples)")}
        assert {
            "resource_process_window",
            "resource_execution_window",
            "resource_retention",
        } <= indices
        db.execute(
            "INSERT INTO write_observations(observation_id,environment_id,group_id,repository_id,rs_operation_id,process_instance_id,logical_net_change_bytes,observed_outcome,quality,recorded_at_us) VALUES ('id','e','g','r','op','p',-10,'succeeded','available',7)"
        )
        assert db.execute("SELECT logical_net_change_bytes FROM write_observations").fetchone() == (
            -10,
        )


def test_statistics_configuration_has_finite_defaults_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_STATISTICS_SAMPLE_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("GATEWAY_STATISTICS_QUEUE_MAX_ITEMS", "256")
    monkeypatch.setenv("GATEWAY_STATISTICS_EXPORT_CONCURRENCY", "1")
    config = StatisticsConfig()
    assert config.sample_interval_seconds == 2
    assert config.queue_max_items == 256
    assert config.export_concurrency == 1
    assert config.max_page_count == 524288
    assert config.wal_soft_limit_bytes == 128 * 1024**2
    assert statistics_database_path(Path("/metadata")) == Path(
        "/metadata/telemetry/statistics.sqlite3"
    )
    with pytest.raises(ValidationError):
        StatisticsConfig(queue_max_bytes=1024)
    monkeypatch.setenv("GATEWAY_STATISTICS_EXPORT_CONCURRENCY", "2")
    with pytest.raises(ValidationError):
        StatisticsConfig()
