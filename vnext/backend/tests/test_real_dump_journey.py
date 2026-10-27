"""Safety checks for the host-side real dump journey runner."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_repository_contracts import GetOperationResponse

from benchmarks import real_dump_journey
from benchmarks.real_dump_journey import (
    INITIAL_OPERATION_TIMEOUT_SECONDS,
    JOURNEY_STEP_IDS,
    JourneyFailure,
    JourneyStepRunner,
    _assert_identity_pair,
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
    WorkerHeartbeatMonitor,
    WorkerHeartbeatTracker,
    WorkerStalledFailure,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.infrastructure.control_db.database import (
    connect_control_db,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db.sqlite_submission import submit_attempt_to_row

pytestmark = pytest.mark.unit

REPOSITORY_OPERATION_ID = "00000000-0000-0000-0000-000000000001"


def _succeeded_repository_operation_payload(operation_id: str) -> dict[str, Any]:
    response = GetOperationResponse.model_validate(
        {
            "operation": {
                "operation_id": operation_id,
                "status": "SUCCEEDED",
                "result": {
                    "commit_id": "commit-2",
                    "target_ref": "main",
                    "artifact_id": "00000000-0000-0000-0000-000000000002",
                    "canonicalization_manifest_digest": "sha256:" + "a" * 64,
                    "expected_commit_id": "commit-1",
                    "completed_verification_policy": "STRUCTURAL",
                    "unknown_type_policy": "REJECT",
                },
                "error": None,
            }
        }
    )
    return response.model_dump(mode="json")


def _initialize_repository_service_control_db(db_path: Path) -> None:
    service_source = Path(__file__).resolve().parents[2] / "repository_service" / "src"
    initialize_script = """
import sys
import types
from pathlib import Path

source = Path(sys.argv[1])
package = types.ModuleType("gateway_repository_service")
package.__path__ = [str(source / "gateway_repository_service")]
sys.modules["gateway_repository_service"] = package
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore

