"""History compare job payload, dependency contracts, and JobDefinition metadata."""

from __future__ import annotations

import json

from collections.abc import Callable
from dataclasses import dataclass
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HistoryCompareNodeBinding,
)
from gateway_backend.application.history.ports import (
    HistoryControlTransaction as HistoryCompareControlTransaction,
)
from gateway_backend.application.job_definitions import (
    JobDefinition,
    NormalPublicationCapability,
)
from gateway_backend.application.job_steps import (
    require_non_empty_str,
    successor_step_id,
)
from gateway_backend.application.payloads import (
    PayloadDecodeError,
    load_job_payload_bytes,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.artifacts.computation_cache import ComputationCachePort
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryTableAccessProvider,
)
from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationRecord,
)
from typing import (
    ContextManager,
    cast,
)

HISTORY_COMPARE_STEP_MATERIALIZE = "materialize_inputs"

HISTORY_COMPARE_STEP_ASSEMBLE = "assemble_comparison"

HISTORY_COMPARE_STEP_PUBLISH = "publish_result"

HISTORY_COMPARE_MATERIALIZE_DECODER = "backend-vnext/history-compare/materialize/decoder/v1"

HISTORY_COMPARE_ASSEMBLE_DECODER = "backend-vnext/history-compare/assemble/decoder/v1"

HISTORY_COMPARE_PUBLISH_DECODER = "backend-vnext/history-compare/publish/decoder/v1"

HISTORY_COMPARE_MATERIALIZE_HANDLER = "backend-vnext/history-compare/materialize/handler/v1"

HISTORY_COMPARE_ASSEMBLE_HANDLER = "backend-vnext/history-compare/assemble/handler/v1"

HISTORY_COMPARE_PUBLISH_HANDLER = "backend-vnext/history-compare/publish/handler/v1"


class HistoryCompareJobError(ValueError):
    """Bounded history compare job failure surfaced to the operation runtime."""

    def __init__(self, message: str, *, diagnostic_code: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


class HistoryCompareInputError(HistoryCompareJobError):
    """Known exact-commit authority failure before comparison publication."""


class HistoryCompareRulesetVersionMismatch(HistoryCompareJobError):
    """Raised when frozen compare ruleset version does not match runtime."""


@dataclass(frozen=True, slots=True)
class HistoryCompareJobPayload:
    gateway_device_external_key: str
    business_project_id: str
    repository_id: str
    acceptance_id: str
    idempotency_key: str
    request_fingerprint: str
    comparison_ruleset_digest: str
    comparison_contract_version: str
    view_kind: str
    pair_count: int
    nodes: tuple[HistoryCompareNodeBinding, ...]


HistoryCompareControlTransactionFactory = Callable[
    [], ContextManager[HistoryCompareControlTransaction]
]

RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]


@dataclass(frozen=True, slots=True)
class HistoryCompareRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    control_transaction_factory: HistoryCompareControlTransactionFactory
    snapshot_export_cache: SnapshotTableExportCachePort | None = None
    computation_cache: ComputationCachePort | None = None


def history_compare_materialize_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(
            job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_MATERIALIZE
        ),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_MATERIALIZE_DECODER,
        handler_identity=HISTORY_COMPARE_MATERIALIZE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def history_compare_assemble_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_ASSEMBLE),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_ASSEMBLE_DECODER,
        handler_identity=HISTORY_COMPARE_ASSEMBLE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def history_compare_publish_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_PUBLISH),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_PUBLISH_DECODER,
        handler_identity=HISTORY_COMPARE_PUBLISH_HANDLER,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def decode_history_compare_payload(payload_object: dict[str, object]) -> HistoryCompareJobPayload:
    gateway_device_external_key = require_non_empty_str(
        payload_object, "gateway_device_external_key"
    )
    business_project_id = require_non_empty_str(payload_object, "business_project_id")
    repository_id = require_non_empty_str(payload_object, "repository_id")
    acceptance_id = require_non_empty_str(payload_object, "acceptance_id")
    idempotency_key = require_non_empty_str(payload_object, "idempotency_key")
    request_fingerprint = require_non_empty_str(payload_object, "request_fingerprint")
    comparison_ruleset_digest = require_non_empty_str(payload_object, "comparison_ruleset_digest")
    comparison_contract_version = require_non_empty_str(
        payload_object, "comparison_contract_version"
    )
    view_kind = require_non_empty_str(payload_object, "view_kind")
    pair_count = _require_positive_int(payload_object, "pair_count")
    nodes = _decode_nodes(payload_object.get("nodes"))
    return HistoryCompareJobPayload(
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
        repository_id=repository_id,
        acceptance_id=acceptance_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        comparison_ruleset_digest=comparison_ruleset_digest,
        comparison_contract_version=comparison_contract_version,
        view_kind=view_kind,
        pair_count=pair_count,
        nodes=nodes,
    )


