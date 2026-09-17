"""Production HTTP runtime composition for readiness, admission, and submit wiring."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from gateway_repository_client import RepositoryClient
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.preview_jobs import preview_job_definitions
from gateway_backend.application.preview_registry import assert_preview_registry_ready
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.submit_jobs import (
    SubmitRuntimeDependencies,
    bind_submit_control_transaction_factory,
    build_submit_operator_recovery_port,
    _read_write_factory,
)
from gateway_backend.application.submit_registry import submit_job_definitions
from gateway_backend.application.submission.accept_transaction import assert_submit_job_registered
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    assemble_bundle,
    collect_surface_refs,
)
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonPlan,
    DetailedFactsResult,
    FailedResult,
    PairRole,
    PairViewKind,
    bind_pair_input,
    compare_plan,
    plan_pair,
    publish_records_closure,
)
from gateway_backend.capabilities.comparison.contracts import (
    IdentityStatus,
    InputCompleteness as ComparisonInputCompleteness,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskOptions,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    materialize_repository_ref,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryTableAccessProvider,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.source_package_staging.contracts import NeverCancel
from gateway_backend.capabilities.surface_assembly import (
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewAcceptanceRecord,
    PreviewResult,
    ResolvedScope,
    UploadRevision,
    Workspace,
    WorkspaceScope,
)
from gateway_backend.http.auth import (
    LiveFileSessionPort,
    StaticInternalBearerPort,
    load_internal_bearer_token,
    load_session_file,
)
from gateway_backend.http.dependencies import (
    ClosableAdmissionGate,
    ReadOnlyOperationStore,
    ReadOnlySubmissionStore,
    WorkspaceHttpDependencies,
)
from gateway_backend.http.errors import ApiError
from gateway_backend.infrastructure.artifact_store import (
    BoundedArtifactStore,
    LocalArtifactStore,
    validate_artifact_root,
)
from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    initialize_and_verify_control_db,
)
from gateway_backend.infrastructure.control_db.sqlite_mapping import (
    ProvisionedBaselineHeadRead,
    ProvisionedScopeResolution,
    seed_provisioned_mappings,
)
from gateway_backend.infrastructure.repository_read import (
    build_http_repository_provider_factory,
    load_repository_bearer_token,
)
from gateway_backend.infrastructure.repository_write import (
    HttpRepositoryAbortEvidencePort,
    HttpRepositoryWriteClient,
)
from gateway_backend.operations.contracts import JobStepKey
from gateway_backend.operations.recovery import RecoveryCapabilityValue
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from gateway_backend.settings import BackendSettings

_PAIR_IDENTITY = "baseline-identity"
_PAIR_VIEW = "baseline-to-current"


class FailClosedSessionPort:
    """Reject callers until an identity provider is composed outside this slice."""

    def resolve(self, request: object) -> IdentityContext:
        del request
        raise ApiError(
            code="AUTHENTICATION_REQUIRED",
            message="authentication required",
            status_code=401,
        )


class FailClosedScopeResolution:
    def resolve(self, context: IdentityContext) -> ResolvedScope:
        del context
        raise ScopeResolutionError("provisioned mapping is missing")


class TransactionWorkspaceRepository:
    """WorkspaceRepository that opens one control-DB transaction per call."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _read_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self._db_path, read_only=True)

    def _write_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self._db_path)

    def find_open_by_scope(self, scope: WorkspaceScope) -> Workspace | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_open_by_scope(scope)

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_workspace(workspace_id)

    def get_upload_revision(self, upload_revision_id: str) -> UploadRevision | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_upload_revision(upload_revision_id)

    def get_preview_result(self, preview_result_id: str) -> PreviewResult | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.get_preview_result(preview_result_id)

    def find_upload_idempotency(self, workspace_id: str, idempotency_key: str) -> UploadRevision | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_upload_idempotency(workspace_id, idempotency_key)

    def find_preview_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> PreviewAcceptanceRecord | None:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.find_preview_idempotency(workspace_id, idempotency_key)

    def list_preview_acceptances(self, workspace_id: str) -> tuple[PreviewAcceptanceRecord, ...]:
        with self._read_uow() as unit_of_work:
            return unit_of_work.workspace.list_preview_acceptances(workspace_id)

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_acceptance(record)

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        with self._write_uow() as unit_of_work:
            return unit_of_work.workspace.save_workspace(workspace, expected_version=expected_version)

    def save_upload_revision(self, revision: UploadRevision) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_upload_revision(revision)

    def save_preview_result(self, result: PreviewResult) -> None:
        with self._write_uow() as unit_of_work:
            unit_of_work.workspace.save_preview_result(result)


