"""Backend-only structural-change evidence, independently retained by READY closure."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.store import ArtifactStorePort, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.comparison.contracts import COMPARISON_CONTRACT_VERSION, ComparisonFacts, ComparisonPlan
from gateway_backend.capabilities.comparison import (
    ComparisonTableFactDocument, describe_table_fact, structure_change_is_audit_only,
)


class HiddenStructureFact(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    table_name: str
    before_raw_content_digest: str
    current_raw_content_digest: str
    before_business_schema_digest: str
    current_business_schema_digest: str
    table_fact_digest: str
    raw_fact: ComparisonTableFactDocument
    equality_evidence: Literal["BOUND_EMPTY_DESCRIPTORS", "NATIVE_SHARED_VALUES"]
    hidden_reason: Literal["ONLY_COLUMNS_CHANGED_SHARED_VALUES_EQUAL"]

    @model_validator(mode="after")
    def consistent_evidence(self) -> HiddenStructureFact:
        if self.raw_fact.shared_value_equality != self.equality_evidence:
            raise ValueError("structure audit equality evidence mismatch")
        return self



class ComparisonStructureAudit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    document_type: Literal["comparison-structure-audit"]
    comparison_contract_version: str
    pair_id: str
    before_snapshot_digest: str
    current_snapshot_digest: str
    comparison_digest: str
    ruleset_digest: str
    tables: tuple[HiddenStructureFact, ...]

    @field_validator("comparison_contract_version")
    @classmethod
    def current_comparison_contract(cls, value: str) -> str:
        if value != COMPARISON_CONTRACT_VERSION:
            raise ValueError("unsupported structure audit comparison contract")
        return value


def publish_structure_audit(
    plan: ComparisonPlan, facts: ComparisonFacts, store: ArtifactStorePort,
) -> ArtifactRef | None:
    from gateway_backend.capabilities.table_access import current_kernel_context

    hidden = tuple(table for table in facts.tables if structure_change_is_audit_only(table))
    if not hidden:
        return None
    context = current_kernel_context()
    if context is None:
        raise ValueError("structure audit requires the operation kernel context")
    upper = 1024 * 1024 + sum(65536 + sum((len(name) + 1) * 256 for name in (
        *table.schema_changes.before_only_columns, *table.schema_changes.current_only_columns,
        *table.schema_changes.selected_columns)) for table in hidden)
    with context.memory.reserve(upper):
        context.checkpoint()
        return _publish_structure_audit(plan, facts, store)


def _publish_structure_audit(
    plan: ComparisonPlan, facts: ComparisonFacts, store: ArtifactStorePort,
) -> ArtifactRef | None:
    from gateway_backend.capabilities.table_access import current_kernel_context

    context = current_kernel_context()
    assert context is not None
    tables = []
    for table in facts.tables:
        context.checkpoint()
        if not structure_change_is_audit_only(table):
            continue
        before, current = table.before_descriptor, table.current_descriptor
        if (before is None or current is None or before.raw_content_digest is None
                or current.raw_content_digest is None or table.shared_value_equality is None
                or table.table_fact_digest is None):
            raise ValueError("hidden structure audit requires complete content bindings")
        tables.append(HiddenStructureFact(
            table_name=table.table_name,
            before_raw_content_digest=before.raw_content_digest.value,
            current_raw_content_digest=current.raw_content_digest.value,
            before_business_schema_digest=before.business_schema_digest.value,
            current_business_schema_digest=current.business_schema_digest.value,
            table_fact_digest=table.table_fact_digest.value,
            raw_fact=describe_table_fact(table),
            equality_evidence=table.shared_value_equality,
            hidden_reason="ONLY_COLUMNS_CHANGED_SHARED_VALUES_EQUAL",
        ))
    if not tables:
        return None
    if plan.rule_set.ruleset_digest is None:
        raise ValueError("hidden structure audit requires ruleset identity")
    document = ComparisonStructureAudit(
        document_type="comparison-structure-audit",
        comparison_contract_version=facts.comparison_contract_version,
        pair_id=plan.pair_id,
        before_snapshot_digest=facts.before_snapshot_digest.value,
        current_snapshot_digest=facts.current_snapshot_digest.value,
        comparison_digest=facts.comparison_digest.value,
        ruleset_digest=plan.rule_set.ruleset_digest.value,
        tables=tuple(tables),
    )
    raw = canonicalize_json_value(document.model_dump(mode="json"))
    ref = put_with_built_ref(store, raw,
        artifact_id=build_artifact_id(ArtifactLocation.COMPARISON, "structure-audit", raw_blob_digest(raw).value),
        media_type="application/jcs")
    # This exact read checks stored bytes as well as strict document shape before
    # any successful hidden surface can be published, also on comparison reuse.
    context.checkpoint()
    restored = ComparisonStructureAudit.model_validate_json(store.locate(ref))
    if restored != document:
        raise ValueError("hidden structure audit binding mismatch")
    return ref


class StructureAuditBinding(BaseModel):
    """The assemble checkpoint binds every pair, including pairs needing no audit."""
    model_config = ConfigDict(strict=True, extra="forbid")
    pair_id: str
    comparison_digest: str
    audit_artifact_id: str | None


def structure_audit_binding(pair_id: str, comparison_digest: str, ref: ArtifactRef | None) -> dict[str, JsonValue]:
    return StructureAuditBinding(pair_id=pair_id, comparison_digest=comparison_digest,
        audit_artifact_id=None if ref is None else ref.artifact_id).model_dump(mode="json")


def verify_structure_audit_bindings(store: ArtifactStorePort, raw_bindings: object, refs: tuple[ArtifactRef, ...], expected_pair_ids: object) -> None:
    from pydantic import TypeAdapter
    from gateway_backend.application.payloads import CheckpointDecodeError
    from gateway_backend.application.kernel_execution import reserved_artifact_bytes
    from gateway_backend.capabilities.table_access import current_kernel_context

    context = current_kernel_context()
    if context is None:
        raise ValueError("structure audit verification requires the operation kernel context")
    try:
        bindings = TypeAdapter(tuple[StructureAuditBinding, ...]).validate_json(canonicalize_json_value(raw_bindings))
        pair_ids = TypeAdapter(tuple[str, ...]).validate_json(canonicalize_json_value(expected_pair_ids))
        if len(pair_ids) != len(bindings) or {binding.pair_id for binding in bindings} != set(pair_ids):
            raise ValueError("incomplete structure audit pair bindings")
        if len({binding.pair_id for binding in bindings}) != len(bindings):
            raise ValueError("duplicate structure audit pair binding")
        by_id = {ref.artifact_id: ref for ref in refs}
        for binding in bindings:
            if binding.audit_artifact_id is None:
                continue
            ref = by_id.get(binding.audit_artifact_id)
            if ref is None:
                raise ValueError("structure audit is missing from READY closure")
            with reserved_artifact_bytes(store, ref) as raw:
                with context.memory.reserve(65536 + ref.size_bytes * 32):
                    document = ComparisonStructureAudit.model_validate_json(raw)
                    if (document.pair_id != binding.pair_id or document.comparison_digest != binding.comparison_digest
                            or not document.tables):
                        raise ValueError("structure audit pair binding mismatch")
    except (ValueError, TypeError) as exc:
        raise CheckpointDecodeError(str(exc), code="STRUCTURE_AUDIT_INTEGRITY_ERROR") from exc
