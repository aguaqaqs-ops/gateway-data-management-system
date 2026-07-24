"""Runner-owned deep snapshots of harness observations."""

from __future__ import annotations

import copy

from gateway_conformance.runner.types import ActualObservation, Diagnostic


def snapshot_observation(observation: ActualObservation) -> ActualObservation:
    binding = copy.deepcopy(observation.contract_binding)
    descriptor = copy.deepcopy(observation.payload_descriptor)
    payload = copy.deepcopy(observation.payload)
    diagnostics = tuple(
        Diagnostic(code=item.code, message=item.message) for item in observation.diagnostics
    )
    return ActualObservation(
        expectation_id=observation.expectation_id,
        observation_point=observation.observation_point,
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=observation.canonical_encoding_version,
        actual_content_digest=observation.actual_content_digest,
        payload=payload,
        diagnostics=diagnostics,
    )


def snapshot_observations(observations: list[ActualObservation]) -> list[ActualObservation]:
    return [snapshot_observation(item) for item in observations]
