"""HistoryTreeProjection assembly from authoritative control DB facts."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from gateway_shared_kernel import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.application.history.contracts import (
    DEFAULT_HISTORY_PAGE_LIMIT,
    MAX_HISTORY_CURSOR_BYTES,
    MAX_HISTORY_PAGE_LIMIT,
    HistoryEligibilityNote,
    HistoryFacts,
    HistoryHead,
    HistoryNode,
    HistoryNodeKind,
    HistoryNodeRef,
    HistoryNodeRefKind,
    HistorySubmissionFact,
    HistoryTreeProjection,
)
from gateway_backend.application.history.errors import HistoryIntegrityFailure, HistoryRequestValidation
from gateway_backend.domain.baseline.models import BaselineNode
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead

_CURSOR_VERSION = 1
_NODE_KIND_RANK = {
    HistoryNodeKind.BASELINE_NODE: 0,
    HistoryNodeKind.SUBMISSION: 1,
    HistoryNodeKind.SYSTEM_MIGRATION: 2,
}


def project_history_tree(
    *,
    facts: HistoryFacts,
    limit: int | None = None,
    cursor: str | None = None,
) -> HistoryTreeProjection:
    resolved_limit = DEFAULT_HISTORY_PAGE_LIMIT if limit is None else limit
    if type(resolved_limit) is not int or resolved_limit < 1 or resolved_limit > MAX_HISTORY_PAGE_LIMIT:
        raise HistoryRequestValidation("limit must be an integer between 1 and 500")
    head = HistoryHead.from_baseline_head(facts.head)
    promoted_by_submission = _promoted_baseline_nodes(facts.baseline_nodes)
    nodes = _build_nodes(
        facts=facts,
        head=facts.head,
        promoted_by_submission=promoted_by_submission,
    )
    sorted_nodes = tuple(sorted(nodes, key=_node_sort_key))
    cursor_order_key = _decode_cursor(cursor)
    page_nodes = _paginate(sorted_nodes, limit=resolved_limit, after_order_key=cursor_order_key)
    next_cursor = _encode_next_cursor(page_nodes, sorted_nodes, head_version=head.version)
    return HistoryTreeProjection(head=head, nodes=page_nodes, next_cursor=next_cursor)


def _promoted_baseline_nodes(baseline_nodes: tuple[BaselineNode, ...]) -> dict[str, str]:
    promoted: dict[str, str] = {}
    for node in baseline_nodes:
        if node.source_submission_id is not None:
            promoted[node.source_submission_id] = node.node_id
    return promoted


def _build_nodes(
    *,
    facts: HistoryFacts,
    head: BaselineHead,
    promoted_by_submission: dict[str, str],
) -> list[HistoryNode]:
    nodes: list[HistoryNode] = []
    for baseline_node in facts.baseline_nodes:
        parent = None
        if baseline_node.parent_node_id is not None:
            parent = HistoryNodeRef(
                ref_kind=HistoryNodeRefKind.BASELINE_NODE,
                ref_id=baseline_node.parent_node_id,
            )
        nodes.append(
            HistoryNode(
                ref_kind=HistoryNodeRefKind.BASELINE_NODE,
                ref_id=baseline_node.node_id,
                node_kind=HistoryNodeKind.BASELINE_NODE,
                baseline_kind=baseline_node.kind,
                commit_id=baseline_node.commit_id,
                created_at=baseline_node.created_at,
                parent=parent,
            )
        )
    for submission_fact in facts.submissions:
        nodes.append(_submission_node(submission_fact, head=head, promoted_by_submission=promoted_by_submission))
    return nodes


def _submission_node(
    submission_fact: HistorySubmissionFact,
    *,
    head: BaselineHead,
    promoted_by_submission: dict[str, str],
) -> HistoryNode:
    submission = submission_fact.submission
    eligibility_note = _derive_eligibility_note(
        review_status=submission_fact.review_status,
        based_on_baseline_node_id=submission.based_on_baseline_node_id,
        current_head_node_id=head.business_baseline_node_id,
    )
    return HistoryNode(
        ref_kind=HistoryNodeRefKind.SUBMISSION,
        ref_id=submission.submission_id,
        node_kind=HistoryNodeKind.SUBMISSION,
        commit_id=submission.repository_commit_id,
        created_at=submission.created_at,
        parent=HistoryNodeRef(
            ref_kind=HistoryNodeRefKind.BASELINE_NODE,
            ref_id=submission.based_on_baseline_node_id,
        ),
        review_status=submission_fact.review_status,
        archive_disposition=submission_fact.disposition,
        promoted_baseline_node_id=promoted_by_submission.get(submission.submission_id),
        eligibility_note=eligibility_note,
    )


def _derive_eligibility_note(
    *,
    review_status: ReviewStatus,
    based_on_baseline_node_id: str,
    current_head_node_id: str,
) -> HistoryEligibilityNote | None:
    if review_status is ReviewStatus.APPROVED and based_on_baseline_node_id != current_head_node_id:
        return HistoryEligibilityNote.NOT_CANDIDATE_BASE_ADVANCED
    return None


def _node_sort_key(node: HistoryNode) -> tuple[int, int, bytes]:
    created_at_us = _datetime_to_epoch_us(node.created_at)
    return (created_at_us, _NODE_KIND_RANK[node.node_kind], node.ref_id.encode("utf-8"))


def _order_key_from_node(node: HistoryNode) -> list[object]:
    created_at_us, kind_rank, ref_id_bytes = _node_sort_key(node)
    return [created_at_us, kind_rank, ref_id_bytes.decode("utf-8")]


def _paginate(
    sorted_nodes: tuple[HistoryNode, ...],
    *,
    limit: int,
    after_order_key: list[object] | None,
) -> tuple[HistoryNode, ...]:
    start_index = 0
    if after_order_key is not None:
        for index, node in enumerate(sorted_nodes):
            if _order_key_from_node(node) > after_order_key:
                start_index = index
                break
        else:
            return ()
    page = sorted_nodes[start_index : start_index + limit]
    return page


def _encode_next_cursor(
    page_nodes: tuple[HistoryNode, ...],
    sorted_nodes: tuple[HistoryNode, ...],
    *,
    head_version: int,
) -> str | None:
    if not page_nodes:
        return None
    last_page_node = page_nodes[-1]
    try:
        last_index = sorted_nodes.index(last_page_node)
    except ValueError as exc:
        raise HistoryIntegrityFailure("paginated node is missing from sorted projection") from exc
    if last_index >= len(sorted_nodes) - 1:
        return None
    return _encode_cursor(
        order_key=_order_key_from_node(last_page_node),
        head_version=head_version,
    )


def _encode_cursor(*, order_key: list[object], head_version: int) -> str:
    payload = {
        "order_key": order_key,
        "head_version": head_version,
    }
    raw = canonicalize_json_value(payload)
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if len(encoded.encode("utf-8")) > MAX_HISTORY_CURSOR_BYTES:
        raise HistoryIntegrityFailure("generated cursor exceeds its maximum size")
    return encoded


def _decode_cursor(cursor: str | None) -> list[object] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        if canonicalize_jcs(raw) != raw:
            raise ValueError("cursor JSON is not canonical")
        payload = json.loads(raw)
    except (UnicodeEncodeError, ValueError, json.JSONDecodeError, CanonicalEncodingError) as exc:
        raise HistoryRequestValidation("cursor is malformed") from exc
    if type(payload) is not dict:
        raise HistoryRequestValidation("cursor payload must be an object")
    if set(payload) != {"order_key", "head_version"}:
        raise HistoryRequestValidation("cursor fields do not match the requested query")
    order_key = payload["order_key"]
    stored_head_version = payload["head_version"]
    if type(order_key) is not list or len(order_key) != 3:
        raise HistoryRequestValidation("cursor order_key is malformed")
    created_at_us, kind_rank, ref_id = order_key
    if type(created_at_us) is not int or type(kind_rank) is not int or type(ref_id) is not str:
        raise HistoryRequestValidation("cursor order_key is malformed")
    if type(stored_head_version) is not int or stored_head_version < 0:
        raise HistoryRequestValidation("cursor head_version is malformed")
    return [created_at_us, kind_rank, ref_id]


def _datetime_to_epoch_us(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
