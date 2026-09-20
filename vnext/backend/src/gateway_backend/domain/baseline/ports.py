"""Baseline domain ports consumed by application and infrastructure adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.domain.baseline.models import BaselineHeadRecord, BaselineNode
from gateway_backend.domain.workspace.models import BaselineHead


@runtime_checkable
class BaselineHeadReadPort(Protocol):
    def get_current_head(self, repository_id: str) -> BaselineHead:
        """Read the current BaselineHead adapter DTO for one repository."""


@runtime_checkable
class BaselineRepository(Protocol):
    def get_head_record(self, repository_id: str) -> BaselineHeadRecord | None:
        """Return the persisted head record for one repository, if present."""

    def get_node(self, node_id: str) -> BaselineNode | None:
        """Return one baseline node by id."""

    def get_initial_node(self, repository_id: str) -> BaselineNode | None:
        """Return the INITIAL node for one repository, if present."""

    def save_initial_node_and_head(
        self,
        node: BaselineNode,
        head: BaselineHeadRecord,
    ) -> None:
        """Persist one INITIAL node and its version=0 head in the current transaction."""
