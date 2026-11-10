"""Explicit frozen facts for existing lifecycle fixtures; no SQL parser imitation."""
from __future__ import annotations

from dataclasses import replace, fields
from typing import Any

from gateway_backend.domain.configuration_facts import (
    CONFIGURATION_FACTS_SCHEMA, CONFIGURATION_TIME_RULE, CanonicalContentIdentity,
    ConfigurationFacts, ConfigurationGeneratedTime, ConfigurationSideFacts,
)
from gateway_backend.domain.workspace.models import PreviewResult
from gateway_backend.domain.submission.models import Submission, SubmitAttempt


def make_configuration_facts(*, workspace_id: str = "ws-1", upload_revision_id: str = "ur-1",
        generation: int = 1, repository_id: str = "repo-1", baseline_node_id: str = "node-1",
        baseline_commit_id: str = "commit-base", baseline_head_version: int = 1,
        operation_id: str = "op-preview-1", modified_digest: str = "sha256:" + "5" * 64,
        baseline_digest: str = "sha256:" + "4" * 64, initial_digest: str | None = None,
        rules_digest: str = "sha256:" + "6" * 64, initial_source: str = "a1:durable:22822f127d0974f80593e94b220507ff6c54df1c3b6fc3bdf591ee44808e26cf",
        modified_source: str = "a1:durable:ba818a521fed3b2757a17badbc09fd4393d77f7c1c1887a65a74edb8905fe303", uploaded_initial: bool = True) -> ConfigurationFacts:
    def content(digest: str) -> CanonicalContentIdentity:
        return CanonicalContentIdentity(digest, rules_digest, "3", 1)
    time = ConfigurationGeneratedTime(CONFIGURATION_TIME_RULE, "TABLE_ABSENT", None, None, 0, 0, 0, None, None, False)
    baseline = content(baseline_digest)
    return ConfigurationFacts(CONFIGURATION_FACTS_SCHEMA, operation_id, workspace_id, upload_revision_id,
        generation, repository_id, baseline_node_id, baseline_commit_id, baseline_head_version,
        False, "submission-baseline", "UPLOADED" if uploaded_initial else "BASELINE_REUSED", baseline,
        ConfigurationSideFacts(content(initial_digest or baseline_digest), time, initial_source, "sha256:" + "1" * 64),
        ConfigurationSideFacts(content(modified_digest), time, modified_source, "sha256:" + "2" * 64))


def preview_result_with_facts(**kwargs: Any) -> PreviewResult:
    canonical = kwargs["canonical"]
    facts = replace(canonical.configuration_facts, workspace_id=kwargs["workspace_id"],
        upload_revision_id=kwargs["upload_revision_id"], generation=kwargs["generation"],
        repository_id=kwargs["repository_id"], business_baseline_node_id=kwargs["business_baseline_node_id"],
        business_baseline_commit_id=kwargs["business_baseline_commit_id"], baseline_head_version=kwargs["baseline_head_version"],
        operation_id=kwargs["operation_id"])
    kwargs["canonical"] = replace(canonical, configuration_facts=facts)
    return PreviewResult(**kwargs)


def _facts_for_record(kwargs: dict[str, Any]) -> ConfigurationFacts:
    source = tuple(kwargs["source_artifact_refs"])[0]
    return make_configuration_facts(workspace_id=kwargs["workspace_id"], upload_revision_id=kwargs["upload_revision_id"],
        generation=kwargs["workspace_generation"], repository_id=kwargs["repository_id"],
        baseline_node_id=kwargs["business_baseline_node_id"] if "business_baseline_node_id" in kwargs else kwargs["based_on_baseline_node_id"],
        baseline_commit_id=kwargs["business_baseline_commit_id"],
        baseline_head_version=kwargs.get("baseline_head_version", 1), modified_digest=kwargs["canonical_business_digest"],
        initial_source=source, modified_source=source, uploaded_initial=False)


def submit_attempt_with_facts(**kwargs: Any) -> SubmitAttempt:
    kwargs.setdefault("configuration_facts", _facts_for_record(kwargs))
    return SubmitAttempt(**kwargs)


def submission_with_facts(**kwargs: Any) -> Submission:
    kwargs.setdefault("configuration_facts", _facts_for_record(kwargs))
    return Submission(**kwargs)


def replace_preview_with_facts(preview: PreviewResult, **changes: Any) -> PreviewResult:
    values = {field.name: getattr(preview, field.name) for field in fields(preview)}
    return preview_result_with_facts(**{**values, **changes})


def configuration_facts_blob(**bindings: Any) -> bytes:
    from gateway_shared_kernel.jcs import canonicalize_json_value
    facts = make_configuration_facts(initial_source="a1:durable:6ad3484166d34aff54b194e437178effc365b92e344486807818aa10908cd041", modified_source="a1:durable:6ad3484166d34aff54b194e437178effc365b92e344486807818aa10908cd041",
        uploaded_initial=False, **bindings)
    return canonicalize_json_value(facts.to_document())
