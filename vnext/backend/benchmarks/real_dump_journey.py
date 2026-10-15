"""Run the S2b real dump Preview/Submit/History journey from the host.

The source packages are read-only inputs. Journey checks use public HTTP APIs;
the public History result exposes a pair total and digests, while its bundle
contains artifact references without a public artifact-content endpoint. No row
values or row identifiers are emitted.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_repository_contracts import encode_commit_id_path_segment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BASELINE_NODE_ID,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    acquire_compose_gate_lock,
    build_compose_stack_images,
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_image_ids,
    release_compose_gate_lock,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
    wait_repository_service_ready,
    worker_ready,
)

REPOSITORY_SERVICE_IMAGE = os.environ.get(
    "GATEWAY_REPOSITORY_SERVICE_IMAGE", "gateway-repository-service:local"
)
ARCHIVER_TOKEN = "s2b-realdata-archiver-token"
HISTORY_READER_TOKEN = "s2b-realdata-history-reader-token"
PSEUDO_GID_MIN = 4_000_000_000
EXPECTED_PSEUDO_TOTALS = {
    "rd-t1-a-v1": 4,
    "rd-t1-a-v2": 4,
    "rd-t2-b-v1": 3_056,
    "rd-t2-b-v2": 2_674,
    "rd-t3-c-v1": 9_858,
    "rd-t3-c-v2": 9_858,
    "rd-t4-d-v1": 12_676,
    "rd-t4-d-v2": 12_688,
}
EXPECTED_PAIRINGS = {
    "rd-t1-a": ("rd-t1-a-v1", "rd-t1-a-v2"),
    "rd-t2-b": ("rd-t2-b-v1", "rd-t2-b-v2"),
    "rd-t3-c": ("rd-t3-c-v1", "rd-t3-c-v2"),
    "rd-t4-d": ("rd-t4-d-v1", "rd-t4-d-v2"),
}
TERMINAL_OPERATION_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}
INITIAL_OPERATION_TIMEOUT_SECONDS = 3_600
MINIMUM_OPERATION_TIMEOUT_SECONDS = 300

# Operation budgets are calibrated from timestamped runs at the same tier.
# Until that exact tier/step has completed once, use the DC30 one-hour ceiling.
MEASURED_OPERATION_WALL_SECONDS: dict[str, float] = {
    "t1:v1-preview": 52.975,
    "t1:v1-submit": 41.652,
    "t1:repeat-v1-preview": 73.116,
    "t1:v2-preview": 77.105,
    "t1:v2-submit": 41.547,
    "t1:history": 73.002,
    "t2:v1-preview": 721.355,
}
OPERATION_TIERS = ("t1", "t2", "t3", "t4")

JOURNEY_STEP_IDS = (
    "v1-workspace",
    "v1-upload",
    "v1-preview",
    "v1-submit",
    "v1-repository-read",
    "v1-approve",
    "v1-archive",
    "repeat-v1-workspace",
    "repeat-v1-upload",
    "repeat-v1-preview",
    "repeat-v1-submit",
    "v2-workspace",
    "v2-upload",
    "v2-preview",
    "v2-submit",
    "v2-repository-read",
    "v2-approve",
    "history",
)


class JourneyFailure(RuntimeError):
    """A bounded failure without response bodies that could contain row data."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _real_dump_root() -> Path:
    raw = os.environ.get("GATEWAY_REAL_DUMP_ROOT", "").strip()
    if not raw:
        raise JourneyFailure("GATEWAY_REAL_DUMP_ROOT is required")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise JourneyFailure("GATEWAY_REAL_DUMP_ROOT is not a directory")
    return root


