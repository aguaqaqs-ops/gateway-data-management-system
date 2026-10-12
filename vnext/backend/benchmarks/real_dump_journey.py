"""Run the S2b real dump Preview/Submit/History journey from the host.

The source packages are read-only inputs. Uploads and public read operations use
the HTTP APIs; only aggregate comparison facts are inspected inside the backend
container because the public history result exposes a pair total, not per-kind
record counts. No row values or row identifiers are emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
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
    run_compose,
    start_three_container_stack,
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


def _compose_environment(secret_root: Path, project_name: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(_write_compose_secrets(secret_root))
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


def _poll_operation(
    client: httpx.Client,
    operation_id: str,
    *,
    stage: str,
    timeout_seconds: int = 7_200,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = _require(client.get(f"/v1/operations/{operation_id}"), 200, "operation status")
        status = payload.get("status")
        if status in TERMINAL_OPERATION_STATES:
            if status != "SUCCEEDED":
                diagnostic = payload.get("diagnostic")
                code = diagnostic.get("code") if isinstance(diagnostic, dict) else "unknown"
                raise JourneyFailure(f"{stage} operation ended {status}, diagnostic={code}")
            return payload
        time.sleep(2.0)
    raise JourneyFailure("operation did not reach a terminal state before timeout")


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
    return _require(response, 201, "upload revision")


def _preview(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    upload: Mapping[str, Any],
    baseline_node_id: str,
    baseline_head_version: int,
    idempotency_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = _require(
        client.post(
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
        ),
        202,
        "preview acceptance",
    )
    _poll_operation(client, str(accepted["operation_id"]), stage="Preview")
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
    return {"workspace": refreshed, "result": result}, cast(dict[str, Any], {"pairs": summaries})


def _assert_preview_summaries(manifest: Mapping[str, Any], *, unchanged: bool) -> dict[str, int]:
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise JourneyFailure("preview manifest has no pairs")
    totals = Counter()
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
    accepted = _require(response, 202, "submit acceptance")
    _poll_operation(client, str(accepted["operation_id"]), stage="Submit")
    deadline = time.monotonic() + 7_200
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
        raise JourneyFailure("submit attempt did not finalize")
    submission = _require(
        client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submissions/{attempt['submission_id']}"
        ),
        200,
        "submission read",
    )
    if type(submission.get("repository_commit_id")) is not str:
        raise JourneyFailure("submission did not expose its Repository commit id")
    return submission


def _approve(client: httpx.Client, submission_id: str, idempotency_key: str) -> None:
    _require(
        client.post(
            f"/v1/submissions/{submission_id}/review-events",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key=idempotency_key),
            json={"expected_review_version": 0, "action": "APPROVE"},
        ),
        201,
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
    confirmation = _require(
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
        201,
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
    archived = _require(
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
        201,
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


def _summary_history_facts(
    env: Mapping[str, str],
    *,
    operation_id: str,
    before_commit: str,
    current_commit: str,
    ordered_table_names: Iterable[str],
) -> dict[str, Any]:
    """Extract aggregate fact counts in-container without returning row data."""

    remote_script = r'''
import bisect, json, sqlite3
from collections import Counter
from pathlib import Path
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history.compare_jobs import _sides_from_materialize_checkpoint
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.capabilities.comparison import ComparisonPlan, ComparisonRequest, DetailedFactsResult, compare_plan, plan_comparison
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_shared_kernel import SignedIntegerScalar, UnsignedIntegerScalar, StringScalar

operation_id = json.loads(__import__('os').environ['S2B_HISTORY_OPERATION'])
before_commit = json.loads(__import__('os').environ['S2B_HISTORY_BEFORE'])
current_commit = json.loads(__import__('os').environ['S2B_HISTORY_CURRENT'])
ordered_names = set(json.loads(__import__('os').environ['S2B_ORDERED_TABLES']))
step_id = operation_id + '-step-1'
connection = sqlite3.connect('/var/lib/gateway/control/control.sqlite3')
row = connection.execute('SELECT checkpoint_ref FROM step_records WHERE step_id = ?', (step_id,)).fetchone()
if row is None or row[0] is None:
    raise SystemExit('history materialize checkpoint is unavailable')
checkpoint = json.loads(row[0].decode('utf-8') if isinstance(row[0], bytes) else row[0])
store = LocalArtifactStore(Path('/var/lib/gateway/artifacts'))
envelope = load_checkpoint_envelope(store, artifact_ref_from_dict(checkpoint))
sides = _sides_from_materialize_checkpoint(envelope.job_state, store)
before = sides[before_commit]
current = sides[current_commit]
request = ComparisonRequest(pair_id='pair-0', before=before, current=current,
                            rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()))
plan = plan_comparison(request)
if not isinstance(plan, ComparisonPlan):
    raise SystemExit('history pair planning did not produce a comparison plan')
compared = compare_plan(plan)
if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
    raise SystemExit('history comparison did not produce detailed facts')
facts = compared.facts

def scalar_integer(value):
    if isinstance(value, (SignedIntegerScalar, UnsignedIntegerScalar)):
        return int(value.decimal, 10)
    if isinstance(value, StringScalar) and value.text.isdecimal():
        return int(value.text, 10)
    return None

def read_ordered_rows(snapshot, name):
    table = next((item for item in snapshot.tables if item.descriptor.table_name == name), None)
    if table is None or table.reader is None:
        return []
    descriptor = table.descriptor
    indexes = {column.name: index for index, column in enumerate(descriptor.columns)}
    gid_index, position_index = indexes['gid'], indexes['no']
    reader = table.reader.reopen()
    rows = []
    try:
        for raw in reader.iter_rows():
            gid = scalar_integer(raw[gid_index])
            position = scalar_integer(raw[position_index])
            if gid is None or position is None:
                raise SystemExit('ordered snapshot has an invalid gid or position')
            rows.append((gid, position))
    finally:
        reader.close()
    rows.sort(key=lambda item: item[1])
    return rows

def stable_real_rows(rows):
    return [(gid, position) for gid, position in rows if gid < 4000000000]

def lis_backbone(keys, positions):
    if not positions:
        return set()
    reach = [0] * len(positions)
    tails = []
    for index in range(len(positions) - 1, -1, -1):
        slot = bisect.bisect_left(tails, -positions[index])
        if slot == len(tails):
            tails.append(-positions[index])
        else:
            tails[slot] = -positions[index]
        reach[index] = slot + 1
    longest = max(reach)
    levels = [[] for _ in range(longest + 1)]
    for index, length in enumerate(reach):
        levels[length].append(index)
    chosen = []
    previous = -1
    for length in range(longest, 0, -1):
        index = levels[length][bisect.bisect_right(levels[length], previous)]
        chosen.append(index)
        previous = index
    return {keys[index] for index in chosen}

def gaps(rows, anchors):
    result = {}
    previous_anchor = None
    count = 0
    start = end = 0
    for gid, position in rows:
        if gid >= 4000000000:
            if count == 0:
                start = position
            count += 1
            end = position
            continue
        if gid not in anchors:
            continue
        if count:
            result[(previous_anchor, gid)] = (count, start, end)
        previous_anchor = gid
        count = 0
    if count:
        result[(previous_anchor, None)] = (count, start, end)
    return result

counts = Counter()
ordered_results = {}
all_table_names = set(ordered_names)
for table in facts.tables:
    counts.update(record.record_kind.value for record in table.records)
    ordered_records = () if table.ordered_extension is None else table.ordered_extension.records
    blank_records = () if table.blank_extension is None else table.blank_extension.records
    counts.update(record.record_kind.value for record in ordered_records)
    counts.update(record.record_kind.value for record in blank_records)
    if table.table_name not in all_table_names:
        continue
    if table.status.value == 'DEGRADED':
        raise SystemExit('an IEC104 ordered table degraded during History compare')
    before_rows = read_ordered_rows(before, table.table_name)
    current_rows = read_ordered_rows(current, table.table_name)
    before_real = stable_real_rows(before_rows)
    current_real = stable_real_rows(current_rows)
    current_positions = {gid: position for gid, position in current_real}
    common_keys = [gid for gid, _ in before_real if gid in current_positions]
    positions = [current_positions[gid] for gid in common_keys]
    backbone = lis_backbone(common_keys, positions)
    expected_move_count = len(common_keys) - len(backbone)
    moved_count = sum(record.record_kind.value == 'ORDERED_ROW_MOVED' for record in ordered_records)
    if moved_count != expected_move_count:
        raise SystemExit('ordered move count exceeds the minimum required by real row order')
    expected_before = gaps(before_rows, backbone)
    expected_current = gaps(current_rows, backbone)
    expected_intervals = Counter()
    for key in set(expected_before) | set(expected_current):
        before_gap = expected_before.get(key)
        current_gap = expected_current.get(key)
        before_count = 0 if before_gap is None else before_gap[0]
        current_count = 0 if current_gap is None else current_gap[0]
        if before_count == current_count:
            continue
        expected_intervals[(
            None if before_gap is None else before_gap[1],
            None if before_gap is None else before_gap[2],
            None if current_gap is None else current_gap[1],
            None if current_gap is None else current_gap[2],
            abs(current_count - before_count),
            before_count,
            current_count,
        )] += 1
    actual_intervals = Counter((
        record.interval.before_start, record.interval.before_end,
        record.interval.current_start, record.interval.current_end,
        record.interval.row_count, record.before_occupancy, record.current_occupancy,
    ) for record in blank_records)
    if actual_intervals != expected_intervals:
        raise SystemExit('blank records do not match net skeleton interval occupancy changes')
    ordered_results[table.table_name] = {
        'status': table.status.value,
        'standard_record_counts': dict(Counter(record.record_kind.value for record in table.records)),
        'ordered_record_counts': dict(Counter(record.record_kind.value for record in ordered_records)),
        'blank_interval_record_counts': dict(Counter(record.record_kind.value for record in blank_records)),
        'blank_net_row_delta': sum(record.interval.row_count for record in blank_records),
        'expected_real_row_move_count': expected_move_count,
    }
if set(ordered_results) != all_table_names:
    raise SystemExit('History facts omitted one or more IEC104 ordered tables')
print(json.dumps({
    'total_fact_record_count': sum(counts.values()),
    'record_kind_counts': dict(sorted(counts.items())),
    'ordered_tables': ordered_results,
}, sort_keys=True))
'''
    command_env = dict(env)
    command_env.update(
        {
            "S2B_HISTORY_OPERATION": json.dumps(operation_id),
            "S2B_HISTORY_BEFORE": json.dumps(before_commit),
            "S2B_HISTORY_CURRENT": json.dumps(current_commit),
            "S2B_ORDERED_TABLES": json.dumps(sorted(ordered_table_names)),
        }
    )
    result = run_compose(
        command_env,
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        remote_script,
        timeout=900.0,
    )
    if result.returncode != 0:
        raise JourneyFailure("aggregate History facts could not be verified in the backend container")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise JourneyFailure("aggregate History facts response was invalid") from exc
    if not isinstance(payload, dict):
        raise JourneyFailure("aggregate History facts response was not an object")
    return cast(dict[str, Any], payload)


def _history_compare(
    client: httpx.Client,
    *,
    v1_submission_id: str,
    v1_commit_id: str,
    v2_submission_id: str,
    v2_commit_id: str,
    idempotency_key: str,
) -> tuple[dict[str, Any], str]:
    accepted = _require(
        client.post(
            "/v1/history-compares",
            headers=compose_auth_headers(token=HISTORY_READER_TOKEN, idempotency_key=idempotency_key),
            json={
                "nodes": [
                    {"ref_kind": "submission", "ref_id": v1_submission_id},
                    {"ref_kind": "submission", "ref_id": v2_submission_id},
                ]
            },
        ),
        202,
        "History compare acceptance",
    )
    operation_id = str(accepted["operation_id"])
    deadline = time.monotonic() + 7_200
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
        raise JourneyFailure(f"History compare did not succeed, diagnostic={code}")
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
    return {"operation_id": operation_id, "pair": pair, "bundle": bundle}, operation_id


def _run_tier(
    *,
    tier: str,
    v1_id: str,
    v2_id: str,
    root: Path,
    datasets: Mapping[str, dict[str, Any]],
    census: Mapping[str, dict[str, Any]],
    env: dict[str, str],
    secret_root: Path,
    project_name: str,
) -> dict[str, Any]:
    started = time.monotonic()
    v1_bytes, v1_file = _dataset_package(root, datasets[v1_id])
    v2_bytes, v2_file = _dataset_package(root, datasets[v2_id])
    v1_ordered = _ordered_tables(census[v1_id])
    v2_ordered = _ordered_tables(census[v2_id])
    if int(census[v1_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v1_id]:
        raise JourneyFailure(f"{v1_id}: census pseudo total differs from the accepted baseline")
    if int(census[v2_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v2_id]:
        raise JourneyFailure(f"{v2_id}: census pseudo total differs from the accepted baseline")

    repository_id, initial_commit_id = start_three_container_stack(env, secret_root)
    images = compose_image_ids(env)
    repository_url = _repository_service_url(env)
    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(),
        timeout=600.0,
    ) as client:
        # First upload reuses the empty INITIAL repository commit.
        v1_workspace = _workspace(client)
        v1_upload = _upload_revision(
            client,
            workspace=v1_workspace,
            package=v1_bytes,
            idempotency_key=f"{project_name}-{tier}-v1-upload",
        )
        v1_preview, v1_manifest = _preview(
            client,
            workspace=v1_workspace,
            upload=v1_upload,
            baseline_node_id=BASELINE_NODE_ID,
            baseline_head_version=0,
            idempotency_key=f"{project_name}-{tier}-v1-preview",
        )
        v1_summary = _assert_preview_summaries(v1_manifest, unchanged=False)
        v1_submission = _submit(
            client,
            workspace=v1_workspace,
            upload=v1_upload,
            preview=v1_preview,
            baseline_node_id=BASELINE_NODE_ID,
            baseline_head_version=0,
            idempotency_key=f"{project_name}-{tier}-v1-submit",
        )
        v1_submission_id = str(v1_submission["submission_id"])
        v1_commit_id = str(v1_submission["repository_commit_id"])
        v1_repository = _pseudo_counts_from_http(
            base_url=repository_url,
            repository_id=repository_id,
            commit_id=v1_commit_id,
            expected_tables=v1_ordered,
        )
        if v1_repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v1_id]:
            raise JourneyFailure(f"{v1_id}: committed pseudo row count differs from census")

        _approve(client, v1_submission_id, f"{project_name}-{tier}-v1-review")
        archive = _archive(client, v1_submission_id, f"{project_name}-{tier}-v1")
        baseline_node_id = str(archive["baseline_node_id"])
        baseline_head_version = int(archive["baseline_head_version"])
        if archive.get("baseline_commit_id") != v1_commit_id:
            raise JourneyFailure("v1 Archive did not promote the v1 Repository commit")

        # Repeating v1 against its archived canonical state must be all unchanged and a no-op.
        repeat_workspace = _workspace(client)
        repeat_upload = _upload_revision(
            client,
            workspace=repeat_workspace,
            package=v1_bytes,
            idempotency_key=f"{project_name}-{tier}-repeat-v1-upload",
        )
        repeat_preview, repeat_manifest = _preview(
            client,
            workspace=repeat_workspace,
            upload=repeat_upload,
            baseline_node_id=baseline_node_id,
            baseline_head_version=baseline_head_version,
            idempotency_key=f"{project_name}-{tier}-repeat-v1-preview",
        )
        repeat_summary = _assert_preview_summaries(repeat_manifest, unchanged=True)
        repeat_submit = _submit(
            client,
            workspace=repeat_workspace,
            upload=repeat_upload,
            preview=repeat_preview,
            baseline_node_id=baseline_node_id,
            baseline_head_version=baseline_head_version,
            idempotency_key=f"{project_name}-{tier}-repeat-v1-submit",
            expect_no_change=True,
        )

        v2_workspace = _workspace(client)
        v2_upload = _upload_revision(
            client,
            workspace=v2_workspace,
            package=v2_bytes,
            idempotency_key=f"{project_name}-{tier}-v2-upload",
        )
        v2_preview, v2_manifest = _preview(
            client,
            workspace=v2_workspace,
            upload=v2_upload,
            baseline_node_id=baseline_node_id,
            baseline_head_version=baseline_head_version,
            idempotency_key=f"{project_name}-{tier}-v2-preview",
        )
        v2_summary = _assert_preview_summaries(v2_manifest, unchanged=False)
        v2_submission = _submit(
            client,
            workspace=v2_workspace,
            upload=v2_upload,
            preview=v2_preview,
            baseline_node_id=baseline_node_id,
            baseline_head_version=baseline_head_version,
            idempotency_key=f"{project_name}-{tier}-v2-submit",
        )
        v2_submission_id = str(v2_submission["submission_id"])
        v2_commit_id = str(v2_submission["repository_commit_id"])
        v2_repository = _pseudo_counts_from_http(
            base_url=repository_url,
            repository_id=repository_id,
            commit_id=v2_commit_id,
            expected_tables=v2_ordered,
        )
        if v2_repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v2_id]:
            raise JourneyFailure(f"{v2_id}: committed pseudo row count differs from census")
        _approve(client, v2_submission_id, f"{project_name}-{tier}-v2-review")
        history_result, operation_id = _history_compare(
            client,
            v1_submission_id=v1_submission_id,
            v1_commit_id=v1_commit_id,
            v2_submission_id=v2_submission_id,
            v2_commit_id=v2_commit_id,
            idempotency_key=f"{project_name}-{tier}-history-compare",
        )

    expected_ordered_tables = set(v1_ordered) | set(v2_ordered)
    facts = _summary_history_facts(
        env,
        operation_id=operation_id,
        before_commit=v1_commit_id,
        current_commit=v2_commit_id,
        ordered_table_names=expected_ordered_tables,
    )
    api_record_count = int(cast(dict[str, Any], history_result["pair"])["record_count"])
    if int(facts["total_fact_record_count"]) != api_record_count:
        raise JourneyFailure("History HTTP record_count differs from aggregate comparison facts")

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
            },
        ],
        "repeat_v1": {"preview": repeat_summary, "submit": repeat_submit},
        "history": {
            "record_count": api_record_count,
            "record_kind_counts": facts["record_kind_counts"],
            "ordered_tables": facts["ordered_tables"],
        },
        "compose_image_ids": images,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "conclusion": "PASS",
        "empty_initial_commit_id": initial_commit_id,
    }


def run_journey() -> dict[str, Any]:
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
    root_uuid = uuid.uuid4().hex[:8]
    project_name = f"s2b-realdata-{os.getpid()}-{root_uuid}"
    os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
    with tempfile.TemporaryDirectory(prefix="gdds-s2b-realdata-") as temporary_root:
        base = Path(temporary_root)
        first_secret_root = base / "t1"
        first_env = _compose_environment(first_secret_root, project_name)
        # Build once after the authoritative gate, then reuse those same V images for all tiers.
        if subprocess.run(
            ["docker", "image", "inspect", REPOSITORY_SERVICE_IMAGE],
            check=False,
            capture_output=True,
            timeout=30.0,
        ).returncode != 0:
            raise JourneyFailure("the gate Repository Service image is missing")
        build_compose_stack_images(first_env)
        os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"

        results = []
        try:
            for tier, (v1_id, v2_id) in EXPECTED_PAIRINGS.items():
                secret_root = base / tier
                env = _compose_environment(secret_root, project_name)
                acquire_compose_gate_lock()
                try:
                    result = _run_tier(
                        tier=tier,
                        v1_id=v1_id,
                        v2_id=v2_id,
                        root=root,
                        datasets=datasets,
                        census=census,
                        env=env,
                        secret_root=secret_root,
                        project_name=project_name,
                    )
                    results.append(result)
                finally:
                    cleanup_compose_project_artifacts(env)
        finally:
            os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
    return {
        "head": current_head,
        "datasets": results,
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
            }
        )
    return {"datasets": validated, "conclusion": "INPUTS_VALID"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-inputs",
        action="store_true",
        help="check package hashes and the G8a census without starting containers",
    )
    arguments = parser.parse_args()
    try:
        result = validate_inputs() if arguments.validate_inputs else run_journey()
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