store = ControlStore.open(
    Path(sys.argv[2]),
    expected_version=CONTROL_DB_USER_VERSION,
    busy_timeout_ms=1000,
)
store.close()
"""
    subprocess.run(
        [sys.executable, "-c", initialize_script, str(service_source), str(db_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60.0,
    )


def _seed_repository_import_operation(
    db_path: Path,
    *,
    completed_at: str | None,
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO repository_import_operations (
                operation_id, repository_scope, key_hash, request_fingerprint,
                artifact_id, artifact_media_type, artifact_size_bytes,
                artifact_raw_sha256, target_ref, expected_commit_id,
                requested_verification_policy, unknown_type_policy, status,
                private_ref_name, operation_marker, enqueue_sequence, result_json,
                created_at, started_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                REPOSITORY_OPERATION_ID,
                "repository-1",
                b"k" * 32,
                b"fingerprint",
                "artifact-1",
                "application/vnd.gateway.repository-import+zip",
                1,
                "a" * 64,
                "main",
                "commit-1",
                "STRUCTURAL",
                "REJECT",
                "SUCCEEDED",
                "private-ref-1",
                "operation-marker-1",
                1,
                "{}",
                "2026-10-20T15:00:00+00:00",
                "2026-10-20T15:00:05+00:00",
                "2026-10-20T15:01:05+00:00",
                completed_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()

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

IDENTITY_ASSESSMENT_CASES = (
    ("empty baseline", "NOT_APPLICABLE", "DETAILED", "NOT_APPLICABLE"),
    ("same project", "SAME_PROJECT", "DETAILED", "APPLICABLE"),
    (
        "different project replacement",
        "DIFFERENT_PROJECT",
        "DATASET_REPLACEMENT",
        "APPLICABLE",
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

COMPOSE_LOGS_ON_FAILURE_CASES = (
    ("stack startup", "synthetic Compose startup failure"),
    ("journey step", "synthetic Preview failure"),
    ("worker stall", "worker_stalled"),
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


def _seed_succeeded_submit_control_db(
    db_path: Path,
    *,
    repository_operation_id: str | None,
) -> None:
    initialize_control_db(db_path)
    connection = connect_control_db(db_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO workspace_records (
                    workspace_id, owner_actor_id, gateway_device_external_key,
                    business_project_id, repository_id, state, generation,
                    optimistic_version, current_upload_revision_id,
                    current_preview_result_id, created_at_us, updated_at_us, closed_at_us
                ) VALUES ('workspace-1', 'actor-1', 'device-1', 'project-1', 'repository-1',
                          'OPEN', 1, 0, NULL, NULL, 1, 1, NULL)
                """
            )
            connection.execute(
                """
                INSERT INTO operation_records (
                    operation_id, contract_version, optimistic_version, job_kind,
                    job_contract_version, job_payload, job_payload_ref, business_refs,
                    artifact_refs, repository_operation_id, checkpoint_ref, ready_closure_ref,
                    status, diagnostic, cancel_requested, created_at_us, updated_at_us,
                    completed_at_us
                ) VALUES (?, 'operation-runtime/v1', 1, 'submit', 'backend-submit/v1',
                          NULL, NULL, ?, X'5B5D', NULL, NULL, NULL, 'SUCCEEDED', NULL,
                          0, 1, 2, 2)
                """,
                (
                    "operation-1",
                    json.dumps(
                        [{"kind": "submit_attempt", "value": "submit-attempt-1"}],
                        separators=(",", ":"),
                    ).encode(),
                ),
            )
            connection.execute(
                """
                INSERT INTO step_records (
                    step_id, operation_id, contract_version, optimistic_version,
                    step_name, attempt_count, status, diagnostic, cancel_requested,
                    retry_not_before_us, worker_id, lease_token, lease_expires_at_us,
                    checkpoint_ref, prior_output_refs, created_at_us, updated_at_us,
                    started_at_us, completed_at_us, eligible_at_us
                ) VALUES ('step-1', 'operation-1', 'operation-runtime/v1', 1,
                          'await_import_result', 2, 'SUCCEEDED', NULL, 0, NULL, NULL,
                          NULL, NULL, NULL, X'5B5D', 1, 2, 1, 2, NULL)
                """
            )
            timestamp = datetime(2026, 10, 20, 15, 0, 0, tzinfo=UTC)
            attempt = SubmitAttempt(
                submit_attempt_id="submit-attempt-1",
                workspace_id="workspace-1",
                workspace_generation=1,
                upload_revision_id="upload-1",
                preview_result_id="preview-1",
                repository_id="repository-1",
                business_baseline_node_id="baseline-1",
                business_baseline_commit_id="commit-base",
                baseline_head_version=1,
                repository_expected_commit_id="commit-expected",
                canonical_business_digest="sha256:canonical",
                source_digest="sha256:source",
                snapshot_digest="sha256:snapshot",
                source_artifact_refs=(),
                canonical_table_set_closure_ref="table-closure-1",
                canonical_table_set_closure_digest="sha256:table-closure",
                preview_ready_closure_ref="preview-closure-1",
                preview_ready_closure_digest="sha256:preview-closure",
                canonicalization_manifest_ref="manifest-1",
                canonicalization_manifest_digest="sha256:manifest",
                repository_import_artifact_ref=BackendArtifactRef(
                    artifact_id="backend-artifact-1",
                    media_type="application/vnd.gateway.repository-import",
                    size_bytes=1,
                    raw_sha256="sha256:" + "a" * 64,
                ),
                repository_artifact_ref=RepositoryArtifactRef(
                    artifact_id="repository-artifact-1",
                    media_type="application/vnd.gateway.repository-artifact",
                    size_bytes=1,
                    raw_sha256="sha256:" + "b" * 64,
                ),
                repository_operation_id=repository_operation_id,
                repository_operation_evidence="confirmed",
                requested_target_ref=SubmitTargetRef.MAIN,
                requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
                requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
                builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
                accept_idempotency_key="accept-1",
                accept_request_fingerprint="sha256:accept",
                repository_upload_idempotency_key="upload-1",
                repository_import_idempotency_key="import-1",
                operation_id="operation-1",
                state=SubmitAttemptState.FINALIZED,
                submission_id="submission-1",
                optimistic_version=1,
                created_by="actor-1",
                created_at=timestamp,
                prepared_canonicalization_manifest_ref="prepared-manifest-1",
                prepared_canonicalization_manifest_digest="sha256:prepared-manifest",
                effect_pending_at=timestamp,
                finalized_at=timestamp,
            )
            attempt_values = submit_attempt_to_row(attempt)
            placeholders = ", ".join("?" for _ in attempt_values)
            connection.execute(
                f"INSERT INTO submit_attempt_records VALUES ({placeholders})",
                attempt_values,
            )
    finally:
        connection.close()