class LocalArtifactBundleReader:
    def __init__(self, local_store: LocalArtifactStore) -> None:
        self._local_store = local_store

    def read_bundle(self, artifact_id: str) -> tuple[str, Iterator[bytes]]:
        try:
            ref = self._local_store._load_stored_ref(artifact_id)  # noqa: SLF001
            payload = self._local_store.locate(ref)
        except ManifestVerificationError:
            raise KeyError(artifact_id) from None
        return artifact_id, iter([payload])


class LocalArtifactRefLookup:
    def __init__(self, local_store: LocalArtifactStore) -> None:
        self._local_store = local_store

    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        try:
            return self._local_store._load_stored_ref(artifact_id)  # noqa: SLF001
        except ManifestVerificationError:
            return None


@dataclass(frozen=True, slots=True)
class _BaselineIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: IdentityStatus
    assessment_digest: DigestRef


@dataclass(frozen=True, slots=True)
class BackendRuntime:
    settings: BackendSettings
    admission_gate: ClosableAdmissionGate
    workspace_http: WorkspaceHttpDependencies


def build_workspace_job_registry() -> JobDefinitionRegistry:
    """Immutable preview+submit registry shared by HTTP acceptance and the worker."""

    return JobDefinitionRegistry.build(preview_job_definitions() + submit_job_definitions())


def assert_workspace_registry_ready(registry: JobDefinitionRegistry) -> None:
    assert_preview_registry_ready(registry)
    assert_submit_job_registered(registry)


def assert_repository_service_ready(
    base_url: str,
    bearer_token: str,
    *,
    timeout_seconds: float,
) -> None:
    """Fail closed when Repository Service /readyz is unavailable."""

    if type(base_url) is not str or base_url == "":
        raise ValueError("repository base URL is missing")
    if type(bearer_token) is not str or bearer_token == "":
        raise ValueError("repository bearer token is missing")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/readyz",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise ValueError("repository service is not ready")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ValueError("repository service is not ready") from None


