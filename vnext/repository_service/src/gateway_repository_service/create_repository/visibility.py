"""Repository visibility helpers for create/upload dual-condition checks."""

from __future__ import annotations

from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import MutationStore


def has_published_repository_tree(layout: DurableLayout, repository_id: UUID) -> bool:
    """Return True when the published repository directory exists on disk."""

    published = layout.published_repository(repository_key(repository_id))
    return published.is_dir() and (published / ".dolt").is_dir()


def is_repository_visible(
    store: MutationStore,
    layout: DurableLayout,
    repository_id: UUID,
) -> bool:
    """Repository is visible only when DB and filesystem evidence both exist."""

    return store.has_succeeded_create(repository_id) and has_published_repository_tree(
        layout,
        repository_id,
    )
