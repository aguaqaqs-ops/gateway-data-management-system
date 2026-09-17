"""Authoritative Submit JobDefinition registry for worker and acceptance gates."""

from __future__ import annotations

from collections.abc import Callable

from gateway_backend.application.job_definitions import JobDefinition, JobDefinitionRegistry, NormalPublicationCapability
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.operations.recovery import RecoveryCapabilityValue
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.operations.contracts import JobStepKey

PREPARE_IMPORT_DECODER = "backend-vnext/submit/prepare-import/decoder/v1"
PREPARE_IMPORT_HANDLER = "backend-vnext/submit/prepare-import/handler/v1"
SUBMIT_IMPORT_DECODER = "backend-vnext/submit/submit-import/decoder/v1"
SUBMIT_IMPORT_HANDLER = "backend-vnext/submit/submit-import/handler/v1"
AWAIT_IMPORT_DECODER = "backend-vnext/submit/await-import-result/decoder/v1"
AWAIT_IMPORT_HANDLER = "backend-vnext/submit/await-import-result/handler/v1"


def submit_job_definitions() -> tuple[JobDefinition, ...]:
    return (
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_PREPARE),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity=PREPARE_IMPORT_DECODER,
            handler_identity=PREPARE_IMPORT_HANDLER,
            publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
            recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
        ),
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_SUBMIT),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity=SUBMIT_IMPORT_DECODER,
            handler_identity=SUBMIT_IMPORT_HANDLER,
            publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
            recovery_capability=RecoveryCapability.EXTERNAL_EFFECT,
        ),
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_AWAIT),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity=AWAIT_IMPORT_DECODER,
            handler_identity=AWAIT_IMPORT_HANDLER,
            publication_capability=NormalPublicationCapability.TERMINAL,
            recovery_capability=RecoveryCapability.EXTERNAL_EFFECT,
        ),
    )


def submit_job_registry() -> JobDefinitionRegistry:
    return JobDefinitionRegistry.build(submit_job_definitions())


def assert_submit_registry_decoders(registry: JobDefinitionRegistry) -> None:
    expected = (
        (SUBMIT_STEP_PREPARE, PREPARE_IMPORT_DECODER),
        (SUBMIT_STEP_SUBMIT, SUBMIT_IMPORT_DECODER),
        (SUBMIT_STEP_AWAIT, AWAIT_IMPORT_DECODER),
    )
    for step_name, decoder_identity in expected:
        definition = registry.get(JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=step_name))
        if definition.decoder_identity != decoder_identity:
            raise ValueError("submit JobDefinition registry decoder mismatch")


def build_submit_recovery_capability_mapping(
    registry: JobDefinitionRegistry,
) -> dict[tuple[str, str], RecoveryCapabilityValue]:
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
    return mapping


def build_submit_recovery_capability_lookup(
    registry: JobDefinitionRegistry,
) -> Callable[[str, str], RecoveryCapabilityValue]:
    mapping = build_submit_recovery_capability_mapping(registry)

    def lookup(job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        return mapping[(job_kind, step_name)]

    return lookup


__all__ = [
    "assert_submit_registry_decoders",
    "build_submit_recovery_capability_lookup",
    "build_submit_recovery_capability_mapping",
    "AWAIT_IMPORT_DECODER",
    "AWAIT_IMPORT_HANDLER",
    "PREPARE_IMPORT_DECODER",
    "PREPARE_IMPORT_HANDLER",
    "SUBMIT_IMPORT_DECODER",
    "SUBMIT_IMPORT_HANDLER",
    "submit_job_definitions",
    "submit_job_registry",
]
