"""HTTP contract tests for Archive routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from gateway_backend.application.archive.contracts import (
    validate_archive_confirmation_reason,
    validate_utf8_id,
    validate_utf8_reason,
)
from gateway_backend.application.archive.queries import PERMISSION_ARCHIVE_SUBMISSION
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from gateway_backend.http.dependencies import ClosableAdmissionGate
from gateway_backend.http.schemas.archive import (
    AppendArchiveConfirmationRequest,
    AppendArchiveAnomalyResolutionRequest,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.archive_fixtures import (
    append_selection_confirmation,
    seed_approved_archive_candidate,
    seed_approved_dual_sibling_archive,
)
from tests.support.http_workspace_harness import (
    TEST_BEARER,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_submit_transactions import BASELINE_HEAD

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
    before = _archive_table_counts(archive_env.db_path)
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
    after = _archive_table_counts(archive_env.db_path)
    assert before == after


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


def test_archive_get_result_hides_cross_scope_result(tmp_path: Path) -> None:
    env = _archive_env(tmp_path)
    seed = seed_approved_archive_candidate(env.db_path)
    confirmation_sequence = append_selection_confirmation(seed)
    started = archive_env_start(env, seed, confirmation_sequence)
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_env = create_workspace_http_environment(
        other_root,
        identity=make_identity(
            device_key="device-2",
            project_id="project-2",
            permissions=_archive_permissions(),
        ),
    )
    response = other_env.client.get(
        f"/v1/archives/{started['archive_result_id']}",
        headers=_auth_headers(other_env),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


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
        with pytest.raises(ValueError):
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
    validate_utf8_id(id_value, field_name="idempotency_key") if expected_status == 201 else None
    if expected_status == 422:
        with pytest.raises(ValueError):
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
        with pytest.raises(ValueError):
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
    with pytest.raises(ValueError):
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
