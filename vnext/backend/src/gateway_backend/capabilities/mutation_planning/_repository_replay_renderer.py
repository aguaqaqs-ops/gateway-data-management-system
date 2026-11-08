"""Public ChangeSet replay facade; Rust owns every SQL byte and batch rule."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.mutation_planning.contracts import (
    MAX_REPLAY_SQL_BYTES,
    RENDERER_CAPABILITY_CONTRACT_VERSION,
    ChangeSetClosure,
    MutationFailureCode,
    MutationTargetKind,
    RendererCapabilityDeclaration,
    validate_canonical_cell_value,
)
from gateway_backend.capabilities.mutation_planning.native import render_change_set_native
from gateway_backend.capabilities.storage_projection import KernelExecutionContext, require_storage_operation

_REPOSITORY_REPLAY_CAPABILITY_VERSION = "v1"
_REPOSITORY_REPLAY_DIALECT = "mysql-repository-replay/v1"
_SUPPORTED_OPERATIONS = ("DELETE", "INSERT", "UPDATE")
_SUPPORTED_CELL_KINDS = (
    "bit", "binary", "boolean", "date", "datetime", "decimal", "float32",
    "float64", "null", "signed-integer", "string", "time-duration",
    "timestamp", "unsigned-integer",
)

ReplayRenderStatus = Literal["READY", "FAILED"]


@dataclass(frozen=True, slots=True)
class ReplayRenderOutcome:
    status: ReplayRenderStatus
    sql_bytes: bytes | None = None
    failure_code: MutationFailureCode | None = None
    sql_digest: DigestRef | None = None


def repository_replay_capability_payload() -> dict[str, object]:
    return {
        "dialect": _REPOSITORY_REPLAY_DIALECT,
        "identifier_quoting": "backtick",
        "supported_cell_kinds": list(_SUPPORTED_CELL_KINDS),
        "supported_operations": list(_SUPPORTED_OPERATIONS),
    }


def compute_repository_replay_capability_digest() -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(repository_replay_capability_payload()))


REPOSITORY_REPLAY_RENDERER_CAPABILITY = RendererCapabilityDeclaration(
    target_kind=MutationTargetKind.CANONICAL_REPOSITORY_REPLAY,
    capability_version=_REPOSITORY_REPLAY_CAPABILITY_VERSION,
    capability_digest=compute_repository_replay_capability_digest(),
    capability_contract_version=RENDERER_CAPABILITY_CONTRACT_VERSION,
)


def _failed(code: MutationFailureCode) -> ReplayRenderOutcome:
    return ReplayRenderOutcome(status="FAILED", failure_code=code)


def _structural_resident_bound(closure: ChangeSetClosure) -> int:
    """Bound the already constructed row graph without serializing it first."""
    total = 4096 + len(closure.mutations) * 2048
    for mutation in closure.mutations:
        total += len(mutation.canonical_table) * 8
        for image in (mutation.canonical_storage_key, mutation.after_image):
            if image is None:
                continue
            for name, cell in image.columns:
                total += len(name) * 8 + 512
                for key, value in cell.items():
                    total += (len(key) * 8 if type(key) is str else 1024)
                    total += (len(value) * 8 if type(value) is str else 1024) + 128
    return total


def _validated_columns(columns: tuple[tuple[str, dict[str, object]], ...]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name, cell in columns:
        if cell.get("kind") == "source-literal-anomaly":
            raise ValueError("source literal anomaly has no SQL encoding")
        result.append({"column": name, "value": validate_canonical_cell_value(cell, name)})
    return result


def render_change_set_replay(
    closure: ChangeSetClosure,
    *,
    context: KernelExecutionContext,
    expected_renderer_capability: RendererCapabilityDeclaration | None = None,
) -> ReplayRenderOutcome:
    active = cast(KernelExecutionContext, require_storage_operation(context))
    manifest_capability = closure.manifest.renderer_capability
    expected = expected_renderer_capability or REPOSITORY_REPLAY_RENDERER_CAPABILITY
    if (manifest_capability != expected
            or manifest_capability.target_kind is not MutationTargetKind.CANONICAL_REPOSITORY_REPLAY):
        return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    # The structural closure is caller-owned. This common backing key shares a
    # retained metadata charge if the caller already registered this object.
    structural = _structural_resident_bound(closure)
    active.memory.retain_metadata(closure, structural * 4)
    conversion = active.memory.reserve(structural * 16)
    try:
        try:
            payload = json.dumps(
                [{"canonical_table": mutation.canonical_table,
                  "operation": mutation.operation.value,
                  "canonical_storage_key": _validated_columns(mutation.canonical_storage_key.columns),
                  "after_image": None if mutation.after_image is None
                    else _validated_columns(mutation.after_image.columns)}
                 for mutation in closure.mutations],
                separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")
        except (ValueError, TypeError):
            return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
        # A CASE repeats each key predicate once per persisted nonkey column.
        # This is only a conservative memory bound, never a SQL size policy.
        case_columns = max((len(m.after_image.columns) for m in closure.mutations
                            if m.operation.value == "UPDATE" and m.after_image is not None),
                           default=1)
        output_upper = min(MAX_REPLAY_SQL_BYTES,
                           len(payload) * 16 * case_columns + len(closure.mutations) * 4096 + 4096)
        try:
            sql_bytes = render_change_set_native(payload, active, MAX_REPLAY_SQL_BYTES, output_upper)
        except ValueError as exc:
            return _failed(MutationFailureCode.RESOURCE_EXCEEDED if str(exc) == "RESOURCE_EXCEEDED"
                           else MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    finally:
        conversion.close()
    return ReplayRenderOutcome(
        status="READY", sql_bytes=sql_bytes, sql_digest=raw_blob_digest(sql_bytes),
    )
