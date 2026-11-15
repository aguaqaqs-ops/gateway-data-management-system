"""Strict persisted Preview binding documents; SQL scalar scope is checked first."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, JsonValue
from gateway_shared_kernel import DigestRef
from gateway_backend.domain.configuration_facts import ConfigurationFacts
from gateway_backend.domain.workspace.models import (
    PreviewArtifactRef, PreviewCanonicalBindings, PreviewComparisonPair, PreviewIdentityPair,
    ProjectIdentityApplicability, ProjectIdentityMode, ProjectIdentityStatus,
)


class _StrictDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class PreviewRefDocument(_StrictDocument):
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def to_model(self) -> PreviewArtifactRef:
        return PreviewArtifactRef(self.artifact_id, self.media_type, self.size_bytes, DigestRef(self.raw_sha256))


class PreviewDigestsDocument(_StrictDocument):
    source_digest: str
    input_digest: str
    snapshot_digest: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    bundle_digest: str


class PreviewIdentityDocument(_StrictDocument):
    pair_id: str
    applicability: str
    status: str
    mode: str
    assessment_ref: PreviewRefDocument | None
    assessment_digest: str | None

    def to_model(self) -> PreviewIdentityPair:
        return PreviewIdentityPair(pair_id=self.pair_id,
            applicability=ProjectIdentityApplicability(self.applicability),
            status=ProjectIdentityStatus(self.status), mode=ProjectIdentityMode(self.mode),
            assessment_ref=None if self.assessment_ref is None else self.assessment_ref.to_model(),
            assessment_digest=None if self.assessment_digest is None else DigestRef(self.assessment_digest))


class PreviewCanonicalDocument(_StrictDocument):
    initial_canonical_state_digest: str
    configuration_facts: dict[str, JsonValue]
    canonical_table_set_closure_ref: PreviewRefDocument
    canonical_table_set_closure_digest: str
    canonicalization_manifest_ref: PreviewRefDocument
    canonicalization_manifest_digest: str
    baseline_canonical_state_digest: str
    modified_canonical_state_digest: str
    storage_projection_ruleset_digest: str
    rules_semantically_equal: bool

    def to_model(self) -> PreviewCanonicalBindings:
        return PreviewCanonicalBindings(
            initial_canonical_state_digest=DigestRef(self.initial_canonical_state_digest),
            configuration_facts=ConfigurationFacts.from_document(self.configuration_facts),
            canonical_table_set_closure_ref=self.canonical_table_set_closure_ref.to_model(),
            canonical_table_set_closure_digest=DigestRef(self.canonical_table_set_closure_digest),
            canonicalization_manifest_ref=self.canonicalization_manifest_ref.to_model(),
            canonicalization_manifest_digest=DigestRef(self.canonicalization_manifest_digest),
            baseline_canonical_state_digest=DigestRef(self.baseline_canonical_state_digest),
            modified_canonical_state_digest=DigestRef(self.modified_canonical_state_digest),
            storage_projection_ruleset_digest=DigestRef(self.storage_projection_ruleset_digest),
            rules_semantically_equal=self.rules_semantically_equal)


class PreviewBindingDocument(_StrictDocument):
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    ruleset_version: str
    contract_version: Literal["backend-vnext/preview/v4"]
    provider_versions: dict[str, str]
    digests: PreviewDigestsDocument
    canonical: PreviewCanonicalDocument
    identity_assessment_set_digest: str
    identity_pairs: tuple[PreviewIdentityDocument, ...]
    comparison_pairs: tuple[PreviewComparisonPair, ...]
    bundle_artifact_id: str
    ready_closure_artifact_id: str
