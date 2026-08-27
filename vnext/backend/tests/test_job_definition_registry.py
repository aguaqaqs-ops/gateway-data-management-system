"""Immutable JobDefinition registry and WorkerRegistry adapter tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application import (
    JobDefinition,
    JobDefinitionLookupError,
    JobDefinitionRegistry,
    NormalPublicationCapability,
    RecoveryCapability,
    build_worker_registry,
)
from gateway_backend.application.job_definitions import (
    build_job_worker_composition,
    validate_active_pairs_job_contract_versions,
)
from gateway_backend.application.payloads import PayloadDecodeError
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION, OperationStatus, StepStatus
from gateway_backend.operations.contracts import JobStepKey, OperationRecord, StepRecord
from gateway_backend.operations.worker import (
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    WorkerRegistry,
)

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
LEASE_EXPIRES_AT = BASE_TIME + timedelta(seconds=30)

BACKEND_SRC = Path(__file__).parents[1] / "src"
JOB_DEFINITIONS_SOURCE = (
    BACKEND_SRC / "gateway_backend" / "application" / "job_definitions.py"
)

VERSION_V1 = "backend-vnext/synthetic/pure-compute/v1"
VERSION_V2 = "backend-vnext/synthetic/pure-compute/v2"
DECODER_V1 = "backend-vnext/synthetic/pure-compute/decoder/v1"
HANDLER_V1 = "backend-vnext/synthetic/pure-compute/handler/v1"
HANDLER_V2 = "backend-vnext/synthetic/stub/handler/v1"

KEY_VALIDATE = JobStepKey(job_kind="import.package", step_name="validate")
KEY_PUBLISH = JobStepKey(job_kind="import.package", step_name="publish")
UNKNOWN_KEY = JobStepKey(job_kind="import.package", step_name="unknown")


def _definition(
    *,
    key: JobStepKey = KEY_VALIDATE,
    versions: frozenset[str] = frozenset({VERSION_V1}),
    decoder_identity: str = DECODER_V1,
    handler_identity: str = HANDLER_V1,
    publication_capability: NormalPublicationCapability = NormalPublicationCapability.TERMINAL,
) -> JobDefinition:
    return JobDefinition(
        key=key,
        supported_payload_versions=versions,
        decoder_identity=decoder_identity,
        handler_identity=handler_identity,
        publication_capability=publication_capability,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def _executor(
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
) -> ExecutorAcknowledgment:
    del operation, step, control, lease_session
    return ExecutorAcknowledgment.PUBLISHED


UNKNOWN_LOOKUP_CASES: tuple[tuple[JobStepKey, str], ...] = (
    (UNKNOWN_KEY, "registry has no JobDefinition for the JobStepKey"),
    (
        JobStepKey(job_kind="missing.kind", step_name="step"),
        "registry has no JobDefinition for the JobStepKey",
    ),
)

UNSUPPORTED_VERSION_CASES: tuple[tuple[str, str], ...] = (
    (VERSION_V2, "job_contract_version is not supported by the JobDefinition"),
    ("backend-vnext/unknown/v9", "job_contract_version is not supported by the JobDefinition"),
)

MALFORMED_REGISTRY_BUILDS: tuple[tuple[Any, str], ...] = (
    (
        [
            _definition(),
        ],
        "definitions must be a tuple",
    ),
    (
        (
            _definition(),
            JobDefinition(
                key=KEY_VALIDATE,
                supported_payload_versions=frozenset({VERSION_V1}),
                decoder_identity=DECODER_V1,
                handler_identity=HANDLER_V2,
                publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
                recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
            ),
        ),
        "duplicate JobStepKey in registry build",
    ),
    (
        (
            _definition(handler_identity=HANDLER_V1),
            _definition(
                key=KEY_PUBLISH,
                handler_identity=HANDLER_V1,
                publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
            ),
        ),
        "duplicate handler_identity in registry build",
    ),
)

MALFORMED_WORKER_REGISTRY_BINDINGS: tuple[tuple[dict[str, Callable[..., Any]], str], ...] = (
    ({HANDLER_V2: _executor}, "executors must bind exactly one callable per handler_identity"),
    ({}, "executors must bind exactly one callable per handler_identity"),
    (
        {HANDLER_V1: _executor, HANDLER_V2: _executor},
        "executors must bind exactly one callable per handler_identity",
    ),
)


def test_registry_build_produces_independent_immutable_instances() -> None:
    first_definition = _definition()
    second_definition = _definition(
        key=KEY_PUBLISH,
        decoder_identity="backend-vnext/synthetic/stub/decoder/v1",
        handler_identity=HANDLER_V2,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
    )
    first = JobDefinitionRegistry.build((first_definition, second_definition))
    second = JobDefinitionRegistry.build((first_definition, second_definition))

    assert first is not second
    assert first.definitions() == (first_definition, second_definition)
    assert first.get(KEY_VALIDATE) == first_definition
    assert first.get(KEY_PUBLISH) == second_definition


def test_registry_definitions_snapshot_is_read_only() -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    snapshot = registry.definitions()
    assert snapshot == (_definition(),)
    assert isinstance(snapshot, tuple)


def test_registry_lookup_map_rejects_post_build_mutation() -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    extra = _definition(
        key=KEY_PUBLISH,
        decoder_identity="backend-vnext/synthetic/stub/decoder/v1",
        handler_identity=HANDLER_V2,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
    )
    with pytest.raises(TypeError):
        registry._by_key[KEY_PUBLISH] = extra  # type: ignore[index]
    assert registry.get(KEY_VALIDATE) == _definition()
    with pytest.raises(JobDefinitionLookupError):
        registry.get(KEY_PUBLISH)


def test_worker_registry_executor_map_rejects_post_build_mutation() -> None:
    from gateway_backend.application.job_definitions import _JobDefinitionWorkerRegistry

    registry = JobDefinitionRegistry.build((_definition(),))
    adapter = cast(
        _JobDefinitionWorkerRegistry,
        build_worker_registry(registry, {HANDLER_V1: _executor}),
    )
    with pytest.raises(TypeError):
        adapter._executors[HANDLER_V2] = _executor  # type: ignore[index]
    assert adapter.resolve(KEY_VALIDATE) is _executor
    assert adapter.resolve(UNKNOWN_KEY) is None


@pytest.mark.parametrize(("key", "message"), UNKNOWN_LOOKUP_CASES)
def test_registry_get_rejects_unknown_key(key: JobStepKey, message: str) -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    with pytest.raises(JobDefinitionLookupError, match=message) as exc_info:
        registry.get(key)
    error = exc_info.value
    assert error.key == key
    assert error.job_contract_version is None


@pytest.mark.parametrize(("version", "message"), UNSUPPORTED_VERSION_CASES)
def test_registry_resolve_runnable_rejects_unsupported_version(version: str, message: str) -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    with pytest.raises(JobDefinitionLookupError, match=message) as exc_info:
        registry.resolve_runnable(KEY_VALIDATE, version)
    error = exc_info.value
    assert error.key == KEY_VALIDATE
    assert error.job_contract_version == version


def test_registry_resolve_runnable_accepts_supported_version() -> None:
    registry = JobDefinitionRegistry.build(
        (_definition(versions=frozenset({VERSION_V1, VERSION_V2})),)
    )
    assert registry.resolve_runnable(KEY_VALIDATE, VERSION_V2) == _definition(
        versions=frozenset({VERSION_V1, VERSION_V2})
    )


@pytest.mark.parametrize(("definitions", "message"), MALFORMED_REGISTRY_BUILDS)
def test_registry_build_rejects_malformed_definitions(definitions: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        JobDefinitionRegistry.build(definitions)


@pytest.mark.parametrize(("executors", "message"), MALFORMED_WORKER_REGISTRY_BINDINGS)
def test_build_worker_registry_rejects_malformed_bindings(
    executors: dict[str, Callable[..., Any]],
    message: str,
) -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    with pytest.raises(ValueError, match=message):
        build_worker_registry(registry, executors)


def test_worker_registry_adapter_resolves_known_and_unknown_keys() -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    adapter = build_worker_registry(registry, {HANDLER_V1: _executor})

    assert isinstance(adapter, WorkerRegistry)
    resolved = adapter.resolve(KEY_VALIDATE)
    assert callable(resolved)
    assert adapter.resolve(UNKNOWN_KEY) is None


def test_job_definitions_module_has_no_filesystem_or_network_surface() -> None:
    text = JOB_DEFINITIONS_SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "httpx",
        "subprocess",
        "open(",
        "pathlib",
        "socket",
        "urllib",
    )
    for token in forbidden:
        assert token not in text


def test_build_job_worker_composition_with_empty_definitions() -> None:
    store = InMemoryArtifactStore()
    composition = build_job_worker_composition((), {}, artifact_store=store, decoders={})

    assert composition.definition_registry.definitions() == ()
    assert composition.worker_registry.resolve(KEY_VALIDATE) is None


def _failing_payload_decoder(_payload: dict[str, object]) -> object:
    raise ValueError("typed decode failed")


def test_validate_active_pairs_job_contract_versions_rejects_unsupported_version() -> None:
    registry = JobDefinitionRegistry.build((_definition(),))
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="operation-validate-1",
        job_kind=KEY_VALIDATE.job_kind,
        job_contract_version=VERSION_V2,
        job_payload=canonicalize_json_value({}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.QUEUED,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-validate-1",
        operation_id=operation.operation_id,
        step_name=KEY_VALIDATE.step_name,
        prior_output_refs=(),
        status=StepStatus.PENDING,
        diagnostic=None,
        cancel_requested=False,
        attempt_count=0,
        retry_not_before=None,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        checkpoint_ref=None,
        started_at=None,
        completed_at=None,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        optimistic_version=0,
    )
    with pytest.raises(ValueError, match="job_contract_version is not supported"):
        validate_active_pairs_job_contract_versions(registry, ((operation, step),))


def test_decoding_executor_wrapper_invokes_handler_after_successful_decode() -> None:
    handler_calls: list[str] = []

    def handler(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        del control, lease_session
        handler_calls.append(f"{operation.operation_id}:{step.step_id}")
        return ExecutorAcknowledgment.PUBLISHED

    store = InMemoryArtifactStore()
    composition = build_job_worker_composition(
        (_definition(),),
        {HANDLER_V1: handler},
        artifact_store=store,
        decoders={DECODER_V1: lambda payload: payload},
    )
    executor = composition.worker_registry.resolve(KEY_VALIDATE)
    assert executor is not None
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="operation-decode-1",
        job_kind=KEY_VALIDATE.job_kind,
        job_contract_version=VERSION_V1,
        job_payload=canonicalize_json_value({"seed": "alpha"}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.QUEUED,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-decode-1",
        operation_id=operation.operation_id,
        step_name=KEY_VALIDATE.step_name,
        prior_output_refs=(),
        status=StepStatus.RUNNING,
        diagnostic=None,
        cancel_requested=False,
        attempt_count=1,
        retry_not_before=None,
        worker_id="worker-decode-1",
        lease_token="lease-decode-1",
        lease_expires_at=LEASE_EXPIRES_AT,
        checkpoint_ref=None,
        started_at=BASE_TIME,
        completed_at=None,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        optimistic_version=0,
    )
    assert executor(operation, step, ExecutionControl(), cast(LeaseSession, object())) is (
        ExecutorAcknowledgment.PUBLISHED
    )
    assert handler_calls == ["operation-decode-1:step-decode-1"]


def test_decoding_executor_wrapper_does_not_invoke_handler_on_decode_failure() -> None:
    handler_called = False

    def handler(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        del operation, step, control, lease_session
        nonlocal handler_called
        handler_called = True
        return ExecutorAcknowledgment.PUBLISHED

    store = InMemoryArtifactStore()
    composition = build_job_worker_composition(
        (_definition(),),
        {HANDLER_V1: handler},
        artifact_store=store,
        decoders={DECODER_V1: _failing_payload_decoder},
    )
    executor = composition.worker_registry.resolve(KEY_VALIDATE)
    assert executor is not None
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="operation-decode-2",
        job_kind=KEY_VALIDATE.job_kind,
        job_contract_version=VERSION_V1,
        job_payload=canonicalize_json_value({"seed": "alpha"}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.QUEUED,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-decode-2",
        operation_id=operation.operation_id,
        step_name=KEY_VALIDATE.step_name,
        prior_output_refs=(),
        status=StepStatus.RUNNING,
        diagnostic=None,
        cancel_requested=False,
        attempt_count=1,
        retry_not_before=None,
        worker_id="worker-decode-2",
        lease_token="lease-decode-2",
        lease_expires_at=LEASE_EXPIRES_AT,
        checkpoint_ref=None,
        started_at=BASE_TIME,
        completed_at=None,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        optimistic_version=0,
    )
    with pytest.raises(PayloadDecodeError, match="typed decode failed"):
        executor(operation, step, ExecutionControl(), cast(LeaseSession, object()))
    assert handler_called is False
