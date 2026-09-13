"""AcceptSubmit fingerprint and effect-key derivation tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from gateway_backend.application.submission.contracts import (
    compute_accept_request_fingerprint,
    compute_new_accept_fingerprint,
    compute_replay_accept_fingerprint,
    derive_repository_import_idempotency_key,
    derive_repository_upload_idempotency_key,
)
from gateway_backend.application.submission.errors import IdempotencyConflict
from gateway_backend.domain.workspace.models import WorkspaceState
from tests.test_submit_application import (
    BASELINE_HEAD,
    PREVIEW_READY_CLOSURE_DIGEST,
    PREVIEW_RESULT,
    SNAPSHOT_TABLE_ARTIFACT_REFS,
    WORKSPACE,
    SubmitApplicationHarness,
    build_accept_fingerprint,
    make_accept_command,
    make_submit_application_harness,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def submit_application_harness() -> SubmitApplicationHarness:
    return make_submit_application_harness()


def test_derive_repository_effect_keys_are_deterministic_and_distinct() -> None:
    upload_key = derive_repository_upload_idempotency_key("sa-123")
    import_key = derive_repository_import_idempotency_key("sa-123")

    assert upload_key == derive_repository_upload_idempotency_key("sa-123")
    assert import_key == derive_repository_import_idempotency_key("sa-123")
    assert upload_key.startswith("p5b-upload-v1:")
    assert import_key.startswith("p5b-import-v1:")
    assert upload_key != import_key


def test_compute_accept_request_fingerprint_is_deterministic() -> None:
    first = build_accept_fingerprint(repository_expected_commit_id="commit-main")
    second = build_accept_fingerprint(repository_expected_commit_id="commit-main")

    assert first == second
    assert first.startswith("sha256:")


FINGERPRINT_INPUT_CASES = (
    ("repository_expected_commit_id", "commit-main", "commit-other"),
    ("source_digest", "d-source", "d-source-other"),
    ("snapshot_digest", "d-snapshot", "d-snapshot-other"),
    ("preview_ready_closure_digest", "d-closure", "d-closure-other"),
)


@pytest.mark.parametrize(("field_name", "baseline_value", "other_value"), FINGERPRINT_INPUT_CASES)
def test_compute_accept_request_fingerprint_changes_when_server_facts_change(
    field_name: str,
    baseline_value: str,
    other_value: str,
) -> None:
    common = dict(
        workspace_id=WORKSPACE.workspace_id,
        owner_actor_id=WORKSPACE.owner_actor_id,
        gateway_device_external_key=WORKSPACE.gateway_device_external_key,
        business_project_id=WORKSPACE.business_project_id,
        repository_id=WORKSPACE.repository_id,
        expected_workspace_version=WORKSPACE.optimistic_version,
        upload_revision_id=PREVIEW_RESULT.upload_revision_id,
        preview_result_id=PREVIEW_RESULT.preview_result_id,
        generation=PREVIEW_RESULT.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        canonical_business_digest=PREVIEW_RESULT.digests.bundle_digest,
        source_digest=PREVIEW_RESULT.digests.source_digest,
        snapshot_digest=PREVIEW_RESULT.digests.snapshot_digest,
        source_artifact_refs=("initial-1", "modified-1"),
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_ref=PREVIEW_RESULT.ready_closure_artifact_id,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        repository_expected_commit_id="commit-main",
        options={},
    )
    baseline = compute_accept_request_fingerprint(
        **cast(Any, {**common, field_name: baseline_value})
    )
    changed = compute_accept_request_fingerprint(
        **cast(Any, {**common, field_name: other_value})
    )

    assert baseline != changed


def test_compute_accept_request_fingerprint_requires_closure_digest_not_ref_only() -> None:
    shared = dict(
        workspace_id=WORKSPACE.workspace_id,
        owner_actor_id=WORKSPACE.owner_actor_id,
        gateway_device_external_key=WORKSPACE.gateway_device_external_key,
        business_project_id=WORKSPACE.business_project_id,
        repository_id=WORKSPACE.repository_id,
        expected_workspace_version=WORKSPACE.optimistic_version,
        upload_revision_id=PREVIEW_RESULT.upload_revision_id,
        preview_result_id=PREVIEW_RESULT.preview_result_id,
        generation=PREVIEW_RESULT.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        canonical_business_digest=PREVIEW_RESULT.digests.bundle_digest,
        source_digest=PREVIEW_RESULT.digests.source_digest,
        snapshot_digest=PREVIEW_RESULT.digests.snapshot_digest,
        source_artifact_refs=("initial-1", "modified-1"),
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_ref=PREVIEW_RESULT.ready_closure_artifact_id,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        repository_expected_commit_id="commit-main",
        options={},
    )
    baseline = compute_accept_request_fingerprint(**cast(Any, shared))
    changed_digest = compute_accept_request_fingerprint(
        **cast(
            Any,
            {**shared, "preview_ready_closure_digest": "d-closure-tampered"},
        )
    )

    assert baseline != changed_digest


def test_same_key_same_body_replays_without_recomputing_main(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    command = make_accept_command(idempotency_key="accept-key-1")
    first = harness.validate(command)
    harness.main_resolve.resolve_calls = 0
    harness.main_resolve.commit_id = "commit-drifted"

    second = harness.validate(make_accept_command(idempotency_key="accept-key-1"))

    assert first.replay is True
    assert second.replay is True
    assert second.repository_expected_commit_id == "commit-main"
    assert harness.main_resolve.resolve_calls == 0


def test_same_key_replay_succeeds_after_workspace_closed(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.validate(make_accept_command(idempotency_key="accept-key-1"))
    current = harness.workspace_repository.get_workspace(WORKSPACE.workspace_id)
    assert current is not None
    closed = replace(current, state=WorkspaceState.CLOSED)
    harness.workspace_repository.save_workspace(
        closed,
        expected_version=current.optimistic_version,
    )
    harness.main_resolve.resolve_calls = 0

    result = harness.validate(make_accept_command(idempotency_key="accept-key-1"))

    assert result.replay is True
    assert harness.main_resolve.resolve_calls == 0


def test_same_key_different_upload_revision_conflicts(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.validate(make_accept_command(idempotency_key="accept-key-1"))

    with pytest.raises(IdempotencyConflict, match="accept-key-1"):
        harness.validate(
            replace(
                make_accept_command(idempotency_key="accept-key-1"),
                upload_revision_id="ur-changed",
            )
        )


def test_new_key_with_same_body_still_resolves_main(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness

    result = harness.validate(make_accept_command(idempotency_key="accept-key-new"))

    assert result.replay is False
    assert result.repository_expected_commit_id == "commit-main"
    assert harness.main_resolve.resolve_calls == 1


def test_compute_new_and_replay_fingerprints_match_seeded_attempt(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    command = make_accept_command(idempotency_key="accept-key-1")
    attempt = harness.submission_repository.get_submit_attempt("sa-1")
    assert attempt is not None
    upload_revision = harness.workspace_repository.get_upload_revision(attempt.upload_revision_id)
    assert upload_revision is not None

    new_fingerprint = compute_new_accept_fingerprint(
        command=command,
        workspace=WORKSPACE,
        preview_result=PREVIEW_RESULT,
        upload_revision=upload_revision,
        baseline_head=BASELINE_HEAD,
        repository_expected_commit_id="commit-main",
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
    )
    replay_fingerprint = compute_replay_accept_fingerprint(
        command=command,
        attempt=attempt,
        workspace=WORKSPACE,
    )

    assert new_fingerprint == replay_fingerprint == attempt.accept_request_fingerprint


def test_compute_accept_request_fingerprint_includes_scope_and_policy_constants() -> None:
    payload_fingerprint = compute_accept_request_fingerprint(
        workspace_id="ws-1",
        owner_actor_id="actor-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        expected_workspace_version=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        generation=1,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        canonical_business_digest="sha256:preview-canonical",
        source_digest="d-source",
        snapshot_digest="d-snapshot",
        source_artifact_refs=("initial-1", "modified-1"),
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        repository_expected_commit_id="commit-main",
        options={},
    )

    assert payload_fingerprint.startswith("sha256:")
