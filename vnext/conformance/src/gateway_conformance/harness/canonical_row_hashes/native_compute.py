"""Rust native facade compute path."""

from __future__ import annotations

import io
from typing import Any

import pyarrow as pa

from gateway_conformance.harness.canonical_row_hashes.constants import TABLE_STREAM_LOGICAL_NAME
from gateway_conformance.harness.canonical_row_hashes.result_payload import (
    declared_fields_from_plan,
    request_jcs_from_plan,
    result_value_from_compute_jcs,
)
from gateway_conformance.runner.runtime import HarnessRuntimeContext

# Test probes (not part of formal observation identity).
NATIVE_FACADE_INVOKE_COUNT = 0


def compute_native_result_value(
    context: HarnessRuntimeContext,
    plan: dict[str, object],
) -> dict[str, Any]:
    global NATIVE_FACADE_INVOKE_COUNT
    from gateway_backend.compute import canonical_row_hashes_v1

    NATIVE_FACADE_INVOKE_COUNT += 1
    ipc_bytes = context.resolver.read_bytes(TABLE_STREAM_LOGICAL_NAME)
    reader = pa.ipc.open_stream(io.BytesIO(ipc_bytes))
    request_jcs = request_jcs_from_plan(plan)
    _fields = declared_fields_from_plan(plan)
    _output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    return result_value_from_compute_jcs(result_jcs)


def reset_native_invoke_probe() -> None:
    global NATIVE_FACADE_INVOKE_COUNT
    NATIVE_FACADE_INVOKE_COUNT = 0
