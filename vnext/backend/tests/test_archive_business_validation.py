"""The unique owner of current-round source and generated-time business rules."""
from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

from dataclasses import replace
import hashlib
import itertools

import pytest

from gateway_backend.application.archive.business_validation import (
    ArchiveBusinessCandidate, derive_archive_business_validation,
)
from gateway_backend.domain.configuration_facts import (
    CONFIGURATION_TIME_RULE, CanonicalContentIdentity, ConfigurationGeneratedTime, ConfigurationSideFacts,
)
from tests.support.configuration_facts import make_configuration_facts

pytestmark = pytest.mark.unit


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _time(hour: int | None = 12, *, invalid: int = 0, maximum: int | None = None) -> ConfigurationGeneratedTime:
    if hour is None:
        return ConfigurationGeneratedTime(CONFIGURATION_TIME_RULE, "NO_VALID_VALUE" if invalid else "TABLE_ABSENT",
            None, None, 0, 0, invalid, None, None, False)
    text = f"2026-11-07T{hour:02d}:00:00Z"
    max_text = f"2026-11-07T{maximum if maximum is not None else hour:02d}:00:00Z"
    return ConfigurationGeneratedTime(CONFIGURATION_TIME_RULE, "VALID", text, max_text,
        2 if maximum is not None else 1, 0, invalid,
        2 if maximum is not None else 1, 1, maximum is not None and maximum > hour)


def _side(label: str, *, hour: int | None = 12, rules: str = "A") -> ConfigurationSideFacts:
    return ConfigurationSideFacts(CanonicalContentIdentity(_digest(label), _digest(rules), "3", 1),
        _time(hour), build_artifact_id(ArtifactLocation.DURABLE, "archive-business-fixture", label), _digest("sql-" + label))


def _candidate(name: str, initial: str, modified: str, *, rules: str = "A") -> ArchiveBusinessCandidate:
    facts = make_configuration_facts()
    facts = replace(facts, baseline_content_identity=_side("X").content_identity,
        initial=_side(initial, rules=rules), modified=_side(modified, rules=rules))
    return ArchiveBusinessCandidate(name, _digest(name), facts)


SOURCE_CASES = (
    ((("A", "X", "Y"), ("B", "Y", "Z")), ()),
    ((("A", "X", "Y"), ("B", "X", "Z")), ()),
    ((("C", "X", "Q"), ("A", "Q", "Y"), ("B", "Q", "Z")), ()),
    ((("A", "Q", "Y"), ("B", "Q", "Z")), (("A", "B"),)),
    ((("A", "Q", "R"), ("B", "R", "Q")), (("A", "B"),)),
    ((("A", "Q", "Y"), ("B", "Y", "Z")), (("A", "B"),)),
    ((("A", "Q", "X"), ("B", "R", "X")), (("A",), ("B",))),
)


@pytest.mark.parametrize(("edges", "groups"), SOURCE_CASES)
def test_sources_require_a_baseline_anchor_and_are_independent_of_input_order(
        edges: tuple[tuple[str, str, str], ...], groups: tuple[tuple[str, ...], ...]) -> None:
    results = []
    for permutation in itertools.permutations(edges):
        result = derive_archive_business_validation(candidates=tuple(_candidate(*edge) for edge in permutation),
            baseline=_side("X"), baseline_facts_digest=_digest("baseline"))
        assert tuple(issue.affected_submission_ids for issue in result.issues) == groups
        results.append(result.to_document())
    assert all(result == results[0] for result in results)


def test_complete_rules_identity_does_not_merge_equal_digests_but_allows_an_anchored_change() -> None:
    unanchored = _candidate("B", "X", "Y", rules="B")
    result = derive_archive_business_validation(candidates=(unanchored,), baseline=_side("X"), baseline_facts_digest=_digest("baseline"))
    assert result.issues[0].issue_code == "INITIAL_SOURCE_UNEXPLAINED"
    assert result.source_diagnostics[0]["rules_identity_differs_from_baseline"] is True
    bridge = _candidate("A", "X", "X", rules="B")
    bridge = replace(bridge, configuration_facts=replace(bridge.configuration_facts,
        initial_origin="BASELINE_REUSED", initial=_side("X")))
    explained = derive_archive_business_validation(candidates=(unanchored, bridge), baseline=_side("X"), baseline_facts_digest=_digest("baseline"))
    assert not explained.issues
    # Removing a closed bridge removes its edge; acceptance never becomes an edge.
    assert result.source_diagnostics[0]["detected_status"] == "UNEXPLAINED"


