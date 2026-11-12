"""CreateRepository application command."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from gateway_repository_contracts import CreateRepositoryResponse

from gateway_repository_service.create_repository.adapters import (
    DoltCreateAdapter,
    FilesystemPublicationAdapter,
)
from gateway_repository_service.create_repository.ports import (
    CreateRepositoryFaultInjector,
    NoOpCreateRepositoryFaultInjector,
    RepositoryCreatePort,
    RepositoryPublicationPort,
)
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    EffectStatus,
    FingerprintConflict,
    IdempotencyScope,
    MutationStore,
)
from gateway_repository_service.settings import RepositoryServiceSettings

DEFAULT_REF = "main"


class CreateRepositoryCommand:
    """Orchestrates crash-safe repository creation with idempotent replay."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        mutation_store: MutationStore,
        create_port: RepositoryCreatePort | None = None,
        publication_port: RepositoryPublicationPort | None = None,
        fault_injector: CreateRepositoryFaultInjector | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._mutation_store = mutation_store
        self._create_port = create_port
        self._publication_port = publication_port or FilesystemPublicationAdapter()
        self._fault_injector = fault_injector or NoOpCreateRepositoryFaultInjector()

    def execute(self, idempotency_key: str) -> CreateRepositoryResponse:
        with self._mutation_store.create_execution.admit():
            return self._execute(idempotency_key)

    def _execute(self, idempotency_key: str) -> CreateRepositoryResponse:
        from gateway_repository_service.create_repository.execution import unresolved
        from gateway_repository_service.create_repository.recovery import (
            CreateEvidenceUnresolved, cleanup_create_staging, inspect_create_publication,
        )
        from gateway_repository_service.mutation_store import MutationStoreError

        scope = IdempotencyScope.for_create()
        key_hash = MutationStore.hash_idempotency_key(idempotency_key)
        fingerprint = create_repository_fingerprint_v1()
        try:
            previous = self._mutation_store.lookup_create_effect(key_hash=key_hash, fingerprint=fingerprint)
            if previous is not None and previous.status == EffectStatus.SUCCEEDED:
                return _response_from_effect(previous.response_body)
            runner = self._mutation_store.create_execution.configure(self._settings, self._layout)
            if previous is not None:
                initial = inspect_create_publication(settings=self._settings, layout=self._layout,
                    repository_id=previous.resource_id, runner=runner)
                if initial is not None:
                    if previous.terminal_not_published:
                        raise CreateEvidenceUnresolved("terminal create has a published target")
                    body = {"repository_id": str(previous.resource_id), "default_ref": DEFAULT_REF,
                        "initial_commit_id": initial}
                    self._mutation_store.mark_succeeded(previous.effect_id, response_body=body)
                    return CreateRepositoryResponse.model_validate(body)
                cleanup_create_staging(self._layout, previous.resource_id)
                if previous.terminal_not_published:
                    self._mutation_store.reopen_unpublished_create(previous)
                effect_id = previous.effect_id
                repository_id = previous.resource_id
            else:
                self._mutation_store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
                repository_id = uuid4()
                allocated = self._mutation_store.allocate_pending(scope, key_hash=key_hash,
                    fingerprint=fingerprint, resource_id=repository_id)
                effect_id = allocated.effect_id
        except FingerprintConflict as exc:
            raise _idempotency_conflict() from exc
        except (CreateEvidenceUnresolved, MutationStoreError, OSError) as exc:
            raise unresolved() from exc

        self._fault_injector.after_pending()
        key = repository_key(repository_id)
        staged: Path | None = self._layout.staging_repository(key, uuid4().hex[:12])
        self._fault_injector.after_staging()
        try:
            create_port = self._create_port or DoltCreateAdapter(self._settings, self._layout, runner)
            initial_commit_id = create_port.initialize_and_head(staged)
            self._fault_injector.after_dolt_init()
            target = self._layout.published_repository(key)
            self._layout.assert_publication_devices(staged, target.parent)
            self._publication_port.publish(staged, target, fault=self._fault_injector.publication_fault())
            staged = None
            body = {"repository_id": str(repository_id), "default_ref": DEFAULT_REF,
                "initial_commit_id": initial_commit_id}
            self._mutation_store.mark_succeeded(effect_id, response_body=body)
            self._fault_injector.after_succeeded_before_response()
            return CreateRepositoryResponse.model_validate(body)
        except FileExistsError as exc:
            _cleanup_staging(staged)
            raise unresolved() from exc
        except BaseException:
            # Never remove staging while a child may still use it.
            if not runner.has_active_children():
                _cleanup_staging(staged)
            raise


def _cleanup_staging(staged: Path | None) -> None:
    if staged is not None and staged.exists():
        shutil.rmtree(staged, ignore_errors=True)


def _response_from_effect(response_body: dict[str, object] | None) -> CreateRepositoryResponse:
    if response_body is None:
        raise ServiceError(
            code="INTERNAL_ERROR",
            message="stored create response is missing",
            status_code=500,
        )
    return CreateRepositoryResponse.model_validate(response_body)


def _idempotency_conflict() -> ServiceError:
    return ServiceError(
        code="IDEMPOTENCY_CONFLICT",
        message="idempotency key conflicts with a different request",
        status_code=409,
    )
