"""Python reference compute path (shared-kernel oracle only)."""

from __future__ import annotations

from typing import Any

from gateway_conformance.harness.canonical_row_hashes.constants import TABLE_STREAM_LOGICAL_NAME
from gateway_conformance.harness.canonical_row_hashes.result_payload import (
    declared_fields_from_plan,
    result_value_from_reference_ipc,
)
from gateway_conformance.runner.runtime import HarnessRuntimeContext


def compute_reference_result_value(
    context: HarnessRuntimeContext,
    plan: dict[str, object],
) -> dict[str, Any]:
    ipc_bytes = context.resolver.read_bytes(TABLE_STREAM_LOGICAL_NAME)
    fields = declared_fields_from_plan(plan)
    requests = plan["observation_requests"]
    if not isinstance(requests, list) or not requests:
        raise ValueError("missing observation requests")
    first = requests[0]
    if not isinstance(first, dict):
        raise ValueError("invalid observation request")
    binding = first["contract_binding"]
    if not isinstance(binding, dict):
        raise ValueError("invalid contract binding")
    return result_value_from_reference_ipc(
        ipc_bytes,
        fields,
        contract_binding={
            "contract_id": str(binding["contract_id"]),
            "semantic_version": str(binding["semantic_version"]),
        },
    )
