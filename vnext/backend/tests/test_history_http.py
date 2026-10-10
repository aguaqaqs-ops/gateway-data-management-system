"""History HTTP route tests."""

from __future__ import annotations

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
from tests.test_review_transactions import _apply_command, _apply_review, _seed_pending_review_submission
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
    _apply_review(review_seed, _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-history"))
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-readonly"),
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


def test_list_history_returns_integrity_failure_for_corrupt_facts(db_path: Path, tmp_path: Path) -> None:
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


def test_list_history_rejects_disabled_mapping_without_stale_scope_reads(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-scope-http"),
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-cjk-commit"),
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
    submission_node = next(item for item in response.json()["nodes"] if item["node_kind"] == "SUBMISSION")
    assert submission_node["commit_id"] == cjk_commit


@pytest.mark.parametrize(("case_id", "params", "expected_status"), HISTORY_HTTP_QUERY_BOUNDARY_CASES)
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{len(ref_id)}"),
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
    history_env = _history_env(db_path.parent / f"history-ref-{len(ref_id.encode('utf-8'))}", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    assert any(item["ref_id"] == ref_id for item in response.json()["nodes"])


def _tamper_checkpoint_semantically_same_length(
    artifact_store: ArtifactStorePort,
    ref: object,
    *,
    local_store: object | None = None,
) -> None:
    from gateway_backend.application.checkpoints import StepCheckpointEnvelope, load_checkpoint_envelope
    from gateway_backend.artifacts import ArtifactRef
    assert isinstance(ref, ArtifactRef)
    envelope = load_checkpoint_envelope(artifact_store, ref)
    original_bytes = envelope.to_canonical_bytes()
    job_state = dict(envelope.job_state)
    assemble_state = dict(cast(dict[str, object], job_state["assemble_state"]))
    pairs = list(cast(list[object], assemble_state["pairs"]))
    pair0 = dict(cast(dict[str, object], pairs[0]))
    digest = str(pair0["comparison_digest"])
    replacement = "b" if digest[-1] != "b" else "a"
    pair0["comparison_digest"] = digest[:-1] + replacement
    pairs[0] = pair0
    assemble_state["pairs"] = pairs
    job_state["assemble_state"] = assemble_state
    tampered = StepCheckpointEnvelope(
        job_kind=envelope.job_kind,
        step_name=envelope.step_name,
        operation_id=envelope.operation_id,
        job_contract_version=envelope.job_contract_version,
        checkpoint_generation=envelope.checkpoint_generation,
        prior_output_refs=envelope.prior_output_refs,
        job_state=job_state,
    )
    tampered_bytes = tampered.to_canonical_bytes()
    assert len(tampered_bytes) == len(original_bytes)
    if local_store is not None:
        from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

        assert isinstance(local_store, LocalArtifactStore)
        target, _sidecar = local_store._validated_paths(ref.artifact_id)  # noqa: SLF001
        target.write_bytes(tampered_bytes)
        return
    memory_store = cast(InMemoryArtifactStore, artifact_store)
    memory_store._artifacts[ref.artifact_id] = (ref, tampered_bytes)  # noqa: SLF001


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
        permissions=permissions
        or frozenset({"workspace_read", PERMISSION_READ_PROJECT_HISTORY}),
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
    from gateway_backend.application.history.compare_jobs import (
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
                f"history-compare-{operation_id}.bundle",
                payload,
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{case_name}"),
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-byte-boundary"),
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-255-byte"),
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-replay"),
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
    from gateway_backend.application.history.compare_jobs import (
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-succeeded"),
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
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)

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
    from gateway_backend.application.history.compare_jobs import (
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-bundle"),
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
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="history-compare-{operation_id}.bundle"'
    )


def test_get_history_compare_result_returns_queued_shape(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-compare-get"),
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
    from gateway_backend.application.history.compare_jobs import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        history_compare_step_id,
    )
    from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
    from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
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
        local_store = LocalArtifactStore(tmp_path / "artifact-root")
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
    from gateway_backend.application.history.compare_jobs import (
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
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{field}"),
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


def test_integrity_ack_route_requires_internal_bearer(db_path: Path, tmp_path: Path) -> None:
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_MATERIALIZE_HANDLER
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        insert_history_compare_operation,
        run_through_step,
    )

    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)
    harness = build_history_compare_harness(
        tmp_path,
        db_path=db_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-ack-http",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    history_env = _history_env(db_path.parent / "history-integrity-ack", db_path=db_path)
    response = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=history_env.auth_headers(),
        json={
            "acknowledgement_status": "ACKNOWLEDGED",
            "resolution_reference": "ticket-401",
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_integrity_ack_route_acknowledges_incident(db_path: Path, tmp_path: Path) -> None:
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_MATERIALIZE_HANDLER
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        insert_history_compare_operation,
        run_through_step,
    )

    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)
    harness = build_history_compare_harness(
        tmp_path,
        db_path=db_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-ack-200",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    history_env = _history_env(db_path.parent / "history-integrity-ack-200", db_path=db_path)
    response = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=history_env.internal_auth_headers(),
        json={
            "acknowledgement_status": "ACKNOWLEDGED",
            "resolution_reference": "ticket-200",
        },
    )
    assert response.status_code == 200
    assert response.json()["acknowledgement_status"] == "ACKNOWLEDGED"
    assert response.json()["resolution_reference"] == "ticket-200"


def test_integrity_ack_route_rejects_resolution_change(db_path: Path, tmp_path: Path) -> None:
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_MATERIALIZE_HANDLER
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        insert_history_compare_operation,
        run_through_step,
    )

    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)
    harness = build_history_compare_harness(
        tmp_path,
        db_path=db_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-ack-409",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    history_env = _history_env(db_path.parent / "history-integrity-ack-409", db_path=db_path)
    headers = history_env.internal_auth_headers()
    first = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=headers,
        json={
            "acknowledgement_status": "ACKNOWLEDGED",
            "resolution_reference": "ticket-first",
        },
    )
    second = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=headers,
        json={
            "acknowledgement_status": "ACKNOWLEDGED",
            "resolution_reference": "ticket-second",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_history_compare_accept_idempotency_conflict_on_changed_nodes(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-idem-conflict"),
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


def test_integrity_ack_route_replays_same_resolution_reference(db_path: Path, tmp_path: Path) -> None:
    from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_MATERIALIZE_HANDLER
    from tests.support.history_compare_job_harness import (
        build_history_compare_harness,
        insert_history_compare_operation,
        run_through_step,
    )

    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)
    harness = build_history_compare_harness(
        tmp_path,
        db_path=db_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-ack-replay",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    history_env = _history_env(db_path.parent / "history-integrity-ack-replay", db_path=db_path)
    headers = history_env.internal_auth_headers()
    payload = {
        "acknowledgement_status": "ACKNOWLEDGED",
        "resolution_reference": "ticket-replay",
    }
    first = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=headers,
        json=payload,
    )
    second = history_env.client.post(
        f"/v1/history-compares/{harness.operation_id}/integrity-ack",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["resolution_reference"] == "ticket-replay"


def test_accept_history_compare_rejects_pending_integrity_incident(
    db_path: Path,
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    from gateway_backend.application.history.contracts import (
        HISTORY_INTEGRITY_FAILURE_CLASS,
        HISTORY_INTEGRITY_RECOMMENDED_ACTION,
        HistoryCompareIntegrityRecord,
        IntegrityAcknowledgementStatus,
    )

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-integrity-block"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    ts = datetime(2026, 9, 24, tzinfo=UTC)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.history_compare.save_integrity_record(
            HistoryCompareIntegrityRecord(
                incident_id="hci-http-block",
                operation_id="op-other",
                repository_id="repo-1",
                commit_refs=({"commit_id": "commit-b"},),
                failure_class=HISTORY_INTEGRITY_FAILURE_CLASS,
                expected_digest="sha256:" + "a" * 64,
                observed_digest="sha256:" + "b" * 64,
                affected_tables=(),
                recommended_action=HISTORY_INTEGRITY_RECOMMENDED_ACTION,
                first_seen_at=ts,
                last_seen_at=ts,
                acknowledgement_status=IntegrityAcknowledgementStatus.PENDING,
                resolution_reference=None,
                created_at=ts,
                updated_at=ts,
            )
        )
    history_env = _history_env(db_path.parent / "history-integrity-block", db_path=db_path)
    response = history_env.client.post(
        "/v1/history-compares",
        headers=history_env.auth_headers(idempotency_key="compare-integrity-block"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": node_a},
                {"ref_kind": "baseline_node", "ref_id": node_b},
            ]
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "HISTORY_INTEGRITY_UNRESOLVED"


def test_history_compare_cross_scope_node_returns_404_without_disclosure(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    from tests.support.baseline_fixtures import upsert_provisioned_mapping_row

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-cross-scope"),
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
    from gateway_backend.application.history.compare_jobs import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER,
        HISTORY_COMPARE_MATERIALIZE_HANDLER,
        HISTORY_COMPARE_PUBLISH_HANDLER,
    )
    from gateway_backend.bootstrap.composition import LocalArtifactBundleReader
    from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
    from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
    from tests.support.history_compare_job_harness import build_history_compare_harness, run_through_step

    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-local-bundle"),
    )
    node_a, node_b = _seed_compare_nodes(db_path)
    local_store = LocalArtifactStore(tmp_path / "bundle-artifacts")
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
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="history-compare-{operation_id}.bundle"'
    )


def test_accept_history_compare_is_read_only(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-zero-write"),
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
