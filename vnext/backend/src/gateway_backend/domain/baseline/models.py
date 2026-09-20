"""Baseline domain records for persisted business Head authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BaselineNodeKind(StrEnum):
    INITIAL = "INITIAL"
    ARCHIVED_SUBMISSION = "ARCHIVED_SUBMISSION"


@dataclass(frozen=True, slots=True)
class BaselineNode:
    node_id: str
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    commit_id: str
    kind: BaselineNodeKind
    parent_node_id: str | None
    source_submission_id: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if type(self.node_id) is not str or not self.node_id:
            raise ValueError("node_id must be a non-empty string")
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")
        if type(self.commit_id) is not str or not self.commit_id:
            raise ValueError("commit_id must be a non-empty string")
        if type(self.kind) is not BaselineNodeKind:
            raise ValueError("kind must be BaselineNodeKind")
        if self.kind is BaselineNodeKind.INITIAL:
            if self.parent_node_id is not None or self.source_submission_id is not None:
                raise ValueError("INITIAL baseline node must not have parent or source submission")
        else:
            if type(self.parent_node_id) is not str or not self.parent_node_id:
                raise ValueError("ARCHIVED_SUBMISSION baseline node must have parent_node_id")
            if type(self.source_submission_id) is not str or not self.source_submission_id:
                raise ValueError("ARCHIVED_SUBMISSION baseline node must have source_submission_id")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be an aware datetime")


@dataclass(frozen=True, slots=True)
class BaselineHeadRecord:
    repository_id: str
    node_id: str
    optimistic_version: int

    def __post_init__(self) -> None:
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.node_id) is not str or not self.node_id:
            raise ValueError("node_id must be a non-empty string")
        if type(self.optimistic_version) is not int or self.optimistic_version < 0:
            raise ValueError("optimistic_version must be a non-negative integer")
