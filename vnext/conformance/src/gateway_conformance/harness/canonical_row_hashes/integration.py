"""Integration profile: facade, artifact persist, fresh reopen."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.constants import TABLE_STREAM_LOGICAL_NAME
from gateway_conformance.harness.canonical_row_hashes.result_payload import (
    declared_fields_from_plan,
    request_jcs_from_plan,
    result_value_from_compute_jcs,
)
from gateway_conformance.runner.runtime import HarnessRuntimeContext

INTEGRATION_FACADE_INVOKE_COUNT = 0
INTEGRATION_PERSIST_COUNT = 0
INTEGRATION_REOPEN_COUNT = 0


def _import_backend_ipc() -> Any:
    from gateway_backend.artifacts import RetentionClass, build_logical_ref
    from gateway_backend.canonical_row_hash_ipc import (
        content_manifest_from_compute_result,
        persist_canonical_row_hash_stream,
        reopen_and_verify_canonical_row_hash_artifact,
    )
    from gateway_backend.compute import canonical_row_hashes_v1
    from gateway_backend.infrastructure.artifact_store import LocalArtifactStore

    return {
        "RetentionClass": RetentionClass,
        "build_logical_ref": build_logical_ref,
        "content_manifest_from_compute_result": content_manifest_from_compute_result,
        "persist_canonical_row_hash_stream": persist_canonical_row_hash_stream,
        "reopen_and_verify_canonical_row_hash_artifact": reopen_and_verify_canonical_row_hash_artifact,
        "canonical_row_hashes_v1": canonical_row_hashes_v1,
        "LocalArtifactStore": LocalArtifactStore,
    }


def compute_integration_result_value(
    context: HarnessRuntimeContext,
    plan: dict[str, object],
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    global INTEGRATION_FACADE_INVOKE_COUNT, INTEGRATION_PERSIST_COUNT, INTEGRATION_REOPEN_COUNT
    backend = _import_backend_ipc()
    import io

    ipc_bytes = context.resolver.read_bytes(TABLE_STREAM_LOGICAL_NAME)
    reader = pa.ipc.open_stream(io.BytesIO(ipc_bytes))
    request_jcs = request_jcs_from_plan(plan)
    fields = declared_fields_from_plan(plan)
    INTEGRATION_FACADE_INVOKE_COUNT += 1
    output, result_jcs = backend["canonical_row_hashes_v1"](request_jcs, reader)
    content = backend["content_manifest_from_compute_result"](result_jcs)
    logical_ref = backend["build_logical_ref"]("canonical-row-hash", "wp5-r4-integration")
    store = backend["LocalArtifactStore"](artifact_root)
    INTEGRATION_PERSIST_COUNT += 1
    ref = backend["persist_canonical_row_hash_stream"](
        store,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
        retention_class=backend["RetentionClass"].OPERATION,
    )
    _ = ref
    fresh_store = backend["LocalArtifactStore"](artifact_root)
    INTEGRATION_REOPEN_COUNT += 1
    backend["reopen_and_verify_canonical_row_hash_artifact"](
        fresh_store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )
    return result_value_from_compute_jcs(result_jcs)


def reset_integration_probes() -> None:
    global INTEGRATION_FACADE_INVOKE_COUNT, INTEGRATION_PERSIST_COUNT, INTEGRATION_REOPEN_COUNT
    INTEGRATION_FACADE_INVOKE_COUNT = 0
    INTEGRATION_PERSIST_COUNT = 0
    INTEGRATION_REOPEN_COUNT = 0


class IntegrationArtifactSession:
    """Profile-owned temporary artifact storage (not serialized into plan/evidence)."""

    __slots__ = ("_directory", "_root")

    def __init__(self) -> None:
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._root: Path | None = None

    def provision(self) -> Path:
        if self._directory is not None:
            raise ConformanceValidationError("integration artifact session already provisioned")
        self._directory = tempfile.TemporaryDirectory(prefix="wp5-r4-artifacts-")
        self._root = Path(self._directory.name)
        return self._root

    def cleanup(self) -> None:
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
            self._root = None
