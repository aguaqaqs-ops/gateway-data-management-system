"""History compare JobDefinition registry completeness checks."""

from __future__ import annotations

from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_DECODER,
    HISTORY_COMPARE_JOB_KIND,
    HISTORY_COMPARE_MATERIALIZE_DECODER,
    HISTORY_COMPARE_PUBLISH_DECODER,
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
)
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.operations.contracts import JobStepKey


def assert_compare_registry_ready(registry: JobDefinitionRegistry) -> None:
    if type(registry) is not JobDefinitionRegistry:
        raise ValueError("history compare JobDefinition registry is incomplete")
    expected = (
        (HISTORY_COMPARE_STEP_MATERIALIZE, HISTORY_COMPARE_MATERIALIZE_DECODER),
        (HISTORY_COMPARE_STEP_ASSEMBLE, HISTORY_COMPARE_ASSEMBLE_DECODER),
        (HISTORY_COMPARE_STEP_PUBLISH, HISTORY_COMPARE_PUBLISH_DECODER),
    )
    for step_name, decoder_identity in expected:
        definition = registry.get(JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=step_name))
        if definition.decoder_identity != decoder_identity:
            raise ValueError("history compare JobDefinition registry decoder mismatch")


__all__ = [
    "assert_compare_registry_ready",
]
