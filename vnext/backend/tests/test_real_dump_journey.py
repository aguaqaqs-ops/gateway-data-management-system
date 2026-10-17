"""Safety checks for the host-side real dump journey runner."""

from __future__ import annotations

import json
import subprocess
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
    _assert_s3_catalog_summary,
    _assert_s3_history_count,
    _assert_s3_preview_summary,
    _assert_preview_summaries,
    _canonical_state_digest_from_submission,
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

S3_PREVIEW_SUMMARY_CASES = (
    ("composite unchanged", {"table_count": 125, "changed_table_count": 4, "degraded_table_count": 0, "failed_table_count": 0}, 4, True),
    ("composite changed", {"table_count": 125, "changed_table_count": 5, "degraded_table_count": 0, "failed_table_count": 0}, 5, True),
    ("unexpected changed count", {"table_count": 125, "changed_table_count": 6, "degraded_table_count": 0, "failed_table_count": 0}, 5, False),
    ("unexpected table count", {"table_count": 124, "changed_table_count": 4, "degraded_table_count": 0, "failed_table_count": 0}, 4, False),
)

CANONICAL_STATE_DIGEST_INPUTS: tuple[tuple[str, dict[str, Any], bool], ...] = (
    ("valid canonical state digest", {"canonical_business_digest": "sha256:" + "a" * 64}, True),
    ("missing digest", {}, False),
    ("wrong digest scheme", {"canonical_business_digest": "sha1:" + "a" * 64}, False),
    ("invalid digest characters", {"canonical_business_digest": "sha256:" + "g" * 64}, False),
)

