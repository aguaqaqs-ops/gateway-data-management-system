"""Preview assemble_preview closure and pair topology tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_STEP_PUBLISH,
    compute_baseline_canonical_bundle_digest,
)
from gateway_backend.capabilities.table_rules.contracts import RULESET_VERSION
from gateway_backend.domain.workspace.models import BaselineHead, InputCompleteness
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import StepStatus
from tests.support.preview_job_harness import (
    BASELINE_HEAD,
    REPOSITORY_ID,
    PreviewJobHarness,
    build_preview_harness,
    claim_next_step,
    insert_preview_operation,
    run_claimed_handler,
    step_id_for,
)

pytestmark = [pytest.mark.unit, pytest.mark.integration]


def _run_materialize(harness: PreviewJobHarness, operation_id: str) -> None:
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)


def test_full_assemble_checkpoint_contains_dual_pair_closure(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    operation_id = "op-assemble-full"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
        publish_step = unit_of_work.operations.get_step(step_id_for(operation_id, PREVIEW_STEP_PUBLISH))
    assert assemble_step.status is StepStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    assert publish_step.status is StepStatus.PENDING
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    assert assemble_state["pair_ids"] == ["baseline_to_initial", "initial_to_modified"]
    assert envelope.job_state["ready_closure_artifact_id"]
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    assert required_refs


def test_modified_only_assemble_checkpoint_contains_single_pair(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    operation_id = "op-assemble-modified-only"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
    checkpoint_ref = assemble_step.checkpoint_ref
    assert checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    assert assemble_state["pair_ids"] == ["initial_to_modified"]
    assert assemble_state["input_completeness"] == InputCompleteness.MODIFIED_ONLY.value
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    assert required_refs


def test_full_canonical_noop_bundle_digest_matches_baseline_port(tmp_path: Path) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=InputCompleteness.FULL,
        canonical_noop=True,
    )
    operation_id = "op-assemble-full-noop"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    preview_bundle_digest = assemble_state["digests"]["bundle_digest"]
    assert isinstance(preview_bundle_digest, str)

    port_bundle_digest = compute_baseline_canonical_bundle_digest(
        repository_id=REPOSITORY_ID,
        baseline_head=BaselineHead(
            business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
            baseline_head_version=BASELINE_HEAD.baseline_head_version,
        ),
        input_completeness=InputCompleteness.FULL,
        ruleset_version=RULESET_VERSION,
        provider_factory=harness.deps.repository_provider_factory,
        store=harness.artifact_store,
    )
    assert preview_bundle_digest == port_bundle_digest


def test_assemble_resumes_from_checkpoint_when_repository_is_unavailable(tmp_path: Path) -> None:
    from gateway_backend.application.preview_jobs import (
        PREVIEW_ASSEMBLE_HANDLER,
        PreviewRuntimeDependencies,
        build_assemble_preview_handler,
    )

    harness = build_preview_harness(tmp_path)
    operation_id = "op-assemble-offline-repo"
    _run_materialize(harness, operation_id)

    def unavailable(repository_id: str, commit_id: str) -> object:
        del repository_id, commit_id
        raise RuntimeError("repository is unavailable")

    harness.handlers[PREVIEW_ASSEMBLE_HANDLER] = build_assemble_preview_handler(
        PreviewRuntimeDependencies(
            artifact_store=harness.artifact_store,
            repository_provider_factory=unavailable,  # type: ignore[arg-type]
            baseline_head_read=harness.baseline_head_read,
            control_transaction_factory=harness.control_transaction_factory,
        )
    )
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
    assert assemble_step.status is StepStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None


@pytest.mark.parametrize(
    ("case_id", "side_document", "match"),
    (
        ("missing_tables", {"snapshot": {}}, "closed table refs"),
        ("null_tables", {"tables": None, "snapshot": {}}, "closed table refs"),
        ("invalid_tables_type", {"tables": "bad", "snapshot": {}}, "table refs must be a list"),
    ),
)
def test_materialize_checkpoint_rejects_invalid_empty_shapes(
    case_id: str,
    side_document: dict[str, object],
    match: str,
) -> None:
    del case_id
    from gateway_backend.application.payloads import CheckpointDecodeError
    from gateway_backend.application.preview_jobs import _sides_from_materialize_checkpoint
    from gateway_backend.artifacts import InMemoryArtifactStore

    with pytest.raises(CheckpointDecodeError, match=match):
        _sides_from_materialize_checkpoint(
            {
                "sides": {
                    "BASELINE": side_document,
                    "INITIAL": side_document,
                    "MODIFIED": side_document,
                }
            },
            InMemoryArtifactStore(),
        )


@pytest.mark.parametrize(
    "input_completeness",
    [InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY],
    ids=["full", "modified_only"],
)
def test_empty_baseline_assemble_produces_ready_closure_and_matching_digest(
    tmp_path: Path,
    input_completeness: InputCompleteness,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=input_completeness,
        empty_baseline=True,
    )
    operation_id = f"op-assemble-empty-{input_completeness.value.lower()}"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
    assert assemble_step.status is StepStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state["assemble_state"]
    assert isinstance(assemble_state, dict)
    assert assemble_state["required_refs"]
    if input_completeness is InputCompleteness.FULL:
        assert assemble_state["pair_ids"] == ["baseline_to_initial", "initial_to_modified"]
    else:
        assert assemble_state["pair_ids"] == ["initial_to_modified"]
    port_bundle_digest = compute_baseline_canonical_bundle_digest(
        repository_id=REPOSITORY_ID,
        baseline_head=BaselineHead(
            business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
            baseline_head_version=BASELINE_HEAD.baseline_head_version,
        ),
        input_completeness=input_completeness,
        ruleset_version=RULESET_VERSION,
        provider_factory=harness.deps.repository_provider_factory,
        store=harness.artifact_store,
    )
    assert isinstance(port_bundle_digest, str)
    assert port_bundle_digest.startswith("sha256:")
