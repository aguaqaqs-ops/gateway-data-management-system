"""SQLite submit repository roundtrip and CAS tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.submission.errors import SubmitAttemptVersionConflict
from gateway_backend.domain.submission.errors import SubmitOccupancyConflict
from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    Submission,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def _sample_attempt(*, operation_id: str = "op-submit-1") -> SubmitAttempt:
    return SubmitAttempt(
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=1,
        repository_expected_commit_id="commit-main",
        canonical_business_digest="sha256:canonical",
        source_digest="d-source",
        snapshot_digest="d-snapshot",
        source_artifact_refs=("initial-1",),
        snapshot_table_artifact_refs=("snap-1",),
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest="d-closure",
        canonicalization_manifest_ref=None,
        canonicalization_manifest_digest=None,
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:fp",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id=operation_id,
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by="actor-1",
        created_at=TS0,
    )


def _seed_operation(db_path: Path, operation_id: str) -> None:
    from gateway_backend.operations import (
        OPERATION_RUNTIME_CONTRACT_VERSION,
        OperationRecord,
        OperationStatus,
        StepRecord,
        StepStatus,
    )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        operation = OperationRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            operation_id=operation_id,
            job_kind="backend-vnext/submit",
            job_contract_version="backend-vnext/submit/v1",
            job_payload=b"{}",
            job_payload_ref=None,
            business_refs=(),
            artifact_refs=(),
            repository_operation_id=None,
            checkpoint_ref=None,
            ready_closure_ref=None,
            status=OperationStatus.QUEUED,
            diagnostic=None,
            cancel_requested=False,
            created_at=TS0,
            updated_at=TS0,
            completed_at=None,
            optimistic_version=0,
        )
        step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=f"{operation_id}-step-1",
            operation_id=operation_id,
            step_name="prepare_import",
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=TS0,
            updated_at=TS0,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)


def _seed_workspace(db_path: Path, workspace_id: str = "ws-1") -> None:
    from gateway_backend.domain.workspace.models import Workspace, WorkspaceState

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = Workspace(
            workspace_id=workspace_id,
            owner_actor_id="actor-1",
            gateway_device_external_key="device-1",
            business_project_id="project-1",
            repository_id="repo-1",
            state=WorkspaceState.OPEN,
            generation=1,
            optimistic_version=0,
            current_upload_revision_id="ur-1",
            current_preview_result_id="pr-1",
            created_at=TS0,
            updated_at=TS0,
        )
        unit_of_work.connection.execute(
            """
            INSERT INTO workspace_records (
                workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
                repository_id, state, generation, optimistic_version, current_upload_revision_id,
                current_preview_result_id, created_at_us, updated_at_us, closed_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                workspace.workspace_id,
                workspace.owner_actor_id,
                workspace.gateway_device_external_key,
                workspace.business_project_id,
                workspace.repository_id,
                workspace.state.value,
                workspace.generation,
                workspace.optimistic_version,
                workspace.current_upload_revision_id,
                workspace.current_preview_result_id,
                1_718_240_400_000_000,
                1_718_240_400_000_000,
            ),
        )


def test_submit_attempt_roundtrip_and_cas_conflict(db_path: Path) -> None:
    _seed_workspace(db_path)
    _seed_operation(db_path, "op-submit-1")
    attempt = _sample_attempt()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_idempotency(
            SubmitAcceptanceRecord(
                workspace_id="ws-1",
                idempotency_key="accept-key-1",
                request_fingerprint="sha256:fp",
                submit_attempt_id="sa-1",
            )
        )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        loaded = unit_of_work.submission.get_submit_attempt("sa-1")
        record = unit_of_work.submission.find_submit_idempotency("ws-1", "accept-key-1")
    assert loaded == attempt
    assert record is not None
    assert record.submit_attempt_id == "sa-1"

    updated = replace(attempt, optimistic_version=1, state=SubmitAttemptState.ABORTED, abort_code="IMPORT_REJECTED", aborted_at=TS0)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.cas_update_attempt(updated, expected_version=0)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        with pytest.raises(SubmitAttemptVersionConflict):
            unit_of_work.submission.cas_update_attempt(updated, expected_version=0)


