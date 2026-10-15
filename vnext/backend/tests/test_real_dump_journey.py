"""Safety checks for the host-side real dump journey runner."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pyarrow as pa
import pyarrow.ipc as pa_ipc

from benchmarks import real_dump_journey
from benchmarks.real_dump_journey import (
    INITIAL_OPERATION_TIMEOUT_SECONDS,
    JOURNEY_STEP_IDS,
    JourneyFailure,
    JourneyStepRunner,
    _assert_preview_summaries,
    _history_surface_ref,
    _keyless_fallback_candidates,
    _ordered_table_row_counts,
    _operation_timeout_seconds,
    _parse_cpu_stat,
    _pseudo_counts_from_http,
    _require_one_of,
    _step_measurement,
)

pytestmark = pytest.mark.unit

CPU_STAT_INVALID_SHAPES = (
    ("missing usage", "user_usec 7\nsystem_usec 4\n"),
    ("malformed", "usage_usec nope\n"),
    ("negative", "usage_usec -1\n"),
    ("duplicate", "usage_usec 4\nusage_usec 5\n"),
)

PREVIEW_SUMMARY_FAILURES = (
    (
        "empty table summary",
        {"table_count": 0, "changed_table_count": 0, "degraded_table_count": 0, "failed_table_count": 0},
        False,
    ),
    (
        "degraded table",
        {"table_count": 3, "changed_table_count": 0, "degraded_table_count": 1, "failed_table_count": 0},
        False,
    ),
    (
        "repeat changed",
        {"table_count": 3, "changed_table_count": 1, "degraded_table_count": 0, "failed_table_count": 0},
        True,
    ),
)


def _cpu_snapshot(usage_usec: int) -> dict[str, dict[str, int]]:
    return {
        service: {
            "usage_usec": usage_usec,
            "user_usec": usage_usec - 10,
            "system_usec": 10,
        }
        for service in ("backend", "worker", "repository-service")
    }


@pytest.mark.parametrize(
    ("case", "payload"),
    (
        ("counters", "usage_usec 123\nuser_usec 100\nsystem_usec 23\n"),
        ("extra cgroup counters", "usage_usec 123\nnr_periods 5\nnr_throttled 1\n"),
    ),
    ids=("standard", "additional-counters"),
)
def test_cpu_stat_parser_keeps_nonnegative_integer_counters(case: str, payload: str) -> None:
    del case
    parsed = _parse_cpu_stat(payload)

    assert parsed["usage_usec"] == 123


@pytest.mark.parametrize(
    ("case", "payload"),
    CPU_STAT_INVALID_SHAPES,
    ids=[case for case, _payload in CPU_STAT_INVALID_SHAPES],
)
def test_cpu_stat_parser_rejects_incomplete_or_invalid_counters(
    case: str,
    payload: str,
) -> None:
    del case
    with pytest.raises(JourneyFailure):
        _parse_cpu_stat(payload)


def test_step_measurement_reports_wall_and_per_container_cpu_deltas() -> None:
    started = time.monotonic()

    measurement = _step_measurement(
        started_monotonic=started,
        started_utc="2026-10-14T10:00:00.000Z",
        cpu_start=_cpu_snapshot(100_000),
        cpu_end=_cpu_snapshot(1_100_000),
    )

    assert measurement["started_at_utc"] == "2026-10-14T10:00:00.000Z"
    assert measurement["wall_seconds"] >= 0
    assert measurement["cpu_seconds"] == {
        "backend": 1.0,
        "worker": 1.0,
        "repository-service": 1.0,
    }
    assert measurement["cpu_delta_usec"] == {
        "backend": 1_000_000,
        "worker": 1_000_000,
        "repository-service": 1_000_000,
    }


def test_operation_timeout_uses_five_times_measurement_with_five_minute_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _operation_timeout_seconds("t1", "v1-preview") == 300
    assert _operation_timeout_seconds("t2", "v1-preview") == 3_612
    assert _operation_timeout_seconds("t2", "v1-submit") == 1_186
    assert _operation_timeout_seconds("t2", "repeat-v1-preview") == 3_069
    assert _operation_timeout_seconds("t2", "v2-preview") == 3_521
    assert _operation_timeout_seconds("t2", "v2-submit") == 1_196
    assert _operation_timeout_seconds("t2", "history") == 2_514
    assert _operation_timeout_seconds("t3", "v1-preview") == 6_225
    assert _operation_timeout_seconds("t3", "v1-submit") == 2_404
    assert _operation_timeout_seconds("t3", "repeat-v1-preview") == 6_827
    assert _operation_timeout_seconds("t3", "v2-preview") == 7_642
    assert _operation_timeout_seconds("t3", "v2-submit") == 2_484
    assert _operation_timeout_seconds("t3", "history") == 4_823
    assert _operation_timeout_seconds("t4", "v1-preview") == 12_908
    assert _operation_timeout_seconds("t4", "v1-submit") == 4_076
    assert _operation_timeout_seconds("t4", "repeat-v1-preview") == 3_600
    assert _operation_timeout_seconds("t4", "unknown") == INITIAL_OPERATION_TIMEOUT_SECONDS
    assert _operation_timeout_seconds("t4", "history") == INITIAL_OPERATION_TIMEOUT_SECONDS

    monkeypatch.setitem(
        real_dump_journey.MEASURED_OPERATION_WALL_SECONDS,
        "t2:v2-submit",
        180.01,
    )
    assert _operation_timeout_seconds("t2", "v2-submit") == 901

    monkeypatch.setitem(
        real_dump_journey.MEASURED_OPERATION_WALL_SECONDS,
        "t2:v2-submit",
        45.0,
    )
    assert _operation_timeout_seconds("t2", "v2-submit") == 300

    with pytest.raises(JourneyFailure, match="unknown tier"):
        _operation_timeout_seconds("t5", "history")


def test_journey_step_runner_emits_metrics_and_persists_debug_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshots = iter((_cpu_snapshot(100), _cpu_snapshot(500)))
    monkeypatch.setattr(
        real_dump_journey,
        "_container_cpu_stats",
        lambda _env: next(snapshots),
    )
    state_path = tmp_path / "t1.state.json"
    state: dict[str, Any] = {}
    runner = JourneyStepRunner(
        tier="t1",
        env={},
        state=state,
        from_step=None,
        state_path=state_path,
    )

    assert runner.run("v1-workspace", lambda: {"workspace_id": "ws-test"}) == {
        "workspace_id": "ws-test"
    }
    assert json.loads(state_path.read_text(encoding="utf-8"))["v1-workspace"] == {
        "workspace_id": "ws-test"
    }
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["event"] for item in events] == ["step_started", "step_succeeded"]
    assert all(item["timestamp_utc"].endswith("Z") for item in events)
    assert events[1]["metrics"]["cpu_seconds"]["worker"] == 0.0


def test_journey_step_runner_reuses_completed_steps_before_resume_point(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        real_dump_journey,
        "_container_cpu_stats",
        lambda _env: pytest.fail("a reused step must not read container metrics"),
    )
    runner = JourneyStepRunner(
        tier="t1",
        env={},
        state={"v1-workspace": {"workspace_id": "saved"}},
        from_step="v1-upload",
        state_path=None,
    )

    workspace = runner.run(
        "v1-workspace",
        lambda: pytest.fail("a reused step must not run again"),
    )

    assert workspace == {"workspace_id": "saved"}
    assert json.loads(capsys.readouterr().out)["event"] == "step_reused"


def test_preview_summary_requires_one_complete_pair() -> None:
    manifest = {
        "pairs": [
            {
                "summary": {
                    "table_count": 3,
                    "changed_table_count": 0,
                    "degraded_table_count": 0,
                    "failed_table_count": 0,
                }
            }
        ]
    }

    summary = _assert_preview_summaries(
        manifest,
        unchanged=True,
    )

    assert summary == {
        "pair_count": 1,
        "table_count": 3,
        "changed_table_count": 0,
        "degraded_table_count": 0,
        "failed_table_count": 0,
    }


@pytest.mark.parametrize(
    ("case", "summary", "unchanged"),
    PREVIEW_SUMMARY_FAILURES,
    ids=[case for case, _summary, _unchanged in PREVIEW_SUMMARY_FAILURES],
)
def test_preview_summary_rejects_incomplete_degradation_or_change(
    case: str,
    summary: dict[str, int],
    unchanged: bool,
) -> None:
    del case
    with pytest.raises(JourneyFailure):
        _assert_preview_summaries(
            {"pairs": [{"summary": summary}]},
            unchanged=unchanged,
        )


def test_keyless_fallback_candidates_come_from_census_unresolved_tables() -> None:
    names = _keyless_fallback_candidates(
        {
            "effective_key_scan": {
                "unresolved_tables": ["fallback_b", "fallback_a", "fallback_b"]
            }
        }
    )

    assert names == ("fallback_a", "fallback_b")


def test_repository_pseudo_counts_use_row_streams_and_census_row_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = pa.schema([("gid", pa.int64())])

    def arrow_stream(values: list[int]) -> bytes:
        sink = pa.BufferOutputStream()
        with pa_ipc.new_stream(sink, schema) as writer:
            if values:
                writer.write_batch(
                    pa.RecordBatch.from_arrays([pa.array(values, type=pa.int64())], schema=schema)
                )
        return cast(bytes, sink.getvalue().to_pybytes())

    class FakeRepositoryClient:
        def __init__(self, **_kwargs: Any) -> None:
            self.requested_tables: list[str] = []

        def __enter__(self) -> FakeRepositoryClient:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def close(self) -> None:
            return None

        def get(self, path: str, *, params: dict[str, str]) -> httpx.Response:
            assert path.endswith("/rows")
            table_name = params["table_name"]
            self.requested_tables.append(table_name)
            rows = {
                "ordered_with_pseudo": arrow_stream([3_999_999_999, 4_000_000_000, 4_000_000_001]),
                "ordered_without_rows": arrow_stream([]),
            }
            return httpx.Response(200, content=rows[table_name])

    fake_clients: list[FakeRepositoryClient] = []

    def fake_client(**kwargs: Any) -> FakeRepositoryClient:
        client = FakeRepositoryClient(**kwargs)
        fake_clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)

    counts = _pseudo_counts_from_http(
        base_url="http://repository.invalid",
        repository_id="repository-id",
        commit_id="a" * 32,
        expected_tables={"ordered_with_pseudo": 2, "ordered_without_rows": 0},
        expected_row_counts={"ordered_with_pseudo": 3, "ordered_without_rows": 0},
    )

    assert counts == {
        "ordered_table_count": 2,
        "ordered_row_count_total": 3,
        "ordered_table_pseudo_counts": {"ordered_with_pseudo": 2, "ordered_without_rows": 0},
        "pseudo_rows_total": 2,
    }
    assert fake_clients[0].requested_tables == ["ordered_with_pseudo", "ordered_without_rows"]


def test_ordered_census_row_counts_are_selected_by_table() -> None:
    census = {
        "ordered_projection": {
            "status": "COMPLETE",
            "tables": {
                "table_a": {"status": "COMPLETE", "row_count": 2},
                "table_b": {"status": "COMPLETE", "row_count": 0},
            },
        }
    }

    assert _ordered_table_row_counts(census) == {"table_a": 2, "table_b": 0}


def test_history_bundle_surface_reference_is_selected_from_its_single_pair() -> None:
    surface_ref = {
        "artifact_id": "surface-abc",
        "media_type": "application/json",
        "raw_sha256": "sha256:" + "a" * 64,
        "size_bytes": 12,
    }
    bundle = {
        "pairs": [{"pair_id": "op-p0"}],
        "closure_entries": [
            {
                "kind": "SURFACE",
                "logical_path": "pairs/op-p0/comparison-surface.json",
                "artifact_ref": surface_ref,
            }
        ],
    }

    assert _history_surface_ref(bundle) == surface_ref


@pytest.mark.parametrize(
    ("status_code", "accepted"),
    ((200, True), (201, True), (409, False)),
    ids=("replayed", "created", "conflict"),
)
def test_idempotent_http_acceptance_handles_replay_status(
    status_code: int,
    accepted: bool,
) -> None:
    response = httpx.Response(status_code, json={"status": "QUEUED"})

    if accepted:
        assert _require_one_of(response, {200, 201}, "test acceptance") == {"status": "QUEUED"}
    else:
        with pytest.raises(JourneyFailure, match="HTTP 409"):
            _require_one_of(response, {200, 201}, "test acceptance")


def test_cli_passes_tier_resume_and_keep_stack_controls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, Any] = {}

    def fake_run_journey(**kwargs: Any) -> dict[str, str]:
        calls.update(kwargs)
        return {"conclusion": "PASS"}

    monkeypatch.setattr(real_dump_journey, "run_journey", fake_run_journey)

    result = real_dump_journey.main(
        [
            "--tier",
            "t1",
            "--from-step",
            "v2-preview",
            "--keep-stack",
            "--project-name",
            "s2b-debug",
        ]
    )

    assert result == 0
    assert calls == {
        "tier_filter": "t1",
        "from_step": "v2-preview",
        "keep_stack": True,
        "requested_project_name": "s2b-debug",
    }
    assert json.loads(capsys.readouterr().out) == {"conclusion": "PASS"}


def test_debug_step_order_covers_every_business_action() -> None:
    assert JOURNEY_STEP_IDS[0] == "v1-workspace"
    assert JOURNEY_STEP_IDS[-1] == "history"
    assert "v1-submit" in JOURNEY_STEP_IDS
    assert "repeat-v1-submit" in JOURNEY_STEP_IDS