def _read_metadata(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        datasets_document = json.loads((root / "datasets.json").read_text(encoding="utf-8"))
        census_document = json.loads(
            (_repo_root() / "docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise JourneyFailure("real dump metadata could not be read") from exc
    datasets = {
        str(item["dataset_id"]): cast(dict[str, Any], item)
        for item in datasets_document.get("datasets", [])
        if isinstance(item, dict) and type(item.get("dataset_id")) is str
    }
    census = {
        str(item["dataset_id"]): cast(dict[str, Any], item)
        for item in census_document.get("datasets", [])
        if isinstance(item, dict) and type(item.get("dataset_id")) is str
    }
    if set(datasets) != set(EXPECTED_PSEUDO_TOTALS) or set(census) != set(datasets):
        raise JourneyFailure("dataset census does not contain the eight expected datasets")
    for tier_id, (v1_id, v2_id) in EXPECTED_PAIRINGS.items():
        del tier_id
        if datasets[v1_id].get("pair_of") is not None:
            raise JourneyFailure("v1 dataset unexpectedly declares a pair")
        if datasets[v2_id].get("pair_of") != v1_id:
            raise JourneyFailure("dataset pairing differs from the accepted same-tier pairing")
    return datasets, census


def _dataset_package(root: Path, dataset: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    dataset_id = str(dataset["dataset_id"])
    files = dataset.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise JourneyFailure(f"{dataset_id}: package manifest shape is invalid")
    file_info = cast(dict[str, Any], files[0])
    if Path(str(file_info["path"])).name != "package.tar.gz":
        raise JourneyFailure(f"{dataset_id}: dataset manifest package filename is unexpected")
    package_path = root / "packages" / f"{dataset_id}.tar.gz"
    payload = package_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != int(file_info["bytes"]) or digest != file_info["sha256"]:
        raise JourneyFailure(f"{dataset_id}: package size or SHA-256 differs from datasets.json")
    if dataset.get("has_logics_xml") is not True:
        raise JourneyFailure(f"{dataset_id}: logics.xml is required by DC22")
    return payload, file_info


def _ordered_tables(census: Mapping[str, Any]) -> dict[str, int]:
    projection = census.get("ordered_projection")
    if not isinstance(projection, dict) or projection.get("status") != "COMPLETE":
        raise JourneyFailure("ordered census must be COMPLETE before the journey")
    raw_tables = projection.get("tables")
    if not isinstance(raw_tables, dict):
        raise JourneyFailure("ordered census table map is invalid")
    result: dict[str, int] = {}
    for table_name, raw in raw_tables.items():
        if not isinstance(raw, dict) or raw.get("status") != "COMPLETE":
            raise JourneyFailure("ordered census contains a non-COMPLETE table")
        result[str(table_name)] = int(raw["pseudo_gid_count"])
    if sum(result.values()) != int(projection["pseudo_rows_total"]):
        raise JourneyFailure("ordered census pseudo count does not reconcile")
    return result


def _write_compose_secrets(root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    bearer = root / "repository-bearer-token"
    bearer.write_text(f"{BEARER_TOKEN}\n", encoding="utf-8")
    session_file = root / "session.json"
    session_file.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": SESSION_TOKEN,
                        "actor_id": "s2b-realdata-submitter",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                            "review_submission",
                        ],
                    },
                    {
                        "token": ARCHIVER_TOKEN,
                        "actor_id": "s2b-realdata-archiver",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": HISTORY_READER_TOKEN,
                        "actor_id": "s2b-realdata-history-reader",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": ["workspace_read", "read_project_history"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    internal_bearer = root / "internal-bearer-token"
    internal_bearer.write_text("s2b-realdata-internal-bearer\n", encoding="utf-8")
    mapping = root / "provisioned-mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "repository_id": "pending-repository-seed",
                        "business_baseline_node_id": BASELINE_NODE_ID,
                        "business_baseline_commit_id": "pending-commit-seed",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
        "GATEWAY_BACKEND_SESSION_FILE": str(session_file),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
        "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(bearer),
    }


def _compose_environment(
    secret_root: Path,
    project_name: str,
    *,
    write_secrets: bool = True,
) -> dict[str, str]:
    environment = os.environ.copy()
    if write_secrets:
        environment.update(_write_compose_secrets(secret_root))
    else:
        environment.update(
            {
                "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(secret_root / "repository-bearer-token"),
                "GATEWAY_BACKEND_SESSION_FILE": str(secret_root / "session.json"),
                "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(secret_root / "provisioned-mapping.json"),
                "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(secret_root / "internal-bearer-token"),
                "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(secret_root / "repository-bearer-token"),
            }
        )
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": project_name,
            "GATEWAY_COMPOSE_GATE_PREBUILT": "1",
        }
    )
    return environment


def _require(response: httpx.Response, expected: int, label: str) -> dict[str, Any]:
    if response.status_code != expected:
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("code") if isinstance(body, dict) else None
        suffix = f" code={error}" if type(error) is str else ""
        raise JourneyFailure(f"{label}: HTTP {response.status_code}, expected {expected}{suffix}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise JourneyFailure(f"{label}: response was not JSON") from exc
    if not isinstance(payload, dict):
        raise JourneyFailure(f"{label}: response was not an object")
    return cast(dict[str, Any], payload)


def _require_one_of(
    response: httpx.Response,
    expected: set[int],
    label: str,
) -> dict[str, Any]:
    if response.status_code not in expected:
        _require(response, min(expected), label)
    return _require(response, response.status_code, label)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _emit_progress(stage: str, event: str, **details: Any) -> None:
    print(
        json.dumps(
            {"event": event, "stage": stage, "timestamp_utc": _utc_timestamp(), **details},
            sort_keys=True,
        ),
        flush=True,
    )


def _parse_cpu_stat(payload: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in payload.splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[a-z][a-z0-9_.]*", parts[0]):
            raise JourneyFailure("container cpu.stat has an invalid row")
        try:
            value = int(parts[1])
        except ValueError as exc:
            raise JourneyFailure("container cpu.stat has a non-integer value") from exc
        if value < 0 or parts[0] in values:
            raise JourneyFailure("container cpu.stat contains an invalid counter")
        values[parts[0]] = value
    if "usage_usec" not in values:
        raise JourneyFailure("container cpu.stat has no usage_usec counter")
    return values


def _container_cpu_stats(env: Mapping[str, str]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for service in ("backend", "worker", "repository-service"):
        listed = run_compose(dict(env), "ps", "-q", service)
        container_ids = listed.stdout.strip().splitlines()
        if listed.returncode != 0 or len(container_ids) != 1:
            raise JourneyFailure(f"could not resolve the {service} container for cpu.stat")
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", container_ids[0]],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        if inspected.returncode != 0:
            raise JourneyFailure(f"could not inspect the {service} container for cpu.stat")
        pid = inspected.stdout.strip()
        if not pid.isdigit() or pid == "0":
            raise JourneyFailure(f"the {service} container has no running host pid")
        try:
            cgroup_lines = (Path("/proc") / pid / "cgroup").read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise JourneyFailure(f"could not read the {service} host cgroup") from exc
        unified_path = next(
            (line.partition("::")[2] for line in cgroup_lines if line.startswith("0::")),
            None,
        )
        if not unified_path:
            raise JourneyFailure(f"the {service} container is not in a unified cgroup")
        cgroup_root = Path("/sys/fs/cgroup").resolve()
        cpu_stat_path = (cgroup_root / unified_path.lstrip("/") / "cpu.stat").resolve()
        if not cpu_stat_path.is_relative_to(cgroup_root):
            raise JourneyFailure(f"the {service} cgroup path escaped the host cgroup root")
        try:
            stats[service] = _parse_cpu_stat(cpu_stat_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise JourneyFailure(f"could not read the {service} host cpu.stat") from exc
    return stats


def _step_measurement(
    *,
    started_monotonic: float,
    started_utc: str,
    cpu_start: Mapping[str, Mapping[str, int]],
    cpu_end: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    cpu_seconds: dict[str, float] = {}
    cpu_delta_usec: dict[str, int] = {}
    for service in ("backend", "worker", "repository-service"):
        delta = int(cpu_end[service]["usage_usec"]) - int(cpu_start[service]["usage_usec"])
        if delta < 0:
            raise JourneyFailure(f"the {service} cpu.stat counter moved backwards")
        cpu_delta_usec[service] = delta
        cpu_seconds[service] = round(delta / 1_000_000, 3)
    return {
        "started_at_utc": started_utc,
        "ended_at_utc": _utc_timestamp(),
        "wall_seconds": round(time.monotonic() - started_monotonic, 3),
        "cpu_seconds": cpu_seconds,
        "cpu_delta_usec": cpu_delta_usec,
        "cpu_stat_start": cpu_start,
        "cpu_stat_end": cpu_end,
    }


def _operation_timeout_seconds(tier: str, step_id: str) -> int:
    if tier not in OPERATION_TIERS:
        raise JourneyFailure("operation timeout profile has an unknown tier")
    measured_wall_seconds = MEASURED_OPERATION_WALL_SECONDS.get(f"{tier}:{step_id}")
    timeout = (
        INITIAL_OPERATION_TIMEOUT_SECONDS
        if measured_wall_seconds is None
        else max(
            MINIMUM_OPERATION_TIMEOUT_SECONDS,
            math.ceil(measured_wall_seconds * 5),
        )
    )
    if timeout < MINIMUM_OPERATION_TIMEOUT_SECONDS:
        raise JourneyFailure("operation timeout profile is below the five minute minimum")
    return timeout


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


class JourneyStepRunner:
    def __init__(
        self,
        *,
        tier: str,
        env: Mapping[str, str],
        state: dict[str, Any],
        from_step: str | None,
        state_path: Path | None,
    ) -> None:
        self.tier = tier
        self.env = env
        self.state = state
        self.state_path = state_path
        self.from_index = 0 if from_step is None else JOURNEY_STEP_IDS.index(from_step)
        self.metrics: list[dict[str, Any]] = []

    def run(self, step_id: str, action: Callable[[], Any]) -> Any:
        index = JOURNEY_STEP_IDS.index(step_id)
        stage = f"{self.tier} {step_id}"
        if index < self.from_index:
            if step_id not in self.state:
                raise JourneyFailure(f"debug state is missing the completed step {step_id}")
            _emit_progress(stage, "step_reused")
            return self.state[step_id]

        started_utc = _utc_timestamp()
        started_monotonic = time.monotonic()
        cpu_start = _container_cpu_stats(self.env)
        _emit_progress(stage, "step_started", cpu_stat=cpu_start)
        try:
            value = action()
            cpu_end = _container_cpu_stats(self.env)
            measurement = _step_measurement(
                started_monotonic=started_monotonic,
                started_utc=started_utc,
                cpu_start=cpu_start,
                cpu_end=cpu_end,
            )
        except BaseException:
            try:
                cpu_end = _container_cpu_stats(self.env)
                measurement = _step_measurement(
                    started_monotonic=started_monotonic,
                    started_utc=started_utc,
                    cpu_start=cpu_start,
                    cpu_end=cpu_end,
                )
            except Exception as metric_error:
                measurement = {
                    "started_at_utc": started_utc,
                    "ended_at_utc": _utc_timestamp(),
                    "wall_seconds": round(time.monotonic() - started_monotonic, 3),
                    "cpu_stat_error": type(metric_error).__name__,
                }
            self.metrics.append({"step_id": step_id, **measurement})
            _emit_progress(stage, "step_failed", metrics=measurement)
            raise

        stored_value = _json_copy(value)
        self.state[step_id] = stored_value
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(self.state, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self.state_path)
        self.metrics.append({"step_id": step_id, **measurement})
        _emit_progress(stage, "step_succeeded", metrics=measurement)
        return value


def _poll_operation(
    client: httpx.Client,
    operation_id: str,
    *,
    stage: str,
    timeout_seconds: int = INITIAL_OPERATION_TIMEOUT_SECONDS,
    deadline: float | None = None,
) -> dict[str, Any]:
    _emit_progress(stage, "operation_started", timeout_seconds=timeout_seconds)
    operation_deadline = time.monotonic() + timeout_seconds if deadline is None else deadline
    while time.monotonic() < operation_deadline:
        payload = _require(client.get(f"/v1/operations/{operation_id}"), 200, "operation status")
        status = payload.get("status")
        if status in TERMINAL_OPERATION_STATES:
            if status != "SUCCEEDED":
                diagnostic = payload.get("diagnostic")
                code = diagnostic.get("code") if isinstance(diagnostic, dict) else "unknown"
                raise JourneyFailure(f"{stage} operation ended {status}, diagnostic={code}")
            _emit_progress(stage, "operation_succeeded")
            return payload
        time.sleep(2.0)
    raise JourneyFailure(f"{stage} operation did not reach a terminal state before timeout")


def _workspace(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/v1/workspaces",
        json={
            "gateway_device_external_key": DEVICE_KEY,
            "business_project_id": PROJECT_ID,
        },
    )
    if response.status_code not in {200, 201}:
        _require(response, 201, "workspace")
    return _require(response, response.status_code, "workspace")


def _upload_revision(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    package: bytes,
    idempotency_key: str,
) -> dict[str, Any]:
    expected_version = int(workspace["optimistic_version"])
    digest = hashlib.sha256(package).hexdigest()
    manifest = {
        "expected_workspace_version": expected_version,
        "input_completeness": "MODIFIED_ONLY",
        "artifacts": {
            "MODIFIED": {
                "part_name": "modified",
                "media_type": "application/gzip",
                "size_bytes": len(package),
                "raw_sha256": f"sha256:{digest}",
            }
        },
    }
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode("utf-8"), "application/json"),
            "modified": ("package.tar.gz", package, "application/gzip"),
        },
    )
    return _require_one_of(response, {200, 201}, "upload revision")


def _preview(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    upload: Mapping[str, Any],
    baseline_node_id: str,
    baseline_head_version: int,
    idempotency_key: str,
    stage: str,
    operation_timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        json={
            "expected_workspace_version": upload["optimistic_version"],
            "upload_revision_id": upload["upload_revision_id"],
            "generation": upload["generation"],
            "expected_baseline_node_id": baseline_node_id,
            "expected_baseline_head_version": baseline_head_version,
            "options": {},
        },
    )
    accepted = _require_one_of(response, {200, 202}, "preview acceptance")
    deadline = time.monotonic() + operation_timeout_seconds
    _poll_operation(
        client,
        str(accepted["operation_id"]),
        stage=stage,
        timeout_seconds=operation_timeout_seconds,
        deadline=deadline,
    )
    refreshed = _workspace(client)
    result_id = refreshed.get("current_preview_result_id")
    if type(result_id) is not str or not result_id:
        raise JourneyFailure("preview did not publish a current result")
    result = _require(
        client.get(f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}"),
        200,
        "preview result",
    )
    manifest_response = client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}/bundle"
    )
    if manifest_response.status_code != 200:
        raise JourneyFailure(f"preview bundle: HTTP {manifest_response.status_code}")
    try:
        manifest = cast(dict[str, Any], json.loads(manifest_response.content))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JourneyFailure("preview bundle was not a JSON manifest") from exc
    summaries = manifest.get("pairs")
    if not isinstance(summaries, list) or not summaries:
        raise JourneyFailure("preview bundle did not include a pair summary")
    return {"workspace": refreshed, "result": result}, manifest


def _assert_preview_summaries(
    manifest: Mapping[str, Any],
    *,
    unchanged: bool,
) -> dict[str, int]:
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 1:
        raise JourneyFailure("preview manifest must have exactly one pair")
    totals: Counter[str] = Counter()
    for pair in pairs:
        if not isinstance(pair, dict) or not isinstance(pair.get("summary"), dict):
            raise JourneyFailure("preview pair summary is invalid")
        summary = cast(dict[str, Any], pair["summary"])
        table_count = int(summary.get("table_count", -1))
        changed = int(summary.get("changed_table_count", -1))
        degraded = int(summary.get("degraded_table_count", -1))
        failed = int(summary.get("failed_table_count", -1))
        if min(table_count, changed, degraded, failed) < 0 or table_count == 0:
            raise JourneyFailure("preview table summary is incomplete")
        if degraded or failed or (unchanged and changed):
            raise JourneyFailure("preview table summary violated no-degradation/no-change expectations")
        totals.update(
            {
                "pair_count": 1,
                "table_count": table_count,
                "changed_table_count": changed,
                "degraded_table_count": degraded,
                "failed_table_count": failed,
            }
        )
    return dict(totals)


def _submit(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    upload: Mapping[str, Any],
    preview: Mapping[str, Any],
    baseline_node_id: str,
    baseline_head_version: int,
    idempotency_key: str,
    stage: str,
    operation_timeout_seconds: int,
    expect_no_change: bool = False,
) -> dict[str, Any]:
    workspace_state = cast(Mapping[str, Any], preview["workspace"])
    result = cast(Mapping[str, Any], preview["result"])
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        json={
            "expected_workspace_version": workspace_state["optimistic_version"],
            "upload_revision_id": upload["upload_revision_id"],
            "preview_result_id": result["preview_result_id"],
            "generation": workspace_state["generation"],
            "expected_baseline_node_id": baseline_node_id,
            "expected_baseline_head_version": baseline_head_version,
            "options": {},
        },
    )
    if expect_no_change:
        payload = _require(response, 409, "no-change submit")
        if payload.get("code") != "NO_CANONICAL_CHANGE":
            raise JourneyFailure("repeat submit did not return NO_CANONICAL_CHANGE")
        return {"result": "NO_CANONICAL_CHANGE"}
    accepted = _require_one_of(response, {200, 202}, "submit acceptance")
    deadline = time.monotonic() + operation_timeout_seconds
    _poll_operation(
        client,
        str(accepted["operation_id"]),
        stage=stage,
        timeout_seconds=operation_timeout_seconds,
        deadline=deadline,
    )
    _emit_progress(stage, "submit_finalization_started")
    attempt: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        attempt_response = client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}"
        )
        attempt_payload = _require(attempt_response, 200, "submit attempt")
        if attempt_payload.get("state") in {"FINALIZED", "ABORTED"}:
            attempt = attempt_payload
            break
        time.sleep(2.0)
    if attempt is None or attempt.get("state") != "FINALIZED":
        raise JourneyFailure(f"{stage} attempt did not finalize")
    submission = _require(
        client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submissions/{attempt['submission_id']}"
        ),
        200,
        "submission read",
    )
    if type(submission.get("repository_commit_id")) is not str:
        raise JourneyFailure("submission did not expose its Repository commit id")
    _emit_progress(stage, "submit_finalized")
    return submission


