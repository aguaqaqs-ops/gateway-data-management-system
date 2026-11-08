"""Canonical reference/TTL behavior at the actual SQLite transaction owner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.canonical_table_store import (
    CANONICAL_IPC_MEDIA_TYPE,
    CANONICAL_TABLE_TTL_SECONDS,
    CanonicalTableKey,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.baseline.models import BaselineHeadRecord, BaselineNode, BaselineNodeKind
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_canonical_tables import BASELINE_HEAD_OWNER

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 6, tzinfo=UTC)


def cached_entry(seed: bytes = b"table", repository_id: str = "repo") -> tuple[CanonicalTableKey, ArtifactRef]:
    key = CanonicalTableKey(repository_id, "3", raw_blob_digest(b"schema"), 1, raw_blob_digest(seed))
    return key, ArtifactRef(key.artifact_id, CANONICAL_IPC_MEDIA_TYPE, len(seed), raw_blob_digest(seed))


def test_preview_to_attempt_shared_release_and_expiry_are_transactional(db_path: Path) -> None:
    key, ref = cached_entry()
    with ControlDbUnitOfWork(db_path, now=lambda: NOW) as uow:
        uow.canonical_tables.register(key, ref)
        for owner in ("preview-1", "preview-2"):
            uow.set_artifact_protection((ref,), owner_kind="current-preview", owner_id=owner, intent="pin")
        uow.set_artifact_protection((ref,), owner_kind="submit-attempt", owner_id="attempt", intent="pin")
        uow.clear_artifact_protection(owner_kind="current-preview", owner_id="preview-1")
        uow.clear_artifact_protection(owner_kind="submit-attempt", owner_id="attempt")
    future = NOW + timedelta(days=7)
    with ControlDbUnitOfWork(db_path, now=lambda: future) as uow:
        assert uow.canonical_tables.lookup(key) == ref
        assert uow.protection.is_protected(ref.artifact_id)
    with pytest.raises(RuntimeError, match="rollback"):
        with ControlDbUnitOfWork(db_path, now=lambda: future) as uow:
            uow.clear_artifact_protection(owner_kind="current-preview", owner_id="preview-2")
            raise RuntimeError("rollback")
    with ControlDbUnitOfWork(db_path, now=lambda: future) as uow:
        assert uow.canonical_tables.lookup(key) == ref
        uow.clear_artifact_protection(owner_kind="current-preview", owner_id="preview-2")
        assert uow.protection.is_protected(ref.artifact_id)
    expired = future + timedelta(seconds=CANONICAL_TABLE_TTL_SECONDS)
    with ControlDbUnitOfWork(db_path, now=lambda: expired) as uow:
        assert uow.canonical_tables.lookup(key) is None
        assert not uow.protection.is_protected(ref.artifact_id)


def test_cache_hit_touches_protection_before_file_check_and_readonly_does_not_touch(db_path: Path) -> None:
    key, ref = cached_entry()
    with ControlDbUnitOfWork(db_path, now=lambda: NOW) as uow:
        uow.canonical_tables.register(key, ref)
    near_expiry = NOW + timedelta(seconds=CANONICAL_TABLE_TTL_SECONDS - 1)
    with ControlDbUnitOfWork(db_path, now=lambda: near_expiry) as uow:
        assert uow.canonical_tables.lookup(key) == ref
        assert uow.protection.is_protected(ref.artifact_id)
    original_expiry = NOW + timedelta(seconds=CANONICAL_TABLE_TTL_SECONDS + 1)
    with ControlDbUnitOfWork(db_path, read_only=True, now=lambda: original_expiry) as uow:
        assert uow.canonical_tables.lookup(key) == ref
    with ControlDbUnitOfWork(
        db_path, now=lambda: near_expiry + timedelta(seconds=CANONICAL_TABLE_TTL_SECONDS),
    ) as uow:
        assert uow.canonical_tables.lookup(key) is None


def test_initial_and_current_head_bind_only_the_exact_commit(db_path: Path) -> None:
    key, ref = cached_entry()
    old_key, old_ref = cached_entry(b"historical")
    node = BaselineNode("initial", "repo", "device", "project", "exact", BaselineNodeKind.INITIAL, None, None, NOW)
    with ControlDbUnitOfWork(db_path, now=lambda: NOW) as uow:
        uow.canonical_tables.register(key, ref)
        uow.canonical_tables.bind_commit(repository_id="repo", commit_id="exact", refs=(ref,))
        uow.baseline.save_initial_node_and_head(node, BaselineHeadRecord("repo", "initial", 0))
        assert uow.list_artifact_protection_for_owner(owner_kind=BASELINE_HEAD_OWNER, owner_id="repo") == {ref.artifact_id}
        uow.canonical_tables.register(old_key, old_ref)
        uow.canonical_tables.bind_commit(repository_id="repo", commit_id="historical", refs=(old_ref,))
        assert uow.list_artifact_protection_for_owner(owner_kind=BASELINE_HEAD_OWNER, owner_id="repo") == {ref.artifact_id}
    with ControlDbUnitOfWork(db_path, now=lambda: NOW + timedelta(days=7)) as uow:
        assert uow.canonical_tables.lookup(key) == ref
        assert uow.canonical_tables.lookup(old_key) is None


def test_commit_index_rejects_cross_scope_refs(db_path: Path) -> None:
    key, ref = cached_entry()
    with ControlDbUnitOfWork(db_path, now=lambda: NOW) as uow:
        uow.canonical_tables.register(key, ref)
        with pytest.raises(ValueError, match="scope"):
            uow.canonical_tables.bind_commit(repository_id="other", commit_id="exact", refs=(ref,))
