"""Submission-bound review reads: current authority, exact closure and terminal retention."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.application.submission.finalize_transaction import finalize_submit_transaction
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.domain.workspace.models import InputCompleteness
from gateway_backend.artifacts.store import ArtifactUnavailableError
from tests.support.http_workspace_harness import create_workspace_http_environment, InMemoryBundleReader
from tests.support.review_result_fixtures import closed_review_preview, review_artifact_refs
from tests.support.preview_fixtures import make_canonical_artifact_fixture
from tests.support.workspace_fixtures import make_identity
from tests.test_submit_transactions import seed_submit_ready_workspace, _seed_effect_pending_attempt
from tests.test_submit_finalize import _request

pytestmark = pytest.mark.unit

_RESULT_ENDPOINTS = ("result", "result/bundle")
_ACCESS_CASES: tuple[tuple[str, str, frozenset[str], str, str, int], ...] = (
    ("reviewer", "reviewer", frozenset({"review_submission"}), "device-1", "project-1", 200),
    ("own-withdraw", "actor-1", frozenset({"withdraw_own_submission"}), "device-1", "project-1", 200),
    ("other-withdraw", "other", frozenset({"withdraw_own_submission"}), "device-1", "project-1", 404),
    ("denied", "actor-1", frozenset(), "device-1", "project-1", 403),
    ("device", "reviewer", frozenset({"review_submission"}), "other-device", "project-1", 404),
    ("project", "reviewer", frozenset({"review_submission"}), "device-1", "other-project", 404),
)


def _environment(tmp_path: Path, *, identity: Any = None,
    input_completeness: InputCompleteness = InputCompleteness.FULL) -> tuple[Any, Any]:
    env = create_workspace_http_environment(tmp_path,
        identity=identity or make_identity(actor_id="reviewer", permissions=frozenset({"review_submission"})))
    seed = seed_submit_ready_workspace(env.db_path, input_completeness=input_completeness)
    canonical = make_canonical_artifact_fixture(seed.workspace.repository_id)
    preview, refs, payloads = closed_review_preview(seed.preview_result, canonical.refs)
    with ControlDbUnitOfWork(env.db_path) as uow:
        uow.connection.execute("UPDATE preview_result_records SET binding=? WHERE preview_result_id=?",
            (preview_result_to_row(preview)[5], preview.preview_result_id))
        uow.set_artifact_protection(refs, owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id, intent="current-preview")
    source_ids = {binding.artifact_id for binding in seed.upload_revision.source_artifacts.values()}
    seed = replace(seed, preview_result=preview, protected_refs=(
        *(ref for ref in seed.protected_refs if ref.artifact_id in source_ids), *refs))
    for ref in refs:
        env.artifact_store.register_bytes(ref, {**canonical.payloads, **payloads}[ref.artifact_id])
    attempt = _seed_effect_pending_attempt(env.db_path, seed)
    with ControlDbUnitOfWork(env.db_path) as uow:
        finalize_submit_transaction(request=_request(env.db_path, seed, attempt), unit_of_work=uow)
    # The fake tar reader is independent of exact metadata preflight in these
    # routing tests. Actual tar framing/integrity stays owned by bundle tests.
    assert isinstance(env.bundle_reader, InMemoryBundleReader)
    env.bundle_reader.register(preview.bundle_artifact_id, "review.tar", b"review-bundle",
        bundle_digest=preview.digests.bundle_digest)
    return env, seed


@pytest.mark.parametrize("endpoint", _RESULT_ENDPOINTS)
@pytest.mark.parametrize("label,actor,permissions,device,project,expected", _ACCESS_CASES,
    ids=[case[0] for case in _ACCESS_CASES])
def test_result_authorizes_current_review_scope_before_artifacts(
    tmp_path: Path, endpoint: str, label: str, actor: str,
    permissions: frozenset[str], device: str, project: str, expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del label
    env, _seed = _environment(tmp_path, identity=make_identity(actor_id=actor,
        permissions=permissions, device_key=device, project_id=project))
    if expected != 200:
        monkeypatch.setattr(env.artifact_store, "read_exact",
            lambda _ref: pytest.fail("unauthorized request read an artifact"))
    response = env.client.get(f"/v1/submissions/sub-1/{endpoint}", headers=env.auth_headers())
    assert response.status_code == expected, response.text


@pytest.mark.parametrize("action", ("REJECT", "WITHDRAW"))
def test_full_result_stays_bound_after_review_release_and_workspace_reuse(tmp_path: Path, action: str) -> None:
    env, seed = _environment(tmp_path)
    path = "/v1/submissions/sub-1/result"
    first = env.client.get(path, headers=env.auth_headers())
    assert first.status_code == 200, first.text
    body = first.json()
    assert [pair["pair_id"] for pair in body["pairs"]] == ["baseline_to_initial", "initial_to_modified"]
    assert body["default_pair_id"] == "initial_to_modified"
    assert body["input_completeness"] == "FULL"
    rejected = env.client.post("/v1/submissions/sub-1/review-events",
        headers=env.auth_headers(idempotency_key="reject"), json={
            "action": action, "expected_review_version": 0, "reason": "redo"})
    assert rejected.status_code == 201, rejected.text
    with ControlDbUnitOfWork(env.db_path) as uow:
        workspace = uow.workspace.get_workspace(seed.workspace.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is None
        uow.workspace.save_workspace(replace(workspace, generation=workspace.generation + 1,
            optimistic_version=workspace.optimistic_version + 1), expected_version=workspace.optimistic_version)
        held = uow.list_artifact_protection_for_owner(owner_kind="submission-review", owner_id="sub-1")
        assert {ref.artifact_id for ref in review_artifact_refs(seed)}.issubset(held)
        submission = uow.submission.get_submission("sub-1")
        assert submission is not None
        assert not uow.list_artifact_protection_for_owner(owner_kind="submit-attempt",
            owner_id=submission.submit_attempt_id)
        assert uow.connection.execute("SELECT count(*) FROM operation_records WHERE job_kind='history-compare'").fetchone()[0] == 0
        uow.connection.execute("UPDATE baseline_head_records SET optimistic_version=optimistic_version+1 WHERE repository_id=?", (seed.workspace.repository_id,))
    for _ in range(2):
        result = env.client.get(path, headers=env.auth_headers())
        assert result.status_code == 200 and result.json() == body


@pytest.mark.parametrize("endpoint", _RESULT_ENDPOINTS)
@pytest.mark.parametrize("fault,code", (("absent", "SUBMISSION_RESULT_UNAVAILABLE"),
    ("corrupt", "SUBMISSION_RESULT_INTEGRITY_FAILURE"),
    ("wrong-pair", "SUBMISSION_RESULT_INTEGRITY_FAILURE"),
    ("wrong-preview", "SUBMISSION_RESULT_INTEGRITY_FAILURE")))
def test_result_missing_corrupt_and_mismatched_never_fall_back(
    tmp_path: Path, endpoint: str, fault: str, code: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    env, seed = _environment(tmp_path)
    if fault in {"absent", "corrupt"}:
        def fail_read(_ref: Any) -> Any:
            if fault == "absent":
                raise ArtifactUnavailableError("missing")
            raise BundleIntegrityError("corrupt")
        monkeypatch.setattr(env.artifact_store, "read_exact", fail_read)
    else:
        preview = seed.preview_result
        if fault == "wrong-pair":
            preview = replace(preview, comparison_pairs=(preview.comparison_pairs[-1],))
        else:
            preview = replace(preview, ready_closure_artifact_id=preview.bundle_artifact_id)
        with ControlDbUnitOfWork(env.db_path) as uow:
            uow.connection.execute("UPDATE preview_result_records SET binding=? WHERE preview_result_id=?",
                (preview_result_to_row(preview)[5], preview.preview_result_id))
    result = env.client.get(f"/v1/submissions/sub-1/{endpoint}", headers=env.auth_headers())
    assert result.status_code == 503 and result.json()["code"] == code, result.text
    with ControlDbUnitOfWork(env.db_path, read_only=True) as uow:
        assert uow.connection.execute("SELECT count(*) FROM operation_records WHERE job_kind='history-compare'").fetchone()[0] == 0


def test_modified_only_result_has_one_bound_pair(tmp_path: Path) -> None:
    env, _seed = _environment(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    result = env.client.get("/v1/submissions/sub-1/result", headers=env.auth_headers())
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["input_completeness"] == "MODIFIED_ONLY"
    assert body["default_pair_id"] == "initial_to_modified"
    assert [pair["pair_id"] for pair in body["pairs"]] == ["initial_to_modified"]


@pytest.mark.parametrize("endpoint", _RESULT_ENDPOINTS)
def test_unknown_result_target_stays_hidden(tmp_path: Path, endpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    env, _seed = _environment(tmp_path)
    monkeypatch.setattr(env.artifact_store, "read_exact", lambda _ref: pytest.fail("unknown target read artifacts"))
    result = env.client.get(f"/v1/submissions/unknown/{endpoint}", headers=env.auth_headers())
    assert result.status_code == 404