def _submit_recovery_capability_lookup(
    registry: JobDefinitionRegistry,
) -> Callable[[str, str], RecoveryCapabilityValue]:
    mapping: dict[tuple[str, str], RecoveryCapabilityValue] = {}
    for step_name in (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT):
        definition = registry.resolve_runnable(
            JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=step_name),
            SUBMIT_JOB_CONTRACT_VERSION,
        )
        capability = definition.recovery_capability
        if capability is RecoveryCapability.PURE_RECOMPUTE:
            mapped = RecoveryCapabilityValue.PURE_RECOMPUTE
        elif capability is RecoveryCapability.EXTERNAL_EFFECT:
            mapped = RecoveryCapabilityValue.EXTERNAL_EFFECT
        else:
            mapped = RecoveryCapabilityValue.NON_RETRYABLE
        mapping[(SUBMIT_JOB_KIND, step_name)] = mapped

    def lookup(job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        return mapping[(job_kind, step_name)]

    return lookup


def _bound_from_materialization(
    result: SnapshotMaterializationResult,
    *,
    label: str,
) -> BoundSnapshotInput:
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        raise ValueError(f"{label} materialization failed")
    if result.snapshot is None or result.summary is None:
        raise ValueError(f"{label} materialization is incomplete")
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _surface_artifact_closure(surface: ComparisonSurface, pair_id: str) -> BundleArtifactClosure:
    bindings: list[BundleArtifactBinding] = []
    prefix = f"pairs/{pair_id}"

    def add(
        ref: ArtifactRef | None,
        logical_path: str,
        kind: BundleArtifactKind,
        *,
        table_name: str | None = None,
    ) -> None:
        if ref is None:
            return
        bindings.append(
            BundleArtifactBinding(
                source_ref=ref,
                logical_path=logical_path,
                kind=kind,
                pair_id=pair_id,
                table_name=table_name,
            )
        )

    add(
        surface.refs.records_closure_ref,
        f"{prefix}/comparison/records/closure.json",
        BundleArtifactKind.RECORDS_CLOSURE,
    )
    add(surface.refs.risk_report_ref, f"{prefix}/risk/report.json", BundleArtifactKind.RISK_REPORT)
    add(
        surface.refs.risk_annotation_closure_ref,
        f"{prefix}/risk/annotations/closure.json",
        BundleArtifactKind.RISK_ANNOTATION_CLOSURE,
    )
    add(
        surface.refs.project_identity_assessment_ref,
        f"{prefix}/identity/assessment.json",
        BundleArtifactKind.OTHER,
    )
    add(surface.refs.diagnostics_ref, f"{prefix}/diagnostics/surface.json", BundleArtifactKind.DIAGNOSTICS)
    for table in surface.tables:
        table_name = table.table_name
        add(
            table.table_refs.before_table_ref,
            f"{prefix}/tables/before/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.table_refs.current_table_ref,
            f"{prefix}/tables/current/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.table_refs.browse_table_ref,
            f"{prefix}/tables/browse/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.records_refs.records_ref,
            f"{prefix}/comparison/records/{table_name}/rows.bin",
            BundleArtifactKind.RECORDS,
            table_name=table_name,
        )
        add(
            table.records_refs.records_manifest_ref,
            f"{prefix}/comparison/records/{table_name}/manifest.json",
            BundleArtifactKind.RECORDS_MANIFEST,
            table_name=table_name,
        )
        add(
            table.risk_refs.report_ref,
            f"{prefix}/risk/tables/{table_name}/report.json",
            BundleArtifactKind.RISK_REPORT,
            table_name=table_name,
        )
        add(
            table.risk_refs.annotation_ref,
            f"{prefix}/risk/tables/{table_name}/annotations.bin",
            BundleArtifactKind.RISK_ANNOTATION,
            table_name=table_name,
        )
        add(
            table.risk_refs.annotation_manifest_ref,
            f"{prefix}/risk/tables/{table_name}/annotations/manifest.json",
            BundleArtifactKind.RISK_ANNOTATION_MANIFEST,
            table_name=table_name,
        )
        add(
            table.diagnostics.diagnostics_ref,
            f"{prefix}/diagnostics/tables/{table_name}.json",
            BundleArtifactKind.DIAGNOSTICS,
            table_name=table_name,
        )
    covered = {binding.source_ref for binding in bindings}
    for ref in collect_surface_refs(surface):
        if ref not in covered:
            raise ValueError("surface ref is not mapped for bundle closure")
    return BundleArtifactClosure(tuple(bindings))


def _run_identity_pair_pipeline(
    *,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: InMemoryArtifactStore,
) -> tuple[SurfaceAssemblyResult, BundleArtifactClosure]:
    assessment_digest = raw_blob_digest(
        f"{before.snapshot.snapshot_digest.value}:{current.snapshot.snapshot_digest.value}".encode()
    )
    assessment = _BaselineIdentityAssessment(
        schema_version="project-identity-assessment/v1",
        rule_version="version-manager-overlap/v1",
        before_snapshot_digest=before.snapshot.snapshot_digest,
        current_snapshot_digest=current.snapshot.snapshot_digest,
        status=IdentityStatus.SAME_PROJECT,
        assessment_digest=assessment_digest,
    )
    bound = bind_pair_input(
        pair_id=_PAIR_IDENTITY,
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        input_completeness=ComparisonInputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=cast(Any, assessment),
        baseline_reconstruction=None,
    )
    if isinstance(bound, FailedResult):
        raise ValueError("baseline pair binding failed")
    plan = plan_pair(bound)
    if isinstance(plan, FailedResult):
        raise ValueError("baseline pair planning failed")
    if not isinstance(plan, ComparisonPlan):
        raise ValueError("baseline pair planning did not produce a plan")
    compared = compare_plan(plan)
    if isinstance(compared, FailedResult):
        raise ValueError("baseline pair comparison failed")
    if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
        raise ValueError("baseline pair comparison did not produce facts")
    published = publish_records_closure(compared, store)
    if isinstance(published, FailedResult):
        raise ValueError("baseline records closure failed")
    if not isinstance(published, DetailedFactsResult) or published.facts is None:
        raise ValueError("baseline records publication did not produce facts")
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=published.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=store,
    )
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise ValueError("baseline risk evaluation failed")
    surface = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=published.facts,
            surface_id=f"surface-{_PAIR_IDENTITY}",
            view_id=_PAIR_VIEW,
            before_role="before",
            current_role="current",
            records_closure=published.records_closure,
            risk_report=risk.risk_report,
            risk_annotation_closure=risk.risk_closure,
            ref_scope=SurfaceRefScope.OPERATION_RELATIVE,
        ),
        context=SurfaceAssemblyContext(cancel_requested=lambda: False),
    )
    if surface.status is not SurfaceAssemblyStatus.READY or surface.surface is None:
        raise ValueError("baseline surface assembly failed")
    return surface, _surface_artifact_closure(surface.surface, _PAIR_IDENTITY)


