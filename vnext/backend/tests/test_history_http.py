"""History HTTP route tests."""

from __future__ import annotations

from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

from tests.support.artifact_layout import open_test_store

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from gateway_backend.artifacts import ArtifactStorePort, InMemoryArtifactStore
from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
from gateway_backend.bootstrap.composition import LocalArtifactBundleReader
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    InMemoryBoundedArtifactStore,
    InMemoryBundleReader,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_review_transactions import (
    _apply_command,
    _apply_review,
    _seed_pending_review_submission,
)
from gateway_backend.domain.submission.review import ReviewAction

from tests.support.history_zero_write_tables import capture_business_table_state

pytestmark = pytest.mark.unit

HISTORY_HTTP_QUERY_BOUNDARY_CASES = (
    ("limit_zero", {"limit": 0}, 422),
    ("limit_over_max", {"limit": 501}, 422),
    ("limit_non_int", {"limit": "x"}, 422),
    ("cursor_over_max", {"cursor": "a" * 1025}, 422),
)

COMPARE_RESULT_DECODE_MALFORMED_CASES = (
    ("bundle_digest_bad_prefix", "bundle_digest", "not-a-digest"),
    ("bundle_digest_bad_hex", "bundle_digest", "sha256:" + "g" * 64),
    ("comparison_digest_bad_hex", "comparison_digest", "sha256:" + "g" * 64),
)

HISTORY_COMPARE_HTTP_VALIDATION_CASES = (
    ("empty_idempotency_key", "", 422, "REQUEST_VALIDATION_FAILED"),
    ("long_idempotency_key", "a" * 300, 422, "REQUEST_VALIDATION_FAILED"),
    ("duplicate_json_key", "duplicate-json", 422, "REQUEST_VALIDATION_FAILED"),
    ("oversized_body", "oversized-body", 413, "REQUEST_TOO_LARGE"),
)

HISTORY_COMPARE_IDEMPOTENCY_BYTE_CASES = (
    ("idempotency_256_bytes_rejects", "a" * 256, 422, "REQUEST_VALIDATION_FAILED"),
)

IDEMPOTENCY_KEY_VALIDATION_CASES = (
    ("empty", None, "REQUEST_VALIDATION_FAILED"),
    ("whitespace", "   ", "REQUEST_VALIDATION_FAILED"),
    ("ascii_255", "a" * 255, None),
    ("ascii_256", "a" * 256, "REQUEST_VALIDATION_FAILED"),
    ("multibyte_255", "汉" * 85, None),
    ("multibyte_258", "汉" * 86, "REQUEST_VALIDATION_FAILED"),
)

HISTORY_HTTP_REF_ID_BOUNDARY_CASES = (
    ("ascii_255", "a" * 255),
    ("chinese_85", "中" * 85),
    ("four_byte_255", "😀" * 63 + "a" * 3),
)


def test_list_history_requires_authentication(env: object, tmp_path: Path) -> None:
    del env
    history_env = _history_env(tmp_path / "history-auth")
    response = history_env.client.get("/v1/history")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_list_history_requires_read_project_history_permission(tmp_path: Path) -> None:
    history_env = _history_env(
        tmp_path / "history-forbidden",
        permissions=frozenset({"workspace_read"}),
    )
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_list_history_returns_projection_shape(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-history"),
    )
    history_env = _history_env(db_path.parent / "history-http", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"head", "nodes", "next_cursor"}
    assert set(body["head"]) == {"node_id", "commit_id", "version"}
    assert len(body["nodes"]) >= 2
    node = next(item for item in body["nodes"] if item["node_kind"] == "SUBMISSION")
    assert node["review_status"] == "APPROVED"
    assert node["parent"]["ref_kind"] == "baseline_node"


def test_list_history_rejects_invalid_cursor(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    history_env = _history_env(db_path.parent / "history-cursor", db_path=db_path)
    response = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"cursor": "not-valid"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_list_history_supports_cursor_pagination(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-page"),
    )
    history_env = _history_env(db_path.parent / "history-page", db_path=db_path)
    first = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"limit": 1},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["nodes"]) == 1
    assert first_body["next_cursor"] is not None
    second = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    assert second.json()["nodes"][0]["ref_id"] != first_body["nodes"][0]["ref_id"]