def _approve(client: httpx.Client, submission_id: str, idempotency_key: str) -> None:
    _require_one_of(
        client.post(
            f"/v1/submissions/{submission_id}/review-events",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key=idempotency_key),
            json={"expected_review_version": 0, "action": "APPROVE"},
        ),
        {200, 201},
        "submission approval",
    )


def _archive(client: httpx.Client, submission_id: str, key_prefix: str) -> dict[str, Any]:
    candidates = _require(
        client.get("/v1/archive-candidates", headers=compose_auth_headers(token=ARCHIVER_TOKEN)),
        200,
        "archive candidates",
    )
    raw_candidates = candidates.get("candidates")
    if not isinstance(raw_candidates, list):
        raise JourneyFailure("archive candidates response is invalid")
    selected = next(
        (
            cast(dict[str, Any], item)
            for item in raw_candidates
            if isinstance(item, dict) and item.get("submission_id") == submission_id
        ),
        None,
    )
    if selected is None:
        raise JourneyFailure("submitted v1 was not an archive candidate")
    preview = _require(
        client.post(
            "/v1/archive-plan-preview",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            json={"selected": selected},
        ),
        200,
        "archive plan preview",
    )
    if preview.get("can_start") is not False:
        raise JourneyFailure("archive plan should require explicit confirmation")
    head = cast(dict[str, Any], preview["head"])
    confirmation = _require_one_of(
        client.post(
            "/v1/archive-confirmations",
            headers=compose_auth_headers(
                token=ARCHIVER_TOKEN,
                idempotency_key=f"{key_prefix}-archive-confirm",
            ),
            json={
                "expected_baseline_node_id": head["business_baseline_node_id"],
                "expected_baseline_head_version": head["baseline_head_version"],
                "selected": selected,
                "candidate_set_digest": preview["candidate_set_digest"],
                "subject_digest": preview["selection_subject_digest"],
                "expected_sequence": 0,
                "action": "CONFIRM",
                "reason": "archive S2b real dump v1",
            },
        ),
        {200, 201},
        "archive confirmation",
    )
    ready = _require(
        client.post(
            "/v1/archive-plan-preview",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            json={"selected": selected},
        ),
        200,
        "confirmed archive plan preview",
    )
    if ready.get("can_start") is not True or ready.get("audit_validity") is not True:
        raise JourneyFailure("confirmed archive plan is not ready")
    ready_head = cast(dict[str, Any], ready["head"])
    archived = _require_one_of(
        client.post(
            "/v1/archives",
            headers=compose_auth_headers(
                token=ARCHIVER_TOKEN,
                idempotency_key=f"{key_prefix}-archive-start",
            ),
            json={
                "expected_baseline_node_id": ready_head["business_baseline_node_id"],
                "expected_baseline_head_version": ready_head["baseline_head_version"],
                "candidate_set_digest": ready["candidate_set_digest"],
                "selected": selected,
                "confirmation_refs": [
                    {
                        "subject_digest": ready["selection_subject_digest"],
                        "sequence": confirmation["sequence"],
                    }
                ],
            },
        ),
        {200, 201},
        "archive start",
    )
    if type(archived.get("baseline_node_id")) is not str:
        raise JourneyFailure("archive did not advance the baseline node")
    return archived


