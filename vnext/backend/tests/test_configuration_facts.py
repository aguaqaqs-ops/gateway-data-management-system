"""Business facts are explicit immutable records, distinct from missing business time."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.domain.configuration_facts import ConfigurationFacts, ConfigurationGeneratedTime

_GOLDEN = Path(__file__).resolve().parents[2] / "fixtures/golden/configuration-facts/v1/frozen-full.json"


def test_configuration_facts_match_independent_frozen_digest_golden() -> None:
    document = json.loads(_GOLDEN.read_bytes())
    facts = ConfigurationFacts.from_document(document)
    assert facts.to_document() == document
    assert facts.initial.content_identity.canonical_state_digest != facts.modified.content_identity.canonical_state_digest
    assert facts.modified.generated_time is not None and facts.modified.generated_time.last_not_max
    assert facts.modified.generated_time.invalid_count == 1


@pytest.mark.parametrize("path", [
    ("facts", "initial"), ("facts", "initial", "generated_time"),
    ("facts", "modified", "generated_time", "rule_id"),
    ("facts", "initial", "content_identity", "scalar_encoding_version"),
    ("facts", "baseline_source_submission_id"), ("facts_digest",),
])
def test_missing_facts_fields_are_integrity_errors(path: tuple[str, ...]) -> None:
    document = json.loads(_GOLDEN.read_bytes())
    current = document
    for name in path[:-1]:
        current = current[name]
    del current[path[-1]]
    with pytest.raises(ValueError):
        ConfigurationFacts.from_document(document)


def test_changed_time_or_source_cannot_reuse_original_facts_digest() -> None:
    original = json.loads(_GOLDEN.read_bytes())
    for name, value in [("source_artifact_id", "another-source"), ("sql_source_digest", "sha256:" + "8" * 64)]:
        document = deepcopy(original)
        document["facts"]["modified"][name] = value
        with pytest.raises(ValueError, match="digest mismatch"):
            ConfigurationFacts.from_document(document)


def test_missing_business_time_and_initial_not_applicable_are_distinct() -> None:
    facts = ConfigurationFacts.from_document(json.loads(_GOLDEN.read_bytes()))
    original = facts.modified.generated_time
    assert original is not None
    missing = ConfigurationGeneratedTime(original.rule_id, "NO_VALUE", None, None, 0, 2, 0, None, None, False)
    modified = replace(facts.modified, generated_time=missing)
    missing_facts = replace(facts, modified=modified)
    assert missing_facts.facts_digest != facts.facts_digest
    assert ConfigurationFacts.from_document(missing_facts.to_document()) == missing_facts
    initial = replace(facts.initial, generated_time=None, source_artifact_id=None, sql_source_digest=None)
    applicable = replace(facts, baseline_is_initial=True, baseline_source_submission_id=None,
        initial_origin="INITIAL_EMPTY", initial=initial)
    assert applicable.initial.generated_time is None
    with pytest.raises(ValueError, match="uploaded initial"):
        replace(applicable, initial_origin="UPLOADED")
    with pytest.raises(ValueError, match="source time facts"):
        replace(facts, modified=initial)


def test_configuration_facts_reject_rule_and_input_identity_mismatch() -> None:
    facts = ConfigurationFacts.from_document(json.loads(_GOLDEN.read_bytes()))
    changed = replace(facts.initial.content_identity, storage_projection_version="future")
    with pytest.raises(ValueError, match="rules/projection/scalar"):
        replace(facts, initial=replace(facts.initial, content_identity=changed))
    binding: dict[str, Any] = dict(workspace_id=facts.workspace_id, upload_revision_id=facts.upload_revision_id,
        generation=facts.generation, repository_id=facts.repository_id,
        business_baseline_node_id=facts.business_baseline_node_id,
        business_baseline_commit_id=facts.business_baseline_commit_id)
    facts.assert_binding(**binding)
    with pytest.raises(ValueError, match="binding mismatch"):
        facts.assert_binding(**{**binding, "repository_id": "another-repository"})
