"""Startup reconciliation for synchronous create/upload mutation effects."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE

from gateway_repository_service.create_repository.visibility import (
    DEFAULT_REF,
    create_response_matches_filesystem,
    has_published_repository_tree,
    read_published_repository_head,
)
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import parse_upload_artifact_fingerprint_v1
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    EffectStatus,
    MutationKind,
    MutationStore,
    StoredEffectView,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import (
    has_published_artifact_file,
    has_ready_artifact_size,
)


class ReconciliationError(RuntimeError):
    """Raised when startup reconciliation cannot complete safely."""


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    blocking_failures: tuple[str, ...]


class SynchronousMutationReconciler:
    """Reconcile create/upload ledgers with filesystem evidence at startup."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        mutation_store: MutationStore,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._mutation_store = mutation_store

    def reconcile(self) -> ReconciliationResult:
        for effect in self._mutation_store.iter_effects_by_status(EffectStatus.PENDING):
            if effect.terminal_not_published:
                continue
            if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
                self._reconcile_pending_create(effect)
            else:
                self._reconcile_pending_upload(effect)

        return ReconciliationResult(blocking_failures=self.consistency_failures_full())

    def consistency_failures_full(self) -> tuple[str, ...]:
        return self._consistency_failures(verify_upload_sha=True)

    def consistency_failures_bounded(self) -> tuple[str, ...]:
        return self._consistency_failures(verify_upload_sha=False)

    def consistency_failures(self) -> tuple[str, ...]:
        """Backward-compatible alias for startup full consistency checks."""

        return self.consistency_failures_full()

    def _consistency_failures(self, *, verify_upload_sha: bool) -> tuple[str, ...]:
        blocking: list[str] = []
        for effect in self._mutation_store.iter_effects_by_status(EffectStatus.SUCCEEDED):
            if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
                if not create_response_matches_filesystem(
                    settings=self._settings,
                    layout=self._layout,
                    repository_id=effect.resource_id,
                    response_body=effect.response_body,
                ):
                    blocking.append(
                        f"create effect {effect.effect_id} succeeded without matching published repository"
                    )
            else:
                repository_id = effect.scope.repository_id
                if repository_id is None:
                    blocking.append(
                        f"upload effect {effect.effect_id} has invalid repository scope"
                    )
                    continue
                lifecycle = self._mutation_store.get_artifact_lifecycle(effect.resource_id)
                if lifecycle is None:
                    blocking.append(
                        f"upload effect {effect.effect_id} succeeded without artifact lifecycle"
                    )
                    continue
                if verify_upload_sha:
                    matches = has_published_artifact_file(
                        self._layout,
                        repository_id,
                        effect.resource_id,
                        size_bytes=lifecycle.size_bytes,
                        raw_sha256=lifecycle.raw_sha256,
                    )
                else:
                    matches = has_ready_artifact_size(
                        self._layout,
                        repository_id,
                        effect.resource_id,
                        size_bytes=lifecycle.size_bytes,
                    )
                if not matches:
                    blocking.append(
                        f"upload effect {effect.effect_id} succeeded without matching ready artifact"
                    )
        return tuple(blocking)

    def _reconcile_pending_create(self, effect: StoredEffectView) -> None:
        repository_id = effect.resource_id
        if has_published_repository_tree(self._layout, repository_id):
            try:
                initial_commit_id = read_published_repository_head(
                    self._settings,
                    self._layout,
                    repository_id,
                )
            except Exception as exc:
                raise ReconciliationError(
                    f"failed to read head for pending create effect {effect.effect_id}"
                ) from exc
            if initial_commit_id is not None:
                response_body = {
                    "repository_id": str(repository_id),
                    "default_ref": DEFAULT_REF,
                    "initial_commit_id": initial_commit_id,
                }
                self._mutation_store.mark_succeeded(effect.effect_id, response_body=response_body)
                return

        self._cleanup_create_staging(repository_id)
        self._assert_create_staging_absent(repository_id)
        self._mutation_store.mark_terminal_not_published(
            effect.scope,
            key_hash=effect.key_hash,
            fingerprint=effect.fingerprint,
            effect_id=effect.effect_id,
        )

    def _reconcile_pending_upload(self, effect: StoredEffectView) -> None:
        repository_id = effect.scope.repository_id
        if repository_id is None:
            return

        parsed = parse_upload_artifact_fingerprint_v1(effect.fingerprint)
        artifact_id = effect.resource_id
        if has_published_artifact_file(
            self._layout,
            repository_id,
            artifact_id,
            size_bytes=parsed.declared_size,
            raw_sha256=parsed.raw_sha256_hex,
        ):
            response_body = {
                "artifact_ref": {
                    "artifact_id": str(artifact_id),
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": parsed.declared_size,
                    "raw_sha256": parsed.raw_sha256_hex,
                }
            }
            self._mutation_store.mark_succeeded(
                effect.effect_id,
                response_body=response_body,
                artifact_lifecycle=ArtifactLifecycleRecord(
                    artifact_id=artifact_id,
                    repository_id=repository_id,
                    media_type=parsed.media_type,
                    size_bytes=parsed.declared_size,
                    raw_sha256=parsed.raw_sha256_hex,
                ),
            )
            return

        self._cleanup_upload_staging(repository_id, artifact_id)
        self._assert_upload_staging_absent(repository_id, artifact_id)
        self._mutation_store.mark_terminal_not_published(
            effect.scope,
            key_hash=effect.key_hash,
            fingerprint=effect.fingerprint,
            effect_id=effect.effect_id,
        )

    def _cleanup_create_staging(self, repository_id: UUID) -> None:
        key = repository_key(repository_id)
        pattern = f"{key}.*"
        for staged in self._layout.staging_versioned.glob(pattern):
            if staged.is_dir():
                shutil.rmtree(staged)

    def _assert_create_staging_absent(self, repository_id: UUID) -> None:
        if staging_dirs_for_repository(self._layout, repository_id):
            raise ReconciliationError(
                f"failed to remove create staging for repository {repository_id.hex}"
            )

    def _cleanup_upload_staging(self, repository_id: UUID, artifact_id: UUID) -> None:
        key = repository_key(repository_id)
        staging_dir, _ready_dir = self._layout.repository_artifact_directories(key)
        pattern = f"{artifact_id.hex}.*"
        for staged in staging_dir.glob(pattern):
            if staged.is_file():
                staged.unlink()

    def _assert_upload_staging_absent(self, repository_id: UUID, artifact_id: UUID) -> None:
        if upload_staging_files_for_artifact(self._layout, repository_id, artifact_id):
            raise ReconciliationError(
                f"failed to remove upload staging for artifact {artifact_id.hex}"
            )


def staging_dirs_for_repository(layout: DurableLayout, repository_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    return list(layout.staging_versioned.glob(f"{key}.*"))


def upload_staging_files_for_artifact(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
) -> list[Path]:
    key = repository_key(repository_id)
    staging_dir, _ready = layout.repository_artifact_directories(key)
    return list(staging_dir.glob(f"{artifact_id.hex}.*"))