def _run_submit_control_query_against_database(
    monkeypatch: pytest.MonkeyPatch,
    db_path: Path,
    repository_db_path: Path | None = None,
) -> None:
    def run_local_control_query(
        _env: dict[str, str],
        *command: str,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ("exec", "-T")
        service = command[2]
        assert service in {"backend", "repository-service"}
        assert command[3:5] == ("python", "-c")
        script, container_db_path, operation_id = command[5:]
        if service == "backend":
            assert container_db_path == "/var/lib/gateway/control/control.sqlite3"
            local_db_path = db_path
        else:
            assert (
                container_db_path
                == real_dump_journey.REPOSITORY_SERVICE_CONTROL_DB_PATH
            )
            assert repository_db_path is not None
            local_db_path = repository_db_path
        return subprocess.run(
            [sys.executable, "-c", script, str(local_db_path), operation_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    monkeypatch.setattr(real_dump_journey, "run_compose", run_local_control_query)


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


def test_worker_heartbeat_log_resets_stall_clock_and_normal_heartbeats_do_not_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [0.0]
    tracker = WorkerHeartbeatTracker(
        stall_threshold_seconds=120,
        monotonic=lambda: current_time[0],
    )
    monkeypatch.setenv("GATEWAY_REAL_DUMP_WORKER_STALL_SECONDS", "45")
    assert real_dump_journey._worker_stall_threshold_seconds() == 45
    monkeypatch.setenv("GATEWAY_REAL_DUMP_WORKER_STALL_SECONDS", "120")

    assert tracker.check_running_operation("operation-1", "RUNNING") is None
    for heartbeat_at in range(10, 131, 10):
        current_time[0] = float(heartbeat_at)
        assert tracker.observe_log_line(
            "worker operation_worker_event code=heartbeat_succeeded "
            "operation_id=operation-1 step_id=step-1 worker_id=worker-1 attempt=1",
            observed_at=current_time[0],
        )
        assert tracker.check_running_operation(
            "operation-1",
            "RUNNING",
            now=current_time[0],
        ) is None

    current_time[0] = 249.0
    assert tracker.check_running_operation("operation-1", "RUNNING") is None
    current_time[0] = 250.0
    stalled = tracker.check_running_operation("operation-1", "RUNNING")
    assert stalled is not None
    assert stalled.step_id == "step-1"
    assert stalled.stalled_seconds == 120.0


def test_worker_stall_monitor_tracks_nonterminal_status_after_running() -> None:
    current_time = [0.0]
    tracker = WorkerHeartbeatTracker(
        stall_threshold_seconds=120,
        monotonic=lambda: current_time[0],
    )

    assert tracker.check_running_operation("operation-1", "QUEUED") is None
    current_time[0] = 300.0
    assert tracker.check_running_operation("operation-1", "QUEUED") is None

    current_time[0] = 400.0
    assert tracker.check_running_operation("operation-1", "RUNNING") is None
    current_time[0] = 410.0
    assert tracker.observe_log_line(
        "worker operation_worker_event code=heartbeat_succeeded "
        "operation_id=operation-1 step_id=step-1 worker_id=worker-1 attempt=1",
        observed_at=current_time[0],
    )

    current_time[0] = 529.0
    assert (
        tracker.check_running_operation("operation-1", "MANUAL_RECOVERY_REQUIRED")
        is None
    )
    current_time[0] = 530.0
    stalled = tracker.check_running_operation(
        "operation-1",
        "MANUAL_RECOVERY_REQUIRED",
    )
    assert stalled is not None
    assert stalled.step_id == "step-1"
    assert stalled.stalled_seconds == 120.0

    current_time[0] = 600.0
    assert tracker.check_running_operation("operation-1", "FAILED") is None
    current_time[0] = 900.0
    assert (
        tracker.check_running_operation("operation-1", "MANUAL_RECOVERY_REQUIRED")
        is None
    )


def test_worker_stall_diagnostics_precede_teardown_and_have_distinct_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current_time = [0.0]
    events: list[str] = []
    diagnostics = tmp_path / "s4-stall-test"
    tracker = WorkerHeartbeatTracker(
        stall_threshold_seconds=2,
        monotonic=lambda: current_time[0],
    )

    def capture_diagnostics(**_kwargs: object) -> Path:
        events.append("diagnostics")
        return diagnostics

    monitor = WorkerHeartbeatMonitor(
        env={},
        repository_id="repository-1",
        repository_url="http://repository-service",
        tracker=tracker,
        diagnostic_capture=capture_diagnostics,
    )

    class OperationClient:
        def get(self, _path: str) -> httpx.Response:
            return httpx.Response(200, json={"status": "RUNNING"})

    def sleep(delay: float) -> None:
        current_time[0] += delay

    monkeypatch.setattr(time, "monotonic", lambda: current_time[0])
    monkeypatch.setattr(time, "sleep", sleep)
    try:
        with pytest.raises(WorkerStalledFailure) as caught:
            real_dump_journey._poll_operation(
                cast(httpx.Client, OperationClient()),
                "operation-1",
                stage="t4 v1 Submit",
                timeout_seconds=10,
                heartbeat_monitor=monitor,
            )
    finally:
        events.append("teardown")

    assert caught.value.reason == "worker_stalled"
    assert caught.value.diagnostics == diagnostics
    assert events == ["diagnostics", "teardown"]


def test_worker_stall_diagnostics_capture_nested_repository_operation_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class OperationResponse:
        status_code = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def json(self) -> dict[str, Any]:
            return self.payload

    class OperationClient:
        def __enter__(self) -> OperationClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _url: str, *, headers: dict[str, str]) -> OperationResponse:
            assert headers
            return OperationResponse(_succeeded_repository_operation_payload(REPOSITORY_OPERATION_ID))

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: OperationClient())
    real_dump_journey._capture_repository_import_status(
        repository_url="http://repository-service",
        repository_id="repository-1",
        operation_id=REPOSITORY_OPERATION_ID,
        root=tmp_path,
    )

    status = json.loads((tmp_path / "repository-operation-public-status.json").read_text())
    assert status == {
        "http_status": 200,
        "operation_id": REPOSITORY_OPERATION_ID,
        "status": "SUCCEEDED",
    }


def test_succeeded_submit_reconciliation_records_repository_import_durations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_import_tmp = tmp_path / "repository-import-tmp"
    repository_import_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(repository_import_tmp))
    db_path = tmp_path / "backend-control.sqlite3"
    _seed_succeeded_submit_control_db(
        db_path,
        repository_operation_id=REPOSITORY_OPERATION_ID,
    )
    repository_db_path = tmp_path / "repository-service-control.sqlite3"
    _initialize_repository_service_control_db(repository_db_path)
    _seed_repository_import_operation(
        repository_db_path,
        completed_at="2026-10-20T15:01:05+00:00",
    )
    _run_submit_control_query_against_database(monkeypatch, db_path, repository_db_path)

    class OperationResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return _succeeded_repository_operation_payload(REPOSITORY_OPERATION_ID)

    class OperationClient:
        def __enter__(self) -> OperationClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, url: str, *, headers: dict[str, str]) -> OperationResponse:
            assert url.endswith(f"/operations/{REPOSITORY_OPERATION_ID}")
            assert headers
            return OperationResponse()

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: OperationClient())
    facts = real_dump_journey._capture_submit_reconciliation_facts(
        env={"PATH": "/usr/bin"},
        repository_url="http://repository-service",
        repository_id="repository-1",
        operation_id="operation-1",
        root=tmp_path / "submit-facts",
        enforce_three_session_limit=True,
    )

    assert facts["repository_operation_id"] == REPOSITORY_OPERATION_ID
    assert facts["await_import_result_attempt_count"] == 2
    assert facts["repository_import_elapsed_seconds"] == 60.0
    assert facts["repository_import_queue_seconds"] == 5.0
    assert facts["repository_import_status"] == "SUCCEEDED"
    selected_rows = json.loads(
        (tmp_path / "submit-facts" / "control-db-selected-rows.json").read_text()
    )
    assert selected_rows["submit_attempt"] == {
        "repository_operation_id": REPOSITORY_OPERATION_ID,
        "submit_attempt_id": "submit-attempt-1",
    }
    assert selected_rows["steps"][0]["step_name"] == "await_import_result"
    assert selected_rows["steps"][0]["attempt_count"] == 2
    repository_row = json.loads(
        (tmp_path / "submit-facts" / "repository-import-control-row.json").read_text()
    )
    assert repository_row == {
        "status": "SUCCEEDED",
        "created_at": "2026-10-20T15:00:00+00:00",
        "started_at": "2026-10-20T15:00:05+00:00",
        "completed_at": "2026-10-20T15:01:05+00:00",
    }
    assert list(repository_import_tmp.glob("repository-import-*.sqlite3*")) == []


