"""Shared startup/online CREATE publication decision; no alternate recovery ledger."""
from __future__ import annotations

import shutil
import stat
from pathlib import Path
from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.settings import RepositoryServiceSettings


class CreateEvidenceUnresolved(RuntimeError):
    pass


def inspect_create_publication(*, settings: RepositoryServiceSettings, layout: DurableLayout,
                               repository_id: UUID, runner: DoltRunner | None = None) -> str | None:
    """None means proven absent; a hash means the original, still-empty initial commit."""
    target = layout.published_repository(repository_key(repository_id))
    try:
        info = target.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        raise CreateEvidenceUnresolved("create target is not an ordinary directory")
    try:
        if not stat.S_ISDIR((target / ".dolt").lstat().st_mode):
            raise CreateEvidenceUnresolved("create target has no ordinary Dolt directory")
        provider = OfflineCliProvider(settings, layout, target, runner or DoltRunner.for_layout(settings, layout))
        head = provider.head()
        history = provider._query_json("create_initial_history", "SELECT commit_hash FROM dolt_log;\n")
        tables = provider._query_json("create_initial_tables", "SHOW TABLES;\n")
        changes = provider._query_json("create_initial_status", "SELECT * FROM dolt_status;\n")
        if len(history) != 1 or str(history[0].get("commit_hash")) != head or tables or changes:
            raise CreateEvidenceUnresolved("pending create is not the original empty repository")
        return head
    except Exception as exc:
        raise CreateEvidenceUnresolved("published create evidence cannot be established") from exc


def cleanup_create_staging(layout: DurableLayout, repository_id: UUID) -> None:
    """Only this effect's server-generated staging; never touch the formal target."""
    key = repository_key(repository_id)
    for staged in layout.staging_versioned.glob(f"{key}.*"):
        suffix = staged.name[len(key) + 1:]
        if len(suffix) != 12 or any(c not in "0123456789abcdef" for c in suffix):
            raise CreateEvidenceUnresolved("unexpected create staging name")
        _remove_staging(staged)
    if list(layout.staging_versioned.glob(f"{key}.*")):
        raise CreateEvidenceUnresolved("create staging remains")


def _remove_staging(staged: Path) -> None:
    if not stat.S_ISDIR(staged.lstat().st_mode):
        raise CreateEvidenceUnresolved("create staging is not an ordinary directory")
    shutil.rmtree(staged)