def _compute_baseline_bundle_digest(
    *,
    repository_id: str,
    baseline_head: BaselineHead,
    provider_factory: Callable[[str, str], object],
    store: InMemoryArtifactStore,
) -> str:
    provider = cast(
        RepositoryTableAccessProvider,
        provider_factory(repository_id, baseline_head.business_baseline_commit_id),
    )
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(
            repository_id=repository_id,
            ref=baseline_head.business_baseline_commit_id,
        ),
        provider=provider,
        ruleset=TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION),
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=store,
    )
    baseline = _bound_from_materialization(materialize_repository_ref(request), label="baseline")
    surface_result, closure = _run_identity_pair_pipeline(
        before=baseline,
        current=baseline,
        store=store,
    )
    bundle_result = assemble_bundle(
        BundleAssemblyInput(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_profile=BundleProfile.SINGLE_PAIR,
            inputs=(
                BundleInput(0, "baseline", "Baseline"),
                BundleInput(1, "current", "Current"),
            ),
            pairs=(
                BundlePairInput(
                    _PAIR_IDENTITY,
                    0,
                    1,
                    surface_result,
                    closure,
                ),
            ),
            ref_scope=BundleRefScope.BUNDLE_RELATIVE,
        ),
        source_store=store,
        context=BundleAssemblyContext(
            checkpoint=lambda: None,
            cancel_requested=lambda: False,
        ),
    )
    if bundle_result.status is not BundleAssemblyStatus.READY or bundle_result.bundle is None:
        raise ValueError("baseline bundle assembly failed")
    return bundle_result.bundle.bundle_digest.value


class HttpBaselineCanonicalDigestPort:
    def __init__(
        self,
        *,
        provider_factory: Callable[[str, str], object],
    ) -> None:
        self._provider_factory = provider_factory

    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: BaselineHead,
    ) -> str:
        del baseline_head.business_baseline_node_id, baseline_head.baseline_head_version
        store = InMemoryArtifactStore()
        try:
            return _compute_baseline_bundle_digest(
                repository_id=repository_id,
                baseline_head=baseline_head,
                provider_factory=self._provider_factory,
                store=store,
            )
        except ValueError:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="baseline canonical digest is unavailable",
                status_code=503,
            ) from None


class HttpRepositoryMainResolvePort:
    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        client = RepositoryClient(
            base_url=self._base_url,
            bearer_token=self._bearer_token,
            timeout_seconds=self._timeout_seconds,
            transport=self._transport,
        )
        try:
            response = asyncio.run(
                client.resolve_versioned_ref(
                    repository_id=UUID(repository_id),
                    ref_name="main",
                )
            )
        except Exception:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="repository main resolve is unavailable",
                status_code=503,
            ) from None
        return str(response.commit_id)


