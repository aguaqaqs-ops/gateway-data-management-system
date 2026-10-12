"""Ordered history compare compose journey with policy checkpoint and oracle."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    accept_history_compare,
    assert_running_backend_worker_images_match_build,
    canonical_rules_ordered_upload_files,
    capture_business_table_state_in_compose,
    capture_r4_manifest_artifact_ids,
    capture_running_container_provenance,
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_project_name,
    list_repository_commit_ids,
    normalize_running_images,
    oracle_history_compare_digest_from_materialize_checkpoint,
    ordered_compare_facts_from_materialize_checkpoint,
    ordered_syx_sized_upload_files,
    persist_compose_gate_provenance,
    read_history_compare_materialize_job_state,
    read_repository_catalog,
    require_docker,
    resolve_main_commit_id,
    run_accept_to_submission_read_journey,
    start_three_container_stack,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ARCHIVER_TOKEN = "compose-archiver-token"
ACTOR2_TOKEN = "compose-actor-2-token"
HISTORY_READER_TOKEN = "compose-history-reader-token"


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
                        "business_baseline_node_id": "pending-node-seed",
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
        "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="ordered-compare"),
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
        "GATEWAY_BACKEND_SESSION_FILE": str(session),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
        "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(bearer),
    }


def _approve_submission(client: httpx.Client, submission_id: str, *, idempotency_key: str) -> None:
    response = client.post(
        f"/v1/submissions/{submission_id}/review-events",
        headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key=idempotency_key),
        json={"expected_review_version": 0, "action": "APPROVE"},
    )
    assert response.status_code == 201, response.text


def _archive_submission(client: httpx.Client, submission_id: str) -> dict[str, Any]:
    candidates = client.get("/v1/archive-candidates")
    assert candidates.status_code == 200, candidates.text
    selected = next(
        item
        for item in candidates.json()["candidates"]
        if item["submission_id"] == submission_id
    )
    preview = client.post("/v1/archive-plan-preview", json={"selected": selected})
    assert preview.status_code == 200, preview.text
    preview_body = cast(dict[str, Any], preview.json())
    assert preview_body["can_start"] is False
    head = cast(dict[str, Any], preview_body["head"])
    confirmation = client.post(
        "/v1/archive-confirmations",
        headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="ordered-archive-confirm"),
        json={
            "expected_baseline_node_id": head["business_baseline_node_id"],
            "expected_baseline_head_version": head["baseline_head_version"],
            "selected": selected,
            "candidate_set_digest": preview_body["candidate_set_digest"],
            "subject_digest": preview_body["selection_subject_digest"],
            "expected_sequence": 0,
            "action": "CONFIRM",
            "reason": "archive ordered baseline",
        },
    )
    assert confirmation.status_code == 201, confirmation.text
    ready = client.post("/v1/archive-plan-preview", json={"selected": selected})
    assert ready.status_code == 200, ready.text
    ready_body = cast(dict[str, Any], ready.json())
    assert ready_body["can_start"] is True
    assert ready_body["audit_validity"] is True
    ready_head = cast(dict[str, Any], ready_body["head"])
    started = client.post(
        "/v1/archives",
        headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="ordered-archive-start"),
        json={
            "expected_baseline_node_id": ready_head["business_baseline_node_id"],
            "expected_baseline_head_version": ready_head["baseline_head_version"],
            "candidate_set_digest": ready_body["candidate_set_digest"],
            "selected": selected,
            "confirmation_refs": [
                {
                    "subject_digest": ready_body["selection_subject_digest"],
                    "sequence": confirmation.json()["sequence"],
                }
            ],
        },
    )
    assert started.status_code == 201, started.text
    return cast(dict[str, Any], started.json())


def _assert_remote_matches_oracle(
    env: dict[str, str],
    *,
    operation_id: str,
    remote_digest: str,
    before_commit: str,
    current_commit: str,
) -> None:
    job_state = read_history_compare_materialize_job_state(env, operation_id)
    assert "table_policies" not in job_state
    oracle_digest = oracle_history_compare_digest_from_materialize_checkpoint(
        env,
        operation_id,
        before_commit=before_commit,
        current_commit=current_commit,
    )
    assert remote_digest == oracle_digest


def test_ordered_history_compare_compose_journey(tmp_path: Path) -> None:
    env = _compose_env(tmp_path)
    require_docker(compose_project_name=env["COMPOSE_PROJECT_NAME"])
    provenance: dict[str, dict[str, str]] = {}
    try:
        repository_id, initial_commit_id = start_three_container_stack(
            env,
            tmp_path,
        )
        assert_running_backend_worker_images_match_build(env)
        provenance = capture_running_container_provenance(env)

        journey_a = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="ordered-a",
            token=SESSION_TOKEN,
            upload_files_factory=lambda version: ordered_syx_sized_upload_files(
                t_rows=(1,),
                before_ordered_rows=(),
                after_ordered_rows=((5, 1, "a"), (7, 2, "b")),
                expected_version=version,
            ),
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_a["submission_id"]),
                idempotency_key="ordered-review-a",
            )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as archiver:
            archive_a = _archive_submission(archiver, str(journey_a["submission_id"]))
        main_after_a = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)
        assert main_after_a == archive_a["baseline_commit_id"]
        baseline_catalog = read_repository_catalog(
            env,
            repository_id=repository_id,
            commit_id=main_after_a,
        )
        assert baseline_catalog["tables"]
        assert "b1_n1_iec104_syx_list" in {
            table["name"] for table in baseline_catalog["tables"]
        }

        rule_preview = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=main_after_a,
            journey_key_prefix="ordered-rule-preview",
            token=ACTOR2_TOKEN,
            expected_baseline_node_id=str(archive_a["baseline_node_id"]),
            expected_baseline_head_version=int(archive_a["baseline_head_version"]),
            preview_only=True,
            upload_files_factory=lambda version: canonical_rules_ordered_upload_files(
                com_cfg_no_before=10,
                com_cfg_no_after=99,
                ordered_rows_before=((5, 1, "a"), (7, 2, "b")),
                ordered_rows_after=((2, 1, "c"), (5, 2, "d")),
                expected_version=version,
            ),
        )
        rule_preview_summaries = cast(list[dict[str, Any]], rule_preview["preview_summaries"])
        assert rule_preview_summaries
        for summary in rule_preview_summaries:
            assert int(summary["table_count"]) > 0
            assert int(summary["degraded_table_count"]) == 0

        journey_b = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=main_after_a,
            journey_key_prefix="ordered-b",
            token=ACTOR2_TOKEN,
            expected_baseline_node_id=str(archive_a["baseline_node_id"]),
            expected_baseline_head_version=int(archive_a["baseline_head_version"]),
            upload_files_factory=lambda version: ordered_syx_sized_upload_files(
                t_rows=(1,),
                before_ordered_rows=((5, 1, "a"), (7, 2, "b")),
                after_ordered_rows=((2, 1, "c"), (5, 2, "d")),
                expected_version=version,
            ),
        )
        preview_summaries = cast(list[dict[str, Any]], journey_b["preview_summaries"])
        assert preview_summaries
        for summary in preview_summaries:
            assert int(summary["table_count"]) > 0
            assert int(summary["degraded_table_count"]) == 0
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_b["submission_id"]),
                idempotency_key="ordered-review-b",
            )
        main_after_both = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)
        assert main_after_a != initial_commit_id
        assert main_after_both != main_after_a

        business_before = capture_business_table_state_in_compose(env)
        commits_before = list_repository_commit_ids(
            env,
            repository_id,
            bearer_token=BEARER_TOKEN,
        )
        manifests_before = capture_r4_manifest_artifact_ids(env)

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
            timeout=120.0,
        ) as history_reader:
            compare = accept_history_compare(
                history_reader,
                nodes=[
                    {"ref_kind": "submission", "ref_id": str(journey_a["submission_id"])},
                    {"ref_kind": "submission", "ref_id": str(journey_b["submission_id"])},
                ],
                idempotency_key=f"ordered-history-compare-ab-{tmp_path.name}",
                token=HISTORY_READER_TOKEN,
            )
            operation_id = str(compare["operation_id"])
            compare_result = history_reader.get(f"/v1/history-compares/{operation_id}")
            assert compare_result.status_code == 200, compare_result.text
            compare_body = cast(dict[str, Any], compare_result.json())
            assert compare_body["status"] == "SUCCEEDED"
            assert compare_body["result"] is not None
            pair = compare_body["result"]["pairs"][0]
            assert pair["before_commit"] == main_after_a
            assert pair["current_commit"] == main_after_both
            assert int(pair["record_count"]) > 0
            _assert_remote_matches_oracle(
                env,
                operation_id=operation_id,
                remote_digest=str(pair["comparison_digest"]),
                before_commit=main_after_a,
                current_commit=main_after_both,
            )
            facts = ordered_compare_facts_from_materialize_checkpoint(
                env,
                operation_id,
                before_commit=main_after_a,
                current_commit=main_after_both,
            )
            tables = cast(list[dict[str, object]], facts["tables"])
            syx = next(
                table
                for table in tables
                if table["table_name"] == "b1_n1_iec104_syx_list"
            )
            assert syx["status"] != "DEGRADED"
            ordered_records = cast(list[dict[str, object]], syx["ordered_records"])
            assert ordered_records
            kinds = Counter(str(record["record_kind"]) for record in ordered_records)
            assert kinds["ORDERED_ROW_ADDED"] >= 1
            assert kinds["ORDERED_ROW_DELETED"] >= 1
            assert kinds["ORDERED_ROW_MODIFIED"] >= 1

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
    finally:
        if provenance:
            normalized = normalize_running_images(provenance, env["COMPOSE_PROJECT_NAME"])
            provenance_path = persist_compose_gate_provenance(env, provenance)
            print(
                "ordered_compare_gate_running_images="
                f"{json.dumps(normalized, indent=2)}"
            )
            print(f"compose gate provenance written to {provenance_path}")
        cleanup_compose_project_artifacts(env)
