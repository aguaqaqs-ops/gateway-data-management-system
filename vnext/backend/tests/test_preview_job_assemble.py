"""Preview assemble_preview closure and pair topology tests."""

from __future__ import annotations

from tests.support.artifact_layout import open_test_store

from tests.support.repository_ref_materialization import canonical_schema_digest_for_descriptor

import copy
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest
import gateway_backend.application.preview_jobs as preview_jobs
import gateway_backend.application.pair_pipeline as pair_pipeline

from gateway_backend.application.preview_jobs import PreviewJobError
from gateway_backend.capabilities.bundle_assembly import (
    BundleAssemblyResult,
    BundleAssemblyStatus,
)
from gateway_backend.capabilities.comparison import (
    ComparisonMode, ComparisonPlan, ComparisonRequest, ComparisonTaskSession,
    NativeComparison,
)

from gateway_backend.application.checkpoints import (
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
    PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION,
    PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
    PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
    PREVIEW_PUBLISH_HANDLER,
    PREVIEW_STEP_PUBLISH,
)
from gateway_backend.application.workspace.preview import build_preview_job_payload
from gateway_backend.application.submission.accept_transaction import (
    accept_submit_transaction,
)
from gateway_backend.application.submission.contracts import AcceptSubmitCommand
from gateway_backend.application.submit_registry import submit_job_registry
from gateway_backend.artifacts.computation_cache import CacheOperationOwner, ComputationCachePort
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactRole
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.http.dependencies import ArtifactRefLookupPort
from gateway_backend.http.orchestration.submit_acceptance import load_accept_submit_preflight
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus, StepStatus
from gateway_backend.operations.worker import ExecutorAcknowledgment, ExecutionControl
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.preview_job_harness import (
    BASELINE_HEAD,
    IDEMPOTENCY_KEY,
    INITIAL_SQL,
    MODIFIED_SQL,
    REPOSITORY_ID,
    PreviewJobHarness,
    build_upload_revision,
    build_preview_harness,
    claim_next_step,
    insert_preview_operation,
    run_claimed_handler,
    store_source_package,
    step_id_for,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from tests.test_submit_transactions import RecordingMainResolvePort

pytestmark = [pytest.mark.unit, pytest.mark.integration]


def _run_materialize(harness: PreviewJobHarness, operation_id: str) -> None:
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)


def _read_materialized_sides_document(
    job_state: Mapping[str, object],
    harness: PreviewJobHarness,
) -> dict[str, object]:
    raw_ref = job_state.get("materialized_sides_ref")
    assert isinstance(raw_ref, dict)
    return load_checkpoint_state_artifact(
        harness.artifact_store,
        artifact_ref_from_dict(raw_ref),
        document_type=PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
        contract_version=PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
    )


def _replace_materialized_sides_document(
    job_state: dict[str, object],
    document: dict[str, object],
    harness: PreviewJobHarness,
) -> None:
    ref = put_checkpoint_state_artifact(
        harness.artifact_store,
        document,
        artifact_id_prefix='preview-materialized-sides',
    )
    job_state["materialized_sides_ref"] = artifact_ref_to_dict(ref)


def _preview_assemble_state(
    harness: PreviewJobHarness,
    job_state: Mapping[str, object],
) -> dict[str, object]:
    raw_ref = job_state.get("assemble_state_ref")
    assert isinstance(raw_ref, dict)
    document = load_checkpoint_state_artifact(
        harness.artifact_store,
        artifact_ref_from_dict(raw_ref),
        document_type=PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
        contract_version=PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
    )
    assemble_state = document.get("assemble_state")
    assert isinstance(assemble_state, dict)
    return assemble_state