def _repository_service_url(env: Mapping[str, str]) -> str:
    result = run_compose(cast(dict[str, str], dict(env)), "ps", "-q", "repository-service")
    container_id = result.stdout.strip().splitlines()
    if result.returncode != 0 or not container_id:
        raise JourneyFailure("could not resolve Repository Service container")
    inspected = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_id[0],
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    address = inspected.stdout.strip()
    if inspected.returncode != 0 or not address:
        raise JourneyFailure("Repository Service container has no reachable network address")
    return f"http://{address}:8000"


def _repository_catalog(
    client: httpx.Client, repository_id: str, commit_id: str
) -> tuple[list[dict[str, Any]], int]:
    encoded = encode_commit_id_path_segment(commit_id)
    response = client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog"
    )
    payload = _require(response, 200, "Repository catalog")
    catalog = cast(dict[str, Any], payload["catalog"])
    tables = catalog.get("tables")
    if not isinstance(tables, list):
        raise JourneyFailure("Repository catalog has no table list")
    normalized = [cast(dict[str, Any], item) for item in tables if isinstance(item, dict)]
    total_rows = sum(int(item["row_count"]) for item in normalized)
    return normalized, total_rows


def _pseudo_counts_from_http(
    *,
    base_url: str,
    repository_id: str,
    commit_id: str,
    expected_tables: Mapping[str, int],
) -> dict[str, Any]:
    catalog_client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        timeout=300.0,
    )
    try:
        catalog, row_count_total = _repository_catalog(catalog_client, repository_id, commit_id)
        catalog_by_name = {str(item["name"]): item for item in catalog}
        missing = sorted(set(expected_tables) - set(catalog_by_name))
        if missing:
            raise JourneyFailure("one or more census ordered tables are absent from Repository")
        actual: dict[str, int] = {}
        for table_name in sorted(expected_tables):
            encoded = encode_commit_id_path_segment(commit_id)
            response = catalog_client.get(
                f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
                params={"table_name": table_name},
            )
            if response.status_code != 200:
                raise JourneyFailure(f"Repository rows HTTP {response.status_code} for ordered table")
            pseudo_count = 0
            total = 0
            try:
                reader = pa_ipc.open_stream(response.content)
                if "gid" not in reader.schema.names:
                    raise JourneyFailure("ordered table Arrow schema has no gid column")
                gid_index = reader.schema.get_field_index("gid")
                for batch in reader:
                    gids = batch.column(gid_index)
                    total += batch.num_rows
                    pseudo_count += sum(
                        int(value.as_py()) >= PSEUDO_GID_MIN
                        for value in gids
                        if value.as_py() is not None
                    )
            except (pa.ArrowInvalid, ValueError, TypeError) as exc:
                raise JourneyFailure("Repository ordered table Arrow stream is invalid") from exc
            expected_rows = int(catalog_by_name[table_name]["row_count"])
            if total != expected_rows:
                raise JourneyFailure("Repository Arrow row count differs from its catalog")
            actual[table_name] = pseudo_count
        expected_total = sum(int(value) for value in expected_tables.values())
        actual_total = sum(actual.values())
        if actual_total != expected_total:
            raise JourneyFailure("Repository ordered pseudo row count differs from census")
        return {
            "table_count": len(catalog),
            "row_count_total": row_count_total,
            "ordered_table_pseudo_counts": actual,
            "pseudo_rows_total": actual_total,
        }
    finally:
        catalog_client.close()


