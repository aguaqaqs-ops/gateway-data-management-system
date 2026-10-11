"""Compose e2e for History list and compare through production wiring."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BASELINE_NODE_ID,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    accept_history_compare,
    assert_running_backend_worker_images_match_build,
    capture_business_table_state_in_compose,
    capture_r4_manifest_artifact_ids,
    capture_running_container_provenance,
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_project_name,
    list_repository_commit_ids,
    modified_table_upload_files,
    persist_compose_gate_provenance,
    read_history_compare_materialize_job_state,
    read_repository_table_rows,
    require_docker,
    resolve_main_commit_id,
    run_accept_to_submission_read_journey,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
)
from tests.support.history_compare_job_harness import history_compare_provider
from tests.support.repository_ref_materialization import FakeRepositoryTableAccessProvider
from tests.support.history_compare_oracle import oracle_comparison_digest

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ARCHIVER_TOKEN = "compose-archiver-token"
ACTOR2_TOKEN = "compose-actor-2-token"
HISTORY_READER_TOKEN = "compose-history-reader-token"
CROSS_SCOPE_TOKEN = "compose-cross-scope-token"
_LOGGER = logging.getLogger(__name__)


def _compose_env(tmp_path: Path) -> dict[str, str]:
    bearer = tmp_path / "repository-bearer-token"
    bearer.write_text(f"{BEARER_TOKEN}\n", encoding="utf-8")
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": SESSION_TOKEN,
                        "actor_id": "compose-actor-1",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": ARCHIVER_TOKEN,
                        "actor_id": "compose-archiver",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": ACTOR2_TOKEN,
                        "actor_id": "compose-actor-2",
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
                        "token": HISTORY_READER_TOKEN,
                        "actor_id": "compose-history-reader",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "read_project_history",
                        ],
                    },
                    {
                        "token": CROSS_SCOPE_TOKEN,
                        "actor_id": "compose-cross-scope",
                        "gateway_device_external_key": "other-device",
                        "business_project_id": "other-project",
                        "permissions": [
                            "workspace_read",
                            "read_project_history",
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    internal_bearer = tmp_path / "internal-bearer-token"
    internal_bearer.write_text("compose-internal-bearer\n", encoding="utf-8")
    mapping = tmp_path / "provisioned-mapping.json"
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
    env = os.environ.copy()
    env.update(
        {
            "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
            "GATEWAY_BACKEND_SESSION_FILE": str(session),
            "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
            "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
            "GATEWAY_REPOSITORY_SERVICE_IMAGE": os.environ.get(
                "GATEWAY_REPOSITORY_SERVICE_IMAGE",
                "gateway-repository-service:local",
            ),
            "COMPOSE_PROJECT_NAME": compose_project_name(
                tmp_path,
                default_prefix="gateway-history-5e",
            ),
        }
    )
    return env


def _auth_headers(
    *,
    token: str = ARCHIVER_TOKEN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _approve_submission(
    client: httpx.Client,
    submission_id: str,
    *,
    idempotency_key: str,
) -> None:
    response = client.post(
        f"/v1/submissions/{submission_id}/review-events",
        headers=_auth_headers(idempotency_key=idempotency_key),
        json={"expected_review_version": 0, "action": "APPROVE"},
    )
    assert response.status_code == 201, response.text


def _candidate_for_submission(candidates_body: dict[str, Any], submission_id: str) -> dict[str, Any]:
    for candidate in candidates_body["candidates"]:
        if candidate["submission_id"] == submission_id:
            return cast(dict[str, Any], candidate)
    raise AssertionError(f"candidate not found for submission {submission_id}")


def _history_node_by_submission(nodes: list[dict[str, Any]], submission_id: str) -> dict[str, Any]:
    for node in nodes:
        if node["ref_kind"] == "submission" and node["ref_id"] == submission_id:
            return node
    raise AssertionError(f"history node not found for submission {submission_id}")


def _collect_history_nodes(client: httpx.Client) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get("/v1/history", params=params)
        assert response.status_code == 200, response.text
        body = cast(dict[str, Any], response.json())
        collected.extend(body["nodes"])
        cursor = body.get("next_cursor")
        if cursor is None:
            return collected


def _standard_provider_from_repository(
    env: dict[str, str],
    repository_id: str,
    commit_id: str,
) -> FakeRepositoryTableAccessProvider:
    raw_rows = read_repository_table_rows(env, repository_id, commit_id, "t")
    if not raw_rows:
        return history_compare_provider(
            commit_id=commit_id,
            row_count=0,
            declared_rows={},
            catalog_without=("t",),
        )
    rows = tuple((int(cast(int, row[0])),) for row in raw_rows)
    return history_compare_provider(
        commit_id=commit_id,
        row_count=len(rows),
        declared_rows={"t": rows},
    )


def _assert_remote_matches_oracle(
    env: dict[str, str],
    *,
    operation_id: str,
    remote_digest: str,
    before_commit: str,
    current_commit: str,
    repository_id: str,
    artifact_store: InMemoryArtifactStore,
) -> None:
    job_state = read_history_compare_materialize_job_state(env, operation_id)
    assert "table_policies" not in job_state
    before_provider = _standard_provider_from_repository(env, repository_id, before_commit)
    current_provider = _standard_provider_from_repository(env, repository_id, current_commit)
    oracle_digest = oracle_comparison_digest(
        before_provider=before_provider,
        current_provider=current_provider,
        before_commit=before_commit,
        current_commit=current_commit,
        artifact_store=artifact_store,
    )
    assert remote_digest == oracle_digest


def test_compose_history_compare_journey_zero_write_restart(
    tmp_path: Path,
) -> None:
    env = _compose_env(tmp_path)
    require_docker(compose_project_name=env["COMPOSE_PROJECT_NAME"])
    provenance: dict[str, dict[str, str]] = {}
    compare_three_operation_id: str | None = None
    zero_table_comparison_digest: str | None = None
    zero_table_bundle_digest: str | None = None

    try:
        repository_id, initial_commit_id = start_three_container_stack(
            env,
            tmp_path,
            import_baseline=False,
        )
        assert_running_backend_worker_images_match_build(env)
        provenance = capture_running_container_provenance(env)
        artifact_store = InMemoryArtifactStore()
        journey_a = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="history-a",
            token=SESSION_TOKEN,
            upload_files_factory=lambda version: modified_table_upload_files(
                insert_value=2,
                expected_version=version,
            ),
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_a["submission_id"]),
                idempotency_key="history-review-a",
            )
        main_after_a = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)

        journey_b = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="history-b",
            token=ACTOR2_TOKEN,
            upload_files_factory=lambda version: modified_table_upload_files(
                insert_value=3,
                expected_version=version,
            ),
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_b["submission_id"]),
                idempotency_key="history-review-b",
            )
        main_after_both = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)
        assert main_after_a != initial_commit_id
        assert main_after_both != main_after_a

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as archiver:
            candidates = archiver.get("/v1/archive-candidates")
            assert candidates.status_code == 200, candidates.text
            candidates_body = cast(dict[str, Any], candidates.json())
            selected = _candidate_for_submission(
                candidates_body,
                str(journey_a["submission_id"]),
            )
            sibling = _candidate_for_submission(
                candidates_body,
                str(journey_b["submission_id"]),
            )

            preview = archiver.post("/v1/archive-plan-preview", json={"selected": selected})
            assert preview.status_code == 200, preview.text
            preview_body = cast(dict[str, Any], preview.json())
            anomaly = preview_body["anomalies"][0]

            confirm = archiver.post(
                "/v1/archive-confirmations",
                headers=_auth_headers(idempotency_key="history-archive-confirm"),
                json={
                    "expected_baseline_node_id": preview_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": preview_body["head"]["baseline_head_version"],
                    "selected": selected,
                    "candidate_set_digest": preview_body["candidate_set_digest"],
                    "subject_digest": preview_body["selection_subject_digest"],
                    "expected_sequence": 0,
                    "action": "CONFIRM",
                    "reason": "confirm archive selection",
                },
            )
            assert confirm.status_code == 201, confirm.text
            resolve = archiver.post(
                "/v1/archive-anomaly-resolutions",
                headers=_auth_headers(idempotency_key="history-archive-resolve"),
                json={
                    "expected_baseline_node_id": preview_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": preview_body["head"]["baseline_head_version"],
                    "selected": selected,
                    "candidate_set_digest": preview_body["candidate_set_digest"],
                    "subject_digest": anomaly["subject_digest"],
                    "expected_sequence": 0,
                    "action": "ACKNOWLEDGE_EXCLUSION",
                    "reason": "acknowledge sibling exclusion",
                    "issue_code": "APPROVED_SIBLING_EXCLUDED",
                    "sibling_submission_id": sibling["submission_id"],
                    "sibling_candidate_digest": sibling["expected_candidate_digest"],
                },
            )
            assert resolve.status_code == 201, resolve.text

            ready_preview = archiver.post(
                "/v1/archive-plan-preview",
                json={"selected": selected},
            )
            assert ready_preview.status_code == 200, ready_preview.text
            ready_body = cast(dict[str, Any], ready_preview.json())

            start = archiver.post(
                "/v1/archives",
                headers=_auth_headers(idempotency_key="history-archive-start"),
                json={
                    "expected_baseline_node_id": ready_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": ready_body["head"]["baseline_head_version"],
                    "candidate_set_digest": ready_body["candidate_set_digest"],
                    "selected": selected,
                    "confirmation_refs": [
                        {
                            "subject_digest": ready_body["selection_subject_digest"],
                            "sequence": confirm.json()["sequence"],
                        }
                    ],
                    "anomaly_resolution_refs": [
                        {
                            "subject_digest": anomaly["subject_digest"],
                            "sequence": resolve.json()["sequence"],
                        }
                    ],
                },
            )
            assert start.status_code == 201, start.text
            post_head = cast(dict[str, Any], archiver.get("/v1/archive-candidates").json())["head"]
            archived_head_node_id = str(post_head["business_baseline_node_id"])
            archived_head_version = int(post_head["baseline_head_version"])

        journey_c = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=main_after_a,
            journey_key_prefix="history-c",
            token=SESSION_TOKEN,
            expected_baseline_node_id=archived_head_node_id,
            expected_baseline_head_version=archived_head_version,
            upload_files_factory=lambda version: modified_table_upload_files(
                insert_value=4,
                expected_version=version,
            ),
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_c["submission_id"]),
                idempotency_key="history-review-c",
            )
        main_after_c = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ACTOR2_TOKEN),
            timeout=120.0,
        ) as actor_without_history:
            denied = actor_without_history.get("/v1/history")
            assert denied.status_code == 403
            assert denied.json()["code"] == "SCOPE_FORBIDDEN"

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=CROSS_SCOPE_TOKEN),
            timeout=120.0,
        ) as cross_scope:
            denied_scope = cross_scope.get("/v1/history")
            assert denied_scope.status_code == 403
            assert denied_scope.json()["code"] == "SCOPE_FORBIDDEN"

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
            timeout=120.0,
        ) as history_reader:
            all_nodes = _collect_history_nodes(history_reader)
            assert len(all_nodes) >= 4

            initial_nodes = [
                node
                for node in all_nodes
                if node["ref_kind"] == "baseline_node" and node.get("baseline_kind") == "INITIAL"
            ]
            assert len(initial_nodes) == 1
            assert initial_nodes[0]["ref_id"] == BASELINE_NODE_ID
            assert initial_nodes[0]["commit_id"] == initial_commit_id

            node_a = _history_node_by_submission(all_nodes, str(journey_a["submission_id"]))
            node_b = _history_node_by_submission(all_nodes, str(journey_b["submission_id"]))
            node_c = _history_node_by_submission(all_nodes, str(journey_c["submission_id"]))
            assert node_a["archive_disposition"] == "ARCHIVED_BASELINE"
            assert node_b["archive_disposition"] == "CLOSED_NOT_ARCHIVED"
            assert node_a["promoted_baseline_node_id"] is not None
            assert node_a["commit_id"] == main_after_a
            assert node_b["commit_id"] == main_after_both
            assert node_c["commit_id"] == main_after_c

            first_page = history_reader.get("/v1/history", params={"limit": 1})
            assert first_page.status_code == 200, first_page.text
            first_body = cast(dict[str, Any], first_page.json())
            history_head_before_restart = cast(dict[str, Any], first_body["head"])
            first_node_before_restart = cast(dict[str, Any], first_body["nodes"][0])
            assert history_head_before_restart["version"] == archived_head_version
            assert history_head_before_restart["node_id"] == archived_head_node_id

            business_before = capture_business_table_state_in_compose(env)
            commits_before = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            manifests_before = capture_r4_manifest_artifact_ids(env)
            assert len(manifests_before) > 0

            compare_two = accept_history_compare(
                history_reader,
                nodes=[
                    {"ref_kind": "submission", "ref_id": str(journey_a["submission_id"])},
                    {"ref_kind": "submission", "ref_id": str(journey_b["submission_id"])},
                ],
                idempotency_key="history-compare-ab",
                token=HISTORY_READER_TOKEN,
            )
            compare_two_result = history_reader.get(
                f"/v1/history-compares/{compare_two['operation_id']}",
            )
            assert compare_two_result.status_code == 200, compare_two_result.text
            compare_two_body = cast(dict[str, Any], compare_two_result.json())
            assert compare_two_body["status"] == "SUCCEEDED"
            assert compare_two_body["result"] is not None
            pair_ab = compare_two_body["result"]["pairs"][0]
            assert pair_ab["before_commit"] == main_after_a
            assert pair_ab["current_commit"] == main_after_both
            assert int(pair_ab["record_count"]) > 0
            _assert_remote_matches_oracle(
                env,
                operation_id=str(compare_two["operation_id"]),
                remote_digest=str(pair_ab["comparison_digest"]),
                before_commit=main_after_a,
                current_commit=main_after_both,
                repository_id=repository_id,
                artifact_store=artifact_store,
            )

            compare_three = accept_history_compare(
                history_reader,
                nodes=[
                    {"ref_kind": "baseline_node", "ref_id": BASELINE_NODE_ID},
                    {"ref_kind": "submission", "ref_id": str(journey_a["submission_id"])},
                    {"ref_kind": "submission", "ref_id": str(journey_c["submission_id"])},
                ],
                idempotency_key="history-compare-iac",
                token=HISTORY_READER_TOKEN,
            )
            compare_three_operation_id = str(compare_three["operation_id"])
            compare_three_result = history_reader.get(
                f"/v1/history-compares/{compare_three_operation_id}",
            )
            assert compare_three_result.status_code == 200, compare_three_result.text
            compare_three_body = cast(dict[str, Any], compare_three_result.json())
            assert compare_three_body["status"] == "SUCCEEDED"
            assert compare_three_body["result"] is not None
            assert len(compare_three_body["result"]["pairs"]) == 2
            pair_initial_a = compare_three_body["result"]["pairs"][0]
            assert pair_initial_a["before_commit"] == initial_commit_id
            assert pair_initial_a["current_commit"] == main_after_a
            assert int(pair_initial_a["record_count"]) == 1
            zero_table_comparison_digest = str(pair_initial_a["comparison_digest"])
            bundle_digest = str(compare_three_body["result"]["bundle_digest"])
            zero_table_bundle_digest = bundle_digest
            three_pair_digests = [
                str(pair["comparison_digest"]) for pair in compare_three_body["result"]["pairs"]
            ]

            bundle_three = history_reader.get(
                f"/v1/history-compares/{compare_three_operation_id}/bundle",
            )
            assert bundle_three.status_code == 200, bundle_three.text
            assert bundle_three.headers.get("content-disposition", "").startswith("attachment")

            compare_ac = accept_history_compare(
                history_reader,
                nodes=[
                    {"ref_kind": "submission", "ref_id": str(journey_a["submission_id"])},
                    {"ref_kind": "submission", "ref_id": str(journey_c["submission_id"])},
                ],
                idempotency_key="history-compare-ac",
                token=HISTORY_READER_TOKEN,
            )
            compare_ac_result = history_reader.get(
                f"/v1/history-compares/{compare_ac['operation_id']}",
            )
            assert compare_ac_result.status_code == 200, compare_ac_result.text
            compare_ac_body = cast(dict[str, Any], compare_ac_result.json())
            assert compare_ac_body["status"] == "SUCCEEDED"
            assert int(compare_ac_body["result"]["pairs"][0]["record_count"]) > 0

            missing_submission_ref_compare = history_reader.post(
                "/v1/history-compares",
                headers=compose_auth_headers(
                    token=HISTORY_READER_TOKEN,
                    idempotency_key="history-compare-missing-ref",
                ),
                json={
                    "nodes": [
                        {"ref_kind": "submission", "ref_id": "missing-submission-ref"},
                        {"ref_kind": "submission", "ref_id": str(journey_b["submission_id"])},
                    ]
                },
            )
            assert missing_submission_ref_compare.status_code == 404
            assert missing_submission_ref_compare.json()["code"] == "RESOURCE_NOT_FOUND"

            business_after = capture_business_table_state_in_compose(env)
            commits_after = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            manifests_after = capture_r4_manifest_artifact_ids(env)
            assert business_before == business_after
            assert commits_before == commits_after
            assert manifests_before == manifests_after

            operation_read = history_reader.get(f"/v1/operations/{compare_three_operation_id}")
            assert operation_read.status_code == 200, operation_read.text
            assert operation_read.json()["job_kind"] == "backend-vnext/history-compare"

            restart = run_compose(env, "restart", "backend", "worker")
            if restart.returncode != 0:
                pytest.fail(f"compose restart failed: {restart.stderr}\n{restart.stdout}")
            wait_http_ok(f"{BACKEND_URL}/readyz")

            restarted_history = history_reader.get("/v1/history", params={"limit": 1})
            assert restarted_history.status_code == 200, restarted_history.text
            restarted_history_body = cast(dict[str, Any], restarted_history.json())
            restarted_head = cast(dict[str, Any], restarted_history_body["head"])
            restarted_first_node = cast(dict[str, Any], restarted_history_body["nodes"][0])
            assert restarted_head["version"] == history_head_before_restart["version"]
            assert restarted_head["node_id"] == history_head_before_restart["node_id"]
            assert restarted_first_node["commit_id"] == first_node_before_restart["commit_id"]

            business_after_restart = capture_business_table_state_in_compose(env)
            commits_after_restart = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            manifests_after_restart = capture_r4_manifest_artifact_ids(env)
            assert business_before == business_after_restart
            assert commits_before == commits_after_restart
            assert manifests_before == manifests_after_restart

            restarted_compare = history_reader.get(
                f"/v1/history-compares/{compare_three_operation_id}",
            )
            assert restarted_compare.status_code == 200, restarted_compare.text
            restarted_body = cast(dict[str, Any], restarted_compare.json())
            assert restarted_body["status"] == "SUCCEEDED"
            assert restarted_body["result"]["bundle_digest"] == bundle_digest
            restarted_pair_digests = [
                str(pair["comparison_digest"]) for pair in restarted_body["result"]["pairs"]
            ]
            assert restarted_pair_digests == three_pair_digests
            restarted_bundle = history_reader.get(
                f"/v1/history-compares/{compare_three_operation_id}/bundle",
            )
            assert restarted_bundle.status_code == 200, restarted_bundle.text
            restarted_operation = history_reader.get(f"/v1/operations/{compare_three_operation_id}")
            assert restarted_operation.status_code == 200, restarted_operation.text

            replay = history_reader.post(
                "/v1/history-compares",
                headers=compose_auth_headers(
                    token=HISTORY_READER_TOKEN,
                    idempotency_key="history-compare-iac",
                ),
                json={
                    "nodes": [
                        {"ref_kind": "baseline_node", "ref_id": BASELINE_NODE_ID},
                        {"ref_kind": "submission", "ref_id": str(journey_a["submission_id"])},
                        {"ref_kind": "submission", "ref_id": str(journey_c["submission_id"])},
                    ],
                },
            )
            assert replay.status_code == 200, replay.text
            replay_body = cast(dict[str, Any], replay.json())
            assert replay_body["replayed"] is True
            assert replay_body["operation_id"] == compare_three_operation_id

            business_after_replay = capture_business_table_state_in_compose(env)
            commits_after_replay = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            manifests_after_replay = capture_r4_manifest_artifact_ids(env)
            assert business_before == business_after_replay
            assert commits_before == commits_after_replay
            assert manifests_before == manifests_after_replay

        print(
            "zero_table_pair_digest="
            f"{zero_table_comparison_digest} bundle_digest={zero_table_bundle_digest}"
        )

    finally:
        if provenance:
            provenance_path = persist_compose_gate_provenance(env, provenance)
            print(f"compose gate provenance written to {provenance_path}")
        primary_exc = sys.exc_info()
        try:
            cleanup_compose_project_artifacts(env)
        except Exception as cleanup_exc:
            if primary_exc[0] is not None:
                _LOGGER.error("compose cleanup failed during teardown: %s", cleanup_exc)
            else:
                raise