def _assert_persisted_canonical_preview(assemble_state: dict[str, object], *, full: bool) -> None:
    canonical = assemble_state.get("canonical_preview")
    assert isinstance(canonical, dict)
    assert set(canonical) == {
        "canonical_table_set_closure_ref",
        "canonicalization_manifest_ref",
        "canonicalization_manifest_digest",
        "initial_canonicalization_manifest_ref",
        "initial_canonicalization_manifest_digest",
        "baseline_canonical_state_digest",
        "initial_canonical_state_digest",
        "configuration_facts",
        "modified_canonical_state_digest",
        "storage_projection_ruleset_digest",
        "baseline_is_initial",
    }
    for key in (
        "canonicalization_manifest_digest",
        "baseline_canonical_state_digest",
        "modified_canonical_state_digest",
        "storage_projection_ruleset_digest",
    ):
        value = canonical[key]
        assert isinstance(value, str)
        assert value.startswith("sha256:")
    assert isinstance(canonical["canonical_table_set_closure_ref"], dict)
    assert isinstance(canonical["canonicalization_manifest_ref"], dict)
    assert (canonical["initial_canonicalization_manifest_ref"] is not None) is full
    assert (canonical["initial_canonicalization_manifest_digest"] is not None) is full
    assert type(canonical["baseline_is_initial"]) is bool


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
    assemble_state = _preview_assemble_state(harness, envelope.job_state)
    assert assemble_state["pair_ids"] == ["baseline_to_initial", "initial_to_modified"]
    assert envelope.job_state["ready_closure_artifact_id"]
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    assert required_refs