def test_submit_reconciliation_fails_when_repository_import_completion_time_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_import_tmp = tmp_path / "repository-import-tmp"
    repository_import_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(repository_import_tmp))
    db_path = tmp_path / "backend-control.sqlite3"
    _seed_succeeded_submit_control_db(
        db_path,
        repository_operation_id=REPOSITORY_OPERATION_ID,
    )
    repository_db_path = tmp_path / "repository-service-control.sqlite3"
    _initialize_repository_service_control_db(repository_db_path)
    _seed_repository_import_operation(repository_db_path, completed_at=None)
    _run_submit_control_query_against_database(monkeypatch, db_path, repository_db_path)

    class OperationResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return _succeeded_repository_operation_payload(REPOSITORY_OPERATION_ID)

    class OperationClient:
        def __enter__(self) -> OperationClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _url: str, *, headers: dict[str, str]) -> OperationResponse:
            assert headers
            return OperationResponse()

    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: OperationClient())
    with pytest.raises(JourneyFailure, match="completed_at timestamp is missing"):
        real_dump_journey._capture_submit_reconciliation_facts(
            env={"PATH": "/usr/bin"},
            repository_url="http://repository-service",
            repository_id="repository-1",
            operation_id="operation-1",
            root=tmp_path / "submit-facts",
            enforce_three_session_limit=True,
        )
    assert list(repository_import_tmp.glob("repository-import-*.sqlite3*")) == []


