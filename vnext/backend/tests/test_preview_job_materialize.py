"""Preview materialize_inputs integration tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from gateway_backend.application.checkpoints import (
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
)
from gateway_backend.application.preview_jobs import (
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION,
    PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
    PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
    PREVIEW_STEP_ASSEMBLE,
    PreviewJobError,
    decode_preview_payload,
)
from gateway_backend.application.workspace.preview import build_preview_job_payload
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.capabilities.storage_projection import open_canonicalization_manifest
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactRole
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus, StepStatus
from gateway_backend.operations.worker import ExecutorAcknowledgment
from tests.support.preview_job_harness import (
    IDEMPOTENCY_KEY,
    REPOSITORY_ID,
    WORKSPACE_ID,
    PreviewJobHarness,
    build_preview_harness,
    claim_next_step,
    decode_payload_object,
    insert_preview_operation,
    run_claimed_handler,
    step_id_for,
    store_source_package,
)
from tests.support.canonical_metadata import (
    CatalogCommitCanonicalMetadataPort,
    MetadataControlDbUnitOfWork,
    metadata_for_catalog,
)
from tests.support.table_rules import _runtime_comparison_ruleset_digest

pytestmark = pytest.mark.integration

DETERMINISTIC_CATALOG_FAILURE_CASES = (
    ("RESPONSE_LIMIT_EXCEEDED", "REPOSITORY_CATALOG_LOAD_FAILED"),
)


def _materialized_side_documents(
    job_state: Mapping[str, object],
    harness: PreviewJobHarness,
) -> dict[str, object]:
    raw_ref = job_state.get("materialized_sides_ref")
    assert isinstance(raw_ref, dict)
    state_document = load_checkpoint_state_artifact(
        harness.artifact_store,
        artifact_ref_from_dict(raw_ref),
        document_type=PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
        contract_version=PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
    )
    sides = state_document.get("sides")
    assert isinstance(sides, dict)
    return sides


def test_materialize_uses_frozen_baseline_exact_commit(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    harness.seed_workspace()
    payload = decode_preview_payload(decode_payload_object(harness))
    from gateway_backend.application.preview_jobs import _materialize_all_sides

    _materialize_all_sides(payload, harness.deps)
    assert harness.baseline_provider.last_session is not None
    assert harness.baseline_provider.last_session.pinned_commit_hash() == "commit-base"


def test_initial_baseline_rejects_repository_user_tables(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    harness.seed_workspace()
    metadata_port = CatalogCommitCanonicalMetadataPort(
        {
            (REPOSITORY_ID, "commit-base"): metadata_for_catalog(
                harness.baseline_provider.catalog,
                initial=True,
            )
        }
    )

    def control_uow_factory() -> MetadataControlDbUnitOfWork:
        return MetadataControlDbUnitOfWork(harness.db_path, metadata_port)

    deps = replace(
        harness.deps,
        control_transaction_factory=control_uow_factory,
    )
    payload = decode_preview_payload(decode_payload_object(harness))
    from gateway_backend.application.preview_jobs import _materialize_all_sides

    with pytest.raises(PreviewJobError) as error:
        _materialize_all_sides(payload, deps)
    assert error.value.diagnostic_code == "INITIAL_BASELINE_NOT_EMPTY"


def test_full_materialize_publishes_checkpoint_and_assemble_successor(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    operation_id = "op-materialize-full"
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, PREVIEW_STEP_ASSEMBLE))
    assert materialize_step.status is StepStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    assert assemble_step.status is StepStatus.PENDING
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = _materialized_side_documents(envelope.job_state, harness)
    assert {"BASELINE", "INITIAL", "MODIFIED"}.issubset(sides)
    for role in ("BASELINE", "INITIAL", "MODIFIED"):
        side_document = sides[role]
        assert isinstance(side_document, dict)
        assert side_document["contract_version"] == PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION
    canonical = envelope.job_state["canonical_preview"]
    assert isinstance(canonical, dict)
    assert canonical["baseline_canonical_state_digest"].startswith("sha256:")
    assert canonical["modified_canonical_state_digest"].startswith("sha256:")
    assert canonical["storage_projection_ruleset_digest"].startswith("sha256:")
    closure_ref = artifact_ref_from_dict(canonical["canonical_table_set_closure_ref"])
    closure = json.loads(harness.artifact_store.locate(closure_ref).decode("utf-8"))
    assert [item["table_name"] for item in closure["tables"]] == ["t"]
    manifest_ref = artifact_ref_from_dict(canonical["canonicalization_manifest_ref"])
    manifest = open_canonicalization_manifest(harness.artifact_store, manifest_ref)
    assert manifest.manifest_digest is not None
    assert manifest.manifest_digest.value == canonical["canonicalization_manifest_digest"]
    assert tuple(table.name for table in manifest.tables) == ("t",)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.protection.is_protected(materialize_step.checkpoint_ref.artifact_id)
        raw_sides_ref = envelope.job_state["materialized_sides_ref"]
        assert isinstance(raw_sides_ref, dict)
        sides_ref = artifact_ref_from_dict(raw_sides_ref)
        assert unit_of_work.protection.is_protected(sides_ref.artifact_id)


def test_modified_only_reuses_baseline_for_effective_initial(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    harness.seed_workspace()
    operation_id = "op-materialize-modified-only"
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = _materialized_side_documents(envelope.job_state, harness)
    assert sides.get("initial_reuses_baseline") is True
    baseline_side = sides["BASELINE"]
    initial_side = sides["INITIAL"]
    assert isinstance(baseline_side, dict) and isinstance(initial_side, dict)
    assert baseline_side["snapshot_digest"] == initial_side["snapshot_digest"]


def test_materialize_fails_when_upload_package_is_invalid(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    harness.seed_workspace()
    bad_binding = store_source_package(
        harness.artifact_store,
        b"not-a-valid-package",
        artifact_id="bad-package",
    )
    upload_revision = replace(
        harness.upload_revision,
        source_artifacts={SourceArtifactRole.MODIFIED: bad_binding},
    )
    harness.upload_revision = upload_revision
    harness.job_payload = build_preview_job_payload(
        workspace_id=WORKSPACE_ID,
        upload_revision=upload_revision,
        repository_id=REPOSITORY_ID,
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=3,
        idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    payload = decode_preview_payload(decode_payload_object(harness))
    from gateway_backend.application.preview_jobs import _materialize_all_sides

    with pytest.raises(PreviewJobError, match="uploaded"):
        _materialize_all_sides(payload, harness.deps)


@pytest.mark.parametrize(
    ("wire_code", "expected_diagnostic_code"),
    DETERMINISTIC_CATALOG_FAILURE_CASES,
)
def test_deterministic_catalog_failure_is_publicly_diagnostic(
    tmp_path: Path,
    wire_code: str,
    expected_diagnostic_code: str,
) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    harness.baseline_provider.catalog_error_message = (
        f"catalog read failed ({wire_code}: response exceeded the configured limit)"
    )
    operation_id = "op-catalog-response-limit"
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)

    acknowledgment = run_claimed_handler(
        harness,
        PREVIEW_MATERIALIZE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(operation_id)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert persisted.status is OperationStatus.FAILED
    assert persisted.diagnostic is not None
    assert persisted.diagnostic.code == expected_diagnostic_code
    assert wire_code in persisted.diagnostic.message
