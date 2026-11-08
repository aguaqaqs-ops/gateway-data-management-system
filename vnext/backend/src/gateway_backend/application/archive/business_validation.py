"""Bounded source graph and generated-time rules over immutable business facts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from gateway_backend.domain.archive.models import ArchiveSubjectKind
from gateway_backend.domain.configuration_facts import (
    CanonicalContentIdentity, ConfigurationFacts, ConfigurationGeneratedTime,
    ConfigurationSideFacts,
)

ARCHIVE_BUSINESS_RULE = "gateway-vnext/archive-business-validation/v1"


@dataclass(frozen=True, slots=True)
class ArchiveBusinessCandidate:
    submission_id: str
    candidate_digest: str
    configuration_facts: ConfigurationFacts


@dataclass(frozen=True, slots=True)
class ArchiveBusinessIssue:
    subject_kind: ArchiveSubjectKind
    issue_code: str
    affected_submission_ids: tuple[str, ...]
    side: str | None
    relations: tuple[str, ...]
    details: dict[str, Any]

    def to_document(self) -> dict[str, Any]:
        return {**asdict(self), "subject_kind": self.subject_kind.value}


@dataclass(frozen=True, slots=True)
class ArchiveBusinessValidation:
    rule_id: str
    baseline_facts_digest: str | None
    source_diagnostics: tuple[dict[str, Any], ...]
    time_comparisons: tuple[dict[str, Any], ...]
    issues: tuple[ArchiveBusinessIssue, ...]

    def to_document(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "baseline_facts_digest": self.baseline_facts_digest,
            "source_diagnostics": list(self.source_diagnostics),
            "time_comparisons": list(self.time_comparisons),
            "issues": [issue.to_document() for issue in self.issues]}


def _identity_key(value: CanonicalContentIdentity) -> tuple[str, str, str, int]:
    return (value.canonical_state_digest, value.storage_projection_ruleset_digest,
        value.storage_projection_version, value.scalar_encoding_version)


def _instant(value: str | None) -> datetime | None:
    # These are validated V1 canonical UTC facts, not source text extraction.
    return None if value is None else datetime.fromisoformat(value[:-1] + "+00:00")


def _selected(side: ConfigurationSideFacts | None) -> str | None:
    return None if side is None or side.generated_time is None else side.generated_time.selected_time_utc


def derive_archive_business_validation(
    *, candidates: tuple[ArchiveBusinessCandidate, ...],
    baseline: ConfigurationSideFacts | None,
    baseline_facts_digest: str | None,
) -> ArchiveBusinessValidation:
    """Derive complete diagnostics; acceptance never supplies graph edges."""
    if len(candidates) > 200 or len({item.submission_id for item in candidates}) != len(candidates):
        raise ValueError("invalid bounded archive business candidate set")
    ordered = tuple(sorted(candidates, key=lambda item: item.submission_id.encode("utf-8")))
    reached = set() if baseline is None else {baseline.content_identity}
    if baseline is not None:
        changed = True
        while changed:
            changed = False
            for item in ordered:
                facts = item.configuration_facts
                if facts.initial.content_identity in reached and facts.modified.content_identity not in reached:
                    reached.add(facts.modified.content_identity)
                    changed = True
    unknown = tuple(item for item in ordered if baseline is not None
        and item.configuration_facts.initial.content_identity not in reached)
    unknown_ids = {item.submission_id for item in unknown}
    issues: list[ArchiveBusinessIssue] = []
    # Union only unreachable states. A known endpoint cannot join independent roots.
    adjacency: dict[CanonicalContentIdentity, set[CanonicalContentIdentity]] = {}
    for item in unknown:
        identities = (item.configuration_facts.initial.content_identity,
            item.configuration_facts.modified.content_identity)
        nodes = tuple(value for value in identities if value not in reached)
        for node in nodes:
            adjacency.setdefault(node, set()).update(nodes)
    unseen = set(adjacency)
    while unseen:
        todo = [min(unseen, key=_identity_key)]
        component: set[CanonicalContentIdentity] = set()
        while todo:
            node = todo.pop()
            if node in component:
                continue
            component.add(node)
            todo.extend(adjacency[node] - component)
        unseen.difference_update(component)
        members = tuple(item for item in unknown if item.configuration_facts.initial.content_identity in component)
        edges = [{"submission_id": item.submission_id, "candidate_digest": item.candidate_digest,
            "configuration_facts_digest": item.configuration_facts.facts_digest,
            "initial": asdict(item.configuration_facts.initial.content_identity),
            "modified": asdict(item.configuration_facts.modified.content_identity)} for item in members]
        issues.append(ArchiveBusinessIssue(ArchiveSubjectKind.CONFIGURATION_SOURCE,
            "INITIAL_SOURCE_UNEXPLAINED", tuple(item.submission_id for item in members),
            "INITIAL", (), {"states": [asdict(value) for value in sorted(component, key=_identity_key)],
                "edges": edges, "detected_status": "UNEXPLAINED"}))
    source_diagnostics: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    baseline_time = _selected(baseline)
    if baseline is not None and baseline_time is None and ordered:
        issues.append(ArchiveBusinessIssue(ArchiveSubjectKind.CONFIGURATION_TIME_QUALITY,
            "BASELINE_TIME_UNAVAILABLE", tuple(item.submission_id for item in ordered),
            "BASELINE", (), {"generated_time": None if baseline.generated_time is None
                else asdict(baseline.generated_time), "comparison_status": "NOT_COMPARABLE"}))
    for item in ordered:
        facts = item.configuration_facts
        matches: list[dict[str, str]] = []
        if baseline is not None and facts.initial.content_identity == baseline.content_identity:
            matches.append({"source_kind": "BASELINE", "side": "MODIFIED"})
        if item.submission_id not in unknown_ids and baseline is not None:
            for peer in ordered:
                if peer.submission_id == item.submission_id or peer.submission_id in unknown_ids:
                    continue
                for side_name, peer_side in (("INITIAL", peer.configuration_facts.initial),
                    ("MODIFIED", peer.configuration_facts.modified)):
                    if facts.initial.content_identity == peer_side.content_identity:
                        matches.append({"source_kind": "SUBMISSION", "submission_id": peer.submission_id,
                            "side": side_name})
        source_diagnostics.append({"submission_id": item.submission_id,
            "initial_origin": facts.initial_origin,
            "detected_status": "NOT_APPLICABLE" if baseline is None else (
                "UNEXPLAINED" if item.submission_id in unknown_ids else "EXPLAINED"),
            "initial_identity": asdict(facts.initial.content_identity),
            "baseline_identity": None if baseline is None else asdict(baseline.content_identity),
            "rules_identity_differs_from_baseline": baseline is not None and
                _identity_key(facts.initial.content_identity)[1:] != _identity_key(baseline.content_identity)[1:],
            "matching_sources": matches})
        uploaded = (("INITIAL", facts.initial), ("MODIFIED", facts.modified)) if facts.initial_origin == "UPLOADED" else (("MODIFIED", facts.modified),)
        for side_name, side in uploaded:
            time = side.generated_time
            if time is None:
                raise ValueError("uploaded configuration side is missing immutable time facts")
            _append_time_quality(issues, item.submission_id, side_name, time)
        relation_values = (("MODIFIED_BEFORE_INITIAL", _selected(facts.modified), _selected(facts.initial)),
            ("MODIFIED_BEFORE_BASELINE", _selected(facts.modified), baseline_time),
            ("INITIAL_BEFORE_BASELINE", _selected(facts.initial), baseline_time))
        backward: dict[str, list[str]] = {"MODIFIED": [], "INITIAL": []}
        for relation, left, right in relation_values:
            status = "NOT_APPLICABLE" if baseline is None and (relation != "MODIFIED_BEFORE_INITIAL" or facts.initial_origin == "INITIAL_EMPTY") else (
                "NOT_COMPARABLE" if left is None or right is None else
                "BACKWARD" if _instant(left) < _instant(right) else "NORMAL")  # type: ignore[operator]
            comparisons.append({"submission_id": item.submission_id, "relation": relation,
                "left_time_utc": left, "right_time_utc": right, "detected_status": status})
            if status == "BACKWARD":
                backward["INITIAL" if relation == "INITIAL_BEFORE_BASELINE" else "MODIFIED"].append(relation)
        for side_name, relations in backward.items():
            if relations:
                issues.append(ArchiveBusinessIssue(ArchiveSubjectKind.CONFIGURATION_TIME_ORDER,
                    "TIME_ABNORMAL_" + side_name, (item.submission_id,), side_name,
                    tuple(relations), {"comparisons": [value for value in comparisons
                        if value["submission_id"] == item.submission_id and value["relation"] in relations]}))
    return ArchiveBusinessValidation(ARCHIVE_BUSINESS_RULE, baseline_facts_digest,
        tuple(source_diagnostics), tuple(comparisons), tuple(issues))


def _append_time_quality(issues: list[ArchiveBusinessIssue], submission_id: str,
        side: str, time: ConfigurationGeneratedTime) -> None:
    details = {"generated_time": asdict(time)}
    if time.selected_time_utc is None or time.invalid_count:
        code = "GENERATION_TIME_MISSING" if time.selected_time_utc is None else "GENERATION_TIME_INVALID_VALUES"
        issues.append(ArchiveBusinessIssue(ArchiveSubjectKind.CONFIGURATION_TIME_QUALITY,
            code, (submission_id,), side, (), details))
    if time.last_not_max:
        issues.append(ArchiveBusinessIssue(ArchiveSubjectKind.CONFIGURATION_TIME_ORDER,
            "GENERATION_TIME_LAST_NOT_MAX", (submission_id,), side, (), details))