def test_succeeded_submit_without_attempt_repository_identity_fails_reconciliation_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "control.sqlite3"
    _seed_succeeded_submit_control_db(db_path, repository_operation_id=None)
    _run_submit_control_query_against_database(monkeypatch, db_path)

    with pytest.raises(JourneyFailure, match="missing from its attempt record"):
        real_dump_journey._capture_submit_reconciliation_facts(
            env={"PATH": "/usr/bin"},
            repository_url="http://repository-service",
            repository_id="repository-1",
            operation_id="operation-1",
            root=tmp_path / "submit-facts",
            enforce_three_session_limit=True,
        )


def test_operation_timeout_remains_distinct_from_worker_stall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [0.0]

    class OperationClient:
        def get(self, _path: str) -> httpx.Response:
            return httpx.Response(200, json={"status": "RUNNING"})

    monkeypatch.setattr(time, "monotonic", lambda: current_time[0])
    monkeypatch.setattr(time, "sleep", lambda delay: current_time.__setitem__(0, current_time[0] + delay))
    with pytest.raises(JourneyFailure, match="before timeout") as caught:
        real_dump_journey._poll_operation(
            cast(httpx.Client, OperationClient()),
            "operation-1",
            stage="t1 Preview",
            timeout_seconds=3,
        )
    assert not isinstance(caught.value, WorkerStalledFailure)


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
    ("case", "status", "mode", "applicability"),
    IDENTITY_ASSESSMENT_CASES,
    ids=[case for case, _status, _mode, _applicability in IDENTITY_ASSESSMENT_CASES],
)
def test_real_data_journey_requires_the_expected_project_identity(
    case: str,
    status: str,
    mode: str,
    applicability: str,
) -> None:
    del case
    preview = {
        "result": {
            "identity_assessment_set_digest": "sha256:" + "a" * 64,
            "identity_pairs": [
                {
                    "applicability": applicability,
                    "status": status,
                    "mode": mode,
                }
            ],
        }
    }

    result = _assert_identity_pair(
        preview,
        expected_status=status,
        expected_mode=mode,
    )

    assert result == {
        "assessment_set_digest": "sha256:" + "a" * 64,
        "applicability": applicability,
        "status": status,
        "mode": mode,
    }


@pytest.mark.parametrize(
    ("expected_status", "expected_mode", "actual_status", "actual_mode", "applicability"),
    (
        ("SAME_PROJECT", "DETAILED", "DIFFERENT_PROJECT", "DATASET_REPLACEMENT", "APPLICABLE"),
        ("DIFFERENT_PROJECT", "DATASET_REPLACEMENT", "SAME_PROJECT", "DETAILED", "APPLICABLE"),
        ("NOT_APPLICABLE", "DETAILED", "NOT_APPLICABLE", "DETAILED", "APPLICABLE"),
    ),
    ids=("unexpected-project-change", "missed-project-change", "applicability-mismatch"),
)
def test_real_data_journey_stops_when_project_identity_differs(
    expected_status: str,
    expected_mode: str,
    actual_status: str,
    actual_mode: str,
    applicability: str,
) -> None:
    with pytest.raises(JourneyFailure, match="identity differs"):
        _assert_identity_pair(
            {
                "result": {
                    "identity_assessment_set_digest": "sha256:" + "a" * 64,
                    "identity_pairs": [
                        {
                            "applicability": applicability,
                            "status": actual_status,
                            "mode": actual_mode,
                        }
                    ],
                }
            },
            expected_status=expected_status,
            expected_mode=expected_mode,
        )


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
        "scope": "full",
        "cross_project": False,
        "from_step": "v2-preview",
        "keep_stack": True,
        "requested_project_name": "s2b-debug",
        "dc32_output": None,
        "debug_t1_submit_probe": False,
    }
    assert json.loads(capsys.readouterr().out) == {"conclusion": "PASS"}


