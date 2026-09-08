"""SQLite workspace persistence CAS, idempotency and rollback tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.workspace.contracts import AcceptUploadCommand
from gateway_backend.application.workspace.errors import IdempotencyConflict
from gateway_backend.application.workspace.services import accept_upload, create_or_get_workspace
from gateway_backend.domain.workspace.errors import WorkspaceVersionConflict
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_baseline_head, make_identity

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 5, 0, tzinfo=UTC)

INITIAL_BINDING = SourceArtifactBinding(
    artifact_id="initial-1",
    media_type="application/gzip",
    size_bytes=11,
    raw_sha256="sha256:initial",
)
MODIFIED_BINDING = SourceArtifactBinding(
    artifact_id="modified-1",
    media_type="application/gzip",
    size_bytes=12,
    raw_sha256="sha256:modified",
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def _accept_command(
    *,
    workspace_id: str,
    expected_workspace_version: int,
    idempotency_key: str = "upload-key-1",
) -> AcceptUploadCommand:
    return AcceptUploadCommand(
        context=make_identity(),
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        idempotency_key=idempotency_key,
        input_completeness=InputCompleteness.FULL,
        source_artifacts={
            SourceArtifactRole.INITIAL: INITIAL_BINDING,
            SourceArtifactRole.MODIFIED: MODIFIED_BINDING,
        },
        now=TS1,
    )


def test_create_or_get_workspace_persists_open_scope_idempotently(db_path: Path) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        replay = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )

    assert created.replay is False
    assert replay.replay is True
    assert replay.workspace.workspace_id == created.workspace.workspace_id


def test_accept_upload_persists_revision_with_generation_cas(db_path: Path) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace
        result = accept_upload(
            command=_accept_command(
                workspace_id=workspace.workspace_id,
                expected_workspace_version=workspace.optimistic_version,
            ),
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )

    assert result.revision.generation == 1
    assert result.workspace.current_upload_revision_id == result.revision.upload_revision_id

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        loaded = unit_of_work.workspace.get_upload_revision(result.revision.upload_revision_id)
    assert loaded == result.revision


def test_accept_upload_same_key_replays_from_sqlite(db_path: Path) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace
        command = _accept_command(
            workspace_id=workspace.workspace_id,
            expected_workspace_version=0,
        )
        first = accept_upload(
            command=command,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )
        replay = accept_upload(
            command=command,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )

    assert replay.replay is True
    assert replay.revision.upload_revision_id == first.revision.upload_revision_id


def test_accept_upload_same_key_different_fingerprint_conflicts_in_sqlite(db_path: Path) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace
        accept_upload(
            command=_accept_command(
                workspace_id=workspace.workspace_id,
                expected_workspace_version=0,
            ),
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )
        conflicting = AcceptUploadCommand(
            context=make_identity(),
            workspace_id=workspace.workspace_id,
            expected_workspace_version=0,
            idempotency_key="upload-key-1",
            input_completeness=InputCompleteness.MODIFIED_ONLY,
            source_artifacts={SourceArtifactRole.MODIFIED: MODIFIED_BINDING},
            now=TS1,
        )
        with pytest.raises(IdempotencyConflict):
            accept_upload(
                command=conflicting,
                scope_resolution=scope_resolution,
                repository=unit_of_work.workspace,
            )


@pytest.mark.parametrize(("actual_version", "expected_version"), ((2, 1),))
def test_accept_upload_stale_workspace_version_does_not_persist_revision(
    db_path: Path,
    actual_version: int,
    expected_version: int,
) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace
        bumped_once = unit_of_work.workspace.save_workspace(
            replace(workspace, optimistic_version=1, updated_at=TS1),
            expected_version=workspace.optimistic_version,
        )
        unit_of_work.workspace.save_workspace(
            replace(bumped_once, optimistic_version=actual_version, updated_at=TS1),
            expected_version=bumped_once.optimistic_version,
        )
        with pytest.raises(WorkspaceVersionConflict):
            accept_upload(
                command=_accept_command(
                    workspace_id=workspace.workspace_id,
                    expected_workspace_version=expected_version,
                ),
                scope_resolution=scope_resolution,
                repository=unit_of_work.workspace,
            )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        assert unit_of_work.workspace.find_upload_idempotency(workspace.workspace_id, "upload-key-1") is None


def test_upload_publication_rolls_back_when_revision_insert_fails(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace

    with pytest.raises(RuntimeError, match="synthetic revision failure"):
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            def fail_revision(_revision: object) -> None:
                raise RuntimeError("synthetic revision failure")

            monkeypatch.setattr(unit_of_work.workspace, "save_upload_revision", fail_revision)
            accept_upload(
                command=_accept_command(
                    workspace_id=workspace.workspace_id,
                    expected_workspace_version=0,
                ),
                scope_resolution=scope_resolution,
                repository=unit_of_work.workspace,
            )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        reloaded = unit_of_work.workspace.get_workspace(workspace.workspace_id)
        assert reloaded is not None
        assert reloaded.optimistic_version == 0
        assert reloaded.current_upload_revision_id is None


def test_open_workspace_unique_conflict_rereads_existing_workspace(db_path: Path) -> None:
    scope_resolution = FixedScopeResolutionPort(baseline_head=make_baseline_head())
    context = make_identity()

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        first = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        ).workspace
        duplicate = replace(first, workspace_id="ws-duplicate")
        saved = unit_of_work.workspace.save_workspace(duplicate, expected_version=0)
        assert saved.workspace_id == first.workspace_id