def test_submission_and_occupancy_roundtrip(db_path: Path) -> None:
    _seed_workspace(db_path)
    _seed_operation(db_path, "op-submit-1")
    attempt = _sample_attempt()
    submission = Submission(
        submission_id="sub-1",
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        based_on_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        repository_commit_id="commit-new",
        canonical_business_digest="sha256:canonical",
        source_artifact_refs=("initial-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_raw_sha256="sha256:package",
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=TS0,
    )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_submission(submission)
        unit_of_work.submission.insert_workspace_attempt_occupancy(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
        )
        unit_of_work.submission.insert_repository_occupancy(
            RepositorySubmitOccupancy(
                repository_id="repo-1",
                workspace_id="ws-1",
                submit_attempt_id="sa-1",
                business_baseline_node_id="node-1",
                baseline_head_version=1,
                acquired_at=TS0,
            )
        )
        unit_of_work.submission.switch_workspace_occupancy_to_submission(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
            submission_id="sub-1",
        )
        unit_of_work.submission.delete_repository_occupancy(
            repository_id="repo-1",
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
            business_baseline_node_id="node-1",
            baseline_head_version=1,
        )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        loaded_submission = unit_of_work.submission.get_submission_by_attempt("sa-1")
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy("ws-1")
        repository_occupancy = unit_of_work.submission.get_repository_occupancy("repo-1")

    assert loaded_submission == submission
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submission_id == "sub-1"
    assert workspace_occupancy.active_submit_attempt_id is None
    assert repository_occupancy is None


def _sample_submission() -> Submission:
    return Submission(
        submission_id="sub-1",
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        based_on_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        repository_commit_id="commit-new",
        canonical_business_digest="sha256:canonical",
        source_artifact_refs=("initial-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_raw_sha256="sha256:package",
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=TS0,
    )


def test_submission_occupancy_delete_succeeds_for_matching_owner(db_path: Path) -> None:
    _seed_workspace(db_path)
    _seed_operation(db_path, "op-submit-1")
    attempt = _sample_attempt()
    submission = _sample_submission()
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_submission(submission)
        unit_of_work.submission.insert_workspace_attempt_occupancy(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
        )
        unit_of_work.submission.switch_workspace_occupancy_to_submission(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
            submission_id="sub-1",
        )
        unit_of_work.submission.delete_workspace_submission_occupancy(
            "ws-1",
            expected_submission_id="sub-1",
        )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy("ws-1")
    assert workspace_occupancy is None


def test_submission_occupancy_delete_rejects_mismatched_owner(db_path: Path) -> None:
    _seed_workspace(db_path)
    _seed_operation(db_path, "op-submit-1")
    attempt = _sample_attempt()
    submission = _sample_submission()
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_submission(submission)
        unit_of_work.submission.insert_workspace_attempt_occupancy(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
        )
        unit_of_work.submission.switch_workspace_occupancy_to_submission(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
            submission_id="sub-1",
        )
        with pytest.raises(SubmitOccupancyConflict, match="workspace submission occupancy delete"):
            unit_of_work.submission.delete_workspace_submission_occupancy(
                "ws-1",
                expected_submission_id="sub-other",
            )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy("ws-1")
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submission_id == "sub-1"


def test_occupancy_delete_rejects_mismatched_owner(db_path: Path) -> None:
    _seed_workspace(db_path)
    _seed_operation(db_path, "op-submit-1")
    attempt = _sample_attempt()
    occupancy = RepositorySubmitOccupancy(
        repository_id="repo-1",
        workspace_id="ws-1",
        submit_attempt_id="sa-1",
        business_baseline_node_id="node-1",
        baseline_head_version=1,
        acquired_at=TS0,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_workspace_attempt_occupancy(
            workspace_id="ws-1",
            submit_attempt_id="sa-1",
        )
        unit_of_work.submission.insert_repository_occupancy(occupancy)
        with pytest.raises(SubmitOccupancyConflict, match="workspace submit occupancy delete"):
            unit_of_work.submission.delete_workspace_occupancy(
                "ws-1",
                expected_submit_attempt_id="sa-other",
            )
        with pytest.raises(SubmitOccupancyConflict, match="repository submit occupancy delete"):
            unit_of_work.submission.delete_repository_occupancy(
                repository_id="repo-1",
                workspace_id="ws-1",
                submit_attempt_id="sa-other",
                business_baseline_node_id="node-1",
                baseline_head_version=1,
            )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy("ws-1")
        repository_occupancy = unit_of_work.submission.get_repository_occupancy("repo-1")
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submit_attempt_id == "sa-1"
    assert repository_occupancy is not None
    assert repository_occupancy.submit_attempt_id == "sa-1"


MALFORMED_JSON_SHAPES = (
    (
        "string-list-integer-item",
        lambda: _decode_string_list(json.dumps(["ok", 123]).encode("utf-8")),
        "string list items must be strings",
    ),
    (
        "string-list-null-item",
        lambda: _decode_string_list(json.dumps(["ok", None]).encode("utf-8")),
        "string list items must be strings",
    ),
    (
        "backend-ref-integer-id",
        lambda: _decode_backend_artifact_ref(_artifact_ref_bytes(artifact_id=123)),
        "artifact_id must be a non-empty string",
    ),
    (
        "backend-ref-bool-size",
        lambda: _decode_backend_artifact_ref(_artifact_ref_bytes(size_bytes=True)),
        "size_bytes must be an integer",
    ),
    (
        "backend-ref-extra-key",
        lambda: _decode_backend_artifact_ref(
            json.dumps(
                {
                    "artifact_id": "a",
                    "media_type": "application/octet-stream",
                    "size_bytes": 1,
                    "raw_sha256": "sha256:x",
                    "extra": "no",
                }
            ).encode("utf-8")
        ),
        "keys must match exactly",
    ),
    (
        "backend-ref-missing-key",
        lambda: _decode_backend_artifact_ref(
            json.dumps(
                {
                    "artifact_id": "a",
                    "media_type": "application/octet-stream",
                    "size_bytes": 1,
                }
            ).encode("utf-8")
        ),
        "keys must match exactly",
    ),
    (
        "repository-ref-string-size",
        lambda: _decode_repository_artifact_ref(_artifact_ref_bytes(size_bytes="1")),
        "size_bytes must be an integer",
    ),
)


def _artifact_ref_bytes(**overrides: object) -> bytes:
    document: dict[str, object] = {
        "artifact_id": "a",
        "media_type": "application/octet-stream",
        "size_bytes": 1,
        "raw_sha256": "sha256:x",
    }
    document.update(overrides)
    return json.dumps(document).encode("utf-8")


def _decode_string_list(payload: bytes) -> object:
    from gateway_backend.infrastructure.control_db.sqlite_submission import _decode_string_list

    return _decode_string_list(payload)


def _decode_backend_artifact_ref(value: bytes) -> object:
    from gateway_backend.infrastructure.control_db.sqlite_submission import _decode_backend_artifact_ref

    return _decode_backend_artifact_ref(value)


def _decode_repository_artifact_ref(value: bytes) -> object:
    from gateway_backend.infrastructure.control_db.sqlite_submission import (
        _decode_repository_artifact_ref,
    )

    return _decode_repository_artifact_ref(value)


@pytest.mark.parametrize(("name", "decode", "match"), MALFORMED_JSON_SHAPES)
def test_submit_json_decoders_reject_malformed_shapes(
    name: str,
    decode: object,
    match: str,
) -> None:
    del name
    with pytest.raises(ValueError, match=match):
        assert callable(decode)
        decode()