def test_cli_accepts_the_t4_preview_and_submit_debug_scope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: dict[str, Any] = {}

    def fake_run_journey(**kwargs: Any) -> dict[str, str]:
        calls.update(kwargs)
        return {"conclusion": "PASS"}

    monkeypatch.setattr(real_dump_journey, "run_journey", fake_run_journey)

    result = real_dump_journey.main(["--tier", "t4", "--scope", "t4-v1-submit"])

    assert result == 0
    assert calls["tier_filter"] == "t4"
    assert calls["scope"] == "t4-v1-submit"
    assert calls["cross_project"] is False
    assert json.loads(capsys.readouterr().out) == {"conclusion": "PASS"}


@pytest.mark.parametrize(
    ("failure_point", "failure_message"),
    COMPOSE_LOGS_ON_FAILURE_CASES,
    ids=[failure_point for failure_point, _message in COMPOSE_LOGS_ON_FAILURE_CASES],
)
def test_failed_real_dump_saves_logs_and_preserves_requested_stack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_point: str,
    failure_message: str,
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
    monkeypatch.setattr(real_dump_journey, "_repository_service_url", lambda _env: "http://repository")
    monkeypatch.setattr(
        real_dump_journey,
        "_offline_composite_comparison",
            lambda **_kwargs: {"counts": {}, "elapsed_seconds": 0.0},
    )
    monkeypatch.setattr(
        real_dump_journey,
        "acquire_compose_gate_lock",
        lambda: None,
    )
    def start_stack(*_args: Any) -> tuple[str, str]:
        if failure_point == "stack startup":
            raise JourneyFailure(failure_message)
        return "repository-1", "commit-1"

    monkeypatch.setattr(real_dump_journey, "start_three_container_stack", start_stack)

    events: list[str] = []

    class FakeHeartbeatMonitor:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> FakeHeartbeatMonitor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def check_operation(self, *_args: Any, **_kwargs: Any) -> None:
            events.append("diagnostics")
            raise WorkerStalledFailure(
                stage="t4 v1 Submit",
                operation_id="operation-1",
                diagnostics=tmp_path / "s4-stall-test",
            )

    monkeypatch.setattr(real_dump_journey, "WorkerHeartbeatMonitor", FakeHeartbeatMonitor)

    def fail_tier(**_kwargs: Any) -> dict[str, Any]:
        if failure_point == "worker stall":
            cast(WorkerHeartbeatMonitor, _kwargs["heartbeat_monitor"]).check_operation(
                "operation-1",
                "RUNNING",
                stage="t4 v1 Submit",
            )
        raise JourneyFailure(failure_message)

    monkeypatch.setattr(real_dump_journey, "_run_tier", fail_tier)

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

    with pytest.raises(JourneyFailure, match=failure_message):
        real_dump_journey.run_journey(
            tier_filter="t1",
            keep_stack=failure_point == "worker stall",
            requested_project_name="unit-real-dump" if failure_point == "worker stall" else None,
        )

    assert events == (
        ["diagnostics", "logs"]
        if failure_point == "worker stall"
        else ["logs", "cleanup"]
    )
    compose_logs = list(log_directory.glob("*.compose.log"))
    assert len(compose_logs) == 1
    assert "all service logs" in compose_logs[0].read_text(encoding="utf-8")
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["event"] == "compose_logs_saved"


def test_debug_step_order_covers_every_business_action() -> None:
    assert JOURNEY_STEP_IDS[0] == "v1-workspace"
    assert JOURNEY_STEP_IDS.index("history") < JOURNEY_STEP_IDS.index("cross-source-workspace")
    assert JOURNEY_STEP_IDS[-1] == "cross-replacement-archive"
    assert "v1-submit" in JOURNEY_STEP_IDS
    assert "repeat-v1-submit" in JOURNEY_STEP_IDS
