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


def _published_cli_provider(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
) -> OfflineCliProvider:
    published = layout.published_repository(repository_key(repository_id))
    runner = DoltRunner(settings, layout.root)
    return OfflineCliProvider(settings, layout, published, runner)


def read_published_repository_head_strict(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
) -> str | None:
    """Read main head, propagating provider errors when the published tree exists."""

    if not has_published_repository_tree(layout, repository_id):
        return None
    return _published_cli_provider(settings, layout, repository_id).head()


def read_published_repository_head(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
) -> str | None:
    """Read main head, returning None when the tree is missing or unreadable."""

    try:
        return read_published_repository_head_strict(settings, layout, repository_id)
    except Exception:
        return None


def create_repository_visible_bounded(
    store: MutationStore,
    layout: DurableLayout,
    repository_id: UUID,
) -> bool:
    """Repository is visible when DB and published tree evidence both exist."""

    return store.has_succeeded_create(repository_id) and has_published_repository_tree(
        layout, repository_id
    )


def create_repository_matches_ledger_full(
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
    if not has_published_repository_tree(layout, repository_id):
        return False
    try:
        provider = _published_cli_provider(settings, layout, repository_id)
        head = provider.head()
        if head == initial_commit_id:
            return True
        return provider.commit_reachable_from_main(initial_commit_id)
    except Exception:
        return False


def create_response_matches_filesystem(
    *,
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository_id: UUID,
    response_body: dict[str, Any] | None,
) -> bool:
    """Backward-compatible alias for startup full create consistency checks."""

    return create_repository_matches_ledger_full(
        settings=settings,
        layout=layout,
        repository_id=repository_id,
        response_body=response_body,
    )


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

    del settings
    return create_repository_visible_bounded(store, layout, repository_id)