def test_cancel_during_preview_assembly_loop_leaves_operation_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    operation_id = "op-assemble-cancel-loop"
    _run_materialize(harness, operation_id)
    original = preview_jobs._run_pair_pipeline
    calls = 0

    def run_pair_then_cancel(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            kwargs["control"].request_cancel()
        return result

    monkeypatch.setattr(preview_jobs, "_run_pair_pipeline", run_pair_then_cancel)
    session, control, operation, step = claim_next_step(harness)
    acknowledgment = run_claimed_handler(
        harness,
        PREVIEW_ASSEMBLE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(operation_id)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert calls == 1
    assert persisted.status is OperationStatus.CANCELLED


def test_cancel_inside_pair_pipeline_leaves_operation_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    operation_id = "op-assemble-cancel-pair-pipeline"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    original = pair_pipeline.publish_records_closure_arrow

    def publish_records_then_cancel(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        control.request_cancel()
        return result

    monkeypatch.setattr(pair_pipeline, "publish_records_closure_arrow", publish_records_then_cancel)
    acknowledgment = run_claimed_handler(
        harness,
        PREVIEW_ASSEMBLE_HANDLER,
        session,
        control,
        operation,
        step,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_operation(operation_id)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert persisted.status is OperationStatus.CANCELLED


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
    assemble_state = _preview_assemble_state(harness, envelope.job_state)
    assert assemble_state["pair_ids"] == ["initial_to_modified"]
    assert assemble_state["input_completeness"] == InputCompleteness.MODIFIED_ONLY.value
    required_refs = assemble_state["required_refs"]
    assert isinstance(required_refs, list)
    assert required_refs


def test_assemble_failure_retains_bounded_bundle_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    operation_id = "op-assemble-bundle-failure"
    _run_materialize(harness, operation_id)

    def fail_bundle(*_args: object, **_kwargs: object) -> BundleAssemblyResult:
        return BundleAssemblyResult(
            status=BundleAssemblyStatus.FAILED,
            diagnostics=("BUNDLE_CLOSURE_JSON_BUDGET_EXCEEDED",),
        )

    monkeypatch.setattr(preview_jobs, "assemble_bundle", fail_bundle)
    session, control, operation, step = claim_next_step(harness)

    with pytest.raises(
        PreviewJobError,
        match="bundle assembly failed: BUNDLE_CLOSURE_JSON_BUDGET_EXCEEDED",
    ):
        run_claimed_handler(
            harness,
            PREVIEW_ASSEMBLE_HANDLER,
            session,
            control,
            operation,
            step,
        )


def test_full_preview_checkpoint_persists_canonical_state_bindings(tmp_path: Path) -> None:
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
    assemble_state = _preview_assemble_state(harness, envelope.job_state)
    _assert_persisted_canonical_preview(assemble_state, full=True)


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
        (
            "missing_tables",
            {"contract_version": PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION, "snapshot": {}},
            "table refs must be a list",
        ),
        (
            "null_tables",
            {"contract_version": PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION, "tables": None, "snapshot": {}},
            "table refs must be a list",
        ),
        (
            "invalid_tables_type",
            {"contract_version": PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION, "tables": "bad", "snapshot": {}},
            "table refs must be a list",
        ),
    ),
)
def test_materialize_checkpoint_rejects_invalid_empty_shapes(
    case_id: str,
    side_document: dict[str, object],
    match: str,
) -> None:
    del case_id
    from gateway_backend.application.payloads import CheckpointDecodeError
    from gateway_backend.application.preview_jobs import _materialized_preview_inputs_from_checkpoint
    store = InMemoryArtifactStore()
    sides_ref = put_checkpoint_state_artifact(
        store,
        {
            "document_type": PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
            "contract_version": PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
            "sides": {
                "BASELINE": side_document,
                "INITIAL": side_document,
                "MODIFIED": side_document,
                "initial_reuses_baseline": False,
            },
        },
        artifact_id_prefix='preview-materialized-sides',
    )

    with pytest.raises(CheckpointDecodeError, match=match):
        _materialized_preview_inputs_from_checkpoint(
            {
                "materialized_sides_ref": artifact_ref_to_dict(sides_ref),
                "canonical_preview": {},
            },
            store, repository_id=REPOSITORY_ID,
        )


def test_materialize_checkpoint_rejects_tables_cleared_from_nonempty_summary(tmp_path: Path) -> None:
    from gateway_backend.application.payloads import CheckpointDecodeError
    from gateway_backend.application.preview_jobs import _materialized_preview_inputs_from_checkpoint

    harness = build_preview_harness(
        tmp_path,
        input_completeness=InputCompleteness.MODIFIED_ONLY,
    )
    operation_id = "op-materialize-tamper"
    _run_materialize(harness, operation_id)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    job_state = dict(copy.deepcopy(envelope.job_state))
    sides_document = _read_materialized_sides_document(job_state, harness)
    sides = sides_document["sides"]
    assert isinstance(sides, dict)
    baseline_side = sides["BASELINE"]
    assert isinstance(baseline_side, dict)
    assert baseline_side["tables"]
    baseline_side["tables"] = []
    _replace_materialized_sides_document(job_state, sides_document, harness)

    with pytest.raises(CheckpointDecodeError, match="summary does not match its snapshot and tables"):
        _materialized_preview_inputs_from_checkpoint(job_state, harness.artifact_store, repository_id=REPOSITORY_ID)


def test_materialize_checkpoint_rejects_missing_summary(tmp_path: Path) -> None:
    from gateway_backend.application.payloads import CheckpointDecodeError
    from gateway_backend.application.preview_jobs import _materialized_preview_inputs_from_checkpoint

    harness = build_preview_harness(tmp_path)
    operation_id = "op-materialize-missing-summary"
    _run_materialize(harness, operation_id)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    job_state = dict(copy.deepcopy(envelope.job_state))
    sides_document = _read_materialized_sides_document(job_state, harness)
    sides = sides_document["sides"]
    assert isinstance(sides, dict)
    baseline_side = sides["BASELINE"]
    assert isinstance(baseline_side, dict)
    baseline_side.pop("summary", None)
    _replace_materialized_sides_document(job_state, sides_document, harness)

    with pytest.raises(CheckpointDecodeError, match="summary does not match its snapshot and tables"):
        _materialized_preview_inputs_from_checkpoint(job_state, harness.artifact_store, repository_id=REPOSITORY_ID)


def _run_through_publish(harness: PreviewJobHarness, operation_id: str) -> None:
    harness.seed_workspace()
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)


def test_unchanged_identity_table_reuses_current_rows_without_baseline_read(
    tmp_path: Path,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=InputCompleteness.MODIFIED_ONLY,
        canonical_noop=True,
        include_identity_table=True,
    )

    _run_through_publish(harness, "op-unchanged-project-identity")

    assert harness.baseline_provider.last_session is not None
    assert harness.baseline_provider.last_session.table_readers == []
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None
        assert workspace.current_preview_result_id is not None
        preview_result = unit_of_work.workspace.get_preview_result(
            workspace.current_preview_result_id
        )
    assert preview_result is not None
    assert [
        (item.applicability.value, item.status.value, item.mode.value)
        for item in preview_result.identity_pairs
    ] == [("APPLICABLE", "SAME_PROJECT", "DETAILED")]


def test_full_different_project_declares_replacement_for_matching_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_preview_harness(
        tmp_path, input_completeness=InputCompleteness.FULL,
        include_identity_table=True, identity_project_id="project-a",
    )
    modified_identity_sql = (
        "CREATE TABLE version_manager (`project_id` VARCHAR(32));\n"
        "INSERT INTO version_manager VALUES ('project-b');\n"
    )
    modified_binding = store_source_package(
        harness.artifact_store, (MODIFIED_SQL + modified_identity_sql).encode("utf-8"),
        artifact_id="a1:durable:ae5f90059b8c3d63c6a5c8ee811fde0af18b5e258f48c06b29989454dad9eecc",
    )
    initial_binding = harness.upload_revision.source_artifacts[SourceArtifactRole.INITIAL]
    harness.upload_revision = build_upload_revision(
        input_completeness=InputCompleteness.FULL,
        initial_binding=initial_binding,
        modified_binding=modified_binding,
        generation=harness.upload_revision.generation,
    )
    harness.job_payload = build_preview_job_payload(
        workspace_id=harness.upload_revision.workspace_id,
        upload_revision=harness.upload_revision,
        repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    declared_modes: list[tuple[ComparisonMode, ...]] = []
    original = pair_pipeline.declare_pair_comparison_session
    native_modes_and_calls: list[tuple[ComparisonMode, int]] = []
    original_native = pair_pipeline.compare_plan_native

    def capture_declaration(
        requests: tuple[ComparisonRequest, ...], *,
        computation_cache: ComputationCachePort | None = None,
        cache_owner: CacheOperationOwner | None = None, repository_id: str | None = None,
    ) -> ComparisonTaskSession | None:
        declared_modes.append(tuple(request.mode for request in requests))
        return original(requests, computation_cache=computation_cache, cache_owner=cache_owner,
            repository_id=repository_id)

    def capture_native(
        plan: ComparisonPlan, *, session: ComparisonTaskSession | None = None,
    ) -> NativeComparison:
        result = original_native(plan, session=session)
        assert result.metrics is not None
        native_modes_and_calls.append((plan.mode, result.metrics.native_calls))
        return result

    monkeypatch.setattr(preview_jobs, "declare_pair_comparison_session", capture_declaration)
    monkeypatch.setattr(pair_pipeline, "compare_plan_native", capture_native)
    _run_through_publish(harness, "op-full-different-project-declaration")
    assert declared_modes == [
        (ComparisonMode.DETAILED, ComparisonMode.DATASET_REPLACEMENT),
    ]
    assert len(native_modes_and_calls) == 2
    assert native_modes_and_calls[1] == (ComparisonMode.DATASET_REPLACEMENT, 0)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is not None
        preview_result = unit_of_work.workspace.get_preview_result(workspace.current_preview_result_id)
    assert preview_result is not None
    assert [
        (pair.status.value, pair.mode.value) for pair in preview_result.identity_pairs
    ] == [
        ("SAME_PROJECT", "DETAILED"),
        ("DIFFERENT_PROJECT", "DATASET_REPLACEMENT"),
    ]


@dataclass
class _HarnessArtifactRefLookup:
    store: InMemoryArtifactStore

    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        stored = self.store._artifacts.get(artifact_id)  # noqa: SLF001
        if stored is None:
            return None
        return stored[0]


@dataclass
class _HarnessBoundedArtifactStore:
    store: InMemoryArtifactStore

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        yield self.store.locate(ref)


@pytest.mark.parametrize(
    "input_completeness",
    [InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY],
    ids=["full", "modified_only"],
)
def test_empty_baseline_assemble_produces_ready_closure_and_canonical_bindings(
    tmp_path: Path,
    input_completeness: InputCompleteness,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=input_completeness,
        empty_baseline=True,
        canonical_noop=True,
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
    assemble_state = _preview_assemble_state(harness, envelope.job_state)
    assert assemble_state["required_refs"]
    identity_pairs = assemble_state["identity_pairs"]
    assert isinstance(identity_pairs, list)
    if input_completeness is InputCompleteness.FULL:
        assert assemble_state["pair_ids"] == ["baseline_to_initial", "initial_to_modified"]
        assert isinstance(identity_pairs[0], dict)
        assert identity_pairs[0]["applicability"] == "NOT_APPLICABLE"
        assert identity_pairs[0]["status"] == "NOT_APPLICABLE"
        assert identity_pairs[0]["assessment_ref"] is None
    else:
        assert assemble_state["pair_ids"] == ["initial_to_modified"]
        assert isinstance(identity_pairs[0], dict)
        assert identity_pairs[0]["applicability"] == "NOT_APPLICABLE"
        assert identity_pairs[0]["status"] == "NOT_APPLICABLE"
        assert identity_pairs[0]["assessment_ref"] is None
    assert isinstance(assemble_state["identity_assessment_set_digest"], str)
    digests = assemble_state["digests"]
    assert isinstance(digests, dict)
    preview_bundle_digest = digests["bundle_digest"]
    assert isinstance(preview_bundle_digest, str)
    _assert_persisted_canonical_preview(
        assemble_state,
        full=input_completeness is InputCompleteness.FULL,
    )


@pytest.mark.parametrize(
    "input_completeness",
    [InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY],
    ids=["full", "modified_only"],
)
def test_empty_baseline_assemble_produces_ready_closure_for_table_addition(
    tmp_path: Path,
    input_completeness: InputCompleteness,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=input_completeness,
        empty_baseline=True,
    )
    operation_id = f"op-assemble-empty-add-{input_completeness.value.lower()}"
    _run_materialize(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
    assert assemble_step.status is StepStatus.SUCCEEDED
    assert assemble_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, assemble_step.checkpoint_ref)
    assemble_state = _preview_assemble_state(harness, envelope.job_state)
    assert assemble_state["required_refs"]
    if input_completeness is InputCompleteness.FULL:
        assert assemble_state["pair_ids"] == ["baseline_to_initial", "initial_to_modified"]
    else:
        assert assemble_state["pair_ids"] == ["initial_to_modified"]
    digests = assemble_state["digests"]
    assert isinstance(digests, dict)
    preview_bundle_digest = digests["bundle_digest"]
    assert isinstance(preview_bundle_digest, str)
    _assert_persisted_canonical_preview(
        assemble_state,
        full=input_completeness is InputCompleteness.FULL,
    )


@pytest.mark.parametrize(
    "input_completeness",
    [InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY],
    ids=["full", "modified_only"],
)
def test_empty_baseline_submit_accepts_table_addition(
    tmp_path: Path,
    input_completeness: InputCompleteness,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        input_completeness=input_completeness,
        empty_baseline=True,
    )
    if input_completeness is InputCompleteness.FULL:
        identity_metadata = (
            "CREATE TABLE version_manager (`project_id` VARCHAR(32));\n"
            "INSERT INTO version_manager VALUES ('project-a');\n"
        )
        initial_binding = store_source_package(
            harness.artifact_store,
            (INITIAL_SQL + identity_metadata).encode("utf-8"),
            artifact_id="a1:durable:7e188889b8b4bafeca70541a9f1a1a2b150fb4c38a0e90c9c3ffa60ff2d13f0e",
        )
        modified_binding = store_source_package(
            harness.artifact_store,
            (MODIFIED_SQL + identity_metadata).encode("utf-8"),
            artifact_id="a1:durable:ba98a29a79e5dd9d253714bc027e975ce56fb717fd1f721715d63bf4b70a355e",
        )
        harness.upload_revision = build_upload_revision(
            input_completeness=input_completeness,
            initial_binding=initial_binding,
            modified_binding=modified_binding,
            generation=harness.upload_revision.generation,
        )
        harness.job_payload = build_preview_job_payload(
            workspace_id=harness.upload_revision.workspace_id,
            upload_revision=harness.upload_revision,
            repository_id=REPOSITORY_ID,
            business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
            baseline_head_version=BASELINE_HEAD.baseline_head_version,
            idempotency_key=IDEMPOTENCY_KEY,
            comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
        )
    seed_provisioned_mapping_with_head(
        harness.db_path,
        repository_id=REPOSITORY_ID,
        baseline_head=BASELINE_HEAD,
    )
    operation_id = f"op-empty-submit-accept-{input_completeness.value.lower()}"
    _run_through_publish(harness, operation_id)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None
        assert workspace.current_preview_result_id is not None
        preview_result = unit_of_work.workspace.get_preview_result(workspace.current_preview_result_id)
    assert preview_result is not None
    if input_completeness is InputCompleteness.FULL:
        assert [
            (pair.applicability.value, pair.status.value)
            for pair in preview_result.identity_pairs
        ] == [("NOT_APPLICABLE", "NOT_APPLICABLE"), ("APPLICABLE", "SAME_PROJECT")]
    else:
        assert [
            (pair.applicability.value, pair.status.value)
            for pair in preview_result.identity_pairs
        ] == [("NOT_APPLICABLE", "NOT_APPLICABLE")]
    command = AcceptSubmitCommand(
        context=make_identity(
            actor_id=workspace.owner_actor_id,
            device_key=workspace.gateway_device_external_key,
            project_id=workspace.business_project_id,
            permissions=frozenset({"upload_submit_workspace", "workspace_read"}),
        ),
        workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version,
        upload_revision_id=harness.upload_revision.upload_revision_id,
        preview_result_id=preview_result.preview_result_id,
        generation=preview_result.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key="empty-baseline-submit-accept",
        options={},
    )
    uow_factory = lambda *, read_only=False: ControlDbUnitOfWork(  # noqa: E731
        harness.db_path,
        read_only=read_only,
    )
    preflight = load_accept_submit_preflight(
        command=command,
        unit_of_work_factory=uow_factory,
        preview_result=preview_result,
        upload_revision=harness.upload_revision,
        artifact_ref_lookup=cast(ArtifactRefLookupPort, _HarnessArtifactRefLookup(harness.artifact_store)),
        artifact_store=cast(
            BoundedArtifactStorePort,
            _HarnessBoundedArtifactStore(harness.artifact_store),
        ),
        current_storage_projection_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    result = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=REPOSITORY_ID,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=uow_factory,
        job_registry=submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=preflight,
        now=harness.upload_revision.created_at,
    )
    assert result.replay is False

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 1


@pytest.mark.parametrize("ordered_identity", (False, True))
def test_pair_memory_admission_rejects_before_native_row_comparison(
    ordered_identity: bool,
) -> None:
    from gateway_backend.capabilities.comparison import BoundSnapshotInput, ComparisonStorageFacts
    from gateway_backend.capabilities.table_rules import CanonicalKeyPolicy, OrderedPolicy, StorageRuleView
    from gateway_backend.capabilities.storage_projection import STORAGE_PROJECTION_VERSION
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, NeverCancel, kernel_execution_scope, KernelMemoryLimit,
    )
    from gateway_backend.capabilities.snapshot_materialization import MaterializationPolicy
    from tests.support.snapshot_materialization import materialize_arrow_sql
    from tests.support.table_rules import comparison_ruleset_for, standard_rule_record, ordered_record
    sides = []
    for value in (("a", "a") if ordered_identity else ("a", "b")):
        sql = ("CREATE TABLE t(gid BIGINT NOT NULL PRIMARY KEY,no INT NOT NULL,v TEXT); INSERT INTO t VALUES (10,1,'a'),(11,2,'b');"
            if ordered_identity else f"CREATE TABLE t(id INT PRIMARY KEY,v TEXT); INSERT INTO t VALUES (1,'{value}');")
        result = materialize_arrow_sql(sql,
            policy=MaterializationPolicy.READERS_REQUIRED)
        assert result.snapshot is not None and result.summary is not None and result.table_set is not None
        bound = BoundSnapshotInput(result.snapshot, result.summary, result.table_set)
        if ordered_identity:
            descriptor = bound.summary.tables[0]
            assert descriptor.raw_content_digest is not None
            view = StorageRuleView(canonical_table="t", canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
                ordered_policy=OrderedPolicy.GID_NO_V1, structural_columns=("no",),
                retained_columns=tuple(column.name for column in descriptor.columns), canonical_key_columns=("gid",))
            bound = replace(bound, storage_facts=(ComparisonStorageFacts(storage_rule_view=view,
                source_schema_digest=descriptor.business_schema_digest, canonical_schema_digest=canonical_schema_digest_for_descriptor(descriptor),
                raw_content_digest=descriptor.raw_content_digest, storage_projection_version=STORAGE_PROJECTION_VERSION),))
        sides.append(bound)
    memory = OperationMemoryBudget(80 * 1024)
    with kernel_execution_scope(KernelExecutionContext(memory, NeverCancel(), 1), new_operation=True):
        with pytest.raises(KernelMemoryLimit):
            pair_pipeline.run_preview_pair_pipeline(pair_id="pair-budget", before=sides[0], current=sides[1],
                store=InMemoryArtifactStore(), control=ExecutionControl(), on_cancel=lambda: None,
                rule_set=comparison_ruleset_for(ordered_record(r"^t$") if ordered_identity else standard_rule_record("t")), assess_identity=False)
    assert memory.stage_admissions[-1]["stage"] == "comparison-metadata"


def test_preview_forms_cache_for_a_new_operation_without_adding_full_pairs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    import json
    from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache

    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    def transaction() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path)
    cache = ControlDbComputationCache(transaction, open_test_store(tmp_path / "derived-cache"))
    deps = replace(harness.deps, computation_cache=cache)
    _, handlers, _ = preview_jobs.preview_composition_bundle(deps)
    harness.handlers = dict(handlers)
    with caplog.at_level("INFO", logger="gateway_backend.application.pair_pipeline"):
        _run_through_publish(harness, "op-persistent-full-cold")
    cold_metrics = [json.loads(record.message.split("s3_pair_metrics ", 1)[1])
        for record in caplog.records if record.message.startswith("s3_pair_metrics ")]
    assert [item["pair_id"] for item in cold_metrics] == ["baseline_to_initial", "initial_to_modified"]
    assert sum(item["comparison"]["native_calls"] for item in cold_metrics) > 0
    caplog.clear()
    harness.job_payload = build_preview_job_payload(
        workspace_id=harness.upload_revision.workspace_id, upload_revision=harness.upload_revision,
        repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key="persistent-full-warm-new-key",
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    with caplog.at_level("INFO", logger="gateway_backend.application.pair_pipeline"):
        _run_through_publish(harness, "op-persistent-full-warm")
    warm_metrics = [json.loads(record.message.split("s3_pair_metrics ", 1)[1])
        for record in caplog.records if record.message.startswith("s3_pair_metrics ")]
    assert [item["pair_id"] for item in warm_metrics] == ["baseline_to_initial", "initial_to_modified"]
    assert sum(item["comparison"]["native_calls"] for item in warm_metrics) == 0
    assert sum(item["comparison"]["cache_hits"] for item in warm_metrics) > 0
    with transaction() as uow:
        producers = {row[0] for row in uow.connection.execute("SELECT DISTINCT producer_operation_id FROM computation_cache_uses")}
        assert producers == {"op-persistent-full-cold", "op-persistent-full-warm"}
        assert uow.connection.execute("SELECT COUNT(*) FROM artifact_protection_intents WHERE intent='active-computation-cache'").fetchone()[0] == 0


@pytest.mark.parametrize("field_name", ["ready_closure_artifact_id", "bundle_artifact_id"])
@pytest.mark.parametrize("artifact_id", ["old-closure", "a1:unknown:" + "a" * 64,
    "00000000-0000-4000-8000-000000000001"])
def test_preview_assemble_checkpoint_rejects_unsupported_bare_refs(field_name: str, artifact_id: str) -> None:
    from gateway_backend.application.preview_jobs import _preview_ready_ref
    from gateway_backend.application.payloads import CheckpointDecodeError
    ready_id = "a1:durable:" + "0" * 64
    state: dict[str, object] = {"ready_closure_artifact_id": ready_id,
        "bundle_artifact_id": "a1:export:" + "1" * 64,
        "ready_closure_ref": {"artifact_id": ready_id, "media_type": "application/jcs",
            "size_bytes": 0, "raw_sha256": "sha256:" + "0" * 64}}
    state[field_name] = artifact_id
    with pytest.raises(CheckpointDecodeError, match="invalid artifact bindings"):
        _preview_ready_ref(state)


@pytest.mark.parametrize("input_completeness", (InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY))
def test_comment_only_preview_restores_frozen_sides_and_submit_has_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input_completeness: InputCompleteness,
) -> None:
    from gateway_backend.application.submission.errors import NoCanonicalChange
    from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
    from tests.support.preview_job_harness import BASELINE_SQL
    harness = build_preview_harness(tmp_path, input_completeness=input_completeness, canonical_noop=True)
    def upload(label: str) -> Any:
        sql = BASELINE_SQL.replace("PRIMARY KEY)", f"PRIMARY KEY COMMENT '{label}-column') COMMENT='{label}'")
        return store_source_package(harness.artifact_store, sql.encode(), artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", label))
    harness.upload_revision = build_upload_revision(input_completeness=input_completeness,
        initial_binding=upload("initial") if input_completeness is InputCompleteness.FULL else None,
        modified_binding=upload("modified"))
    harness.job_payload = build_preview_job_payload(workspace_id=harness.upload_revision.workspace_id,
        upload_revision=harness.upload_revision, repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version, idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest())
    seen: list[tuple[PresentationMetadata, PresentationMetadata]] = []
    original = preview_jobs.run_preview_pair_pipeline
    def capture(**kwargs: Any) -> Any:
        seen.append((kwargs["before_presentation"], kwargs["current_presentation"]))
        return original(**kwargs)
    monkeypatch.setattr(preview_jobs, "run_preview_pair_pipeline", capture)
    _run_through_publish(harness, "op-comment-only")
    expected_before = "initial" if input_completeness is InputCompleteness.FULL else None
    def table_comment(metadata: PresentationMetadata) -> str | None:
        return next(t.comment for t in metadata.tables if t.table_name == "t")
    assert table_comment(seen[-1][0]) == expected_before
    assert table_comment(seen[-1][1]) == "modified"
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is not None
        preview = unit_of_work.workspace.get_preview_result(workspace.current_preview_result_id)
        assert preview is not None and preview.canonical is not None
        assert preview.canonical.baseline_canonical_state_digest == preview.canonical.modified_canonical_state_digest
    command = AcceptSubmitCommand(context=make_identity(actor_id=workspace.owner_actor_id,
        device_key=workspace.gateway_device_external_key, project_id=workspace.business_project_id,
        permissions=frozenset({"upload_submit_workspace", "workspace_read"})), workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version, upload_revision_id=harness.upload_revision.upload_revision_id,
        preview_result_id=preview.preview_result_id, generation=preview.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version, idempotency_key="comment-only-submit", options={})
    def uow_factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path, read_only=read_only)
    preflight = load_accept_submit_preflight(command=command, unit_of_work_factory=uow_factory,
        preview_result=preview, upload_revision=harness.upload_revision,
        artifact_ref_lookup=cast(ArtifactRefLookupPort, _HarnessArtifactRefLookup(harness.artifact_store)),
        artifact_store=cast(BoundedArtifactStorePort, _HarnessBoundedArtifactStore(harness.artifact_store)),
        current_storage_projection_ruleset_digest=_runtime_comparison_ruleset_digest())
    main_resolve = RecordingMainResolvePort()
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(command=command, scope_resolution=FixedScopeResolutionPort(repository_id=REPOSITORY_ID,
            baseline_head=BASELINE_HEAD), unit_of_work_factory=uow_factory, job_registry=submit_job_registry(),
            main_resolve=main_resolve, preflight=preflight, now=harness.upload_revision.created_at)
    assert main_resolve.calls == 0
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 0
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submission_records").fetchone()[0] == 0