def _history_surface_ref(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    pairs = bundle.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 1 or not isinstance(pairs[0], Mapping):
        raise JourneyFailure("History bundle does not contain exactly one pair")
    pair_id = pairs[0].get("pair_id")
    if type(pair_id) is not str or not pair_id:
        raise JourneyFailure("History bundle pair has no identity")
    entries = bundle.get("closure_entries")
    if not isinstance(entries, list):
        raise JourneyFailure("History bundle has no closure entries")
    surface_path = f"pairs/{pair_id}/comparison-surface.json"
    surface_entries = [
        item
        for item in entries
        if isinstance(item, Mapping)
        and item.get("kind") == "SURFACE"
        and item.get("logical_path") == surface_path
    ]
    if len(surface_entries) != 1:
        raise JourneyFailure("History bundle does not contain exactly one surface artifact")
    surface_ref = surface_entries[0].get("artifact_ref")
    if not isinstance(surface_ref, Mapping):
        raise JourneyFailure("History surface artifact has no reference")
    return cast(Mapping[str, Any], surface_ref)


def _history_compare(
    client: httpx.Client,
    *,
    tier: str,
    v1_submission_id: str,
    v1_commit_id: str,
    v2_submission_id: str,
    v2_commit_id: str,
    idempotency_key: str,
    operation_timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    stage = f"{tier} History"
    _emit_progress(stage, "history_compare_started")
    response = client.post(
        "/v1/history-compares",
        headers=compose_auth_headers(token=HISTORY_READER_TOKEN, idempotency_key=idempotency_key),
        json={
            "nodes": [
                {"ref_kind": "submission", "ref_id": v1_submission_id},
                {"ref_kind": "submission", "ref_id": v2_submission_id},
            ]
        },
    )
    accepted = _require_one_of(response, {200, 202}, "History compare acceptance")
    operation_id = str(accepted["operation_id"])
    deadline = time.monotonic() + operation_timeout_seconds
    terminal: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = _require(
            client.get(
                f"/v1/history-compares/{operation_id}",
                headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
            ),
            200,
            "History compare status",
        )
        if payload.get("status") in TERMINAL_OPERATION_STATES:
            terminal = payload
            break
        time.sleep(2.0)
    if terminal is None or terminal.get("status") != "SUCCEEDED":
        diagnostic = terminal.get("diagnostic") if terminal is not None else None
        code = diagnostic.get("code") if isinstance(diagnostic, dict) else "timeout"
        raise JourneyFailure(f"{stage} compare did not succeed, diagnostic={code}")
    result = terminal.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("pairs"), list) or len(result["pairs"]) != 1:
        raise JourneyFailure("History compare result has an unexpected pair count")
    pair = cast(dict[str, Any], result["pairs"][0])
    if pair.get("before_commit") != v1_commit_id or pair.get("current_commit") != v2_commit_id:
        raise JourneyFailure("History compare did not use the v1 and v2 Repository commits")
    bundle_response = client.get(
        f"/v1/history-compares/{operation_id}/bundle",
        headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
    )
    if bundle_response.status_code != 200:
        raise JourneyFailure(f"History compare bundle HTTP {bundle_response.status_code}")
    try:
        bundle = cast(dict[str, Any], json.loads(bundle_response.content))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JourneyFailure("History compare bundle was not a JSON manifest") from exc
    if not isinstance(bundle.get("closure_entries"), list):
        raise JourneyFailure("History compare bundle does not have closure entries")
    _emit_progress(stage, "history_compare_succeeded")
    return {
        "operation_id": operation_id,
        "pair": pair,
        "bundle": bundle,
        "bundle_digest": result.get("bundle_digest"),
    }, operation_id


def _keyless_fallback_candidates(census: Mapping[str, Any]) -> tuple[str, ...]:
    scan = census.get("effective_key_scan")
    if not isinstance(scan, dict):
        raise JourneyFailure("census has no effective-key scan")
    unresolved = scan.get("unresolved_tables")
    if not isinstance(unresolved, list) or any(type(item) is not str for item in unresolved):
        raise JourneyFailure("census effective-key unresolved table list is invalid")
    return tuple(sorted(set(cast(list[str], unresolved))))


def _run_tier(
    *,
    tier: str,
    v1_id: str,
    v2_id: str,
    root: Path,
    datasets: Mapping[str, dict[str, Any]],
    census: Mapping[str, dict[str, Any]],
    env: dict[str, str],
    project_name: str,
    repository_id: str,
    initial_commit_id: str,
    step_state: dict[str, Any],
    from_step: str | None,
    state_path: Path | None,
) -> dict[str, Any]:
    started = time.monotonic()
    v1_bytes, v1_file = _dataset_package(root, datasets[v1_id])
    v2_bytes, v2_file = _dataset_package(root, datasets[v2_id])
    v1_ordered = _ordered_tables(census[v1_id])
    v2_ordered = _ordered_tables(census[v2_id])
    v1_keyless_names = _keyless_fallback_candidates(census[v1_id])
    v2_keyless_names = _keyless_fallback_candidates(census[v2_id])
    if int(census[v1_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v1_id]:
        raise JourneyFailure(f"{v1_id}: census pseudo total differs from the accepted baseline")
    if int(census[v2_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v2_id]:
        raise JourneyFailure(f"{v2_id}: census pseudo total differs from the accepted baseline")

    images = compose_image_ids(env)
    repository_url = _repository_service_url(env)
    runner = JourneyStepRunner(
        tier=tier,
        env=env,
        state=step_state,
        from_step=from_step,
        state_path=state_path,
    )

    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(),
        timeout=600.0,
    ) as client:
        v1_workspace = runner.run("v1-workspace", lambda: _workspace(client))
        v1_upload = runner.run(
            "v1-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                package=v1_bytes,
                idempotency_key=f"{project_name}-{tier}-v1-upload",
            ),
        )

        def v1_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                upload=cast(Mapping[str, Any], v1_upload),
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-{tier}-v1-preview",
                stage=f"{tier} v1 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v1-preview"),
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=False,
            )
            _emit_progress(
                f"{tier} v1 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v1_id]["table_count"]),
            )
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v1_keyless_names),
            }

        v1_preview_state = cast(
            dict[str, Any],
            runner.run("v1-preview", v1_preview_action),
        )
        v1_preview = cast(dict[str, Any], v1_preview_state["preview"])
        v1_summary = cast(dict[str, int], v1_preview_state["summary"])

        v1_submission = runner.run(
            "v1-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                upload=cast(Mapping[str, Any], v1_upload),
                preview=v1_preview,
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-{tier}-v1-submit",
                stage=f"{tier} v1 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v1-submit"),
            ),
        )
        v1_submission = cast(dict[str, Any], v1_submission)
        v1_submission_id = str(v1_submission["submission_id"])
        v1_commit_id = str(v1_submission["repository_commit_id"])

        def v1_repository_read_action() -> dict[str, Any]:
            repository = _pseudo_counts_from_http(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v1_commit_id,
                expected_tables=v1_ordered,
            )
            if repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v1_id]:
                raise JourneyFailure(f"{v1_id}: committed pseudo row count differs from census")
            return repository

        v1_repository = cast(
            dict[str, Any],
            runner.run("v1-repository-read", v1_repository_read_action),
        )
        def approve_v1_action() -> dict[str, bool]:
            _approve(client, v1_submission_id, f"{project_name}-{tier}-v1-review")
            return {"approved": True}

        runner.run("v1-approve", approve_v1_action)

        def archive_v1_action() -> dict[str, Any]:
            archive = _archive(client, v1_submission_id, f"{project_name}-{tier}-v1")
            if archive.get("baseline_commit_id") != v1_commit_id:
                raise JourneyFailure("v1 Archive did not promote the v1 Repository commit")
            return archive

        archive = cast(dict[str, Any], runner.run("v1-archive", archive_v1_action))
        baseline_node_id = str(archive["baseline_node_id"])
        baseline_head_version = int(archive["baseline_head_version"])

        repeat_workspace = runner.run(
            "repeat-v1-workspace",
            lambda: _workspace(client),
        )
        repeat_upload = runner.run(
            "repeat-v1-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                package=v1_bytes,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-upload",
            ),
        )

        def repeat_v1_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                upload=cast(Mapping[str, Any], repeat_upload),
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-preview",
                stage=f"{tier} repeat v1 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "repeat-v1-preview"),
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=True,
            )
            _emit_progress(
                f"{tier} repeat v1 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v1_id]["table_count"]),
            )
            if tuple(v1_keyless_names) != _keyless_fallback_candidates(census[v1_id]):
                raise JourneyFailure("keyless fallback candidates changed during repeated Preview")
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v1_keyless_names),
            }

        repeat_preview_state = cast(
            dict[str, Any],
            runner.run("repeat-v1-preview", repeat_v1_preview_action),
        )
        repeat_preview = cast(dict[str, Any], repeat_preview_state["preview"])
        repeat_summary = cast(dict[str, int], repeat_preview_state["summary"])

        repeat_submit = runner.run(
            "repeat-v1-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                upload=cast(Mapping[str, Any], repeat_upload),
                preview=repeat_preview,
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-submit",
                stage=f"{tier} repeat v1 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "repeat-v1-submit"),
                expect_no_change=True,
            ),
        )

        v2_workspace = runner.run("v2-workspace", lambda: _workspace(client))
        v2_upload = runner.run(
            "v2-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                package=v2_bytes,
                idempotency_key=f"{project_name}-{tier}-v2-upload",
            ),
        )

        def v2_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                upload=cast(Mapping[str, Any], v2_upload),
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-v2-preview",
                stage=f"{tier} v2 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v2-preview"),
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=False,
            )
            _emit_progress(
                f"{tier} v2 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v2_id]["table_count"]),
            )
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v2_keyless_names),
            }

        v2_preview_state = cast(
            dict[str, Any],
            runner.run("v2-preview", v2_preview_action),
        )
        v2_preview = cast(dict[str, Any], v2_preview_state["preview"])
        v2_summary = cast(dict[str, int], v2_preview_state["summary"])

        v2_submission = runner.run(
            "v2-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                upload=cast(Mapping[str, Any], v2_upload),
                preview=v2_preview,
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-v2-submit",
                stage=f"{tier} v2 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v2-submit"),
            ),
        )
        v2_submission = cast(dict[str, Any], v2_submission)
        v2_submission_id = str(v2_submission["submission_id"])
        v2_commit_id = str(v2_submission["repository_commit_id"])

        def v2_repository_read_action() -> dict[str, Any]:
            repository = _pseudo_counts_from_http(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v2_commit_id,
                expected_tables=v2_ordered,
            )
            if repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v2_id]:
                raise JourneyFailure(f"{v2_id}: committed pseudo row count differs from census")
            return repository

        v2_repository = cast(
            dict[str, Any],
            runner.run("v2-repository-read", v2_repository_read_action),
        )
        def approve_v2_action() -> dict[str, bool]:
            _approve(client, v2_submission_id, f"{project_name}-{tier}-v2-review")
            return {"approved": True}

        runner.run("v2-approve", approve_v2_action)

        def history_action() -> dict[str, Any]:
            result, operation_id = _history_compare(
                client,
                tier=tier,
                v1_submission_id=v1_submission_id,
                v1_commit_id=v1_commit_id,
                v2_submission_id=v2_submission_id,
                v2_commit_id=v2_commit_id,
                idempotency_key=f"{project_name}-{tier}-history-compare",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "history"),
            )
            _history_surface_ref(cast(Mapping[str, Any], result["bundle"]))
            return {"operation_id": operation_id, "result": result}

        history_state = cast(
            dict[str, Any],
            runner.run("history", history_action),
        )

    history_result = cast(dict[str, Any], history_state["result"])
    history_pair = cast(dict[str, Any], history_result["pair"])
    api_record_count = int(history_pair["record_count"])
    if api_record_count < 0:
        raise JourneyFailure("History HTTP record_count must be non-negative")
    repeat_keyless_names = v1_keyless_names
    return {
        "tier": tier,
        "datasets": [
            {
                "dataset_id": v1_id,
                "sha256": v1_file["sha256"],
                "package_bytes": v1_file["bytes"],
                "table_count": census[v1_id]["table_count"],
                "row_count_total": census[v1_id]["row_count_total"],
                "storage_column_type_counts": census[v1_id]["storage_column_type_counts"],
                "repository": v1_repository,
                "preview": v1_summary,
                "keyless_fallback_tables": {
                    "count": len(v1_keyless_names),
                    "names": list(v1_keyless_names),
                    "source": "S1 census effective_key_scan.unresolved_tables",
                },
            },
            {
                "dataset_id": v2_id,
                "sha256": v2_file["sha256"],
                "package_bytes": v2_file["bytes"],
                "table_count": census[v2_id]["table_count"],
                "row_count_total": census[v2_id]["row_count_total"],
                "storage_column_type_counts": census[v2_id]["storage_column_type_counts"],
                "repository": v2_repository,
                "preview": v2_summary,
                "keyless_fallback_tables": {
                    "count": len(v2_keyless_names),
                    "names": list(v2_keyless_names),
                    "source": "S1 census effective_key_scan.unresolved_tables",
                },
            },
        ],
        "repeat_v1": {
            "preview": repeat_summary,
            "submit": repeat_submit,
            "keyless_fallback_candidates_unchanged": {
                "count": len(repeat_keyless_names),
                "names": list(repeat_keyless_names),
                "evidence": "all-table preview summary has changed_table_count=0",
            },
        },
        "history": {
            "record_count": api_record_count,
            "bundle_digest": history_result.get("bundle_digest"),
            "surface_digest": history_pair.get("surface_digest"),
            "record_kind_counts": None,
            "detail_availability": (
                "public History HTTP exposes pair record_count and digests; "
                "bundle artifacts are references without public content retrieval"
            ),
        },
        "compose_image_ids": images,
        "step_metrics": runner.metrics,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "conclusion": "PASS",
        "empty_initial_commit_id": initial_commit_id,
    }


