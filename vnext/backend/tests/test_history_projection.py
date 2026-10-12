"""History projection tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlite3

from gateway_backend.application.history.contracts import (
    HistoryEligibilityNote,
    HistoryFacts,
    HistoryNode,
    HistoryNodeKind,
    HistoryNodeRefKind,
    HistorySubmissionFact,
    HistoryTreeProjection,
)
from gateway_backend.application.history.errors import HistoryRequestValidation
from gateway_backend.application.history.errors import HistoryIntegrityFailure
from gateway_backend.application.history.projection import (
    _order_key_from_node,
    project_history_tree,
)
from gateway_backend.application.history.queries import get_project_history
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.submission.models import Submission, SubmitTargetRef, SubmitUnknownTypePolicy, SubmitVerificationPolicy
from gateway_backend.domain.submission.review import ReviewAction, ReviewStatus
from gateway_backend.domain.workspace.errors import PermissionDenied
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_history import HistorySubmissionRow, SQLiteHistoryReader
from gateway_backend.infrastructure.control_db.history_reader import HttpHistoryReader
from gateway_shared_kernel.jcs import canonicalize_json_value
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.test_review_persistence import _insert_operation_record
from tests.test_review_transactions import (
    ReviewSeed,
    _apply_command,
    _apply_review,
    _seed_additional_pending_review_submission,
    _seed_pending_review_submission,
)
from tests.test_submit_transactions import _upsert_provisioned_mapping_row

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
TS2 = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)

INVALID_CURSOR_SHAPES = (
    "not-base64url",
    "!!!",
    "e30",
)

HISTORY_LIMIT_BOUNDARY_CASES = (
    ("limit_zero", 0),
    ("limit_over_max", 501),
)

EXCLUDED_HISTORY_MARKERS = (
    "op-excluded-marker",
    "sa-failed-import",
    "plan-excluded-marker",
    "sub-plan-only",
)

HISTORY_TREE_PAGE_DIFF_LIMITS = (1, 2, 3, 10)
CJK_BASELINE_REF_ID = "中" * 63 + "zz"
DIFF_FIXTURE_PERMISSIONS = frozenset({"read_project_history", "workspace_read"})


def _seed_promotion_duplicate_fixture(db_path: Path) -> ReviewSeed:
    primary = _seed_pending_review_submission(db_path)
    _apply_review(
        primary,
        _apply_command(primary, action=ReviewAction.APPROVE, idempotency_key="approve-dup-primary"),
    )
    return primary


def _seed_history_diff_fixture(db_path: Path) -> ReviewSeed:
    primary = _seed_pending_review_submission(db_path)
    _apply_review(
        primary,
        _apply_command(primary, action=ReviewAction.APPROVE, idempotency_key="approve-diff-primary"),
    )
    sibling = _seed_additional_pending_review_submission(
        db_path,
        submission_id="sub-2",
        device_key="device-1",
        repository_id="repo-1",
        project_id="project-1",
    )
    _apply_review(
        sibling,
        _apply_command(sibling, action=ReviewAction.APPROVE, idempotency_key="approve-diff-sibling"),
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, 'repo-1', 'device-1', 'project-1', 'commit-cjk-archived',
                      'ARCHIVED_SUBMISSION', ?, ?, ?)
            """,
            (
                CJK_BASELINE_REF_ID,
                BASELINE_HEAD.business_baseline_node_id,
                primary.submission_id,
                500_000,
            ),
        )
    return primary


def _load_history_facts(db_path: Path) -> HistoryFacts:
    return HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )


def _history_read_identity() -> IdentityContext:
    return make_identity(permissions=DIFF_FIXTURE_PERMISSIONS)


def _uow_factory(db_path: Path) -> HistoryControlUnitOfWorkFactory:
    def factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(db_path, read_only=read_only)

    return factory


def _assert_history_nodes_equal(left: HistoryNode, right: HistoryNode) -> None:
    assert left.ref_kind == right.ref_kind
    assert left.ref_id == right.ref_id
    assert left.node_kind == right.node_kind
    assert left.commit_id == right.commit_id
    assert left.created_at == right.created_at
    assert left.baseline_kind == right.baseline_kind
    assert left.review_status == right.review_status
    assert left.archive_disposition == right.archive_disposition
    assert left.promoted_baseline_node_id == right.promoted_baseline_node_id
    assert left.eligibility_note == right.eligibility_note
    if left.parent is None:
        assert right.parent is None
    else:
        assert right.parent is not None
        assert left.parent.ref_kind == right.parent.ref_kind
        assert left.parent.ref_id == right.parent.ref_id


