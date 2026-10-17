"""HTTP contract tests for Archive routes."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from gateway_backend.application.archive.contracts import (
    ARCHIVE_MAX_AUDIT_REFS,
    ARCHIVE_MAX_REQUEST_BYTES,
    validate_archive_confirmation_reason,
    validate_utf8_id,
    validate_utf8_reason,
)
from gateway_backend.application.archive.errors import ArchiveRequestValidation
from gateway_backend.application.archive.queries import PERMISSION_ARCHIVE_SUBMISSION
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from gateway_backend.http.dependencies import (
    ArchiveRequestBodyLimitMiddleware,
    ClosableAdmissionGate,
)
from gateway_backend.http.schemas.archive import (
    AppendArchiveConfirmationRequest,
    AppendArchiveAnomalyResolutionRequest,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.archive_fixtures import (
    append_selection_confirmation,
    assert_archive_durable_state_unchanged,
    seed_approved_archive_candidate,
    seed_approved_dual_sibling_archive,
    seed_bulk_approved_archive_candidates,
)
from tests.support.http_workspace_harness import (
    TEST_BEARER,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_submit_transactions import BASELINE_HEAD, _upsert_provisioned_mapping_row

pytestmark = pytest.mark.unit

DENIED_ARCHIVER_BEARER = "denied-archiver-session-token"
OTHER_SCOPE_BEARER = "other-scope-session-token"

ARCHIVE_HTTP_ID_BOUNDARY_CASES = (
    ("ascii_255", "a" * 255, 201),
    ("ascii_256", "a" * 256, 422),
    ("chinese_85", "中" * 85, 201),
    ("chinese_86", "中" * 86, 422),
    ("four_byte_255", "😀" * 63 + "a" * 3, 201),
    ("four_byte_256", "😀" * 64, 422),
)

ARCHIVE_HTTP_REASON_BOUNDARY_CASES = (
    ("ascii_4096", "a" * 4096, 201),
    ("ascii_4097", "a" * 4097, 422),
    ("chinese_1365_plus_one_ascii", "中" * 1365 + "a", 201),
    ("chinese_1365_plus_two_ascii", "中" * 1365 + "aa", 422),
    ("four_byte_1024", "😀" * 1024, 201),
    ("four_byte_1025", "😀" * 1025, 422),
)


def _archive_permissions() -> frozenset[str]:
    return frozenset(
        {
            "workspace_read",
            "upload_submit_workspace",
            "preview_workspace",
            "review_submission",
            PERMISSION_ARCHIVE_SUBMISSION,
        }
    )


def _archive_env(
    tmp_path: Path,
    *,
    extra_sessions: dict[str, Any] | None = None,
    admission_gate: ClosableAdmissionGate | None = None,
) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=_archive_permissions()),
        extra_sessions=extra_sessions,
        admission_gate=admission_gate,
    )


def _auth_headers(
    env: WorkspaceHttpTestEnvironment,
    *,
    bearer: str = TEST_BEARER,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {bearer}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _confirmation_body(
    seed: Any,
    *,
    reason: str | None = "confirm archive selection",
) -> dict[str, object]:
    return {
        "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
        "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
        "selected": {
            "submission_id": seed.selected_ref.submission_id,
            "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
        },
        "candidate_set_digest": seed.candidate_set_digest,
        "subject_digest": seed.selection_subject_digest,
        "expected_sequence": 0,
        "action": "CONFIRM",
        "reason": reason,
    }


def _start_body(
    seed: Any,
    *,
    confirmation_sequence: int,
    anomaly_resolution_sequences: tuple[tuple[str, int], ...] = (),
) -> dict[str, object]:
    return {
        "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
        "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
        "candidate_set_digest": seed.candidate_set_digest,
        "selected": {
            "submission_id": seed.selected_ref.submission_id,
            "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
        },
        "confirmation_refs": [
            {
                "subject_digest": seed.selection_subject_digest,
                "sequence": confirmation_sequence,
            }
        ],
        "anomaly_resolution_refs": [
            {"subject_digest": subject_digest, "sequence": sequence}
            for subject_digest, sequence in anomaly_resolution_sequences
        ],
    }


def _archive_table_counts(db_path: Path) -> tuple[int, int, int]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        plan_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        result_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_result_records"
        ).fetchone()[0]
        confirmation_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    return int(plan_count), int(result_count), int(confirmation_count)


@pytest.fixture
def archive_env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return _archive_env(tmp_path)


def test_list_archive_candidates_returns_approved_submission(archive_env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    response = archive_env.client.get(
        "/v1/archive-candidates",
        headers=_auth_headers(archive_env),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["head"]["baseline_head_version"] == BASELINE_HEAD.baseline_head_version
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["submission_id"] == seed.submission_id
    assert "repository_id" not in body


def test_preview_archive_plan_is_read_only(archive_env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    for _ in range(2):
        response = archive_env.client.post(
            "/v1/archive-plan-preview",
            headers=_auth_headers(archive_env),
            json={
                "selected": {
                    "submission_id": seed.selected_ref.submission_id,
                    "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
                }
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["audit_validity"] is False
        assert body["can_start"] is False
        assert "plan_id" not in body
    assert_archive_durable_state_unchanged(
        archive_env.db_path,
        repository_id="repo-1",
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
    )


def test_archive_confirmation_and_start_journey(archive_env: WorkspaceHttpTestEnvironment) -> None:
    dual = seed_approved_dual_sibling_archive(archive_env.db_path)
    seed = dual.primary
    confirm = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="confirm-http-1"),
        json=_confirmation_body(seed),
    )
    assert confirm.status_code == 201
    resolve = archive_env.client.post(
        "/v1/archive-anomaly-resolutions",
        headers=_auth_headers(archive_env, idempotency_key="resolve-http-1"),
        json={
            **_confirmation_body(seed, reason="acknowledge sibling exclusion"),
            "action": "ACKNOWLEDGE_EXCLUSION",
            "issue_code": "APPROVED_SIBLING_EXCLUDED",
            "sibling_submission_id": dual.sibling_submission_id,
            "sibling_candidate_digest": dual.sibling_candidate_digest,
            "subject_digest": dual.anomaly_subject_digest,
        },
    )
    assert resolve.status_code == 201
    start = archive_env.client.post(
        "/v1/archives",
        headers=_auth_headers(archive_env, idempotency_key="start-http-1"),
        json=_start_body(
            seed,
            confirmation_sequence=confirm.json()["sequence"],
            anomaly_resolution_sequences=((dual.anomaly_subject_digest, resolve.json()["sequence"]),),
        ),
    )
    assert start.status_code == 201
    started = start.json()
    assert started["selected_submission_id"] == seed.submission_id
    assert "operation_id" not in started
    result = archive_env.client.get(
        f"/v1/archives/{started['archive_result_id']}",
        headers=_auth_headers(archive_env),
    )
    assert result.status_code == 200
    assert result.json()["archive_result_id"] == started["archive_result_id"]
    audit = archive_env.client.get(
        "/v1/archive-audit-events",
        headers=_auth_headers(archive_env),
        params={
            "subject_kind": "CONFIRM_SELECTION",
            "subject_digest": seed.selection_subject_digest,
            "after_sequence": 0,
            "limit": 100,
        },
    )
    assert audit.status_code == 200
    assert len(audit.json()["events"]) == 1


def test_archive_confirmation_replays_with_200(archive_env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    first = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="confirm-replay"),
        json=_confirmation_body(seed),
    )
    second = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="confirm-replay"),
        json=_confirmation_body(seed),
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()


def test_archive_mutations_require_archive_permission(tmp_path: Path) -> None:
    env = _archive_env(
        tmp_path,
        extra_sessions={
            DENIED_ARCHIVER_BEARER: make_identity(
                actor_id="archiver-denied",
                permissions=frozenset({"workspace_read", "review_submission"}),
            )
        },
    )
    seed = seed_approved_archive_candidate(env.db_path)
    response = env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(env, bearer=DENIED_ARCHIVER_BEARER, idempotency_key="denied"),
        json=_confirmation_body(seed),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_archive_read_without_permission_hides_candidates(tmp_path: Path) -> None:
    env = _archive_env(
        tmp_path,
        extra_sessions={
            DENIED_ARCHIVER_BEARER: make_identity(
                actor_id="archiver-denied",
                permissions=frozenset({"workspace_read"}),
            )
        },
    )
    seed_approved_archive_candidate(env.db_path)
    response = env.client.get(
        "/v1/archive-candidates",
        headers=_auth_headers(env, bearer=DENIED_ARCHIVER_BEARER),
    )
    assert response.status_code == 403


def test_archive_start_returns_429_when_admission_closed(tmp_path: Path) -> None:
    gate = ClosableAdmissionGate(limit=1)
    env = _archive_env(tmp_path, admission_gate=gate)
    seed = seed_approved_archive_candidate(env.db_path)
    confirmation_sequence = append_selection_confirmation(seed)
    gate.close()
    response = env.client.post(
        "/v1/archives",
        headers=_auth_headers(env, idempotency_key="admission-closed"),
        json=_start_body(seed, confirmation_sequence=confirmation_sequence),
    )
    assert response.status_code == 429
    assert response.json()["code"] == "ADMISSION_LIMIT_REACHED"


def test_archive_get_result_hides_cross_scope_result_same_database(tmp_path: Path) -> None:
    env = _archive_env(
        tmp_path,
        extra_sessions={
            OTHER_SCOPE_BEARER: make_identity(
                actor_id="actor-other-scope",
                device_key="device-other",
                project_id="project-1",
                permissions=_archive_permissions(),
            )
        },
    )
    seed = seed_approved_archive_candidate(env.db_path)
    _upsert_provisioned_mapping_row(
        env.db_path,
        device_key="device-other",
        project_id="project-1",
        repository_id="repo-other",
        baseline_head=BASELINE_HEAD,
    )
    confirmation_sequence = append_selection_confirmation(seed)
    started = archive_env_start(env, seed, confirmation_sequence)
    response = env.client.get(
        f"/v1/archives/{started['archive_result_id']}",
        headers=_auth_headers(env, bearer=OTHER_SCOPE_BEARER),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_archive_get_result_allows_same_scope_different_actor(tmp_path: Path) -> None:
    other_actor_bearer = "same-scope-other-actor"
    env = _archive_env(
        tmp_path,
        extra_sessions={
            other_actor_bearer: make_identity(
                actor_id="actor-2",
                device_key="device-1",
                project_id="project-1",
                permissions=_archive_permissions(),
            )
        },
    )
    seed = seed_approved_archive_candidate(env.db_path)
    confirmation_sequence = append_selection_confirmation(seed)
    started = archive_env_start(env, seed, confirmation_sequence)
    response = env.client.get(
        f"/v1/archives/{started['archive_result_id']}",
        headers=_auth_headers(env, bearer=other_actor_bearer),
    )
    assert response.status_code == 200


def archive_env_start(
    env: WorkspaceHttpTestEnvironment,
    seed: Any,
    confirmation_sequence: int,
) -> dict[str, object]:
    response = env.client.post(
        "/v1/archives",
        headers=_auth_headers(env, idempotency_key=f"start-{confirmation_sequence}"),
        json=_start_body(seed, confirmation_sequence=confirmation_sequence),
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


@pytest.mark.parametrize(
    ("case_id", "id_value", "should_accept"),
    [(case[0], case[1], case[2] == 201) for case in ARCHIVE_HTTP_ID_BOUNDARY_CASES],
    ids=[case[0] for case in ARCHIVE_HTTP_ID_BOUNDARY_CASES],
)
def test_archive_id_utf8_boundaries_match_contract_and_dto(
    archive_env: WorkspaceHttpTestEnvironment,
    case_id: str,
    id_value: str,
    should_accept: bool,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    if should_accept:
        validate_utf8_id(id_value, field_name="submission_id")
        AppendArchiveConfirmationRequest.model_validate(
            {
                **_confirmation_body(seed),
                "expected_baseline_node_id": id_value,
            }
        )
    else:
        with pytest.raises(ArchiveRequestValidation):
            validate_utf8_id(id_value, field_name="submission_id")
        with pytest.raises(ValidationError):
            AppendArchiveConfirmationRequest.model_validate(
                {
                    **_confirmation_body(seed),
                    "expected_baseline_node_id": id_value,
                }
            )


@pytest.mark.parametrize(
    ("case_id", "id_value", "expected_status"),
    (
        ARCHIVE_HTTP_ID_BOUNDARY_CASES[0],
        ARCHIVE_HTTP_ID_BOUNDARY_CASES[1],
    ),
    ids=["ascii_255", "ascii_256"],
)
def test_archive_idempotency_key_ascii_boundaries_over_http(
    archive_env: WorkspaceHttpTestEnvironment,
    case_id: str,
    id_value: str,
    expected_status: int,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    if expected_status == 422:
        with pytest.raises(ArchiveRequestValidation):
            validate_utf8_id(id_value, field_name="idempotency_key")
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key=id_value),
        json=_confirmation_body(seed),
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("case_id", "reason_value", "expected_status"),
    ARCHIVE_HTTP_REASON_BOUNDARY_CASES,
    ids=[case[0] for case in ARCHIVE_HTTP_REASON_BOUNDARY_CASES],
)
def test_archive_reason_utf8_boundaries_match_contract(
    archive_env: WorkspaceHttpTestEnvironment,
    case_id: str,
    reason_value: str,
    expected_status: int,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    if expected_status == 201:
        validate_utf8_reason(reason_value)
        validate_archive_confirmation_reason(ArchiveConfirmationAction.CONFIRM, reason_value)
    else:
        with pytest.raises(ArchiveRequestValidation):
            validate_utf8_reason(reason_value)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key=f"reason-{case_id}"),
        json=_confirmation_body(seed, reason=reason_value),
    )
    assert response.status_code == expected_status


def test_archive_reason_rejects_1500_chinese_characters(archive_env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    reason = "中" * 1500
    with pytest.raises(ArchiveRequestValidation):
        validate_utf8_reason(reason)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="reason-1500-cn"),
        json=_confirmation_body(seed, reason=reason),
    )
    assert response.status_code == 422


def test_archive_reason_accepts_2001_ascii_characters(archive_env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    reason = "a" * 2001
    validate_utf8_reason(reason)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="reason-2001-ascii"),
        json=_confirmation_body(seed, reason=reason),
    )
    assert response.status_code == 201


def test_archive_confirmation_allows_null_reason_for_confirm_action(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    validate_archive_confirmation_reason(ArchiveConfirmationAction.CONFIRM, None)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="confirm-null-reason"),
        json=replace_dict(_confirmation_body(seed), reason=None),
    )
    assert response.status_code == 201


def test_archive_confirmation_rejects_invalid_surrogate_reason(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    with pytest.raises(ValidationError):
        AppendArchiveConfirmationRequest.model_validate(
            {
                **_confirmation_body(seed),
                "reason": "\ud800",
            }
        )


def test_archive_resolution_requires_non_null_reason(archive_env: WorkspaceHttpTestEnvironment) -> None:
    dual = seed_approved_dual_sibling_archive(archive_env.db_path)
    seed = dual.primary
    with pytest.raises(ValidationError):
        AppendArchiveAnomalyResolutionRequest.model_validate(
            {
                **_confirmation_body(seed, reason=None),
                "action": "ACKNOWLEDGE_EXCLUSION",
                "issue_code": "APPROVED_SIBLING_EXCLUDED",
                "sibling_submission_id": dual.sibling_submission_id,
                "sibling_candidate_digest": dual.sibling_candidate_digest,
                "subject_digest": dual.anomaly_subject_digest,
            }
        )


def replace_dict(body: dict[str, object], **updates: object) -> dict[str, object]:
    return {**body, **updates}


ARCHIVE_AUDIT_QUERY_INVALID_CASES = (
    ("invalid_digest", {"subject_digest": "not-a-digest"}, 422),
    ("limit_zero", {"limit": 0}, 422),
    ("limit_over", {"limit": 101}, 422),
    ("limit_negative", {"limit": -1}, 422),
    ("after_sequence_negative", {"after_sequence": -1}, 422),
)

ARCHIVE_HTTP_NON_STRING_FIELD_CASES = (
    ("reason_not_string", "reason", 5),
    ("sequence_not_string", "expected_sequence", "0"),
)

ARCHIVE_MIDDLEWARE_DISCONNECT_SCOPE = {
    "type": "http",
    "method": "POST",
    "path": "/v1/archives",
    "headers": [],
}

ARCHIVE_FORBIDDEN_RESPONSE_SUBSTRINGS = (
    "repository_id",
    "SELECT ",
    "/var/lib/",
)


@pytest.mark.parametrize(
    ("case_id", "extra_params", "expected_status"),
    ARCHIVE_AUDIT_QUERY_INVALID_CASES,
    ids=[case[0] for case in ARCHIVE_AUDIT_QUERY_INVALID_CASES],
)
def test_archive_audit_events_query_validation(
    archive_env: WorkspaceHttpTestEnvironment,
    case_id: str,
    extra_params: dict[str, object],
    expected_status: int,
) -> None:
    seed_approved_archive_candidate(archive_env.db_path)
    params = {
        "subject_kind": "CONFIRM_SELECTION",
        "subject_digest": "sha256:" + "a" * 64,
        "after_sequence": 0,
        "limit": 100,
        **extra_params,
    }
    response = archive_env.client.get(
        "/v1/archive-audit-events",
        headers=_auth_headers(archive_env),
        params=params,
    )
    assert response.status_code == expected_status


def test_archive_confirmation_revoke_requires_reason_over_http(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    for payload in (
        replace_dict(_confirmation_body(seed), action="REVOKE", reason=None),
        {k: v for k, v in replace_dict(_confirmation_body(seed), action="REVOKE").items() if k != "reason"},
    ):
        response = archive_env.client.post(
            "/v1/archive-confirmations",
            headers=_auth_headers(archive_env, idempotency_key="revoke-no-reason"),
            json=payload,
        )
        assert response.status_code == 422


def test_archive_start_rejects_too_many_confirmation_refs(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    digest = seed.selection_subject_digest
    refs = [{"subject_digest": digest, "sequence": index} for index in range(ARCHIVE_MAX_AUDIT_REFS + 1)]
    response = archive_env.client.post(
        "/v1/archives",
        headers=_auth_headers(archive_env, idempotency_key="too-many-refs"),
        json={
            **_start_body(seed, confirmation_sequence=0),
            "confirmation_refs": refs,
            "anomaly_resolution_refs": [],
        },
    )
    assert response.status_code == 422


def test_archive_start_rejects_duplicate_confirmation_refs(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    ref = {"subject_digest": seed.selection_subject_digest, "sequence": 1}
    response = archive_env.client.post(
        "/v1/archives",
        headers=_auth_headers(archive_env, idempotency_key="duplicate-refs"),
        json={
            **_start_body(seed, confirmation_sequence=1),
            "confirmation_refs": [ref, ref],
            "anomaly_resolution_refs": [],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "route",
    (
        "/v1/archive-confirmations",
        "/v1/archive-anomaly-resolutions",
        "/v1/archives",
    ),
)
def test_archive_write_routes_return_429_when_admission_closed(
    tmp_path: Path,
    route: str,
) -> None:
    gate = ClosableAdmissionGate(limit=1)
    env = _archive_env(tmp_path, admission_gate=gate)
    dual = seed_approved_dual_sibling_archive(env.db_path)
    seed = dual.primary
    confirm_sequence = append_selection_confirmation(seed)
    resolve = env.client.post(
        "/v1/archive-anomaly-resolutions",
        headers=_auth_headers(env, idempotency_key=f"resolve-{route}"),
        json={
            **_confirmation_body(seed, reason="acknowledge sibling exclusion"),
            "action": "ACKNOWLEDGE_EXCLUSION",
            "issue_code": "APPROVED_SIBLING_EXCLUDED",
            "sibling_submission_id": dual.sibling_submission_id,
            "sibling_candidate_digest": dual.sibling_candidate_digest,
            "subject_digest": dual.anomaly_subject_digest,
        },
    )
    assert resolve.status_code == 201
    gate.close()
    if route == "/v1/archive-confirmations":
        body = _confirmation_body(seed)
        key = "admission-confirm"
    elif route == "/v1/archive-anomaly-resolutions":
        body = {
            **_confirmation_body(seed, reason="retry"),
            "action": "ACKNOWLEDGE_EXCLUSION",
            "issue_code": "APPROVED_SIBLING_EXCLUDED",
            "sibling_submission_id": dual.sibling_submission_id,
            "sibling_candidate_digest": dual.sibling_candidate_digest,
            "subject_digest": dual.anomaly_subject_digest,
            "expected_sequence": 1,
        }
        key = "admission-resolve"
    else:
        body = _start_body(
            seed,
            confirmation_sequence=confirm_sequence,
            anomaly_resolution_sequences=((dual.anomaly_subject_digest, resolve.json()["sequence"]),),
        )
        key = "admission-start"
    response = env.client.post(
        route,
        headers=_auth_headers(env, idempotency_key=key),
        json=body,
    )
    assert response.status_code == 429
    assert response.json()["code"] == "ADMISSION_LIMIT_REACHED"


def test_archive_confirmation_audit_version_conflict_returns_409_with_details(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    first = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="audit-version-1"),
        json=_confirmation_body(seed),
    )
    assert first.status_code == 201
    conflict = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="audit-version-2"),
        json=replace_dict(_confirmation_body(seed), expected_sequence=99),
    )
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["code"] == "ARCHIVE_AUDIT_VERSION_CONFLICT"
    assert body["details"]["expected"] == 99
    assert body["details"]["actual"] == 1


def test_archive_start_candidate_set_conflict_returns_409(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    confirm_sequence = append_selection_confirmation(seed)
    response = archive_env.client.post(
        "/v1/archives",
        headers=_auth_headers(archive_env, idempotency_key="candidate-set-conflict"),
        json=replace_dict(
            _start_body(seed, confirmation_sequence=confirm_sequence),
            candidate_set_digest="sha256:" + "b" * 64,
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CANDIDATE_SET_CONFLICT"


def test_archive_cross_actor_idempotency_conflict_on_confirmation(
    tmp_path: Path,
) -> None:
    other_actor = "other-actor-bearer"
    env = _archive_env(
        tmp_path,
        extra_sessions={
            other_actor: make_identity(
                actor_id="actor-2",
                permissions=_archive_permissions(),
            )
        },
    )
    seed = seed_approved_archive_candidate(env.db_path)
    body = _confirmation_body(seed)
    first = env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(env, idempotency_key="shared-confirm-key"),
        json=body,
    )
    assert first.status_code == 201
    conflict = env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(env, bearer=other_actor, idempotency_key="shared-confirm-key"),
        json=body,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_archive_cross_actor_start_idempotency_replay_preserves_accepted_by(
    tmp_path: Path,
) -> None:
    other_actor = "other-actor-bearer"
    env = _archive_env(
        tmp_path,
        extra_sessions={
            other_actor: make_identity(
                actor_id="actor-2",
                permissions=_archive_permissions(),
            )
        },
    )
    seed = seed_approved_archive_candidate(env.db_path)
    confirmation_sequence = append_selection_confirmation(seed)
    start_body = _start_body(seed, confirmation_sequence=confirmation_sequence)
    first = env.client.post(
        "/v1/archives",
        headers=_auth_headers(env, idempotency_key="shared-start-key"),
        json=start_body,
    )
    assert first.status_code == 201
    first_body = first.json()
    replay = env.client.post(
        "/v1/archives",
        headers=_auth_headers(env, bearer=other_actor, idempotency_key="shared-start-key"),
        json=start_body,
    )
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["archive_plan_id"] == first_body["archive_plan_id"]
    assert replay_body["archive_result_id"] == first_body["archive_result_id"]
    assert replay_body["archived_by"] == first_body["archived_by"]
    assert first_body["archived_by"] == "actor-1"


def test_archive_list_candidates_returns_scope_limit_exceeded_without_partial_list(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed_bulk_approved_archive_candidates(archive_env.db_path, count=201)
    response = archive_env.client.get(
        "/v1/archive-candidates",
        headers=_auth_headers(archive_env),
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "ARCHIVE_SCOPE_LIMIT_EXCEEDED"
    assert "candidates" not in body


@pytest.mark.parametrize(
    ("case_id", "field_name", "invalid_value"),
    ARCHIVE_HTTP_NON_STRING_FIELD_CASES,
    ids=[case[0] for case in ARCHIVE_HTTP_NON_STRING_FIELD_CASES],
)
def test_archive_confirmation_rejects_non_string_fields_over_http(
    archive_env: WorkspaceHttpTestEnvironment,
    case_id: str,
    field_name: str,
    invalid_value: object,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    with pytest.raises(ValidationError):
        AppendArchiveConfirmationRequest.model_validate(
            replace_dict(_confirmation_body(seed), **{field_name: invalid_value})
        )
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key=f"non-string-{case_id}"),
        json=replace_dict(_confirmation_body(seed), **{field_name: invalid_value}),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


@pytest.mark.serial
def test_archive_body_middleware_returns_on_client_disconnect() -> None:
    """客户端中途断开时中间件必须立即返回，不得空转阻塞事件循环。

    TestClient 总是发送完整 body，无法覆盖该路径，因此直接驱动 ASGI 中间件。
    """
    calls = 0

    async def receive() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"type": "http.request", "body": b'{"selected"', "more_body": True}
        return {"type": "http.disconnect"}

    async def inner_app(scope: object, receive: object, send: object) -> None:  # pragma: no cover
        raise AssertionError("inner app must not run on disconnect")

    async def send(message: object) -> None:  # pragma: no cover
        return None

    def run() -> None:
        asyncio.run(
            ArchiveRequestBodyLimitMiddleware(inner_app)(
                ARCHIVE_MIDDLEWARE_DISCONNECT_SCOPE,
                receive,
                send,
            )
        )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=5.0)
    assert not thread.is_alive(), "middleware spun without yielding on http.disconnect"
    assert calls <= 3


def test_archive_post_rejects_deeply_nested_json_with_422(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    deep_json = b"[" * 50000 + b"0" + b"]" * 50000
    assert len(deep_json) < ARCHIVE_MAX_REQUEST_BYTES
    response = archive_env.client.post(
        "/v1/archive-plan-preview",
        headers={
            **_auth_headers(archive_env, idempotency_key="deep-json-nesting"),
            "Content-Type": "application/json",
        },
        content=deep_json,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_archive_post_rejects_declared_body_over_limit(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed_approved_archive_candidate(archive_env.db_path)
    oversized = b"x" * (ARCHIVE_MAX_REQUEST_BYTES + 1)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers={
            **_auth_headers(archive_env, idempotency_key="oversized-body"),
            "Content-Length": str(len(oversized)),
            "Content-Type": "application/json",
        },
        content=oversized,
    )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_archive_post_rejects_chunked_body_over_limit(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed_approved_archive_candidate(archive_env.db_path)
    oversized = b"x" * (ARCHIVE_MAX_REQUEST_BYTES + 1)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers={
            **_auth_headers(archive_env, idempotency_key="chunked-oversized"),
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
        },
        content=oversized,
    )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_archive_confirmation_rejects_duplicate_json_keys(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    base = _confirmation_body(seed)
    raw = (
        "{"
        f'"expected_baseline_node_id":"{base["expected_baseline_node_id"]}",'
        f'"expected_baseline_head_version":{base["expected_baseline_head_version"]},'
        f'"selected":{json.dumps(base["selected"])},'
        f'"candidate_set_digest":"{base["candidate_set_digest"]}",'
        f'"subject_digest":"{base["subject_digest"]}",'
        f'"expected_sequence":{base["expected_sequence"]},'
        '"action":"CONFIRM",'
        '"reason":"first","reason":"second"'
        "}"
    )
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers={
            **_auth_headers(archive_env, idempotency_key="dup-json-key"),
            "Content-Type": "application/json",
        },
        content=raw.encode("utf-8"),
    )
    assert response.status_code == 422


def test_archive_confirmation_rejects_extra_fields_over_http(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    response = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="extra-field"),
        json=replace_dict(_confirmation_body(seed), unexpected=True),
    )
    assert response.status_code == 422


def test_deploy_session_example_lists_archive_permission_explicitly() -> None:
    session_path = Path(__file__).resolve().parents[2] / "deploy" / "config" / "session.json"
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    for entry in payload["sessions"]:
        permissions = entry["permissions"]
        assert isinstance(permissions, list)
        assert "*" not in permissions
    granted = [entry for entry in payload["sessions"] if "archive_submission" in entry["permissions"]]
    assert granted, "deploy example must show explicit archive_submission grant"


def test_deploy_session_example_lists_read_project_history_explicitly() -> None:
    session_path = Path(__file__).resolve().parents[2] / "deploy" / "config" / "session.json"
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    documented = payload.get("documented_permissions")
    assert isinstance(documented, list)
    assert "read_project_history" in documented
    for entry in payload["sessions"]:
        permissions = entry["permissions"]
        assert isinstance(permissions, list)
        assert "*" not in permissions
    local_dev = next(
        entry for entry in payload["sessions"] if entry["token"] == "local-dev-session-token"
    )
    assert "read_project_history" not in local_dev["permissions"]


@pytest.mark.parametrize("path", ("/v1/archive-candidates", "/v1/archive-plan-preview"))
def test_archive_read_routes_unaffected_by_body_limit_middleware(
    archive_env: WorkspaceHttpTestEnvironment,
    path: str,
) -> None:
    seed = seed_approved_archive_candidate(archive_env.db_path)
    if path.endswith("candidates"):
        response = archive_env.client.get(path, headers=_auth_headers(archive_env))
    else:
        response = archive_env.client.post(
            path,
            headers=_auth_headers(archive_env),
            json={
                "selected": {
                    "submission_id": seed.selected_ref.submission_id,
                    "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
                }
            },
        )
    assert response.status_code == 200


def test_archive_responses_do_not_leak_internal_fields(
    archive_env: WorkspaceHttpTestEnvironment,
) -> None:
    dual = seed_approved_dual_sibling_archive(archive_env.db_path)
    seed = dual.primary
    confirm = archive_env.client.post(
        "/v1/archive-confirmations",
        headers=_auth_headers(archive_env, idempotency_key="leak-scan-confirm"),
        json=_confirmation_body(seed),
    )
    assert confirm.status_code == 201
    resolve = archive_env.client.post(
        "/v1/archive-anomaly-resolutions",
        headers=_auth_headers(archive_env, idempotency_key="leak-scan-resolve"),
        json={
            **_confirmation_body(seed, reason="acknowledge sibling exclusion"),
            "action": "ACKNOWLEDGE_EXCLUSION",
            "issue_code": "APPROVED_SIBLING_EXCLUDED",
            "sibling_submission_id": dual.sibling_submission_id,
            "sibling_candidate_digest": dual.sibling_candidate_digest,
            "subject_digest": dual.anomaly_subject_digest,
        },
    )
    assert resolve.status_code == 201
    start = archive_env.client.post(
        "/v1/archives",
        headers=_auth_headers(archive_env, idempotency_key="leak-scan-start"),
        json=_start_body(
            seed,
            confirmation_sequence=confirm.json()["sequence"],
            anomaly_resolution_sequences=((dual.anomaly_subject_digest, resolve.json()["sequence"]),),
        ),
    )
    assert start.status_code == 201
    started = start.json()
    result = archive_env.client.get(
        f"/v1/archives/{started['archive_result_id']}",
        headers=_auth_headers(archive_env),
    )
    assert result.status_code == 200
    audit = archive_env.client.get(
        "/v1/archive-audit-events",
        headers=_auth_headers(archive_env),
        params={
            "subject_kind": "CONFIRM_SELECTION",
            "subject_digest": seed.selection_subject_digest,
            "after_sequence": 0,
            "limit": 100,
        },
    )
    assert audit.status_code == 200
    bodies = [
        archive_env.client.get("/v1/archive-candidates", headers=_auth_headers(archive_env)).text,
        archive_env.client.post(
            "/v1/archive-plan-preview",
            headers=_auth_headers(archive_env),
            json={
                "selected": {
                    "submission_id": seed.selected_ref.submission_id,
                    "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
                }
            },
        ).text,
        confirm.text,
        resolve.text,
        audit.text,
        start.text,
        result.text,
    ]
    for text in bodies:
        for forbidden in ARCHIVE_FORBIDDEN_RESPONSE_SUBSTRINGS:
            assert forbidden not in text
