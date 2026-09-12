"""Preview JobDefinition registry completeness checks owned by the 5A composition."""

from __future__ import annotations

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_DECODER,
    PREVIEW_JOB_KIND,
    PREVIEW_MATERIALIZE_DECODER,
    PREVIEW_PUBLISH_DECODER,
    PREVIEW_STEP_ASSEMBLE,
    PREVIEW_STEP_MATERIALIZE,
    PREVIEW_STEP_PUBLISH,
    preview_job_definitions,
)
from gateway_backend.operations.contracts import JobStepKey


def build_preview_job_registry() -> JobDefinitionRegistry:
    return JobDefinitionRegistry.build(preview_job_definitions())


def assert_preview_registry_ready(registry: JobDefinitionRegistry) -> None:
    """Fail closed unless the frozen three-step preview registry is complete."""

    if type(registry) is not JobDefinitionRegistry:
        raise ValueError("preview JobDefinition registry is incomplete")
    expected = (
        (PREVIEW_STEP_MATERIALIZE, PREVIEW_MATERIALIZE_DECODER),
        (PREVIEW_STEP_ASSEMBLE, PREVIEW_ASSEMBLE_DECODER),
        (PREVIEW_STEP_PUBLISH, PREVIEW_PUBLISH_DECODER),
    )
    for step_name, decoder_identity in expected:
        definition = registry.get(JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=step_name))
        if definition.decoder_identity != decoder_identity:
            raise ValueError("preview JobDefinition registry decoder mismatch")


__all__ = [
    "assert_preview_registry_ready",
    "build_preview_job_registry",
]