def test_list_history_is_read_only(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-readonly"
        ),
    )
    history_env = _history_env(db_path.parent / "history-readonly", db_path=db_path)
    before = capture_business_table_state(db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    after = capture_business_table_state(db_path)
    assert before == after


def _corrupt_baseline_created_at_us(db_path: Path, *, node_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE baseline_node_records SET created_at_us = ? WHERE node_id = ?",
            ("not-an-int", node_id),
        )
        connection.commit()


def test_list_history_returns_integrity_failure_for_corrupt_facts(
    db_path: Path, tmp_path: Path
) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    _corrupt_baseline_created_at_us(
        db_path,
        node_id=BASELINE_HEAD.business_baseline_node_id,
    )
    history_env = _history_env(db_path.parent / "history-corrupt", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 503
    assert response.json()["code"] == "HISTORY_INTEGRITY_FAILURE"


def test_list_history_ignores_corrupt_submission_heavy_columns_on_page_path(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE submission_records SET source_artifact_refs = ? WHERE submission_id = ?",
            (b"not-json", review_seed.submission_id),
        )
        connection.commit()
    history_env = _history_env(db_path.parent / "history-heavy-column", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200


def test_list_history_rejects_disabled_mapping_without_stale_scope_reads(
    db_path: Path, tmp_path: Path
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-scope-http"
        ),
    )
    from tests.test_submit_transactions import _upsert_provisioned_mapping_row

    _upsert_provisioned_mapping_row(db_path, baseline_head=None, enabled=False)
    history_env = _history_env(db_path.parent / "history-scope", db_path=db_path)
    stale_scope = history_env.scope_resolution
    assert stale_scope.resolve(history_env.identity).repository_id == "repo-1"
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_list_history_accepts_long_cjk_commit_id(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-cjk-commit"
        ),
    )
    cjk_commit = "中" * 200
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE submission_records SET repository_commit_id = ? WHERE submission_id = ?",
            (cjk_commit, review_seed.submission_id),
        )
    history_env = _history_env(db_path.parent / "history-cjk-commit", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    submission_node = next(
        item for item in response.json()["nodes"] if item["node_kind"] == "SUBMISSION"
    )
    assert submission_node["commit_id"] == cjk_commit


@pytest.mark.parametrize(
    ("case_id", "params", "expected_status"), HISTORY_HTTP_QUERY_BOUNDARY_CASES
)
def test_list_history_rejects_out_of_bounds_query(
    db_path: Path,
    tmp_path: Path,
    case_id: str,
    params: dict[str, object],
    expected_status: int,
) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    history_env = _history_env(db_path.parent / "history-query-boundary", db_path=db_path)
    response = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params=params,
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


@pytest.mark.parametrize(("case_id", "ref_id"), HISTORY_HTTP_REF_ID_BOUNDARY_CASES)
def test_list_history_returns_nodes_with_bounded_ref_ids(
    db_path: Path,
    tmp_path: Path,
    case_id: str,
    ref_id: str,
) -> None:
    del tmp_path, case_id
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{len(ref_id)}"
        ),
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, 'repo-1', 'device-1', 'project-1', 'commit-boundary',
                      'ARCHIVED_SUBMISSION', ?, ?, 999)
            """,
            (ref_id, BASELINE_HEAD.business_baseline_node_id, review_seed.submission_id),
        )
    history_env = _history_env(
        db_path.parent / f"history-ref-{len(ref_id.encode('utf-8'))}", db_path=db_path
    )
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    assert any(item["ref_id"] == ref_id for item in response.json()["nodes"])


def _tamper_checkpoint_semantically_same_length(
    artifact_store: ArtifactStorePort,
    ref: object,
    *,
    local_store: object | None = None,
) -> None:
    from gateway_backend.application.checkpoints import (
        load_checkpoint_envelope,
        load_checkpoint_state_artifact,
    )
    from gateway_backend.application.history.compare_jobs.checkpoint import (
        HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
        HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
    )
    from gateway_backend.artifacts import ArtifactRef, artifact_ref_from_dict
    from gateway_shared_kernel.jcs import canonicalize_json_value

    assert isinstance(ref, ArtifactRef)
    envelope = load_checkpoint_envelope(artifact_store, ref)
    state_ref = artifact_ref_from_dict(
        cast(dict[str, object], envelope.job_state["assemble_state_ref"])
    )
    original_bytes = artifact_store.locate(state_ref)
    state_document = load_checkpoint_state_artifact(
        artifact_store,
        state_ref,
        document_type=HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
        contract_version=HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
    )
    assemble_state = dict(cast(dict[str, object], state_document["assemble_state"]))
    pairs = list(cast(list[object], assemble_state["pairs"]))
    pair0 = dict(cast(dict[str, object], pairs[0]))
    digest = str(pair0["comparison_digest"])
    replacement = "b" if digest[-1] != "b" else "a"
    pair0["comparison_digest"] = digest[:-1] + replacement
    pairs[0] = pair0
    assemble_state["pairs"] = pairs
    state_document["assemble_state"] = assemble_state
    tampered_bytes = canonicalize_json_value(state_document)
    assert len(tampered_bytes) == len(original_bytes)
    if local_store is not None:
        assert isinstance(local_store, LocalArtifactStore)
        target = local_store.payload_path(state_ref.artifact_id)
        target.write_bytes(tampered_bytes)
        return
    memory_store = cast(InMemoryArtifactStore, artifact_store)
    memory_store._artifacts[state_ref.artifact_id] = (state_ref, tampered_bytes)  # noqa: SLF001


def _history_env(
    root: Path,
    *,
    db_path: Path | None = None,
    permissions: frozenset[str] | None = None,
    artifact_store: InMemoryBoundedArtifactStore | BoundedArtifactStore | None = None,
    bundle_reader: InMemoryBundleReader | LocalArtifactBundleReader | None = None,
) -> WorkspaceHttpTestEnvironment:
    root.mkdir(parents=True, exist_ok=True)
    resolved_db = db_path or (root / "control.sqlite3")
    if db_path is None:
        from gateway_backend.infrastructure.control_db.database import initialize_control_db
        from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
        from tests.support.http_workspace_harness import BASELINE_HEAD

        initialize_control_db(resolved_db)
        seed_provisioned_mapping_with_head(resolved_db, baseline_head=BASELINE_HEAD)
    identity = make_identity(
        permissions=permissions or frozenset({"workspace_read", PERMISSION_READ_PROJECT_HISTORY}),
    )
    return create_workspace_http_environment(
        root,
        identity=identity,
        db_path=resolved_db,
        artifact_store=artifact_store,
        bundle_reader=bundle_reader,
    )


def _register_history_compare_bundle(
    history_env: WorkspaceHttpTestEnvironment,
    harness: object,
    operation_id: str,
) -> None:
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from tests.support.history_compare_job_harness import HistoryCompareJobHarness

    assert isinstance(harness, HistoryCompareJobHarness)
    with ControlDbUnitOfWork(history_env.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    bundle_artifact_id = envelope.job_state.get("bundle_artifact_id")
    assert isinstance(bundle_artifact_id, str) and bundle_artifact_id
    memory_store = cast(InMemoryArtifactStore, harness.artifact_store)
    for ref, payload in memory_store._artifacts.values():
        if ref.artifact_id == bundle_artifact_id:
            bundle_reader = history_env.bundle_reader
            assert isinstance(bundle_reader, InMemoryBundleReader)
            bundle_reader.register(
                bundle_artifact_id,
                f"history-compare-{operation_id}.tar",
                payload,
                bundle_digest=str(envelope.job_state["bundle_digest"]),
            )
            return
    raise AssertionError("bundle artifact is missing from the artifact store")


def _seed_compare_nodes(db_path: Path) -> tuple[str, str]:
    from tests.support.history_compare_job_harness import seed_archived_baseline_node

    seed_archived_baseline_node(
        db_path,
        node_id="bn-compare-b",
        commit_id="commit-b",
        created_at_us=2,
    )
    return BASELINE_HEAD.business_baseline_node_id, "bn-compare-b"


@pytest.mark.parametrize(
    ("case_name", "idempotency_key", "expected_status", "expected_code"),
    HISTORY_COMPARE_HTTP_VALIDATION_CASES,
)
def test_history_compare_http_validation_cases(
    db_path: Path,
    tmp_path: Path,
    case_name: str,
    idempotency_key: str,
    expected_status: int,
    expected_code: str,
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{case_name}"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / f"history-compare-{case_name}", db_path=db_path)
    headers = history_env.auth_headers()
    if idempotency_key:
        headers = history_env.auth_headers(idempotency_key=idempotency_key)
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    if case_name == "duplicate_json_key":
        raw = (
            b'{"nodes":[{"ref_kind":"baseline_node","ref_id":"'
            + node_a.encode()
            + b'"},{"ref_kind":"baseline_node","ref_id":"'
            + node_b.encode()
            + b'"}],"nodes":[{"ref_kind":"baseline_node","ref_id":"'
            + node_a.encode()
            + b'"},{"ref_kind":"baseline_node","ref_id":"'
            + node_b.encode()
            + b'"}]}'
        )
        response = history_env.client.post(
            "/v1/history-compares",
            headers=headers,
            content=raw,
        )
    elif case_name == "oversized_body":
        response = history_env.client.post(
            "/v1/history-compares",
            headers=headers,
            content=b"x" * (256 * 1024 + 1),
        )
    else:
        response = history_env.client.post("/v1/history-compares", headers=headers, json=body)
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


@pytest.mark.parametrize(
    ("case_name", "idempotency_key", "expected_status", "expected_code"),
    HISTORY_COMPARE_IDEMPOTENCY_BYTE_CASES,
)
def test_history_compare_idempotency_byte_boundary_cases(
    db_path: Path,
    tmp_path: Path,
    case_name: str,
    idempotency_key: str,
    expected_status: int,
    expected_code: str,
) -> None:
    del case_name, tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-byte-boundary"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-byte-boundary", db_path=db_path)
    response = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key=idempotency_key),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


@pytest.mark.parametrize(
    ("case_name", "raw_key", "expected_code"),
    IDEMPOTENCY_KEY_VALIDATION_CASES,
)
def test_validate_idempotency_key_cases(
    case_name: str,
    raw_key: str | None,
    expected_code: str | None,
) -> None:
    from gateway_backend.http.errors import ApiError
    from gateway_backend.http.routes.history import _validate_idempotency_key

    del case_name
    if expected_code is None:
        resolved = _validate_idempotency_key(raw_key)
        assert isinstance(resolved, str) and resolved
        return
    with pytest.raises(ApiError) as exc_info:
        _validate_idempotency_key(raw_key)
    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == 422


def test_validate_idempotency_key_rejects_multibyte_by_bytes_not_chars() -> None:
    from gateway_backend.http.errors import ApiError
    from gateway_backend.http.routes.history import _validate_idempotency_key

    key = "汉" * 86
    assert len(key) < 258
    assert len(key.encode("utf-8")) == 258
    with pytest.raises(ApiError) as exc_info:
        _validate_idempotency_key(key)
    assert exc_info.value.code == "REQUEST_VALIDATION_FAILED"


def test_history_compare_accepts_255_byte_idempotency_key(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-255-byte"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-255-byte", db_path=db_path)
    idempotency_key = "a" * 255
    assert len(idempotency_key.encode("utf-8")) == 255
    response = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key=idempotency_key),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert response.status_code == 202
    assert response.json()["replayed"] is False


def test_accept_history_compare_returns_202(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-accept", db_path=db_path)
    response = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-http-1"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["replayed"] is False
    assert body["operation_id"].startswith("op-")


def test_accept_history_compare_replay_returns_200(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-replay"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-replay", db_path=db_path)
    headers = history_env.auth_headers(idempotency_key="compare-http-replay")
    first = history_env.client.post(
        "/v1/history-compares",
        headers=headers,
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    second = history_env.client.post(
        "/v1/history-compares",
        headers=headers,
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["operation_id"] == first.json()["operation_id"]


def test_get_history_compare_result_succeeded_matches_assemble_checkpoint(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-succeeded"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-succeeded", db_path=db_path)
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-http-succeeded"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        db_path.parent / "harness-succeeded",
        db_path=db_path,
        artifact_store=history_env.artifact_store._store,
        idempotency_key="compare-http-succeeded",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(
        history_env.artifact_store._store,
        assemble_step.checkpoint_ref,
    )
    from gateway_backend.application.history.compare_jobs.checkpoint import (
        history_compare_assemble_state_from_checkpoint,
    )

    _state_ref, assemble_state = history_compare_assemble_state_from_checkpoint(
        envelope.job_state,
        history_env.artifact_store._store,
    )

    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCEEDED"
    assert body["result"] is not None
    assert body["result"]["bundle_digest"] == assemble_state["bundle_digest"]
    pairs = body["result"]["pairs"]
    assert isinstance(pairs, list) and pairs
    checkpoint_pairs = assemble_state["pairs"]
    assert isinstance(checkpoint_pairs, list)
    assert len(pairs) == len(checkpoint_pairs)
    for http_pair, checkpoint_pair in zip(pairs, checkpoint_pairs, strict=True):
        assert http_pair["record_count"] == checkpoint_pair["record_count"]
        assert http_pair["comparison_digest"] == checkpoint_pair["comparison_digest"]


def test_get_history_compare_bundle_streams_attachment(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    )
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-bundle"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-bundle", db_path=db_path)
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-http-bundle"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        db_path.parent / "harness-bundle",
        db_path=db_path,
        artifact_store=history_env.artifact_store._store,
        idempotency_key="compare-http-bundle",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)
    _register_history_compare_bundle(history_env, harness, operation_id)

    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}/bundle",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 200
    assert response.content
    assert response.headers["content-type"] == "application/x-tar"
    assert len(response.content) == int(response.headers["content-length"])
    assert response.headers["content-disposition"].endswith('.tar"')


def test_get_history_compare_result_returns_queued_shape(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-get"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-compare-get", db_path=db_path)
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-http-get"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation_id"] == operation_id
    assert body["status"] == "QUEUED"
    assert body["result"] is None


@pytest.mark.parametrize("store_kind", ("bounded_filesystem", "harness_memory"))
def test_checkpoint_bytes_tamper_returns_artifact_unavailable(
    db_path: Path,
    tmp_path: Path,
    store_kind: str,
) -> None:
    """Store digest rejection: same-length semantic tamper with the original ref.

    This proves the artifact store rejects bytes that no longer match ``raw_sha256``.
    Route-side DTO decode validation is covered by
    ``test_compare_result_decode_malformed_digest_returns_artifact_unavailable``.
    """
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )
    from tests.support.http_workspace_harness import InMemoryBoundedArtifactStore

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-tamper"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    local_store: LocalArtifactStore | None = None
    harness_artifact_store: ArtifactStorePort
    if store_kind == "bounded_filesystem":
        local_store = open_test_store(tmp_path / "artifact-root")
        bounded_store = BoundedArtifactStore(local_store)
        artifact_store: InMemoryBoundedArtifactStore | BoundedArtifactStore = bounded_store
        harness_artifact_store = bounded_store
    else:
        memory_bounded = InMemoryBoundedArtifactStore()
        artifact_store = memory_bounded
        harness_artifact_store = memory_bounded._store
    history_env = _history_env(
        db_path.parent / f"history-compare-tamper-{store_kind}",
        db_path=db_path,
        artifact_store=artifact_store,
    )
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key=f"compare-tamper-{store_kind}"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / f"harness-tamper-{store_kind}",
        db_path=db_path,
        artifact_store=harness_artifact_store,
        idempotency_key=f"compare-tamper-{store_kind}",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    ref = assemble_step.checkpoint_ref
    if store_kind == "bounded_filesystem":
        assert local_store is not None
        _tamper_checkpoint_semantically_same_length(
            harness_artifact_store,
            ref,
            local_store=local_store,
        )
    else:
        assert isinstance(artifact_store, InMemoryBoundedArtifactStore)
        _tamper_checkpoint_semantically_same_length(artifact_store._store, ref)  # noqa: SLF001

    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize(
    ("case_id", "field", "invalid_value"),
    COMPARE_RESULT_DECODE_MALFORMED_CASES,
)
def test_compare_result_decode_malformed_digest_returns_artifact_unavailable(
    db_path: Path,
    tmp_path: Path,
    case_id: str,
    field: str,
    invalid_value: str,
) -> None:
    del case_id
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )
    from tests.support.http_workspace_harness import InMemoryBoundedArtifactStore

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{field}"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    memory_bounded = InMemoryBoundedArtifactStore()
    history_env = _history_env(
        db_path.parent / f"history-compare-decode-{field}",
        db_path=db_path,
        artifact_store=memory_bounded,
    )
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key=f"compare-decode-{field}"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / f"harness-decode-{field}",
        db_path=db_path,
        artifact_store=memory_bounded._store,
        idempotency_key=f"compare-decode-{field}",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert assemble_step.checkpoint_ref is not None
    from tests.support.history_compare_checkpoint_tamper import rebind_tampered_assemble_checkpoint

    rebind_tampered_assemble_checkpoint(
        memory_bounded._store,
        assemble_step.checkpoint_ref,
        db_path=db_path,
        step_id=history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE),
        field=field,
        value=invalid_value,
    )

    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_UNAVAILABLE"


def test_history_compare_accept_idempotency_conflict_on_changed_nodes(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-idem-conflict"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    from tests.support.history_compare_job_harness import seed_archived_baseline_node

    node_c = "bn-compare-c"
    seed_archived_baseline_node(
        db_path,
        node_id=node_c,
        commit_id="commit-c",
        created_at_us=3,
    )
    history_env = _history_env(db_path.parent / "history-compare-idem-conflict", db_path=db_path)
    headers = history_env.auth_headers(idempotency_key="compare-idem-conflict")
    first = history_env.client.post(
        "/v1/history-compares",
        headers=headers,
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    second = history_env.client.post(
        "/v1/history-compares",
        headers=headers,
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_c},
            ]
        },
    )
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_history_compare_cross_scope_node_returns_404_without_disclosure(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    from tests.support.baseline_fixtures import upsert_provisioned_mapping_row

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-cross-scope"
        ),
    )
    node_a, _node_b = _seed_compare_nodes(db_path)
    upsert_provisioned_mapping_row(
        db_path,
        device_key="device-2",
        project_id="project-2",
        repository_id="repo-2",
        baseline_head=BASELINE_HEAD,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        repo2_node_id = unit_of_work.connection.execute(
            "SELECT node_id FROM baseline_head_records WHERE repository_id = ?",
            ("repo-2",),
        ).fetchone()["node_id"]
    history_env = _history_env(
        db_path.parent / "history-cross-scope",
        db_path=db_path,
        permissions=frozenset({"workspace_read", PERMISSION_READ_PROJECT_HISTORY}),
    )
    fictional = "bn-missing-scope"
    real_cross_scope = repo2_node_id
    responses = []
    for ref_id in (real_cross_scope, fictional):
        responses.append(
            history_env.client.post(
                "/v1/history-compares",
                headers=history_env.auth_headers(idempotency_key=f"compare-cross-scope-{ref_id}"),
                json={
                    "nodes": [
                        {"ref_kind": "baseline_node", "ref_id": node_a},
                        {"ref_kind": "baseline_node", "ref_id": ref_id},
                    ]
                },
            )
        )
    for response, ref_id in zip(responses, (real_cross_scope, fictional), strict=True):
        assert response.status_code == 404
        assert response.json()["code"] == "RESOURCE_NOT_FOUND"
        assert ref_id not in response.json()["message"]
    assert responses[0].json()["message"] == responses[1].json()["message"]


def test_get_history_compare_bundle_uses_local_artifact_bundle_reader(
    db_path: Path,
    tmp_path: Path,
) -> None:
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    )
    from gateway_backend.bootstrap.composition import LocalArtifactBundleReader
    from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-local-bundle"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    local_store = open_test_store(tmp_path / "bundle-artifacts")
    bounded_store = BoundedArtifactStore(local_store)
    history_env = _history_env(
        db_path.parent / "history-local-bundle",
        db_path=db_path,
        artifact_store=bounded_store,
        bundle_reader=LocalArtifactBundleReader(local_store),
    )
    accepted = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-local-bundle"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / "harness-local-bundle",
        db_path=db_path,
        artifact_store=bounded_store,
        idempotency_key="compare-local-bundle",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)

    response = history_env.client.get(
        f"/v1/history-compares/{operation_id}/bundle",
        headers=history_env.auth_headers(),
    )
    assert response.status_code == 200
    assert response.content
    assert response.headers["content-type"] == "application/x-tar"
    assert response.headers["content-disposition"].endswith('.tar"')
    assert len(response.content) == int(response.headers["content-length"])
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    for key in ("compare-local-bundle", "compare-local-bundle-alias", "compare-local-bundle-alias"):
        replay = history_env.client.post(
            "/v1/history-compares", headers=history_env.auth_headers(idempotency_key=key), json=body
        )
        assert replay.status_code == 200
        assert replay.json()["operation_id"] == operation_id
        assert replay.json()["replayed"] is True

    # Move the request and transaction clocks to the exact durable expiry.
    from dataclasses import replace
    from datetime import timedelta
    from fastapi import FastAPI

    app = cast(FastAPI, history_env.client.app)
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        operation = uow.operations.get_operation(operation_id)
        acceptance = uow.history_compare.get_acceptance_by_operation_id(operation_id)
    assert (
        operation.completed_at is not None
        and acceptance is not None
        and operation.ready_closure_ref is not None
    )
    from gateway_backend.bootstrap.storage_admin import release_expired_history_results
    from gateway_backend.http.orchestration.history_compare import read_compare_bundle

    prepared = read_compare_bundle(
        operation=operation,
        bundle_reader=LocalArtifactBundleReader(local_store),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only
        ),
        artifact_store=bounded_store,
    )
    expiry = operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds)
    app.state.history_http = replace(
        app.state.history_http,
        now=lambda: expiry,
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only, now=lambda: expiry
        ),
    )
    for suffix in ("", "/bundle"):
        expired = history_env.client.get(
            f"/v1/history-compares/{operation_id}{suffix}", headers=history_env.auth_headers()
        )
        assert expired.status_code == 410
        assert expired.json()["code"] == "HISTORY_COMPARE_RESULT_EXPIRED"
    expired_key = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-local-bundle"),
        json=body,
    )
    assert expired_key.status_code == 409
    assert expired_key.json()["code"] == "HISTORY_COMPARE_REQUEST_EXPIRED"
    expired_alias = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-local-bundle-alias"),
        json=body,
    )
    assert expired_alias.status_code == 409
    with ControlDbUnitOfWork(db_path, now=lambda: expiry) as uow:
        assert release_expired_history_results(uow) == 1
    with local_store.cleanup_session(operation.ready_closure_ref.artifact_id) as acquired:
        assert not acquired
    assert b"".join(prepared.stream) == response.content
    prepared.close()
    with local_store.cleanup_session(operation.ready_closure_ref.artifact_id) as acquired:
        assert acquired
    reused_key = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-local-bundle-alias"),
        json=body,
    )
    assert reused_key.status_code == 202
    new_request = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-local-bundle-after-expiry"),
        json=body,
    )
    assert new_request.status_code == 200
    assert new_request.json()["operation_id"] == reused_key.json()["operation_id"]
    assert new_request.json()["operation_id"] != operation_id


def test_accept_history_compare_is_read_only(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-zero-write"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    history_env = _history_env(db_path.parent / "history-zero-write-accept", db_path=db_path)
    before = capture_business_table_state(db_path)
    response = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-zero-write"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert response.status_code == 202
    after = capture_business_table_state(db_path)
    assert before == after


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_history_pages_and_full_snapshot_expose_both_terminal_sources_without_changing_review(
    db_path: Path,
) -> None:
    from dataclasses import replace
    from gateway_backend.application.archive.manual_close import close_submission
    from gateway_backend.infrastructure.control_db.history_reader import HttpHistoryReader
    from gateway_backend.domain.archive.models import SubmissionDispositionSourceKind
    from tests.support.archive_fixtures import (
        seed_approved_dual_sibling_archive,
        close_command,
        refresh_archive_seed,
        append_selection_confirmation,
        start_archive_for_seed,
        TS_ARCHIVE,
    )
    from tests.test_review_transactions import _uow_factory

    dual = seed_approved_dual_sibling_archive(db_path)
    close_submission(
        command=replace(close_command(dual.primary), submission_id=dual.target_submission_id),
        unit_of_work_factory=_uow_factory(db_path),
        now=TS_ARCHIVE,
    )
    primary = refresh_archive_seed(dual.primary)
    result = start_archive_for_seed(
        primary, confirmation_sequence=append_selection_confirmation(primary)
    )
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id=primary.repository_id,
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    by_id = {item.submission.submission_id: item for item in facts.submissions}
    manual = by_id[dual.target_submission_id].disposition_record
    archived = by_id[primary.submission_id].disposition_record
    assert manual is not None and archived is not None
    assert (
        manual.source_kind is SubmissionDispositionSourceKind.MANUAL_CLOSE
        and manual.result_id is None
    )
    assert (
        archived.source_kind is SubmissionDispositionSourceKind.ARCHIVE
        and archived.result_id == result.archive_result_id
    )
    env = _history_env(db_path.parent / "history-terminal", db_path=db_path)
    nodes = []
    cursor = None
    while True:
        response = env.client.get(
            "/v1/history",
            headers=env.auth_headers(),
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200
        body = response.json()
        nodes.extend(body["nodes"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    by_ref = {item["ref_id"]: item for item in nodes}
    assert by_ref[dual.target_submission_id]["review_status"] == "APPROVED"
    assert by_ref[dual.target_submission_id]["disposition_source_kind"] == "MANUAL_CLOSE"
    assert by_ref[dual.target_submission_id]["closure"]["reason"] == manual.manual_closure.reason  # type: ignore[union-attr]
    assert by_ref[primary.submission_id]["disposition_source_kind"] == "ARCHIVE"


def test_history_compare_list_is_paginated_and_scope_bound(db_path: Path, tmp_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-list"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    env = _history_env(tmp_path / "list", db_path=db_path)
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    first = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key="list-a"), json=body
    )
    body["nodes"].reverse()
    second = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key="list-b"), json=body
    )
    assert first.status_code == second.status_code == 202
    page1 = env.client.get("/v1/history-compares?limit=1", headers=env.auth_headers())
    assert page1.status_code == 200
    cursor = page1.json()["next_cursor"]
    assert set(page1.json()["items"][0]) == {
        "operation_id",
        "nodes",
        "status",
        "accepted_at",
        "completed_at",
        "result_expires_at",
    }
    assert cursor is not None
    page2 = env.client.get(
        "/v1/history-compares", params={"limit": 1, "after": cursor}, headers=env.auth_headers()
    )
    assert page2.status_code == 200
    assert {page1.json()["items"][0]["operation_id"], page2.json()["items"][0]["operation_id"]} == {
        first.json()["operation_id"],
        second.json()["operation_id"],
    }
    assert page2.json()["next_cursor"] is None
    assert (
        env.client.get("/v1/history-compares?after=garbage", headers=env.auth_headers()).status_code
        == 422
    )


def test_unreadable_success_replays_error_and_new_key_rebuilds(
    db_path: Path, tmp_path: Path
) -> None:
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs.checkpoint import (
        history_compare_assemble_state_from_checkpoint,
    )
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )
    from tests.support.http_workspace_harness import InMemoryBoundedArtifactStore

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-broken"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    store = InMemoryBoundedArtifactStore()
    env = _history_env(tmp_path / "broken-candidate", db_path=db_path, artifact_store=store)
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    first = env.client.post(
        "/v1/history-compares",
        headers=env.auth_headers(idempotency_key="broken-original"),
        json=body,
    )
    assert first.status_code == 202
    operation_id = first.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / "broken-harness",
        db_path=db_path,
        artifact_store=store._store,
        idempotency_key="broken-original",
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    for handler in (
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    ):
        run_through_step(harness, handler)
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        step = uow.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(store._store, step.checkpoint_ref)
    state_ref, _ = history_compare_assemble_state_from_checkpoint(envelope.job_state, store._store)
    store._store._artifacts.pop(state_ref.artifact_id)  # noqa: SLF001

    replay = env.client.post(
        "/v1/history-compares",
        headers=env.auth_headers(idempotency_key="broken-original"),
        json=body,
    )
    assert replay.status_code == 404
    assert replay.json()["code"] == "ARTIFACT_UNAVAILABLE"
    rebuilt = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key="broken-new"), json=body
    )
    assert rebuilt.status_code == 202
    assert rebuilt.json()["operation_id"] != operation_id
    result = env.client.get(f"/v1/history-compares/{operation_id}", headers=env.auth_headers())
    assert result.status_code == 404


HISTORY_PAIR_DIGEST_FIELDS = ("surface_digest", "risk_digest")


@pytest.mark.parametrize("field", HISTORY_PAIR_DIGEST_FIELDS)
def test_history_rejects_result_pair_digest_disagreeing_with_bundle(
    db_path: Path,
    tmp_path: Path,
    field: str,
) -> None:
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs.checkpoint import (
        history_compare_assemble_state_from_checkpoint,
    )
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from tests.support.history_compare_checkpoint_tamper import rebind_tampered_assemble_checkpoint
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )
    from tests.support.http_workspace_harness import InMemoryBoundedArtifactStore

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-pair-{field}"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    store = InMemoryBoundedArtifactStore()
    env = _history_env(tmp_path / f"pair-{field}", db_path=db_path, artifact_store=store)
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    original_key = f"pair-original-{field}"
    accepted = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=original_key), json=body
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / f"pair-harness-{field}",
        db_path=db_path,
        artifact_store=store._store,
        idempotency_key=original_key,
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    for handler in (
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    ):
        run_through_step(harness, handler)
    step_id = history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        operation = uow.operations.get_operation(operation_id)
        acceptance = uow.history_compare.get_acceptance_by_operation_id(operation_id)
        step = uow.operations.get_step(step_id)
    assert (
        step.checkpoint_ref is not None
        and operation.completed_at is not None
        and acceptance is not None
    )
    new_ref = rebind_tampered_assemble_checkpoint(
        store._store,
        step.checkpoint_ref,
        db_path=db_path,
        step_id=step_id,
        field=field,
        value="sha256:" + "0" * 64,
    )
    envelope = load_checkpoint_envelope(store._store, new_ref)
    state_ref, _ = history_compare_assemble_state_from_checkpoint(envelope.job_state, store._store)
    from datetime import timedelta

    expiry = operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds)
    with ControlDbUnitOfWork(db_path) as uow:
        uow.set_artifact_protection(
            (new_ref, state_ref),
            owner_kind="history-compare-operation",
            owner_id=operation_id,
            intent="history-compare-result",
            expires_at=expiry,
        )

    for suffix in ("", "/bundle"):
        result = env.client.get(
            f"/v1/history-compares/{operation_id}{suffix}", headers=env.auth_headers()
        )
        assert result.status_code == 503
        assert result.json()["code"] == "HISTORY_INTEGRITY_FAILURE"
    replay = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=original_key), json=body
    )
    assert replay.status_code == 503
    assert replay.json()["code"] == "HISTORY_INTEGRITY_FAILURE"
    retry = env.client.post(
        "/v1/history-compares",
        headers=env.auth_headers(idempotency_key=f"pair-new-{field}"),
        json=body,
    )
    assert retry.status_code == 202
    assert retry.json()["operation_id"] != operation_id


HISTORY_BUNDLE_DAMAGE_CASES = (
    ("missing", 404, "ARTIFACT_UNAVAILABLE"),
    ("corrupt", 503, "BUNDLE_INTEGRITY_FAILURE"),
)


@pytest.mark.parametrize(("damage", "status", "code"), HISTORY_BUNDLE_DAMAGE_CASES)
def test_history_bundle_missing_and_corrupt_are_distinct(
    db_path: Path,
    tmp_path: Path,
    damage: str,
    status: int,
    code: str,
) -> None:
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from gateway_backend.bootstrap.composition import LocalArtifactBundleReader
    from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{damage}"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    local_store = open_test_store(tmp_path / f"damaged-bundle-{damage}")
    bounded = BoundedArtifactStore(local_store)
    env = _history_env(
        tmp_path / f"damaged-env-{damage}",
        db_path=db_path,
        artifact_store=bounded,
        bundle_reader=LocalArtifactBundleReader(local_store),
    )
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    key = f"damage-{damage}"
    accepted = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=key), json=body
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / f"damage-harness-{damage}",
        db_path=db_path,
        artifact_store=bounded,
        idempotency_key=key,
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    for handler in (
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    ):
        run_through_step(harness, handler)
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        step = uow.operations.get_step(
            history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    assert step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(local_store, step.checkpoint_ref)
    bundle_id = envelope.job_state["bundle_artifact_id"]
    assert isinstance(bundle_id, str)
    path = local_store.payload_path(bundle_id)
    if damage == "missing":
        path.unlink()
    else:
        data = path.read_bytes()
        path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    for suffix in ("", "/bundle"):
        result = env.client.get(
            f"/v1/history-compares/{operation_id}{suffix}", headers=env.auth_headers()
        )
        assert result.status_code == status
        assert result.json()["code"] == code
    replay = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=key), json=body
    )
    assert replay.status_code == status
    assert replay.json()["code"] == code


HISTORY_BUNDLE_INPUT_FAULTS = ("role", "direction")


@pytest.mark.parametrize("fault", HISTORY_BUNDLE_INPUT_FAULTS)
def test_history_rejects_bundle_with_wrong_ordered_input_binding(
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import json
    import gateway_backend.application.bundle_download as bundle_download
    from gateway_shared_kernel import raw_blob_digest
    from gateway_shared_kernel.jcs import canonicalize_json_value
    from gateway_backend.application.history.compare_jobs.payload import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    )
    from gateway_backend.capabilities.bundle_assembly import (
        read_bundle_transport_metadata as real_reader,
    )
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        run_through_step,
    )
    from tests.support.http_workspace_harness import InMemoryBoundedArtifactStore

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(
            review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-input-{fault}"
        ),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    store = InMemoryBoundedArtifactStore()
    env = _history_env(tmp_path / f"input-{fault}", db_path=db_path, artifact_store=store)
    body = {
        "nodes": [
            {"ref_kind": "baseline_node", "ref_id": node_a},
            {"ref_kind": "baseline_node", "ref_id": node_b},
        ]
    }
    key = f"input-original-{fault}"
    accepted = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=key), json=body
    )
    operation_id = accepted.json()["operation_id"]
    harness = build_history_compare_harness(
        tmp_path / f"input-harness-{fault}",
        db_path=db_path,
        artifact_store=store._store,
        idempotency_key=key,
        seed_acceptance=False,
        existing_operation_id=operation_id,
    )
    for handler in (
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    ):
        run_through_step(harness, handler)

    def altered_metadata(raw: bytes) -> object:
        document = json.loads(raw)
        if fault == "role":
            document["inputs"][0]["role"] = "wrong-node"
        else:
            pair = document["pairs"][0]
            pair["before_input_index"], pair["current_input_index"] = (
                pair["current_input_index"],
                pair["before_input_index"],
            )
        semantic_keys = {
            "bundle_contract_version",
            "bundle_profile",
            "closure",
            "diagnostics",
            "failed_pairs",
            "inputs",
            "pairs",
            "status",
        }
        document["bundle_digest"] = raw_blob_digest(
            canonicalize_json_value({key: document[key] for key in semantic_keys})
        ).value
        return real_reader(canonicalize_json_value(document))

    monkeypatch.setattr(bundle_download, "read_bundle_transport_metadata", altered_metadata)
    for suffix in ("", "/bundle"):
        result = env.client.get(
            f"/v1/history-compares/{operation_id}{suffix}", headers=env.auth_headers()
        )
        assert result.status_code == 503
        assert result.json()["code"] == "HISTORY_INTEGRITY_FAILURE"
        assert result.json()["message"] == "history bundle input binding disagrees"
    replay = env.client.post(
        "/v1/history-compares", headers=env.auth_headers(idempotency_key=key), json=body
    )
    assert replay.status_code == 503
    assert replay.json()["message"] == "history bundle input binding disagrees"
