"""History compare digest helpers and deterministic identifiers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HistoryCompareNodeBinding,
    HistoryNodeRefKind,
)

HISTORY_COMPARE_DIGEST_PREFIX = "gateway-vnext:history:"
HISTORY_COMPARE_DIGEST_VERSION = "v1"
HISTORY_COMPARE_OPERATION_ID_KIND = "history-compare-operation-id"
HISTORY_COMPARE_OPERATION_ID_VERSION = 1


def compute_history_compare_digest(kind: str, payload: Mapping[str, Any]) -> str:
    if type(kind) is not str or not kind:
        raise ValueError("kind must be a non-empty string")
    preimage = (
        f"{HISTORY_COMPARE_DIGEST_PREFIX}{kind}:{HISTORY_COMPARE_DIGEST_VERSION}".encode("utf-8")
        + b"\x00"
        + canonicalize_jcs(canonicalize_json_value(dict(payload)))
    )
    return f"sha256:{hashlib.sha256(preimage).hexdigest()}"


def _node_binding_payload(node: HistoryCompareNodeBinding) -> dict[str, str]:
    return {
        "ref_kind": node.ref_kind.value,
        "ref_id": node.ref_id,
        "commit_id": node.commit_id,
    }


def _accept_binding_payload(
    *,
    gateway_device_external_key: str,
    business_project_id: str,
    repository_id: str,
    nodes: Sequence[HistoryCompareNodeBinding],
    table_ruleset_version: str,
    comparison_contract_version: str,
    view_kind: str,
    pair_count: int,
) -> dict[str, object]:
    return {
        "gateway_device_external_key": gateway_device_external_key,
        "business_project_id": business_project_id,
        "repository_id": repository_id,
        "nodes": [_node_binding_payload(node) for node in nodes],
        "table_ruleset_version": table_ruleset_version,
        "comparison_contract_version": comparison_contract_version,
        "view_kind": view_kind,
        "pair_count": pair_count,
    }


def compute_accept_binding_fingerprint(
    *,
    gateway_device_external_key: str,
    business_project_id: str,
    repository_id: str,
    nodes: Sequence[HistoryCompareNodeBinding],
    table_ruleset_version: str,
    comparison_contract_version: str = HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    view_kind: str = "HISTORY",
    pair_count: int | None = None,
) -> str:
    resolved_pair_count = pair_count if pair_count is not None else max(len(nodes) - 1, 1)
    payload = _accept_binding_payload(
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
        repository_id=repository_id,
        nodes=nodes,
        table_ruleset_version=table_ruleset_version,
        comparison_contract_version=comparison_contract_version,
        view_kind=view_kind,
        pair_count=resolved_pair_count,
    )
    return compute_history_compare_digest("accept-binding", payload)


def compute_compare_binding_digest(
    *,
    gateway_device_external_key: str,
    business_project_id: str,
    repository_id: str,
    nodes: Sequence[HistoryCompareNodeBinding],
    table_ruleset_version: str,
    table_policies: Sequence[Mapping[str, object]],
    comparison_contract_version: str = HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    view_kind: str = "HISTORY",
    pair_count: int | None = None,
) -> str:
    resolved_pair_count = pair_count if pair_count is not None else max(len(nodes) - 1, 1)
    payload = _accept_binding_payload(
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
        repository_id=repository_id,
        nodes=nodes,
        table_ruleset_version=table_ruleset_version,
        comparison_contract_version=comparison_contract_version,
        view_kind=view_kind,
        pair_count=resolved_pair_count,
    )
    extended = dict(payload)
    extended["table_policies"] = [dict(item) for item in table_policies]
    return compute_history_compare_digest("compare-binding", extended)


def deterministic_history_compare_ids(
    *,
    gateway_device_external_key: str,
    business_project_id: str,
    idempotency_key: str,
) -> tuple[str, str]:
    preimage = canonicalize_json_value(
        {
            "kind": HISTORY_COMPARE_OPERATION_ID_KIND,
            "v": HISTORY_COMPARE_OPERATION_ID_VERSION,
            "gateway_device_external_key": gateway_device_external_key,
            "business_project_id": business_project_id,
            "idempotency_key": idempotency_key,
        }
    )
    digest = hashlib.sha256(preimage).hexdigest()[:24]
    return f"op-{digest}", f"hca-{digest}"


def nodes_json_from_bindings(nodes: Sequence[HistoryCompareNodeBinding]) -> str:
    payload = [_node_binding_payload(node) for node in nodes]
    return canonicalize_jcs(canonicalize_json_value(payload)).decode("utf-8")


def parse_nodes_json(raw: str) -> tuple[HistoryCompareNodeBinding, ...]:
    import json

    decoded = json.loads(raw)
    if type(decoded) is not list:
        raise ValueError("nodes_json must decode to a list")
    nodes: list[HistoryCompareNodeBinding] = []
    for item in decoded:
        if type(item) is not dict:
            raise ValueError("nodes_json entry must be an object")
        nodes.append(
            HistoryCompareNodeBinding(
                ref_kind=HistoryNodeRefKind(str(item["ref_kind"])),
                ref_id=str(item["ref_id"]),
                commit_id=str(item["commit_id"]),
            )
        )
    return tuple(nodes)


__all__ = [
    "HISTORY_COMPARE_DIGEST_PREFIX",
    "HISTORY_COMPARE_DIGEST_VERSION",
    "HISTORY_COMPARE_OPERATION_ID_KIND",
    "HISTORY_COMPARE_OPERATION_ID_VERSION",
    "compute_accept_binding_fingerprint",
    "compute_compare_binding_digest",
    "compute_history_compare_digest",
    "deterministic_history_compare_ids",
    "nodes_json_from_bindings",
    "parse_nodes_json",
]
