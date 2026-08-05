"""Startup reconciliation for synchronous create/upload mutation effects."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE

from gateway_repository_service.create_repository.visibility import has_published_repository_tree
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import parse_upload_artifact_fingerprint_v1
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    EffectStatus,
    MutationKind,
    MutationStore,
    StoredEffectView,
)
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import has_published_artifact_file

DEFAULT_REF = "main"


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

        return ReconciliationResult(blocking_failures=self.consistency_failures())

    def consistency_failures(self) -> tuple[str, ...]:
        blocking: list[str] = []
        for effect in self._mutation_store.iter_effects_by_status(EffectStatus.SUCCEEDED):
            if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
                if not has_published_repository_tree(self._layout, effect.resource_id):
                    blocking.append(
                        f"create effect {effect.effect_id} succeeded without published repository"
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
                if not has_published_artifact_file(
                    self._layout,
                    repository_id,
                    effect.resource_id,
                    size_bytes=lifecycle.size_bytes,
                    raw_sha256=lifecycle.raw_sha256,
                ):
                    blocking.append(
                        f"upload effect {effect.effect_id} succeeded without matching ready artifact"
                    )
        return tuple(blocking)

    def _reconcile_pending_create(self, effect: StoredEffectView) -> None:
        repository_id = effect.resource_id
        if has_published_repository_tree(self._layout, repository_id):
            published = self._layout.published_repository(repository_key(repository_id))
            initial_commit_id = self._read_repository_head(published)
            response_body = {
                "repository_id": str(repository_id),
                "default_ref": DEFAULT_REF,
                "initial_commit_id": initial_commit_id,
            }
            self._mutation_store.mark_succeeded(effect.effect_id, response_body=response_body)
            return

        self._cleanup_create_staging(repository_id)
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
        self._mutation_store.mark_terminal_not_published(
            effect.scope,
            key_hash=effect.key_hash,
            fingerprint=effect.fingerprint,
            effect_id=effect.effect_id,
        )

    def _read_repository_head(self, published: Path) -> str:
        runner = DoltRunner(self._settings, self._layout.root)
        provider = OfflineCliProvider(self._settings, self._layout, published, runner)
        return provider.head()

    def _cleanup_create_staging(self, repository_id: UUID) -> None:
        key = repository_key(repository_id)
        pattern = f"{key}.*"
        for staged in self._layout.staging_versioned.glob(pattern):
            if staged.is_dir():
                shutil.rmtree(staged, ignore_errors=True)

    def _cleanup_upload_staging(self, repository_id: UUID, artifact_id: UUID) -> None:
        key = repository_key(repository_id)
        staging_dir, _ready_dir = self._layout.repository_artifact_directories(key)
        pattern = f"{artifact_id.hex}.*"
        for staged in staging_dir.glob(pattern):
            if staged.is_file():
                staged.unlink()
