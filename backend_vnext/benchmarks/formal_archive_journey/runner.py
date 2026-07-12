from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tarfile
import time
from typing import Any
from urllib.parse import quote
import uuid

import httpx
from fastapi.testclient import TestClient

from ...api.formal_app import VNextFormalAppSettings, create_app
from ...api.formal_security import SsoTicketPayload, sign_sso_ticket
from ...benchmarks._paths import resolve_benchmark_path


DEFAULT_DATASET_ROOT = Path("/home/issac/test-dir/business-benchmark-data/business_large")
DEFAULT_INITIAL_BASELINE_DATASET = "large-1"
DEFAULT_INITIAL_ABNORMAL_DATASET = "large"
DEFAULT_MODIFIED_DATASET = "large-2"

_AUTH_HEADER = {"Authorization": "Bearer gateway-control-plane-internal-dev-token"}
_LOGGER_NAME = "backend_vnext.formal_upload_benchmark"
_TERMINAL_OPERATION_STATUSES = {
    "READY",
    "FAILED_FINAL",
    "FAILED_RETRYABLE",
    "CANCELLED",
    "SUPERSEDED",
}


@dataclass(frozen=True)
class _StageResult:
    name: str
    status: str
    duration_ms: int
    details: dict[str, object]


class FormalArchiveJourneyBenchmarkRunner:
    def __init__(
        self,
        *,
        dataset_root: Path,
        run_root: Path,
        operation_timeout_seconds: float = 3600.0,
    ) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)
        self.run_root = resolve_benchmark_path(run_root)
        self.operation_timeout_seconds = operation_timeout_seconds
        self.summary_path = self.run_root / "summary.json"
        self.events_path = self.run_root / "events.jsonl"

    def run(
        self,
        *,
        baseline_dataset: str = DEFAULT_INITIAL_BASELINE_DATASET,
        abnormal_initial_dataset: str = DEFAULT_INITIAL_ABNORMAL_DATASET,
        modified_dataset: str = DEFAULT_MODIFIED_DATASET,
        include_baseline_initial_diagnostics: bool = True,
    ) -> dict[str, object]:
        self.run_root.mkdir(parents=True, exist_ok=True)
        packages_root = self.run_root / "packages"
        packages_root.mkdir(parents=True, exist_ok=True)
        state_root = self.run_root / "state"
        run_id = f"formal-archive-journey:{uuid.uuid4().hex}"
        previous_benchmark_env = os.environ.get("BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK")
        os.environ["BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK"] = "1"
        event_handler = _JsonlBenchmarkEventHandler(self.events_path)
        logger = logging.getLogger(_LOGGER_NAME)
        logger.addHandler(event_handler)
        logger.setLevel(logging.INFO)
        stages: list[_StageResult] = []
        try:
            packages = {
                "baseline": _build_directory_package(
                    self.dataset_root / baseline_dataset,
                    packages_root / f"{baseline_dataset}.tar.gz",
                ),
                "abnormal_initial": _build_directory_package(
                    self.dataset_root / abnormal_initial_dataset,
                    packages_root / f"{abnormal_initial_dataset}.tar.gz",
                ),
                "modified": _build_directory_package(
                    self.dataset_root / modified_dataset,
                    packages_root / f"{modified_dataset}.tar.gz",
                ),
            }
            app = create_app(
                settings=VNextFormalAppSettings(
                    state_root=state_root,
                ),
                control_plane_transport=httpx.MockTransport(_control_plane_response),
            )
            client = TestClient(app)
            _upsert_gateway(client)
            _consume_session(client)

            workspace_id = self._create_workspace(client)
            upload1 = self._stage(
                stages,
                "upload1_initialize_baseline",
                lambda: self._upload_initialize_baseline(
                    client,
                    workspace_id,
                    packages["baseline"],
                    benchmark_label=baseline_dataset,
                ),
            )
            preview1 = _require_mapping(upload1, "preview_bundle")
            submit1 = self._stage(
                stages,
                "submit1_finalize",
                lambda: self._submit_workspace(
                    client,
                    workspace_id,
                    preview1,
                    packages["baseline"],
                    idempotency_suffix="submit1",
                ),
            )
            submission1 = _require_mapping(submit1, "submission")
            self._stage(
                stages,
                "approve1",
                lambda: self._approve_submission(client, str(submission1["id"])),
            )
            batch1_id = str(_require_mapping(client.get("/api/workspace-tree").json(), "current_batch")["batch_id"])
            archive1 = self._stage(
                stages,
                "archive1_promote",
                lambda: self._archive_approved_submission(
                    client,
                    batch_id=batch1_id,
                    workspace_id=workspace_id,
                    submission_id=str(submission1["id"]),
                    candidate_id="benchmark-mainline-1",
                    idempotency_key=f"{run_id}:archive1",
                ),
            )
            tree_after_archive = client.get("/api/workspace-tree").json()
            workspace2_id = self._create_workspace(client)
            upload2 = self._stage(
                stages,
                "upload2_full_abnormal_initial_modified",
                lambda: self._upload_full(
                    client,
                    workspace2_id,
                    packages["abnormal_initial"],
                    packages["modified"],
                    initial_label=abnormal_initial_dataset,
                    modified_label=modified_dataset,
                ),
            )
            diagnostics_result: dict[str, object] = {"status": "SKIPPED_BY_REQUEST"}
            if include_baseline_initial_diagnostics:
                diagnostics_result = self._stage(
                    stages,
                    "baseline_initial_diagnostics",
                    lambda: self._generate_baseline_initial_diagnostics(client, upload2),
                    accept_failure=True,
                )
            preview2 = _require_mapping(upload2, "preview_bundle")
            submit2 = self._stage(
                stages,
                "submit2_finalize",
                lambda: self._submit_workspace(
                    client,
                    workspace2_id,
                    preview2,
                    packages["modified"],
                    idempotency_suffix="submit2",
                ),
            )
            submission2 = _require_mapping(submit2, "submission")
            self._stage(
                stages,
                "approve2",
                lambda: self._approve_submission(client, str(submission2["id"])),
            )
            batch2_id = str(_require_mapping(client.get("/api/workspace-tree").json(), "current_batch")["batch_id"])
            archive_snapshot2 = self._stage(
                stages,
                "archive2_snapshot_abnormal_initial_check",
                lambda: _checked_json(client.get(f"/api/baseline-batches/{quote(batch2_id, safe='')}/archive-snapshot")),
            )
            graph = _require_mapping(archive_snapshot2, "batch_graph")
            blocking_reasons = list(graph.get("blocking_reason_codes") or graph.get("blocking_reasons") or [])
            summary = {
                "schema_version": "formal-archive-journey-benchmark-summary/v1",
                "run_id": run_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "dataset_root": str(self.dataset_root),
                "datasets": {
                    "first_upload_baseline": baseline_dataset,
                    "second_upload_abnormal_initial": abnormal_initial_dataset,
                    "second_upload_modified": modified_dataset,
                },
                "packages": {
                    key: {
                        "path": str(value),
                        "size_bytes": value.stat().st_size,
                    }
                    for key, value in packages.items()
                },
                "stages": [stage.__dict__ for stage in stages],
                "archive_ready_boundary": {
                    "archive1_status": _archive_execution_status(archive1),
                    "current_batch_after_archive_batch_no": _require_mapping(tree_after_archive, "current_batch").get("batch_no"),
                },
                "second_archive_graph": {
                    "overall_status": graph.get("overall_status"),
                    "blocking_reasons": blocking_reasons,
                    "expected_abnormal_initial_detected": "UNRESOLVED_INITIAL_STATE" in blocking_reasons
                    or "TIME_ABNORMAL_INITIAL" in blocking_reasons,
                },
                "baseline_initial_diagnostics": diagnostics_result,
                "comparison_core_summary": _comparison_core_summary(self.events_path),
                "events_path": str(self.events_path),
            }
            self.summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            return summary
        finally:
            logger.removeHandler(event_handler)
            event_handler.close()
            if previous_benchmark_env is None:
                os.environ.pop("BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK", None)
            else:
                os.environ["BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK"] = previous_benchmark_env

    def _stage(
        self,
        stages: list[_StageResult],
        name: str,
        fn,
        *,
        accept_failure: bool = False,
    ) -> dict[str, object]:
        started_at = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            duration_ms = _elapsed_ms(started_at)
            stage = _StageResult(
                name=name,
                status="FAILED" if not accept_failure else "FAILED_ACCEPTED",
                duration_ms=duration_ms,
                details={
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                },
            )
            stages.append(stage)
            if accept_failure:
                return {"status": stage.status, **stage.details}
            raise
        duration_ms = _elapsed_ms(started_at)
        details = dict(result)
        stage_status = str(details.get("status") or details.get("operation_status") or "OK")
        stages.append(
            _StageResult(
                name=name,
                status=stage_status,
                duration_ms=duration_ms,
                details=_compact_stage_details(details),
            )
        )
        return details

    def _create_workspace(self, client: TestClient) -> str:
        payload = _checked_json(client.post("/api/workspaces/current"))
        return str(_require_mapping(payload, "workspace")["id"])

    def _upload_initialize_baseline(
        self,
        client: TestClient,
        workspace_id: str,
        package_path: Path,
        *,
        benchmark_label: str,
    ) -> dict[str, object]:
        with package_path.open("rb") as handle:
            response = client.post(
                f"/api/workspaces/{quote(workspace_id, safe='')}/uploads",
                data={
                    "upload_mode": "INITIALIZE_BASELINE",
                    "package_format": "directory-tar-gzip",
                    "modified_filename": f"{benchmark_label}.tar.gz",
                },
                files={"modified_file": (package_path.name, handle, "application/gzip")},
            )
        payload = _checked_json(response)
        return _require_ready_result(payload)

    def _upload_full(
        self,
        client: TestClient,
        workspace_id: str,
        initial_package_path: Path,
        modified_package_path: Path,
        *,
        initial_label: str,
        modified_label: str,
    ) -> dict[str, object]:
        with initial_package_path.open("rb") as initial_handle, modified_package_path.open("rb") as modified_handle:
            response = client.post(
                f"/api/workspaces/{quote(workspace_id, safe='')}/uploads",
                data={
                    "upload_mode": "FULL",
                    "package_format": "directory-tar-gzip",
                    "initial_filename": f"{initial_label}.tar.gz",
                    "modified_filename": f"{modified_label}.tar.gz",
                },
                files={
                    "initial_file": (initial_package_path.name, initial_handle, "application/gzip"),
                    "modified_file": (modified_package_path.name, modified_handle, "application/gzip"),
                },
            )
        payload = _checked_json(response)
        return _require_ready_result(payload)

    def _submit_workspace(
        self,
        client: TestClient,
        workspace_id: str,
        preview: dict[str, object],
        package_path: Path,
        *,
        idempotency_suffix: str,
    ) -> dict[str, object]:
        with package_path.open("rb") as handle:
            response = client.post(
                "/api/submissions",
                data={
                    "workspace_id": workspace_id,
                    "preview_token": str(preview["preview_token"]),
                    "preview_revision_id": str(preview["preview_revision_id"]),
                    "preview_strategy_manifest_digest": str(preview["preview_strategy_manifest_digest"]),
                },
                files={"source_file": (package_path.name, handle, "application/gzip")},
            )
        operation = _checked_json(response)
        terminal = self._wait_operation_terminal(client, str(operation["operation_id"]))
        if terminal["status"] != "READY":
            raise RuntimeError(f"submit operation did not become READY: {terminal}")
        return _require_mapping(terminal, "ready_result")

    def _approve_submission(self, client: TestClient, submission_id: str) -> dict[str, object]:
        start = client.post(
            f"/api/submissions/{quote(submission_id, safe='')}/review-actions",
            json={"action": "START_REVIEW", "reason": "benchmark review"},
        )
        _checked_json(start)
        approve = client.post(
            f"/api/submissions/{quote(submission_id, safe='')}/review-actions",
            json={"action": "APPROVE", "reason": "benchmark approve"},
        )
        payload = _checked_json(approve)
        return _require_mapping(payload, "ready_result")

    def _archive_approved_submission(
        self,
        client: TestClient,
        *,
        batch_id: str,
        workspace_id: str,
        submission_id: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        encoded_batch = quote(batch_id, safe="")
        _checked_json(
            client.put(
                f"/api/baseline-batches/{encoded_batch}/archive-candidates/{candidate_id}",
                json={
                    "workspace_id": workspace_id,
                    "source_kind": "APPROVED_SUBMISSION",
                    "role": "MAINLINE_MODIFIED",
                    "source_submission_id": submission_id,
                },
            )
        )
        snapshot = _checked_json(client.get(f"/api/baseline-batches/{encoded_batch}/archive-snapshot"))
        _checked_json(
            client.put(
                f"/api/baseline-batches/{encoded_batch}/workspaces/{quote(workspace_id, safe='')}/archive-confirmation",
                json={
                    "confirmation_status": "CONFIRMED_WITH_CANDIDATE",
                    "archive_candidate_id": candidate_id,
                },
            )
        )
        _checked_json(
            client.put(
                f"/api/baseline-batches/{encoded_batch}/archive-selection",
                json={
                    "selected_modified_candidate_id": candidate_id,
                    "selected_initial_candidate_ids": [],
                    "candidate_set_hash": snapshot["candidate_set_hash"],
                },
            )
        )
        selected_snapshot = _checked_json(client.get(f"/api/baseline-batches/{encoded_batch}/archive-snapshot"))
        operation = _checked_json(
            client.post(
                f"/api/baseline-batches/{encoded_batch}/archive-mainline/execute",
                json={
                    "idempotency_key": idempotency_key,
                    "expected_base_main_hash": selected_snapshot["baseline_batch"]["base_main_hash"],
                    "selected_modified_candidate_id": candidate_id,
                    "selected_initial_candidate_ids": [],
                    "workspace_confirmation_set_hash": selected_snapshot["workspace_confirmation_set_hash"],
                    "candidate_set_hash": selected_snapshot["candidate_set_hash"],
                },
            )
        )
        terminal = self._wait_operation_terminal(client, str(operation["operation_id"]))
        if terminal["status"] != "READY":
            raise RuntimeError(f"archive operation did not become READY: {terminal}")
        return _require_mapping(terminal, "ready_result")

    def _generate_baseline_initial_diagnostics(
        self,
        client: TestClient,
        upload_ready_result: dict[str, object],
    ) -> dict[str, object]:
        preview_bundle_id = str(upload_ready_result["latest_preview_bundle_id"])
        response = client.post(
            f"/api/preview-bundles/{quote(preview_bundle_id, safe='')}/baseline-initial-diagnostics",
            json={"force_refresh": True, "allow_full_readback": True},
        )
        if response.status_code == 404:
            return {
                "status": "SKIPPED_ROUTE_UNAVAILABLE",
                "preview_bundle_id": preview_bundle_id,
            }
        payload = _checked_json(response)
        return {
            "status": payload.get("baseline_initial_diagnostics_status", "UNKNOWN"),
            "preview_bundle_id": preview_bundle_id,
            "summary": payload.get("baseline_initial_diagnostics_summary"),
        }

    def _wait_operation_terminal(self, client: TestClient, operation_id: str) -> dict[str, object]:
        deadline = time.monotonic() + self.operation_timeout_seconds
        last_payload: dict[str, object] | None = None
        while time.monotonic() < deadline:
            payload = _checked_json(client.get(f"/api/operations/{quote(operation_id, safe='')}"))
            last_payload = payload
            if payload["status"] in _TERMINAL_OPERATION_STATUSES:
                return payload
            time.sleep(1.0)
        raise TimeoutError(f"operation {operation_id} did not finish before timeout: {last_payload}")


def _control_plane_response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/workspace-entry-context"):
        return httpx.Response(
            200,
            json={
                "actor_id": "archive-operator",
                "gateway_device_external_key": "E2E_FORMAL_ARCHIVE_GATEWAY_001",
                "business_project_id": "E2E_FORMAL_ARCHIVE_PROJECT_001",
                "permissions": [
                    "view_gateway_workspace",
                    "upload_submit_workspace",
                    "review_submission",
                    "archive_mainline",
                ],
                "entry_mode": "upload",
                "display_context": {"schema_version": "display-context/v1", "sections": []},
            },
        )
    return httpx.Response(404, json={"error": "unexpected control-plane request"})


def _upsert_gateway(client: TestClient) -> None:
    response = client.put(
        "/api/internal/gateway-devices/E2E_FORMAL_ARCHIVE_GATEWAY_001",
        headers=_AUTH_HEADER,
        json={
            "display_name": "E2E Formal Archive Gateway",
            "status": "ACTIVE",
            "business_project_id": "E2E_FORMAL_ARCHIVE_PROJECT_001",
            "repo_key": "E2E_FORMAL_ARCHIVE_GATEWAY_001",
            "artifact_root_key": "E2E_FORMAL_ARCHIVE_GATEWAY_001",
            "requested_by_actor_id": "benchmark",
            "reason": "formal archive journey benchmark",
        },
    )
    _checked_json(response)


def _consume_session(client: TestClient) -> None:
    ticket = sign_sso_ticket(
        SsoTicketPayload(
            owner_actor_id="archive-operator",
            gateway_device_external_key="E2E_FORMAL_ARCHIVE_GATEWAY_001",
            expires_at=int(time.time()) + 3600,
        ),
        secret="control-plane-sso-ticket-secret",
    )
    _checked_json(client.get(f"/api/sso/consume?sso_ticket={quote(ticket, safe='')}"))


def _build_directory_package(source_dir: Path, output_path: Path) -> Path:
    if output_path.exists():
        return output_path
    if not source_dir.is_dir():
        raise FileNotFoundError(str(source_dir))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as archive:
        for path in sorted(source_dir.rglob("*")):
            archive.add(path, arcname=path.relative_to(source_dir).as_posix(), recursive=False)
    return output_path


def _checked_json(response) -> dict[str, object]:  # type: ignore[no-untyped-def]
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("response payload must be an object")
    return payload


def _require_ready_result(operation_payload: dict[str, object]) -> dict[str, object]:
    if operation_payload.get("status") != "READY":
        raise RuntimeError(f"operation was not READY: {operation_payload}")
    return _require_mapping(operation_payload, "ready_result")


def _require_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _compact_stage_details(details: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {}
    for key in (
        "workspace_id",
        "latest_preview_bundle_id",
        "upload_mode",
        "upload_semantics",
        "status",
        "baseline_alignment",
        "operation_id",
    ):
        if key in details:
            compact[key] = details[key]
    submission = details.get("submission")
    if isinstance(submission, dict):
        compact["submission_id"] = submission.get("id")
        compact["submission_status"] = submission.get("status")
        compact["configuration_generated_at"] = submission.get("configuration_generated_at")
        compact["initial_configuration_generated_at"] = submission.get("initial_configuration_generated_at")
    execution = details.get("execution_record")
    if isinstance(execution, dict):
        compact["execution_id"] = execution.get("execution_id") or execution.get("id")
        compact["execution_status"] = execution.get("status")
    if "overall_status" in details:
        compact["overall_status"] = details["overall_status"]
    return compact or details


def _archive_execution_status(payload: dict[str, object]) -> object:
    execution = payload.get("execution_record")
    if isinstance(execution, dict):
        return execution.get("status")
    return payload.get("status")


def _comparison_core_summary(events_path: Path) -> dict[str, object]:
    events = _read_benchmark_events(events_path)
    table_events = [event for event in events if event.get("event") == "comparison_core.table"]
    ordered_events = [
        event for event in events if event.get("event") == "comparison_core.ordered_provider"
    ]
    projection_events = [
        event for event in events if event.get("event") == "comparison_core.projection_build"
    ]
    records_events = [
        event
        for event in events
        if event.get("event") in {"comparison_core.records_build", "comparison_core.records_write"}
    ]
    phase_events = [
        event
        for event in events
        if event.get("event") == "comparison_core.ordered_provider.phase"
    ]
    return {
        "comparison_core_total_ms": _sum_duration(
            event for event in events if event.get("event") == "comparison_core.total"
        ),
        "ordered_provider_total_ms": _sum_duration(ordered_events),
        "projection_total_ms": _sum_duration(projection_events),
        "records_total_ms": _sum_duration(records_events),
        "top_slow_tables": _top_events(
            table_events,
            limit=20,
            keys=(
                "table_name",
                "provider",
                "status",
                "duration_ms",
                "row_count_before",
                "row_count_current",
                "records_count",
                "degrade_reason",
            ),
        ),
        "top_ordered_degraded_tables": _top_events(
            [
                event
                for event in ordered_events
                if event.get("status") == "DEGRADED" or event.get("degrade_reason") is not None
            ],
            limit=20,
            keys=(
                "table_name",
                "status",
                "duration_ms",
                "row_count_before",
                "row_count_current",
                "prepared_row_count_before",
                "prepared_row_count_current",
                "planner_mode",
                "degrade_reason",
                "records_count",
            ),
        ),
        "top_ordered_phases": _top_events(
            phase_events,
            limit=40,
            keys=(
                "table_name",
                "phase",
                "duration_ms",
                "row_count_before",
                "row_count_current",
                "prepared_row_count_before",
                "prepared_row_count_current",
                "planner_mode",
                "degrade_reason",
                "shared_real_count",
                "position_changed_count",
                "semantic_op_count",
                "records_count",
            ),
        ),
    }


def _read_benchmark_events(events_path: Path) -> list[dict[str, object]]:
    if not events_path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _sum_duration(events) -> int:  # type: ignore[no-untyped-def]
    return sum(int(event.get("duration_ms") or 0) for event in events)


def _top_events(
    events: list[dict[str, object]],
    *,
    limit: int,
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    ordered = sorted(
        events,
        key=lambda event: (
            -(int(event.get("duration_ms") or 0)),
            str(event.get("table_name") or ""),
            str(event.get("phase") or ""),
        ),
    )
    return [
        {key: event[key] for key in keys if key in event and event[key] is not None}
        for event in ordered[:limit]
    ]


def _elapsed_ms(started_at: float) -> int:
    return int(round((time.perf_counter() - started_at) * 1000))


class _JsonlBenchmarkEventHandler(logging.Handler):
    def __init__(self, path: Path) -> None:
        super().__init__(level=logging.INFO)
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        marker = "formal_upload_benchmark "
        message = record.getMessage()
        if marker not in message:
            return
        payload = message.split(marker, maxsplit=1)[1]
        self._handle.write(payload + "\n")
        self._handle.flush()

    def close(self) -> None:
        try:
            self._handle.close()
        finally:
            super().close()