def _assert_history_projections_equal(
    left: HistoryTreeProjection,
    right: HistoryTreeProjection,
) -> None:
    assert left.head == right.head
    assert left.next_cursor == right.next_cursor
    assert len(left.nodes) == len(right.nodes)
    for left_node, right_node in zip(left.nodes, right.nodes, strict=True):
        _assert_history_nodes_equal(left_node, right_node)


def _collect_tree_path_pages(*, facts: HistoryFacts, limit: int) -> tuple[HistoryTreeProjection, ...]:
    pages: list[HistoryTreeProjection] = []
    cursor: str | None = None
    while True:
        page = project_history_tree(facts=facts, limit=limit, cursor=cursor)
        pages.append(page)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return tuple(pages)


def _collect_page_path_pages(db_path: Path, *, limit: int) -> tuple[HistoryTreeProjection, ...]:
    pages: list[HistoryTreeProjection] = []
    cursor: str | None = None
    identity = _history_read_identity()
    while True:
        page = get_project_history(
            context=identity,
            unit_of_work_factory=_uow_factory(db_path),
            snapshot_loader=HttpHistoryReader(db_path),
            limit=limit,
            cursor=cursor,
        )
        pages.append(page)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return tuple(pages)


def _insert_duplicate_promoted_baseline_rows(
    db_path: Path,
    *,
    source_submission_id: str,
) -> str:
    expected_winner = "zz-node"
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        for node_id, created_at_us in (
            ("aa-node", 100),
            ("中-node", 150),
            (expected_winner, 200),
        ):
            connection.execute(
                """
                INSERT INTO baseline_node_records (
                    node_id, repository_id, gateway_device_external_key, business_project_id,
                    commit_id, kind, parent_node_id, source_submission_id, created_at_us
                ) VALUES (?, 'repo-1', 'device-1', 'project-1', ?, 'ARCHIVED_SUBMISSION', ?, ?, ?)
                """,
                (
                    node_id,
                    f"commit-{node_id}",
                    BASELINE_HEAD.business_baseline_node_id,
                    source_submission_id,
                    created_at_us,
                ),
            )
        connection.commit()
    return expected_winner


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


def test_history_reader_source_artifact_refs_match_submission_repository(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        repository_submission = unit_of_work.submission.get_submission(review_seed.submission_id)
        assert repository_submission is not None
        unit_of_work.connection.execute(
            "UPDATE submission_records SET source_artifact_refs = ? WHERE submission_id = ?",
            (canonicalize_json_value([]), review_seed.submission_id),
        )
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        repository_submission = unit_of_work.submission.get_submission(review_seed.submission_id)
        assert repository_submission is not None
    history_submission = facts.submissions[0].submission
    assert history_submission.source_artifact_refs == repository_submission.source_artifact_refs
    assert history_submission.source_artifact_refs == ()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE submission_records SET source_artifact_refs = ? WHERE submission_id = ?",
            (canonicalize_json_value(["initial-1", "modified-1"]), review_seed.submission_id),
        )
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        repository_submission = unit_of_work.submission.get_submission(review_seed.submission_id)
        assert repository_submission is not None
    assert facts.submissions[0].submission.source_artifact_refs == repository_submission.source_artifact_refs
    assert facts.submissions[0].submission.source_artifact_refs == ("initial-1", "modified-1")


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


