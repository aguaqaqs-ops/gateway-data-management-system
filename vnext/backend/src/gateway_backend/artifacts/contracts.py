"""Artifact content contract registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from gateway_backend.artifacts.types import ContentContract


@dataclass(frozen=True, slots=True)
class ContentContractSpec:
    contract_id: str
    semantic_version: str
    content_schema_id: str
    media_type: str


CANONICAL_ROW_HASHES_ARTIFACT = ContentContractSpec(
    contract_id="gateway-vnext.canonical-row-hash-compute-boundary",
    semantic_version="1.0.0",
    content_schema_id="gateway-vnext.canonical-row-hash.canonical-row-hashes-artifact.v1",
    media_type="application/vnd.apache.arrow.stream",
)

CONTENT_CONTRACT_SPECS: Mapping[str, ContentContractSpec] = MappingProxyType(
    {
        CANONICAL_ROW_HASHES_ARTIFACT.contract_id: CANONICAL_ROW_HASHES_ARTIFACT,
    }
)


def content_contract_from_spec(spec: ContentContractSpec) -> ContentContract:
    return ContentContract(
        contract_id=spec.contract_id,
        semantic_version=spec.semantic_version,
    )


def lookup_content_contract(contract_id: str) -> ContentContractSpec:
    try:
        return CONTENT_CONTRACT_SPECS[contract_id]
    except KeyError as exc:
        raise ValueError(f"unknown content contract: {contract_id}") from exc
