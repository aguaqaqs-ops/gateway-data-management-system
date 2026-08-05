"""Repository visibility helpers for create/upload dual-condition checks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import EffectStatus, MutationKind, MutationStore
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.settings import RepositoryServiceSettings

DEFAULT_REF = "main"


def has_published_repository_tree(layout: DurableLayout, repository_id: UUID) -> bool:
    """Return True when the published repository directory exists on disk."""

    published = layout.published_repository(repository_key(repository_id))
    return published.is_dir() and (published / ".dolt").is_dir()


def read_published_repository_head(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
) -> str | None:
    """Read the opaque main head for a published repository, or None when unreadable."""

    if not has_published_repository_tree(layout, repository_id):
        return None
    published = layout.published_repository(repository_key(repository_id))
    try:
        runner = DoltRunner(settings, layout.root)
        provider = OfflineCliProvider(settings, layout, published, runner)
        return provider.head()
    except Exception:
        return None


def create_response_matches_filesystem(
    *,
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
    response_body: dict[str, Any] | None,
) -> bool:
    """Return True when published repository evidence matches a stored create response."""

    if response_body is None:
        return False
    if str(response_body.get("repository_id")) != str(repository_id):
        return False
    if str(response_body.get("default_ref")) != DEFAULT_REF:
        return False
    initial_commit_id = response_body.get("initial_commit_id")
    if not isinstance(initial_commit_id, str) or not initial_commit_id:
        return False
    head = read_published_repository_head(settings, layout, repository_id)
    return head == initial_commit_id


def succeeded_create_response_body(
    store: MutationStore,
    repository_id: UUID,
) -> dict[str, Any] | None:
    for effect in store.iter_effects_by_status(EffectStatus.SUCCEEDED):
        if effect.scope.mutation_kind != MutationKind.CREATE_REPOSITORY:
            continue
        if effect.resource_id == repository_id:
            return effect.response_body
    return None


def is_repository_visible(
    store: MutationStore,
    layout: DurableLayout,
    repository_id: UUID,
    *,
    settings: RepositoryServiceSettings | None = None,
) -> bool:
    """Repository is visible only when DB and filesystem evidence both exist."""

    if not store.has_succeeded_create(repository_id):
        return False
    if settings is None:
        return has_published_repository_tree(layout, repository_id)
    response_body = succeeded_create_response_body(store, repository_id)
    return create_response_matches_filesystem(
        settings=settings,
        layout=layout,
        repository_id=repository_id,
        response_body=response_body,
    )
