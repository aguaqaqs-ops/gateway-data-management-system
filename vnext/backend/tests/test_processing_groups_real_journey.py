"""Real t1 grouped consumer preserves approved source/identity boundaries."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from benchmarks import processing_groups_real_journey as grouped
from benchmarks import real_dump_journey as real

pytestmark = pytest.mark.unit

# Each deviation crosses a different pre-Submit source assertion. There is no
# matrix over backend internals, Docker, Dolt or fabricated second real devices.
PREVIEW_DEVIATIONS = (
    None, "different-project", "unverifiable", "identity-mode", "table-count",
    "changed-count", "degraded", "failed",
)


@pytest.mark.parametrize("deviation", PREVIEW_DEVIATIONS)
def test_real_group_driver_checks_original_identity_and_summary_before_submit(
    monkeypatch: pytest.MonkeyPatch, deviation: str | None,
) -> None:
    pair = dict(pair_id="initial_to_modified", status="NOT_APPLICABLE", mode="DETAILED", applicability="NOT_APPLICABLE")
    summary = dict(table_count=125, changed_table_count=125, degraded_table_count=0, failed_table_count=0)
    if deviation in {"different-project", "unverifiable"}:
        pair.update(status="DIFFERENT_PROJECT" if deviation == "different-project" else "UNVERIFIABLE", applicability="APPLICABLE")
    elif deviation == "identity-mode":
        pair["mode"] = "REFERENCE_ONLY"
    elif deviation is not None:
        summary[{"table-count": "table_count", "changed-count": "changed_table_count",
                 "degraded": "degraded_table_count", "failed": "failed_table_count"}[deviation]] = 124 if deviation in {"table-count", "changed-count"} else 1
    preview = {"result": {"identity_assessment_set_digest": "sha256:" + "a" * 64, "identity_pairs": [pair]}}
    manifest = {"pairs": [{"pair_id": "initial_to_modified", "summary": summary}]}
    monkeypatch.setattr(real, "_workspace", lambda client: {"workspace_id": "workspace"})
    monkeypatch.setattr(real, "_upload_revision", lambda *args, **kwargs: {})
    monkeypatch.setattr(real, "_preview", lambda *args, **kwargs: (preview, manifest))
    events: list[str] = []

    def submit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["identity_confirmations"] == ()
        assert kwargs["token"] == "compose-device-token"
        events.append("submit")
        return dict(submission_id="submission", repository_commit_id="submitted-commit",
                    canonical_business_digest="sha256:" + "b" * 64)

    def approve(*args: Any, **kwargs: Any) -> None:
        assert kwargs["token"] == "compose-device-reviewer"
        events.append("approve")

    def archive(*args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {"token": "compose-device-reviewer"}, "identity exception must remain unauthorized"
        events.append("archive")
        return dict(baseline_node_id="archived-node", baseline_commit_id="submitted-commit")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/archive-candidates"
        assert request.headers["Authorization"] == "Bearer compose-device-reviewer"
        return httpx.Response(200, json={"head": dict(business_baseline_node_id="archived-node",
            business_baseline_commit_id="submitted-commit", baseline_head_version=1)})

    monkeypatch.setattr(real, "_submit", submit)
    monkeypatch.setattr(real, "_approve", approve)
    monkeypatch.setattr(real, "_archive", archive)
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond)) as client:
        if deviation is None:
            result, _archive = grouped._run_real_chain(client, b"original source bytes", {"initial_node_id": "initial"})
            assert result["preview_identity"]["status"] == "NOT_APPLICABLE"
            assert result["preview_summary"]["table_count"] == 125
            assert events == ["submit", "approve", "archive"]
        else:
            with pytest.raises(real.JourneyFailure):
                grouped._run_real_chain(client, b"original source bytes", {"initial_node_id": "initial"})
            assert events == []


def test_real_group_driver_requires_explicit_issue_reasons_before_allocating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON", raising=False)
    monkeypatch.setattr(grouped, "ProcessingGroupsStack", lambda *args, **kwargs: pytest.fail("missing authorization must not allocate a deployment"))
    with pytest.raises(real.JourneyFailure, match="approved archive"):
        grouped.run_journey(tmp_path / grouped.SOURCE_NAME, tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


@pytest.mark.parametrize("fault", ["unknown-issue", "identity-exception", "unsupported-subject", "invalid-sequence"])
def test_real_archive_authorizes_the_entire_plan_before_any_confirmation_or_ack(
    monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    selected = dict(submission_id="submission", expected_candidate_digest="sha256:" + "a" * 64)
    first = dict(subject_kind="CONFIGURATION_SOURCE", issue_code="INITIAL_SOURCE_UNEXPLAINED",
        subject_digest="sha256:" + "b" * 64, target_submission_id="submission",
        target_candidate_digest=selected["expected_candidate_digest"], latest_sequence=0, resolution_status="UNRESOLVED")
    second = deepcopy(first)
    second.update(subject_digest="sha256:" + "c" * 64, issue_code="UNKNOWN_SOURCE_ISSUE")
    if fault == "identity-exception":
        second.update(subject_kind="PROJECT_IDENTITY_EXCEPTION", issue_code="PROJECT_IDENTITY_EXCEPTION")
    elif fault == "unsupported-subject":
        second.update(subject_kind="UNKNOWN_SOURCE_KIND")
    elif fault == "invalid-sequence":
        second.update(issue_code="INITIAL_SOURCE_UNEXPLAINED", latest_sequence=-1)
    monkeypatch.setenv("GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON", json.dumps({
        "INITIAL_SOURCE_UNEXPLAINED": "Approved original t1 source fact, retained without a quality PASS",
        # An issue-map entry cannot grant a project-identity exception.
        "PROJECT_IDENTITY_EXCEPTION": "This entry must not authorize identity replacement",
    }))
    writes: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fresh-group-reviewer"
        if request.url.path == "/v1/archive-candidates":
            return httpx.Response(200, json={"candidates": [selected]})
        if request.url.path == "/v1/archive-plan-preview":
            return httpx.Response(200, json=dict(can_start=False, anomalies=[first, second],
                head=dict(business_baseline_node_id="initial", baseline_head_version=0),
                candidate_set_digest="sha256:" + "d" * 64, selection_subject_digest="sha256:" + "e" * 64))
        writes.append(request.url.path)
        return httpx.Response(201, json={"sequence": 1})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(real.JourneyFailure):
            real._archive(client, "submission", "real", token="fresh-group-reviewer")
    assert writes == [], "a later unapproved anomaly must not leave earlier confirmations/ACKs"