def _persist_debug_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary_path.replace(path)


def _load_debug_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JourneyFailure("debug checkpoint could not be read") from exc
    if not isinstance(payload, dict):
        raise JourneyFailure("debug checkpoint is not an object")
    return cast(dict[str, Any], payload)


def _resume_stack(env: dict[str, str], state: Mapping[str, Any]) -> tuple[str, str]:
    stack = state.get("_stack")
    if not isinstance(stack, dict):
        raise JourneyFailure("debug checkpoint has no stack identity")
    repository_id = stack.get("repository_id")
    initial_commit_id = stack.get("initial_commit_id")
    if type(repository_id) is not str or type(initial_commit_id) is not str:
        raise JourneyFailure("debug checkpoint has an invalid stack identity")
    wait_repository_service_ready(env)
    wait_http_ok(f"{BACKEND_URL}/readyz")
    worker_ready(env)
    return repository_id, initial_commit_id


def _validate_project_name(project_name: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project_name):
        raise JourneyFailure("Compose project name must use 1..63 lowercase letters, digits, '_' or '-' ")


def run_journey(
    *,
    tier_filter: str | None = None,
    from_step: str | None = None,
    keep_stack: bool = False,
    requested_project_name: str | None = None,
) -> dict[str, Any]:
    root = _real_dump_root()
    datasets, census = _read_metadata(root)
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
        timeout=10.0,
    ).stdout.strip()
    if keep_stack and tier_filter is None:
        raise JourneyFailure("--keep-stack requires --tier")
    if from_step is not None and not keep_stack:
        raise JourneyFailure("--from-step requires --keep-stack")
    if from_step is not None and requested_project_name is None:
        raise JourneyFailure("--from-step requires --project-name")
    if requested_project_name is not None and not keep_stack:
        raise JourneyFailure("--project-name is only used with --keep-stack")
    if requested_project_name is None:
        project_name = f"s2b-realdata-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    else:
        project_name = requested_project_name
    _validate_project_name(project_name)

    selected_tiers = [
        (key.split("-")[1], pair)
        for key, pair in EXPECTED_PAIRINGS.items()
        if tier_filter is None or key.split("-")[1] == tier_filter
    ]
    if not selected_tiers:
        raise JourneyFailure("requested real-data tier is unknown")

    original_prebuilt = os.environ.get("GATEWAY_COMPOSE_GATE_PREBUILT")
    os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
    results: list[dict[str, Any]] = []
    state_paths: list[str] = []
    stack_start_seconds: dict[str, float] = {}
    project_root = root / "runs" / project_name
    if keep_stack:
        project_root.mkdir(parents=True, exist_ok=True)

    try:
        with (
            contextlib.nullcontext(project_root)
            if keep_stack
            else tempfile.TemporaryDirectory(prefix="gdds-s2b-realdata-")
        ) as temporary_root:
            base = Path(temporary_root) if not keep_stack else cast(Path, temporary_root)
            if from_step is not None:
                os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"
            else:
                first_tier = selected_tiers[0][0]
                first_secret_root = base / f"{first_tier}-secrets"
                first_env = _compose_environment(first_secret_root, project_name)
                if subprocess.run(
                    ["docker", "image", "inspect", REPOSITORY_SERVICE_IMAGE],
                    check=False,
                    capture_output=True,
                    timeout=30.0,
                ).returncode != 0:
                    raise JourneyFailure("the gate Repository Service image is missing")
                build_compose_stack_images(first_env)
                os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"

            for tier, (v1_id, v2_id) in selected_tiers:
                state_path = base / f"{tier}.state.json" if keep_stack else None
                if state_path is not None:
                    state_paths.append(str(state_path))
                if from_step is not None:
                    if state_path is None:
                        raise JourneyFailure("debug checkpoint path is unavailable")
                    step_state = _load_debug_state(state_path)
                else:
                    if state_path is not None and state_path.exists():
                        raise JourneyFailure(
                            "debug checkpoint already exists; choose a new --project-name "
                            "or resume with --from-step"
                        )
                    step_state = {}

                secret_root = base / f"{tier}-secrets"
                env = _compose_environment(
                    secret_root,
                    project_name,
                    write_secrets=from_step is None,
                )
                acquire_compose_gate_lock()
                try:
                    stack_started = time.monotonic()
                    if from_step is None:
                        repository_id, initial_commit_id = start_three_container_stack(
                            env,
                            secret_root,
                        )
                        step_state["_stack"] = {
                            "repository_id": repository_id,
                            "initial_commit_id": initial_commit_id,
                            "project_name": project_name,
                            "tier": tier,
                            "head": current_head,
                        }
                        if state_path is not None:
                            _persist_debug_state(state_path, step_state)
                    else:
                        repository_id, initial_commit_id = _resume_stack(env, step_state)
                    stack_start_seconds[tier] = round(time.monotonic() - stack_started, 3)
                    results.append(
                        _run_tier(
                            tier=tier,
                            v1_id=v1_id,
                            v2_id=v2_id,
                            root=root,
                            datasets=datasets,
                            census=census,
                            env=env,
                            project_name=project_name,
                            repository_id=repository_id,
                            initial_commit_id=initial_commit_id,
                            step_state=step_state,
                            from_step=from_step,
                            state_path=state_path,
                        )
                    )
                finally:
                    if keep_stack:
                        release_compose_gate_lock()
                    else:
                        cleanup_compose_project_artifacts(env)
    finally:
        if original_prebuilt is None:
            os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
        else:
            os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = original_prebuilt

    return {
        "head": current_head,
        "datasets": results,
        "stack_start_seconds": stack_start_seconds,
        "debug_project_name": project_name if keep_stack else None,
        "debug_state_files": state_paths if keep_stack else [],
        "conclusion": "PASS",
    }


