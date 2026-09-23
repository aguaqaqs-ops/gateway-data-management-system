"""History projection tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.history.contracts import (
    HistoryEligibilityNote,
    HistoryFacts,
    HistoryNodeKind,
    HistoryNodeRefKind,
    HistorySubmissionFact,
)
from gateway_backend.application.history.errors import HistoryRequestValidation
from gateway_backend.application.history.projection import project_history_tree
from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.submission.models import Submission, SubmitTargetRef, SubmitUnknownTypePolicy, SubmitVerificationPolicy
from gateway_backend.domain.submission.review import ReviewAction, ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_history import SQLiteHistoryReader
from gateway_backend.http.history_reader import HttpHistoryReader
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.test_review_transactions import _apply_command, _apply_review, _seed_pending_review_submission

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
TS2 = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)

INVALID_CURSOR_SHAPES = (
    "not-base64url",
    "!!!",
    "e30",
)


def _baseline_node(
    *,
    node_id: str,
    commit_id: str,
    kind: BaselineNodeKind,
    created_at: datetime,
    parent_node_id: str | None = None,
    source_submission_id: str | None = None,
) -> BaselineNode:
    return BaselineNode(
        node_id=node_id,
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        commit_id=commit_id,
        kind=kind,
        parent_node_id=parent_node_id,
        source_submission_id=source_submission_id,
        created_at=created_at,
    )


def _submission(
    *,
    submission_id: str,
    created_at: datetime,
    repository_commit_id: str,
    based_on_baseline_node_id: str = "node-1",
) -> Submission:
    return Submission(
        submission_id=submission_id,
        submit_attempt_id=f"attempt-{submission_id}",
        workspace_id="ws-1",
        workspace_generation=0,
        upload_revision_id="upload-1",
        preview_result_id="preview-1",
        repository_id="repo-1",
        based_on_baseline_node_id=based_on_baseline_node_id,
        business_baseline_commit_id="commit-base",
        repository_commit_id=repository_commit_id,
        canonical_business_digest="sha256:" + "a" * 64,
        source_artifact_refs=("artifact-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:" + "b" * 64,
        repository_import_artifact_raw_sha256="sha256:" + "c" * 64,
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=created_at,
    )


def _facts(
    *,
    baseline_nodes: tuple[BaselineNode, ...],
    submissions: tuple[HistorySubmissionFact, ...],
    head: BaselineHead,
) -> HistoryFacts:
    return HistoryFacts(
        repository_id="repo-1",
        baseline_nodes=baseline_nodes,
        submissions=submissions,
        head=head,
    )


def test_projection_builds_baseline_and_submission_nodes_with_parent_edges() -> None:
    initial = _baseline_node(
        node_id="node-1",
        commit_id="commit-initial",
        kind=BaselineNodeKind.INITIAL,
        created_at=TS0,
    )
    archived = _baseline_node(
        node_id="node-2",
        commit_id="commit-sub-1",
        kind=BaselineNodeKind.ARCHIVED_SUBMISSION,
        created_at=TS2,
        parent_node_id="node-1",
        source_submission_id="sub-1",
    )
    submission = _submission(
        submission_id="sub-1",
        created_at=TS1,
        repository_commit_id="commit-sub-1",
    )
    head = BaselineHead(
        business_baseline_node_id="node-2",
        business_baseline_commit_id="commit-sub-1",
        baseline_head_version=2,
    )
    projection = project_history_tree(
        facts=_facts(
            baseline_nodes=(initial, archived),
            submissions=(
                HistorySubmissionFact(
                    submission=submission,
                    review_status=ReviewStatus.APPROVED,
                    disposition=ArchiveDispositionKind.ARCHIVED_BASELINE,
                ),
            ),
            head=head,
        )
    )
    assert projection.head.node_id == "node-2"
    assert len(projection.nodes) == 3
    baseline_node = projection.nodes[0]
    submission_node = projection.nodes[1]
    archived_node = projection.nodes[2]
    assert baseline_node.node_kind is HistoryNodeKind.BASELINE_NODE
    assert baseline_node.parent is None
    assert submission_node.node_kind is HistoryNodeKind.SUBMISSION
    assert submission_node.parent is not None
    assert submission_node.parent.ref_kind is HistoryNodeRefKind.BASELINE_NODE
    assert submission_node.parent.ref_id == "node-1"
    assert submission_node.promoted_baseline_node_id == "node-2"
    assert archived_node.parent is not None
    assert archived_node.parent.ref_id == "node-1"


def test_projection_preserves_same_commit_dual_identity() -> None:
    submission = _submission(
        submission_id="sub-1",
        created_at=TS1,
        repository_commit_id="commit-shared",
    )
    archived = _baseline_node(
        node_id="node-2",
        commit_id="commit-shared",
        kind=BaselineNodeKind.ARCHIVED_SUBMISSION,
        created_at=TS2,
        parent_node_id="node-1",
        source_submission_id="sub-1",
    )
    projection = project_history_tree(
        facts=_facts(
            baseline_nodes=(
                _baseline_node(
                    node_id="node-1",
                    commit_id="commit-initial",
                    kind=BaselineNodeKind.INITIAL,
                    created_at=TS0,
                ),
                archived,
            ),
            submissions=(
                HistorySubmissionFact(
                    submission=submission,
                    review_status=ReviewStatus.APPROVED,
                    disposition=ArchiveDispositionKind.ARCHIVED_BASELINE,
                ),
            ),
            head=BaselineHead(
                business_baseline_node_id="node-2",
                business_baseline_commit_id="commit-shared",
                baseline_head_version=1,
            ),
        )
    )
    assert projection.nodes[1].commit_id == projection.nodes[2].commit_id == "commit-shared"
    assert projection.nodes[1].ref_id != projection.nodes[2].ref_id


def test_projection_derives_not_candidate_base_advanced_issue() -> None:
    submission = _submission(
        submission_id="sub-1",
        created_at=TS1,
        repository_commit_id="commit-sub-1",
        based_on_baseline_node_id="node-1",
    )
    projection = project_history_tree(
        facts=_facts(
            baseline_nodes=(
                _baseline_node(
                    node_id="node-1",
                    commit_id="commit-initial",
                    kind=BaselineNodeKind.INITIAL,
                    created_at=TS0,
                ),
            ),
            submissions=(
                HistorySubmissionFact(
                    submission=submission,
                    review_status=ReviewStatus.APPROVED,
                    disposition=None,
                ),
            ),
            head=BaselineHead(
                business_baseline_node_id="node-advanced",
                business_baseline_commit_id="commit-advanced",
                baseline_head_version=4,
            ),
        )
    )
    submission_node = next(node for node in projection.nodes if node.ref_id == "sub-1")
    assert submission_node.eligibility_note is HistoryEligibilityNote.NOT_CANDIDATE_BASE_ADVANCED


def test_projection_sorts_by_created_at_kind_and_ref_id() -> None:
    projection = project_history_tree(
        facts=_facts(
            baseline_nodes=(
                _baseline_node(
                    node_id="node-z",
                    commit_id="commit-z",
                    kind=BaselineNodeKind.INITIAL,
                    created_at=TS1,
                ),
                _baseline_node(
                    node_id="node-a",
                    commit_id="commit-a",
                    kind=BaselineNodeKind.INITIAL,
                    created_at=TS1,
                ),
            ),
            submissions=(
                HistorySubmissionFact(
                    submission=_submission(
                        submission_id="sub-b",
                        created_at=TS1,
                        repository_commit_id="commit-b",
                    ),
                    review_status=ReviewStatus.PENDING,
                    disposition=None,
                ),
                HistorySubmissionFact(
                    submission=_submission(
                        submission_id="sub-a",
                        created_at=TS1,
                        repository_commit_id="commit-a",
                    ),
                    review_status=ReviewStatus.PENDING,
                    disposition=None,
                ),
            ),
            head=BASELINE_HEAD,
        )
    )
    ref_ids = [node.ref_id for node in projection.nodes]
    assert ref_ids == ["node-a", "node-z", "sub-a", "sub-b"]


@pytest.mark.parametrize("cursor", INVALID_CURSOR_SHAPES)
def test_projection_rejects_invalid_cursor(cursor: str) -> None:
    facts = _facts(
        baseline_nodes=(
            _baseline_node(
                node_id="node-1",
                commit_id="commit-initial",
                kind=BaselineNodeKind.INITIAL,
                created_at=TS0,
            ),
        ),
        submissions=(),
        head=BASELINE_HEAD,
    )
    with pytest.raises(HistoryRequestValidation):
        project_history_tree(facts=facts, cursor=cursor)


def test_projection_paginates_with_opaque_cursor() -> None:
    baseline_nodes = tuple(
        _baseline_node(
            node_id=f"node-{index}",
            commit_id=f"commit-{index}",
            kind=BaselineNodeKind.INITIAL,
            created_at=TS0.replace(minute=index),
        )
        for index in range(3)
    )
    facts = _facts(baseline_nodes=baseline_nodes, submissions=(), head=BASELINE_HEAD)
    first_page = project_history_tree(facts=facts, limit=2)
    assert len(first_page.nodes) == 2
    assert first_page.next_cursor is not None
    second_page = project_history_tree(
        facts=facts,
        limit=2,
        cursor=first_page.next_cursor,
    )
    assert len(second_page.nodes) == 1
    assert first_page.nodes[0].ref_id != second_page.nodes[0].ref_id
    assert first_page.nodes[1].ref_id != second_page.nodes[0].ref_id


def test_sqlite_history_reader_loads_submission_review_facts(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(review_seed, _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-history"))
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    assert len(facts.baseline_nodes) >= 1
    assert len(facts.submissions) == 1
    assert facts.submissions[0].review_status is ReviewStatus.APPROVED


def test_projection_rejects_limit_out_of_range() -> None:
    facts = _facts(
        baseline_nodes=(),
        submissions=(),
        head=BASELINE_HEAD,
    )
    with pytest.raises(HistoryRequestValidation):
        project_history_tree(facts=facts, limit=0)
    with pytest.raises(HistoryRequestValidation):
        project_history_tree(facts=facts, limit=501)


def test_sqlite_history_reader_loads_scope_filtered_facts(db_path: Path) -> None:
    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, 'ARCHIVED_SUBMISSION', ?, 'sub-foreign', ?)
            """,
            (
                "foreign-node",
                "repo-1",
                "device-2",
                "project-2",
                "commit-foreign",
                BASELINE_HEAD.business_baseline_node_id,
                2,
            ),
        )
    reader = SQLiteHistoryReader(db_path)
    snapshot = reader.load_snapshot(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    assert all(node.gateway_device_external_key == "device-1" for node in snapshot.baseline_nodes)
    assert "foreign-node" not in {node.node_id for node in snapshot.baseline_nodes}
