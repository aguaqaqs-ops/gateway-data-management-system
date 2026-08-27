"""Application-owned JobDefinition descriptors and immutable registry."""

from __future__ import annotations

import re
import types
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from typing import TYPE_CHECKING

from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.operations.contracts import JobStepKey, OperationRecord, StepRecord
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    WorkerRegistry,
)

if TYPE_CHECKING:
    from gateway_backend.application.payloads import PayloadDecoder, PayloadDecoderRegistry

_CONTRACT_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,128}$")
_MAX_DEFINITIONS = 256


class NormalPublicationCapability(StrEnum):
    """Static normal completion path for one JobDefinition step."""

    SINGLE_SUCCESSOR = "SINGLE_SUCCESSOR"
    TERMINAL = "TERMINAL"


class JobDefinitionLookupError(ValueError):
    """Bounded lookup failure for an unknown key or unsupported contract version."""

    def __init__(
        self,
        message: str,
        *,
        key: JobStepKey | None = None,
        job_contract_version: str | None = None,
    ) -> None:
        super().__init__(message)
        self.key = key
        self.job_contract_version = job_contract_version


@dataclass(frozen=True, slots=True)
class JobDefinition:
    """Immutable JobDefinition descriptor without business entities or callables."""

    key: JobStepKey
    supported_payload_versions: frozenset[str]
    decoder_identity: str
    handler_identity: str
    publication_capability: NormalPublicationCapability
    recovery_capability: RecoveryCapability

    def __post_init__(self) -> None:
        if type(self.key) is not JobStepKey:
            raise ValueError("key must be JobStepKey")
        if type(self.supported_payload_versions) is not frozenset:
            raise ValueError("supported_payload_versions must be frozenset")
        if not self.supported_payload_versions:
            raise ValueError("supported_payload_versions must not be empty")
        for version in self.supported_payload_versions:
            _validate_contract_version_string(version, "supported_payload_versions")
        _validate_contract_version_string(self.decoder_identity, "decoder_identity")
        _validate_contract_version_string(self.handler_identity, "handler_identity")
        if type(self.publication_capability) is not NormalPublicationCapability:
            raise ValueError("publication_capability must be NormalPublicationCapability")
        if type(self.recovery_capability) is not RecoveryCapability:
            raise ValueError("recovery_capability must be RecoveryCapability")


@dataclass(frozen=True, slots=True)
class JobDefinitionRegistry:
    """Process-local immutable registry with bounded in-memory lookup."""

    _by_key: Mapping[JobStepKey, JobDefinition]
    _definitions: tuple[JobDefinition, ...]

    @classmethod
    def build(cls, definitions: tuple[JobDefinition, ...]) -> JobDefinitionRegistry:
        if type(definitions) is not tuple:
            raise ValueError("definitions must be a tuple")
        if len(definitions) > _MAX_DEFINITIONS:
            raise ValueError("registry exceeds bounded definition count")
        by_key: dict[JobStepKey, JobDefinition] = {}
        seen_handlers: set[str] = set()
        seen_decoders: set[str] = set()
        for definition in definitions:
            if type(definition) is not JobDefinition:
                raise ValueError("definitions must contain JobDefinition")
            if definition.key in by_key:
                raise ValueError("duplicate JobStepKey in registry build")
            if definition.handler_identity in seen_handlers:
                raise ValueError("duplicate handler_identity in registry build")
            if definition.decoder_identity in seen_decoders:
                raise ValueError("duplicate decoder_identity in registry build")
            by_key[definition.key] = definition
            seen_handlers.add(definition.handler_identity)
            seen_decoders.add(definition.decoder_identity)
        return JobDefinitionRegistry(
            _by_key=types.MappingProxyType(by_key),
            _definitions=definitions,
        )

    def decoder_identities(self) -> frozenset[str]:
        return frozenset(definition.decoder_identity for definition in self._definitions)

    def definitions(self) -> tuple[JobDefinition, ...]:
        return self._definitions

    def get(self, key: JobStepKey) -> JobDefinition:
        if type(key) is not JobStepKey:
            raise ValueError("key must be JobStepKey")
        definition = self._by_key.get(key)
        if definition is None:
            raise JobDefinitionLookupError(
                "registry has no JobDefinition for the JobStepKey",
                key=key,
            )
        return definition

    def resolve_runnable(self, key: JobStepKey, job_contract_version: str) -> JobDefinition:
        definition = self.get(key)
        _validate_contract_version_string(job_contract_version, "job_contract_version")
        if job_contract_version not in definition.supported_payload_versions:
            raise JobDefinitionLookupError(
                "job_contract_version is not supported by the JobDefinition",
                key=key,
                job_contract_version=job_contract_version,
            )
        return definition

    def _lookup(self, key: JobStepKey) -> JobDefinition | None:
        if type(key) is not JobStepKey:
            return None
        return self._by_key.get(key)


@dataclass(frozen=True, slots=True)
class _JobDefinitionWorkerRegistry:
    """Adapter mapping immutable definitions to the R3 WorkerRegistry port."""

    _registry: JobDefinitionRegistry
    _executors: Mapping[str, ClaimedExecutor]

    def resolve(self, key: JobStepKey) -> ClaimedExecutor | None:
        definition = self._registry._lookup(key)
        if definition is None:
            return None
        return self._executors.get(definition.handler_identity)