def validate_inputs() -> dict[str, Any]:
    root = _real_dump_root()
    datasets, census = _read_metadata(root)
    validated = []
    for dataset_id in sorted(datasets):
        _package, file_info = _dataset_package(root, datasets[dataset_id])
        ordered = _ordered_tables(census[dataset_id])
        validated.append(
            {
                "dataset_id": dataset_id,
                "sha256": file_info["sha256"],
                "package_bytes": file_info["bytes"],
                "table_count": census[dataset_id]["table_count"],
                "row_count_total": census[dataset_id]["row_count_total"],
                "pseudo_rows_total": sum(ordered.values()),
                "keyless_fallback_candidates": list(
                    _keyless_fallback_candidates(census[dataset_id])
                ),
            }
        )
    return {"datasets": validated, "conclusion": "INPUTS_VALID"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-inputs",
        action="store_true",
        help="check package hashes and the G8a census without starting containers",
    )
    parser.add_argument("--tier", choices=("t1", "t2", "t3", "t4"))
    parser.add_argument("--from-step", choices=JOURNEY_STEP_IDS)
    parser.add_argument("--keep-stack", action="store_true")
    parser.add_argument("--project-name")
    arguments = parser.parse_args(argv)
    try:
        if arguments.validate_inputs and any(
            (
                arguments.tier is not None,
                arguments.from_step is not None,
                arguments.keep_stack,
                arguments.project_name is not None,
            )
        ):
            raise JourneyFailure("--validate-inputs cannot be combined with journey controls")
        result = (
            validate_inputs()
            if arguments.validate_inputs
            else run_journey(
                tier_filter=arguments.tier,
                from_step=arguments.from_step,
                keep_stack=arguments.keep_stack,
                requested_project_name=arguments.project_name,
            )
        )
        print(json.dumps(result, sort_keys=True))
    except JourneyFailure as exc:
        print(json.dumps({"conclusion": "FAILED", "reason": str(exc)}))
        return 1
    except (OSError, subprocess.SubprocessError, httpx.HTTPError) as exc:
        print(json.dumps({"conclusion": "FAILED", "reason": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
