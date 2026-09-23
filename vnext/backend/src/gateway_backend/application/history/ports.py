"""History read ports consumed by application queries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.application.history.contracts import HistoryFacts


@runtime_checkable
class HistoryReadPort(Protocol):
    def load_facts(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> HistoryFacts:
        """Load one readonly snapshot of History facts for an authorized scope."""