def prepare_backend_runtime(
    settings: BackendSettings,
    *,
    repository_transport: httpx.AsyncBaseTransport | None = None,
    skip_repository_ready_probe: bool = False,
) -> BackendRuntime:
    """Validate settings, SQLite, artifact root, registry, and Repository readiness before /readyz."""

    repository_token = load_repository_bearer_token(settings.repository_bearer_token_file)
    load_internal_bearer_token(settings.internal_bearer_token_file)
    load_session_file(settings.session_file)
    validate_artifact_root(settings.artifact_root)
    parent = settings.control_db_path.parent
    parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("control DB parent is not a directory")
    initialize_and_verify_control_db(settings.control_db_path)
    seed_provisioned_mappings(settings.control_db_path, settings.provisioned_mapping_file)
    if not skip_repository_ready_probe:
        assert_repository_service_ready(
            settings.repository_base_url,
            repository_token,
            timeout_seconds=settings.repository_timeout_seconds,
        )
    registry = build_workspace_job_registry()
    assert_workspace_registry_ready(registry)
    local_store = LocalArtifactStore(settings.artifact_root)

    def is_protected(artifact_id: str) -> bool:
        with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as unit_of_work:
            return unit_of_work.protection.is_protected(artifact_id)

    artifact_store = BoundedArtifactStore(
        local_store,
        is_protected=is_protected,
        unpinned_ttl=timedelta(seconds=settings.cleanup_unpinned_ttl_seconds),
    )
    admission_gate = ClosableAdmissionGate(limit=settings.http_new_work_limit)

    def unit_of_work_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    provider_factory = build_http_repository_provider_factory(
        base_url=settings.repository_base_url,
        bearer_token=repository_token,
        timeout_seconds=settings.repository_timeout_seconds,
        transport=repository_transport,
    )
    write_client = HttpRepositoryWriteClient(
        base_url=settings.repository_base_url,
        bearer_token=repository_token,
        timeout_seconds=settings.repository_timeout_seconds,
        transport=repository_transport,
    )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    submit_deps = SubmitRuntimeDependencies(
        artifact_store=artifact_store,
        publication=SubmitImportPublicationAdapter(),
        repository_write=write_client,
        control_transaction_factory=control_transaction_factory,
        submission_id_factory=lambda: f"sub-{uuid4()}",
    )
    submit_control_uow_factory = bind_submit_control_transaction_factory(control_transaction_factory)
    operator_recovery_port = build_submit_operator_recovery_port(
        write_uow_factory=control_transaction_factory,
        capability_lookup=_submit_recovery_capability_lookup(registry),
        submit_control_uow_factory=_read_write_factory(submit_control_uow_factory),
        abort_evidence=HttpRepositoryAbortEvidencePort(client=write_client),
        submit_deps=submit_deps,
    )

    workspace_http = WorkspaceHttpDependencies(
        session_port=LiveFileSessionPort(settings.session_file),
        scope_resolution=ProvisionedScopeResolution(settings.control_db_path),
        baseline_head_read=ProvisionedBaselineHeadRead(settings.control_db_path),
        workspace_repository=TransactionWorkspaceRepository(settings.control_db_path),
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=artifact_store,
        job_registry=registry,
        bundle_reader=LocalArtifactBundleReader(local_store),
        admission_gate=admission_gate,
        operation_reader=ReadOnlyOperationStore(unit_of_work_factory),
        submission_reader=ReadOnlySubmissionStore(unit_of_work_factory),
        artifact_ref_lookup=LocalArtifactRefLookup(local_store),
        internal_bearer_port=StaticInternalBearerPort(
            load_internal_bearer_token(settings.internal_bearer_token_file)
        ),
        baseline_canonical_digest=HttpBaselineCanonicalDigestPort(
            provider_factory=cast(Callable[[str, str], object], provider_factory),
        ),
        main_resolve=HttpRepositoryMainResolvePort(
            base_url=settings.repository_base_url,
            bearer_token=repository_token,
            timeout_seconds=settings.repository_timeout_seconds,
            transport=repository_transport,
        ),
        operator_recovery_port=operator_recovery_port,
        now=lambda: datetime.now(UTC),
    )
    return BackendRuntime(
        settings=settings,
        admission_gate=admission_gate,
        workspace_http=workspace_http,
    )


__all__ = [
    "BackendRuntime",
    "ClosableAdmissionGate",
    "FailClosedScopeResolution",
    "FailClosedSessionPort",
    "HttpBaselineCanonicalDigestPort",
    "HttpRepositoryMainResolvePort",
    "LocalArtifactBundleReader",
    "LocalArtifactRefLookup",
    "TransactionWorkspaceRepository",
    "assert_repository_service_ready",
    "assert_workspace_registry_ready",
    "build_workspace_job_registry",
    "prepare_backend_runtime",
]