TIME_CASES = (
    (12, 12, 12, ()),
    (12, 11, 13, ("TIME_ABNORMAL_MODIFIED", "TIME_ABNORMAL_INITIAL")),
    (13, 12, 12, ("TIME_ABNORMAL_MODIFIED",)),
    (None, 12, 12, ("GENERATION_TIME_MISSING",)),
    (12, None, 12, ("GENERATION_TIME_MISSING",)),
    (12, 12, None, ("BASELINE_TIME_UNAVAILABLE",)),
)


@pytest.mark.parametrize(("initial_hour", "modified_hour", "baseline_hour", "codes"), TIME_CASES)
def test_time_relations_missing_values_and_equal_instants_have_fixed_issue_groups(
        initial_hour: int | None, modified_hour: int | None, baseline_hour: int | None,
        codes: tuple[str, ...]) -> None:
    candidate = _candidate("A", "X", "Y")
    facts = replace(candidate.configuration_facts,
        initial=replace(candidate.configuration_facts.initial, generated_time=_time(initial_hour)),
        modified=replace(candidate.configuration_facts.modified, generated_time=_time(modified_hour)))
    result = derive_archive_business_validation(candidates=(replace(candidate, configuration_facts=facts),),
        baseline=_side("X", hour=baseline_hour), baseline_facts_digest=_digest("baseline"))
    assert tuple(issue.issue_code for issue in result.issues) == codes
    if modified_hour == 11:
        assert result.issues[0].relations == ("MODIFIED_BEFORE_INITIAL", "MODIFIED_BEFORE_BASELINE")
    if baseline_hour is None:
        assert {item["detected_status"] for item in result.time_comparisons[1:]} == {"NOT_COMPARABLE"}


def test_last_not_max_and_invalid_values_are_distinct_and_never_replace_selected_time() -> None:
    candidate = _candidate("A", "X", "Y")
    facts = replace(candidate.configuration_facts,
        modified=replace(candidate.configuration_facts.modified, generated_time=_time(11, invalid=1, maximum=13)))
    result = derive_archive_business_validation(candidates=(replace(candidate, configuration_facts=facts),),
        baseline=_side("X"), baseline_facts_digest=_digest("baseline"))
    assert tuple(issue.issue_code for issue in result.issues) == (
        "GENERATION_TIME_INVALID_VALUES", "GENERATION_TIME_LAST_NOT_MAX", "TIME_ABNORMAL_MODIFIED")
    assert result.time_comparisons[0]["left_time_utc"] == "2026-11-07T11:00:00Z"


def test_initial_empty_baseline_is_not_applicable_and_reused_initial_does_not_repeat_quality() -> None:
    candidate = _candidate("A", "Q", "Y")
    first = derive_archive_business_validation(candidates=(candidate,), baseline=None, baseline_facts_digest=None)
    assert not first.issues
    assert first.source_diagnostics[0]["detected_status"] == "NOT_APPLICABLE"
    assert first.time_comparisons[1]["detected_status"] == "NOT_APPLICABLE"
    missing = _side("X", hour=None)
    facts = replace(candidate.configuration_facts, initial_origin="BASELINE_REUSED", initial=missing)
    reused = derive_archive_business_validation(candidates=(replace(candidate, configuration_facts=facts),),
        baseline=missing, baseline_facts_digest=_digest("baseline"))
    assert tuple(issue.issue_code for issue in reused.issues) == ("BASELINE_TIME_UNAVAILABLE",)


def test_two_hundred_full_candidates_have_two_hundred_modified_time_issues_within_the_structural_bound() -> None:
    candidates = []
    for index in range(200):
        item = _candidate(str(index), "X", "Y")
        candidates.append(replace(item, configuration_facts=replace(item.configuration_facts,
            modified=replace(item.configuration_facts.modified, generated_time=_time(None)))))
    result = derive_archive_business_validation(candidates=tuple(candidates), baseline=_side("X"), baseline_facts_digest=_digest("baseline"))
    assert len(result.issues) == 200
    assert len(result.issues) + 199 == 399
    assert 2 * 200 + 2 * 200 + 2 * 200 + 200 + 199 + 1 + 1 == 8 * 200 + 1 == 1601


def test_first_modified_only_initial_is_explicitly_not_applicable() -> None:
    candidate = _candidate("A", "X", "Y")
    facts = replace(candidate.configuration_facts, baseline_is_initial=True, baseline_source_submission_id=None,
        initial_origin="INITIAL_EMPTY", initial=ConfigurationSideFacts(_side("X").content_identity, None, None, None))
    result = derive_archive_business_validation(candidates=(replace(candidate, configuration_facts=facts),),
        baseline=None, baseline_facts_digest=None)
    assert not result.issues
    assert {value["detected_status"] for value in result.time_comparisons} == {"NOT_APPLICABLE"}