def _load_history_compare_payload(
    operation: OperationRecord, store: ArtifactStorePort
) -> HistoryCompareJobPayload:
    payload_bytes = load_job_payload_bytes(operation, store)
    try:
        payload_object = json.loads(payload_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PayloadDecodeError(
            "job_payload must be canonical JSON bytes",
            code="PAYLOAD_SHAPE_INVALID",
        ) from exc
    if type(payload_object) is not dict:
        raise PayloadDecodeError("job_payload must be a JSON object", code="PAYLOAD_SHAPE_INVALID")
    return decode_history_compare_payload(cast(dict[str, object], payload_object))


_HISTORY_COMPARE_STEP_SUFFIX: dict[str, str] = {
    HISTORY_COMPARE_STEP_MATERIALIZE: "1",
    HISTORY_COMPARE_STEP_ASSEMBLE: "2",
    HISTORY_COMPARE_STEP_PUBLISH: "3",
}


def history_compare_step_id(operation_id: str, step_name: str) -> str:
    return successor_step_id(operation_id, step_name, _HISTORY_COMPARE_STEP_SUFFIX)


def _require_positive_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise PayloadDecodeError(f"{key} must be a positive int", code="PAYLOAD_SHAPE_INVALID")
    return value


def _decode_nodes(value: object) -> tuple[HistoryCompareNodeBinding, ...]:
    from gateway_backend.application.history.contracts import HistoryNodeRefKind

    if type(value) is not list or not value:
        raise PayloadDecodeError("nodes must be a non-empty list", code="PAYLOAD_SHAPE_INVALID")
    nodes: list[HistoryCompareNodeBinding] = []
    for item in value:
        if type(item) is not dict:
            raise PayloadDecodeError("node entry must be an object", code="PAYLOAD_SHAPE_INVALID")
        try:
            ref_kind = HistoryNodeRefKind(str(item["ref_kind"]))
            ref_id = str(item["ref_id"])
            commit_id = str(item["commit_id"])
        except KeyError as exc:
            raise PayloadDecodeError(
                f"node entry is missing required field: {exc.args[0]}",
                code="PAYLOAD_SHAPE_INVALID",
            ) from exc
        nodes.append(
            HistoryCompareNodeBinding(
                ref_kind=ref_kind,
                ref_id=ref_id,
                commit_id=commit_id,
            )
        )
    return tuple(nodes)


__all__ = [
    "HISTORY_COMPARE_STEP_MATERIALIZE",
    "HISTORY_COMPARE_STEP_ASSEMBLE",
    "HISTORY_COMPARE_STEP_PUBLISH",
    "HISTORY_COMPARE_MATERIALIZE_DECODER",
    "HISTORY_COMPARE_ASSEMBLE_DECODER",
    "HISTORY_COMPARE_PUBLISH_DECODER",
    "HISTORY_COMPARE_MATERIALIZE_HANDLER",
    "HISTORY_COMPARE_ASSEMBLE_HANDLER",
    "HISTORY_COMPARE_PUBLISH_HANDLER",
    "HistoryCompareJobError",
    "HistoryCompareInputError",
    "HistoryCompareRulesetVersionMismatch",
    "HistoryCompareJobPayload",
    "HistoryCompareControlTransactionFactory",
    "RepositoryProviderFactory",
    "HistoryCompareRuntimeDependencies",
    "history_compare_materialize_job_definition",
    "history_compare_assemble_job_definition",
    "history_compare_publish_job_definition",
    "decode_history_compare_payload",
    "history_compare_step_id",
]