@dataclass(frozen=True, slots=True)
class JobWorkerComposition:
    """Immutable R4 worker composition bound to one artifact store and decoder registry."""

    definition_registry: JobDefinitionRegistry
    decoder_registry: PayloadDecoderRegistry
    worker_registry: WorkerRegistry
    artifact_store: ArtifactStorePort


def build_job_worker_composition(
    definitions: tuple[JobDefinition, ...],
    handlers: Mapping[str, ClaimedExecutor],
    *,
    artifact_store: ArtifactStorePort,
    decoders: Mapping[str, PayloadDecoder],
) -> JobWorkerComposition:
    """Compose immutable definitions, decoders, and R3-compatible worker registry."""

    from gateway_backend.application.payloads import build_payload_decoder_registry

    if type(definitions) is not tuple:
        raise ValueError("definitions must be a tuple")
    if not isinstance(handlers, Mapping):
        raise ValueError("handlers must be a mapping")
    if not isinstance(decoders, Mapping):
        raise ValueError("decoders must be a mapping")
    definition_registry = JobDefinitionRegistry.build(definitions)
    decoder_registry = build_payload_decoder_registry(definition_registry, decoders)
    wrapped_handlers: dict[str, ClaimedExecutor] = {}
    for definition in definition_registry.definitions():
        handler = handlers.get(definition.handler_identity)
        if handler is None:
            raise ValueError("handlers must bind exactly one callable per handler_identity")
        if not callable(handler):
            raise ValueError("handler must be callable")
        wrapped_handlers[definition.handler_identity] = _wrap_executor_with_payload_decode(
            definition,
            definition_registry,
            decoder_registry,
            artifact_store,
            handler,
        )
    worker_registry = build_worker_registry(definition_registry, wrapped_handlers)
    return JobWorkerComposition(
        definition_registry=definition_registry,
        decoder_registry=decoder_registry,
        worker_registry=worker_registry,
        artifact_store=artifact_store,
    )


def validate_active_pairs_job_contract_versions(
    registry: JobDefinitionRegistry,
    pairs: Iterable[tuple[OperationRecord, StepRecord]],
) -> None:
    """Fail closed when any active pair references an unsupported job contract version."""

    if type(registry) is not JobDefinitionRegistry:
        raise ValueError("registry must be JobDefinitionRegistry")
    for operation, step in pairs:
        if type(operation) is not OperationRecord:
            raise ValueError("operation must be OperationRecord")
        if type(step) is not StepRecord:
            raise ValueError("step must be StepRecord")
        try:
            registry.resolve_runnable(
                JobStepKey(job_kind=operation.job_kind, step_name=step.step_name),
                operation.job_contract_version,
            )
        except JobDefinitionLookupError as exc:
            raise ValueError(str(exc)) from exc


def build_worker_registry(
    registry: JobDefinitionRegistry,
    executors: Mapping[str, ClaimedExecutor],
) -> WorkerRegistry:
    """Compose a WorkerRegistry adapter from definitions and handler_identity bindings."""

    if type(registry) is not JobDefinitionRegistry:
        raise ValueError("registry must be JobDefinitionRegistry")
    if not isinstance(executors, Mapping):
        raise ValueError("executors must be a mapping")
    expected_handlers = frozenset(
        definition.handler_identity for definition in registry.definitions()
    )
    executor_handlers = frozenset(executors.keys())
    if executor_handlers != expected_handlers:
        raise ValueError("executors must bind exactly one callable per handler_identity")
    bound: dict[str, ClaimedExecutor] = {}
    for handler_identity, executor in executors.items():
        _validate_contract_version_string(handler_identity, "handler_identity")
        if not callable(executor):
            raise ValueError("executor must be callable")
        bound[handler_identity] = executor
    return _JobDefinitionWorkerRegistry(
        _registry=registry,
        _executors=types.MappingProxyType(bound),
    )


def _wrap_executor_with_payload_decode(
    definition: JobDefinition,
    registry: JobDefinitionRegistry,
    decoder_registry: PayloadDecoderRegistry,
    artifact_store: ArtifactStorePort,
    inner: ClaimedExecutor,
) -> ClaimedExecutor:
    from gateway_backend.application.payloads import decode_job_payload

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        resolved = registry.resolve_runnable(
            JobStepKey(job_kind=operation.job_kind, step_name=step.step_name),
            operation.job_contract_version,
        )
        if resolved.handler_identity != definition.handler_identity:
            raise ValueError("handler identity does not match the resolved JobDefinition")
        decode_job_payload(resolved, operation, artifact_store, decoder_registry)
        return inner(operation, step, control, lease_session)

    return execute


def _validate_contract_version_string(value: object, label: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    if not _CONTRACT_VERSION_RE.fullmatch(value):
        raise ValueError(f"{label} must be bounded ASCII printable")


__all__ = [
    "JobDefinition",
    "JobDefinitionLookupError",
    "JobDefinitionRegistry",
    "JobWorkerComposition",
    "NormalPublicationCapability",
    "RecoveryCapability",
    "build_job_worker_composition",
    "build_worker_registry",
    "validate_active_pairs_job_contract_versions",
]