def test_page_path_cursor_survives_head_advance(db_path: Path) -> None:
    _seed_history_diff_fixture(db_path)
    identity = _history_read_identity()
    page1 = get_project_history(
        context=identity,
        unit_of_work_factory=_uow_factory(db_path),
        snapshot_loader=HttpHistoryReader(db_path),
        limit=1,
    )
    assert page1.next_cursor is not None
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        head_row = unit_of_work.connection.execute(
            "SELECT node_id, optimistic_version FROM baseline_head_records WHERE repository_id = ?",
            ("repo-1",),
        ).fetchone()
        assert head_row is not None
        new_node_id = "node-head-advanced"
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, 'repo-1', 'device-1', 'project-1', 'commit-head-advanced',
                      'ARCHIVED_SUBMISSION', ?, 'sub-1', ?)
            """,
            (new_node_id, head_row["node_id"], 900_000),
        )
        unit_of_work.connection.execute(
            """
            UPDATE baseline_head_records
            SET node_id = ?, optimistic_version = ?
            WHERE repository_id = ?
            """,
            (new_node_id, head_row["optimistic_version"] + 1, "repo-1"),
        )
    page2 = get_project_history(
        context=identity,
        unit_of_work_factory=_uow_factory(db_path),
        snapshot_loader=HttpHistoryReader(db_path),
        limit=10,
        cursor=page1.next_cursor,
    )
    assert page2.head.version > page1.head.version
    assert _order_key_from_node(page2.nodes[0]) > _order_key_from_node(page1.nodes[-1])
    page1_refs = {node.ref_id for node in page1.nodes}
    page2_refs = {node.ref_id for node in page2.nodes}
    assert page1_refs.isdisjoint(page2_refs)
    known_refs = page1_refs | page2_refs
    for node in page2.nodes:
        if node.parent is not None:
            assert node.parent.ref_id in known_refs


@pytest.mark.parametrize("limit", HISTORY_TREE_PAGE_DIFF_LIMITS)
def test_tree_and_page_paths_match_for_all_cursor_pages(db_path: Path, limit: int) -> None:
    _seed_history_diff_fixture(db_path)
    facts = _load_history_facts(db_path)
    tree_pages = _collect_tree_path_pages(facts=facts, limit=limit)
    query_pages = _collect_page_path_pages(db_path, limit=limit)
    assert len(tree_pages) == len(query_pages)
    for tree_page, query_page in zip(tree_pages, query_pages, strict=True):
        _assert_history_projections_equal(tree_page, query_page)


def test_promoted_baseline_node_is_deterministic_for_duplicate_source_submission(
    db_path: Path,
) -> None:
    # DB allows duplicate source_submission_id; service write paths do not produce this state.
    primary = _seed_promotion_duplicate_fixture(db_path)
    expected_winner = _insert_duplicate_promoted_baseline_rows(
        db_path,
        source_submission_id=primary.submission_id,
    )
    facts = _load_history_facts(db_path)
    tree_page = project_history_tree(facts=facts)
    tree_submission = next(node for node in tree_page.nodes if node.ref_id == primary.submission_id)
    assert tree_submission.promoted_baseline_node_id == expected_winner
    query_pages = _collect_page_path_pages(db_path, limit=10)
    query_submission = next(
        node
        for page in query_pages
        for node in page.nodes
        if node.ref_id == primary.submission_id
    )
    assert query_submission.promoted_baseline_node_id == expected_winner


def test_projection_head_fields_match_readonly_snapshot(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-head"),
    )
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    projection = project_history_tree(facts=facts)
    assert projection.head.node_id == facts.head.business_baseline_node_id
    assert projection.head.commit_id == facts.head.business_baseline_commit_id
    assert projection.head.version == facts.head.baseline_head_version


def test_projection_excludes_non_authoritative_facts(db_path: Path) -> None:
    _seed_pending_review_submission(db_path)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        _insert_operation_record(unit_of_work.connection, operation_id="op-excluded-marker")
        unit_of_work.connection.execute(
            """
            INSERT INTO workspace_records (
                workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
                repository_id, state, generation, optimistic_version, current_upload_revision_id,
                current_preview_result_id, created_at_us, updated_at_us, closed_at_us
            ) VALUES ('ws-failed-import', 'actor-failed-import', 'device-2', 'project-2', 'repo-1',
                      'OPEN', 1, 0, NULL, NULL, 1, 1, NULL)
            """
        )
        unit_of_work.connection.execute(
            """
            INSERT INTO submit_attempt_records (
                submit_attempt_id, workspace_id, workspace_generation, upload_revision_id,
                preview_result_id, repository_id, business_baseline_node_id,
                business_baseline_commit_id, baseline_head_version, repository_expected_commit_id,
                canonical_business_digest, source_digest, snapshot_digest, source_artifact_refs,
                canonical_table_set_closure_ref, canonical_table_set_closure_digest,
                preview_ready_closure_ref, preview_ready_closure_digest,
                canonicalization_manifest_ref, canonicalization_manifest_digest,
                repository_import_artifact_ref, repository_artifact_ref, repository_operation_id,
                repository_operation_evidence, requested_target_ref, requested_verification_policy,
                requested_unknown_type_policy, builder_mutation_policy, accept_idempotency_key,
                accept_request_fingerprint, repository_upload_idempotency_key,
                repository_import_idempotency_key, operation_id, state, submission_id,
                optimistic_version, created_by, created_at_us, effect_pending_at_us,
                finalized_at_us, aborted_at_us, abort_code
            ) VALUES (
                'sa-failed-import', 'ws-failed-import', 1, 'ur-1', 'pr-1', 'repo-1',
                ?, ?, 1, 'commit-main', 'sha256:canonical', 'd-source', 'd-snapshot',
                ?, ?, ?, 'closure-1', 'd-closure', 'manifest-1', 'sha256:manifest', NULL, NULL,
                NULL, NULL, 'main', 'STRUCTURAL', 'REJECT', 'REBUILD_ALWAYS', 'accept-key',
                'sha256:fp', 'upload-key', 'import-key', 'op-excluded-marker', 'ABORTED',
                NULL, 1, 'actor-1', 1, NULL, NULL, 1, 'IMPORT_FAILED'
            )
            """,
            (
                BASELINE_HEAD.business_baseline_node_id,
                BASELINE_HEAD.business_baseline_commit_id,
                canonicalize_json_value([]),
                "canonical-closure-1",
                "sha256:canonical-closure",
            ),
        )
        unit_of_work.connection.execute(
            """
            INSERT INTO archive_plan_records (
                plan_id, repository_id, gateway_device_external_key, business_project_id,
                idempotency_key, request_fingerprint, accepted_by, accepted_at_us,
                old_baseline_node_id, old_baseline_commit_id, old_baseline_head_version,
                candidate_set_digest, selected_submission_id, selected_candidate_digest,
                selected_repository_commit_id, confirmation_refs_json,
                anomaly_resolution_refs_json, frozen_input_json
            ) VALUES (
                'plan-excluded-marker', 'repo-1', 'device-1', 'project-1', 'idem-plan',
                'fp-plan', 'actor-1', 1, ?, ?, 1, 'digest-plan', 'sub-plan-only',
                'cand-plan', 'commit-plan', '[]', '[]', '{}'
            )
            """,
            (
                BASELINE_HEAD.business_baseline_node_id,
                BASELINE_HEAD.business_baseline_commit_id,
            ),
        )
    facts = HttpHistoryReader(db_path).load_facts(
        repository_id="repo-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
    )
    projection = project_history_tree(facts=facts)
    ref_ids = {node.ref_id for node in projection.nodes}
    for marker in EXCLUDED_HISTORY_MARKERS:
        assert marker not in ref_ids


def _corrupt_baseline_created_at_us(db_path: Path, *, node_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE baseline_node_records SET created_at_us = ? WHERE node_id = ?",
            ("not-an-int", node_id),
        )
        connection.commit()


def test_get_project_history_raises_integrity_failure_for_corrupt_facts(db_path: Path) -> None:
    _seed_pending_review_submission(db_path)
    _corrupt_baseline_created_at_us(
        db_path,
        node_id=BASELINE_HEAD.business_baseline_node_id,
    )
    identity = make_identity(
        permissions=frozenset({"read_project_history", "workspace_read"}),
    )
    with pytest.raises(HistoryIntegrityFailure):
        get_project_history(
            context=identity,
            unit_of_work_factory=_uow_factory(db_path),
            snapshot_loader=HttpHistoryReader(db_path),
        )


def test_get_project_history_rejects_disabled_mapping_in_same_transaction(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-scope"),
    )
    _upsert_provisioned_mapping_row(db_path, baseline_head=None, enabled=False)
    identity = make_identity(
        permissions=frozenset({"read_project_history", "workspace_read"}),
    )
    stale_scope = FixedScopeResolutionPort(
        repository_id="repo-1",
        baseline_head=BASELINE_HEAD,
    )
    assert stale_scope.resolve(identity).repository_id == "repo-1"
    with pytest.raises(PermissionDenied):
        get_project_history(
            context=identity,
            unit_of_work_factory=_uow_factory(db_path),
            snapshot_loader=HttpHistoryReader(db_path),
        )


def test_paginated_history_loader_bounds_promotion_fetch(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = _seed_promotion_duplicate_fixture(db_path)
    _insert_duplicate_promoted_baseline_rows(
        db_path,
        source_submission_id=primary.submission_id,
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        for index in range(1000):
            connection.execute(
                """
                INSERT INTO baseline_node_records (
                    node_id, repository_id, gateway_device_external_key, business_project_id,
                    commit_id, kind, parent_node_id, source_submission_id, created_at_us
                ) VALUES (?, 'repo-1', 'device-1', 'project-1', ?, 'ARCHIVED_SUBMISSION', ?, ?, ?)
                """,
                (
                    f"noise-node-{index}",
                    f"commit-noise-{index}",
                    BASELINE_HEAD.business_baseline_node_id,
                    f"noise-sub-{index}",
                    10_000 + index,
                ),
            )
        connection.commit()
    import gateway_backend.infrastructure.control_db.sqlite_history as sqlite_history_module

    promotion_row_counts: list[int] = []
    original_map = sqlite_history_module._promoted_map_from_rows

    def counting_map(rows: list[sqlite3.Row]) -> dict[str, str]:
        promotion_row_counts.append(len(rows))
        return original_map(rows)

    monkeypatch.setattr(sqlite_history_module, "_promoted_map_from_rows", counting_map)
    identity = make_identity(
        permissions=frozenset({"read_project_history", "workspace_read"}),
    )
    first_page = get_project_history(
        context=identity,
        unit_of_work_factory=_uow_factory(db_path),
        snapshot_loader=HttpHistoryReader(db_path),
        limit=1,
    )
    assert len(first_page.nodes) == 1
    assert first_page.nodes[0].node_kind is HistoryNodeKind.BASELINE_NODE
    assert promotion_row_counts == []

    cursor = first_page.next_cursor
    submission_page = None
    while cursor is not None:
        promotion_row_counts.clear()
        page = get_project_history(
            context=identity,
            unit_of_work_factory=_uow_factory(db_path),
            snapshot_loader=HttpHistoryReader(db_path),
            limit=50,
            cursor=cursor,
        )
        submission_nodes = [
            node for node in page.nodes if node.node_kind is HistoryNodeKind.SUBMISSION
        ]
        if submission_nodes:
            submission_page = page
            break
        cursor = page.next_cursor
    assert submission_page is not None
    submission_nodes = [
        node for node in submission_page.nodes if node.node_kind is HistoryNodeKind.SUBMISSION
    ]
    assert promotion_row_counts == [3]
    sub_1 = next(node for node in submission_nodes if node.ref_id == primary.submission_id)
    assert sub_1.promoted_baseline_node_id == "zz-node"


def test_paginated_history_loader_bounds_submission_fetch(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-bounded"),
    )
    import gateway_backend.infrastructure.control_db.sqlite_history as sqlite_history_module

    full_load_calls = 0
    original_loader = sqlite_history_module._load_submission_rows

    def counting_loader(
        connection: sqlite3.Connection,
        *,
        repository_id: str,
    ) -> tuple[HistorySubmissionRow, ...]:
        nonlocal full_load_calls
        full_load_calls += 1
        return original_loader(connection, repository_id=repository_id)

    monkeypatch.setattr(sqlite_history_module, "_load_submission_rows", counting_loader)
    identity = make_identity(
        permissions=frozenset({"read_project_history", "workspace_read"}),
    )
    projection = get_project_history(
        context=identity,
        unit_of_work_factory=_uow_factory(db_path),
        snapshot_loader=HttpHistoryReader(db_path),
        limit=1,
    )
    assert full_load_calls == 0
    assert len(projection.nodes) == 1
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        page = HttpHistoryReader(db_path).load_page_in_transaction(
            unit_of_work,
            repository_id="repo-1",
            gateway_device_external_key="device-1",
            business_project_id="project-1",
            limit=1,
            after_order_key=None,
        )
    assert len(page.entries) == 1
    assert page.has_next_page is True


@pytest.mark.parametrize(("case_id", "limit"), HISTORY_LIMIT_BOUNDARY_CASES)
def test_projection_rejects_limit_boundary_cases(case_id: str, limit: int) -> None:
    del case_id
    facts = _facts(
        baseline_nodes=(),
        submissions=(),
        head=BASELINE_HEAD,
    )
    with pytest.raises(HistoryRequestValidation):
        project_history_tree(facts=facts, limit=limit)
