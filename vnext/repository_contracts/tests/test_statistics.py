"""The feed is bounded, typed telemetry, independent of import responses."""
from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from gateway_repository_contracts.statistics import StatisticsFeedRecord, StatisticsFeedResponse, WriteValues

_ID = UUID("00000000-0000-0000-0000-000000000001")


def _record(sequence: int = 1) -> StatisticsFeedRecord:
    return StatisticsFeedRecord.model_validate({
        "observation_id": str(_ID), "sequence": sequence, "instance_id": "process",
        "environment_id": "e", "group_id": "g", "generated_at_us": 1,
        "observation": {"kind": "resource", "payload": {
            "role": "repository_service", "process_instance_id": "process", "sampled_at_us": 1}},
    })


def test_feed_keeps_missing_counters_null_and_signed_deltas() -> None:
    page = StatisticsFeedResponse(instance_id="process", oldest_sequence=1, next_sequence=2, dropped_count=0, records=(_record(),))
    assert page.records[0].observation.kind == "resource"
    write = WriteValues(rs_operation_id=_ID, process_instance_id="p", logical_net_change_bytes=-1)
    assert write.logical_net_change_bytes == -1
    assert write.after_allocated_bytes is None


@pytest.mark.parametrize("payload", [
    {"schema_version": 2}, {"records": [_record().model_dump()] * 101},
    {"records": [_record(2).model_dump(), _record(1).model_dump()], "next_sequence": 3},
    {"instance_id": "other", "records": [_record().model_dump()]},
    {"path": "/private"},
])
def test_feed_rejects_invalid_version_order_bounds_and_unknown_fields(payload: dict[str, object]) -> None:
    base: dict[str, object] = dict(instance_id="process", oldest_sequence=1, next_sequence=2, dropped_count=0)
    with pytest.raises(ValidationError):
        StatisticsFeedResponse.model_validate({**base, **payload})


@pytest.mark.parametrize("payload", [
    {"category": "public"}, {"category": "filesystem"},
    {"category": "filesystem", "filesystem_id": "disk", "logical_bytes": 1},
    {"category": "repository", "total_bytes": 1},
])
def test_storage_categories_preserve_capacity_scope(payload: dict[str, object]) -> None:
    from gateway_repository_contracts.statistics import StorageValues

    with pytest.raises(ValidationError):
        StorageValues.model_validate({"window_end_us": 1, **payload})
