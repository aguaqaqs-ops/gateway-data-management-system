"""Authoritative Submit JobDefinition registry for worker and acceptance gates."""

from __future__ import annotations

from gateway_backend.application.job_definitions import JobDefinition, JobDefinitionRegistry, NormalPublicationCapability
from gateway_backend.application.recovery import RecoveryCapability
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


__all__ = [
    "AWAIT_IMPORT_DECODER",
    "AWAIT_IMPORT_HANDLER",
    "PREPARE_IMPORT_DECODER",
    "PREPARE_IMPORT_HANDLER",
    "SUBMIT_IMPORT_DECODER",
    "SUBMIT_IMPORT_HANDLER",
    "submit_job_definitions",
    "submit_job_registry",
]