OPERATION_STATUS_POLL_CASES = (
    ("service not ready retries", (503, 200), True, (2.0,), 1),
    ("internal error remains a failure", (500,), False, (), 0),
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
    assert measurement["cpu_stat_reset_services"] == []


def test_step_measurement_records_counter_reset_without_losing_wall_time() -> None:
    started = time.monotonic()
    cpu_start = _cpu_snapshot(1_000_000)
    cpu_end = _cpu_snapshot(1_100_000)
    cpu_end["worker"] = _cpu_snapshot(100_000)["worker"]

    measurement = _step_measurement(
        started_monotonic=started,
        started_utc="2026-10-14T10:00:00.000Z",
        cpu_start=cpu_start,
        cpu_end=cpu_end,
    )

    assert measurement["wall_seconds"] >= 0
    assert measurement["cpu_seconds"] == {
        "backend": 0.1,
        "worker": None,
        "repository-service": 0.1,
    }
    assert measurement["cpu_delta_usec"] == {
        "backend": 100_000,
        "worker": None,
        "repository-service": 100_000,
    }
    assert measurement["cpu_stat_reset_services"] == ["worker"]


def test_operation_timeout_uses_five_times_measurement_with_five_minute_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _operation_timeout_seconds("t1", "v1-preview") == 300
    assert _operation_timeout_seconds("t1", "v1-submit") == 300
    assert _operation_timeout_seconds("t1", "repeat-v1-preview") == 316
    assert _operation_timeout_seconds("t1", "v2-preview") == 386
    assert _operation_timeout_seconds("t1", "v2-submit") == 300
    assert _operation_timeout_seconds("t1", "history") == 315
    assert _operation_timeout_seconds("t2", "v1-preview") == 3_612
    assert _operation_timeout_seconds("t2", "v1-submit") == 1_186
    assert _operation_timeout_seconds("t2", "repeat-v1-preview") == 3_019
    assert _operation_timeout_seconds("t2", "v2-preview") == 3_441
    assert _operation_timeout_seconds("t2", "v2-submit") == 1_186
    assert _operation_timeout_seconds("t2", "history") == 2_464
    assert _operation_timeout_seconds("t3", "v1-preview") == 6_215
    assert _operation_timeout_seconds("t3", "v1-submit") == 2_414
    assert _operation_timeout_seconds("t3", "repeat-v1-preview") == 6_828
    assert _operation_timeout_seconds("t3", "v2-preview") == 7_642
    assert _operation_timeout_seconds("t3", "v2-submit") == 2_480
    assert _operation_timeout_seconds("t3", "history") == 4_813
    assert _operation_timeout_seconds("t4", "v1-preview") == 12_887
    assert _operation_timeout_seconds("t4", "v1-submit") == 4_047
    assert _operation_timeout_seconds("t4", "repeat-v1-preview") == 11_271
    assert _operation_timeout_seconds("t4", "v2-preview") == 11_300
    assert _operation_timeout_seconds("t4", "v2-submit") == 4_055
    assert _operation_timeout_seconds("t4", "unknown") == INITIAL_OPERATION_TIMEOUT_SECONDS
    assert _operation_timeout_seconds("t4", "history") == 6_821

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


def test_operation_terminal_progress_includes_protected_wall_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class OperationClient:
        def get(self, _path: str) -> httpx.Response:
            return httpx.Response(200, json={"status": "SUCCEEDED"})

    result = real_dump_journey._poll_operation(
        cast(httpx.Client, OperationClient()),
        "operation-1",
        stage="t1 Preview",
        timeout_seconds=30,
    )

    assert result == {"status": "SUCCEEDED"}
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    terminal = events[-1]
    assert terminal["event"] == "operation_succeeded"
    assert terminal["operation_status"] == "SUCCEEDED"
    assert terminal["timeout_seconds"] == 30
    assert 0 <= terminal["operation_wall_seconds"] < 30


@pytest.mark.parametrize(
    ("case", "statuses", "succeeds", "expected_sleeps", "expected_retries"),
    OPERATION_STATUS_POLL_CASES,
    ids=[case for case, *_rest in OPERATION_STATUS_POLL_CASES],
)
def test_operation_status_retries_service_not_ready_within_deadline(
    case: str,
    statuses: tuple[int, ...],
    succeeds: bool,
    expected_sleeps: tuple[float, ...],
    expected_retries: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del case
    current_time = [0.0]
    sleeps: list[float] = []
    calls = 0

    class OperationClient:
        def get(self, _path: str) -> httpx.Response:
            nonlocal calls
            status = statuses[calls]
            calls += 1
            if status == 200:
                payload = {"status": "SUCCEEDED"}
            else:
                payload = {"code": "SERVICE_NOT_READY" if status == 503 else "INTERNAL_ERROR"}
            return httpx.Response(status, json=payload)

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        current_time[0] += delay

    monkeypatch.setattr(time, "monotonic", lambda: current_time[0])
    monkeypatch.setattr(time, "sleep", sleep)

    if succeeds:
        result = real_dump_journey._poll_operation(
            cast(httpx.Client, OperationClient()),
            "operation-1",
            stage="t1 Preview",
            timeout_seconds=5,
        )
        assert result["status"] == "SUCCEEDED"
    else:
        with pytest.raises(JourneyFailure, match="HTTP 500"):
            real_dump_journey._poll_operation(
                cast(httpx.Client, OperationClient()),
                "operation-1",
                stage="t1 Preview",
                timeout_seconds=5,
            )

    assert calls == expected_retries + 1
    assert tuple(sleeps) == expected_sleeps
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    retries = [event for event in events if event["event"] == "operation_status_retry"]
    assert len(retries) == expected_retries
    if retries:
        assert retries[0]["status_code"] == 503
        assert retries[0]["retry_count"] == 1


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


@pytest.mark.parametrize(
    ("case", "summary", "expected_changed", "valid"),
    S3_PREVIEW_SUMMARY_CASES,
    ids=[case for case, _summary, _changed, _valid in S3_PREVIEW_SUMMARY_CASES],
)
def test_s3_preview_summary_matches_s2b_plus_composite(
    case: str,
    summary: dict[str, int],
    expected_changed: int,
    valid: bool,
) -> None:
    del case
    if valid:
        _assert_s3_preview_summary(
            summary,
            dataset_id="rd-t1-a-v2",
            expected_changed=expected_changed,
        )
    else:
        with pytest.raises(JourneyFailure):
            _assert_s3_preview_summary(
                summary,
                dataset_id="rd-t1-a-v2",
                expected_changed=expected_changed,
            )


def test_s3_catalog_reconciles_composite_rows_with_s2b_total() -> None:
    _assert_s3_catalog_summary(
        {
            "catalog_table_count": 125,
            "catalog_row_count_total": 3_731,
            "composite_signal_point_row_count": 2,
        },
        dataset_id="rd-t1-a-v1",
        composite_row_count=2,
    )

    with pytest.raises(JourneyFailure):
        _assert_s3_catalog_summary(
            {
                "catalog_table_count": 125,
                "catalog_row_count_total": 3_732,
                "composite_signal_point_row_count": 2,
            },
            dataset_id="rd-t1-a-v1",
            composite_row_count=2,
        )


def test_s3_history_count_adds_production_composite_records() -> None:
    _assert_s3_history_count(tier="t1", actual_record_count=14, composite_record_count=2)
    with pytest.raises(JourneyFailure):
        _assert_s3_history_count(tier="t1", actual_record_count=15, composite_record_count=2)


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
            self.catalog_requests = 0
            self.catalog_payload = json.dumps(
                {
                    "catalog": {
                        "commit_id": "a" * 32,
                        "tables": [
                            {
                                "name": "composite_signal_point",
                                "columns": [
                                    {"name": "source_table", "sql_type": "VARCHAR(64)", "nullable": False},
                                    {"name": "point_gid", "sql_type": "INT", "nullable": False},
                                ],
                                "primary_key": ["source_table", "point_gid"],
                                "row_count": 2,
                            }
                        ],
                    }
                },
                separators=(",", ":"),
            ).encode()

        def __enter__(self) -> FakeRepositoryClient:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def close(self) -> None:
            return None

        def get(
            self,
            path: str,
            *,
            params: dict[str, str] | None = None,
        ) -> httpx.Response:
            if path.endswith("/catalog"):
                self.catalog_requests += 1
                return httpx.Response(200, content=self.catalog_payload)
            assert path.endswith("/rows")
            assert params is not None
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
        "catalog_json_bytes": len(fake_clients[0].catalog_payload),
        "catalog_table_count": 1,
        "catalog_row_count_total": 2,
        "composite_signal_point_row_count": 2,
    }
    assert fake_clients[0].catalog_requests == 1
    assert fake_clients[0].requested_tables == ["ordered_with_pseudo", "ordered_without_rows"]


@pytest.mark.parametrize(
    ("tables", "is_empty"),
    (
        ([], True),
        (
            [
                {
                    "name": "composite_signal_point",
                    "columns": [],
                    "primary_key": [],
                    "row_count": 0,
                }
            ],
            False,
        ),
    ),
    ids=("empty-initial", "nonempty-initial"),
)
def test_initial_repository_commit_must_be_empty(
    monkeypatch: pytest.MonkeyPatch,
    tables: list[dict[str, Any]],
    is_empty: bool,
) -> None:
    class FakeRepositoryClient:
        def __init__(self, **_kwargs: Any) -> None:
            self.closed = False

        def get(self, _path: str) -> httpx.Response:
            return httpx.Response(
                200,
                json={"catalog": {"commit_id": "a" * 32, "tables": tables}},
            )

        def close(self) -> None:
            self.closed = True

    clients: list[FakeRepositoryClient] = []

    def fake_client(**kwargs: Any) -> FakeRepositoryClient:
        client = FakeRepositoryClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)

    if is_empty:
        assert real_dump_journey._assert_initial_repository_commit_empty(
            base_url="http://repository.invalid",
            repository_id="repository-id",
            commit_id="a" * 32,
        ) == {"catalog_table_count": 0, "catalog_row_count_total": 0}
    else:
        with pytest.raises(JourneyFailure, match="not empty"):
            real_dump_journey._assert_initial_repository_commit_empty(
                base_url="http://repository.invalid",
                repository_id="repository-id",
                commit_id="a" * 32,
            )
    assert clients[0].closed


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


@pytest.mark.parametrize(
    ("case", "submission", "valid"),
    CANONICAL_STATE_DIGEST_INPUTS,
    ids=[case for case, _submission, _valid in CANONICAL_STATE_DIGEST_INPUTS],
)
def test_public_submission_digest_is_recorded_as_canonical_state(
    case: str,
    submission: dict[str, Any],
    valid: bool,
) -> None:
    del case
    if valid:
        assert _canonical_state_digest_from_submission(submission, stage="test Submit") == (
            submission["canonical_business_digest"]
        )
    else:
        with pytest.raises(JourneyFailure, match="canonical state digest"):
            _canonical_state_digest_from_submission(submission, stage="test Submit")


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


def test_failed_real_dump_saves_compose_logs_before_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_directory = tmp_path / "compose-logs"
    monkeypatch.setenv("GATEWAY_REAL_DUMP_LOG_DIR", str(log_directory))
    monkeypatch.setattr(real_dump_journey, "_real_dump_root", lambda: tmp_path)
    monkeypatch.setattr(real_dump_journey, "_read_metadata", lambda _root: ({}, {}))

    def fake_subprocess_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        stdout = "ee0a4c43a7\n" if command[:2] == ["git", "rev-parse"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(real_dump_journey, "build_compose_stack_images", lambda _env: None)
    monkeypatch.setattr(
        real_dump_journey,
        "_compose_environment",
        lambda *_args, **_kwargs: {"COMPOSE_PROJECT_NAME": "unit-real-dump"},
    )
    monkeypatch.setattr(
        real_dump_journey,
        "_offline_composite_comparison",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        real_dump_journey,
        "acquire_compose_gate_lock",
        lambda: None,
    )
    monkeypatch.setattr(
        real_dump_journey,
        "start_three_container_stack",
        lambda *_args: ("repository-1", "commit-1"),
    )

    def fail_tier(**_kwargs: Any) -> dict[str, Any]:
        raise JourneyFailure("synthetic Preview failure")

    monkeypatch.setattr(real_dump_journey, "_run_tier", fail_tier)
    events: list[str] = []

    def fake_run_compose(
        _env: dict[str, str],
        *arguments: str,
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        assert arguments == ("logs", "--no-color", "--timestamps")
        events.append("logs")
        return subprocess.CompletedProcess(arguments, 0, stdout="all service logs", stderr="")

    monkeypatch.setattr(real_dump_journey, "run_compose", fake_run_compose)

    def record_cleanup(_env: dict[str, str]) -> None:
        events.append("cleanup")

    monkeypatch.setattr(real_dump_journey, "cleanup_compose_project_artifacts", record_cleanup)

    with pytest.raises(JourneyFailure, match="synthetic Preview failure"):
        real_dump_journey.run_journey(tier_filter="t1")

    assert events == ["logs", "cleanup"]
    compose_logs = list(log_directory.glob("*.compose.log"))
    assert len(compose_logs) == 1
    assert "all service logs" in compose_logs[0].read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["event"] == "compose_logs_saved"


def test_debug_step_order_covers_every_business_action() -> None:
    assert JOURNEY_STEP_IDS[0] == "v1-workspace"
    assert JOURNEY_STEP_IDS[-1] == "history"
    assert "v1-submit" in JOURNEY_STEP_IDS
    assert "repeat-v1-submit" in JOURNEY_STEP_IDS
