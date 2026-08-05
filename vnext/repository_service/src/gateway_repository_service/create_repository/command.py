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
    DuplicateEffectClaim,
    EffectStatus,
    FingerprintConflict,
    IdempotencyScope,
    IdempotencyTerminalNotPublished,
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
        self._create_port = create_port or DoltCreateAdapter(settings, layout)
        self._publication_port = publication_port or FilesystemPublicationAdapter()
        self._fault_injector = fault_injector or NoOpCreateRepositoryFaultInjector()

    def execute(self, idempotency_key: str) -> CreateRepositoryResponse:
        scope = IdempotencyScope.for_create()
        key_hash = MutationStore.hash_idempotency_key(idempotency_key)
        fingerprint = create_repository_fingerprint_v1()

        try:
            claim = self._mutation_store.claim_or_lookup(
                scope,
                key_hash=key_hash,
                fingerprint=fingerprint,
            )
        except FingerprintConflict as exc:
            raise _idempotency_conflict() from exc
        except IdempotencyTerminalNotPublished as exc:
            raise _idempotency_conflict() from exc

        if claim.effect is not None and claim.effect.status == EffectStatus.SUCCEEDED:
            return _response_from_effect(claim.effect.response_body)

        repository_id = uuid4()
        staged: Path | None = None
        try:
            effect = self._mutation_store.allocate_pending(
                scope,
                key_hash=key_hash,
                fingerprint=fingerprint,
                resource_id=repository_id,
            )
        except FingerprintConflict as exc:
            raise _idempotency_conflict() from exc
        except IdempotencyTerminalNotPublished as exc:
            raise _idempotency_conflict() from exc
        except DuplicateEffectClaim as exc:
            stored = self._mutation_store.get_stored_response(
                scope,
                key_hash=key_hash,
                fingerprint=fingerprint,
            )
            if stored is not None:
                _status, body = stored
                return CreateRepositoryResponse.model_validate(body)
            raise _idempotency_conflict() from exc

        if effect.status == EffectStatus.SUCCEEDED:
            return _response_from_effect(effect.response_body)

        key = repository_key(repository_id)
        staged = self._layout.staging_repository(key, uuid4().hex[:12])
        try:
            initial_commit_id = self._create_port.initialize_and_head(staged)
            target = self._layout.published_repository(key)
            self._layout.assert_publication_devices(staged, target.parent)
            self._publication_port.publish(
                staged,
                target,
                fault=self._fault_injector.publication_fault(),
            )
            staged = None
            response_body = {
                "repository_id": str(repository_id),
                "default_ref": DEFAULT_REF,
                "initial_commit_id": initial_commit_id,
            }
            self._mutation_store.mark_succeeded(effect.effect_id, response_body=response_body)
            return CreateRepositoryResponse.model_validate(response_body)
        except FingerprintConflict as exc:
            raise _idempotency_conflict() from exc
        except IdempotencyTerminalNotPublished as exc:
            raise _idempotency_conflict() from exc
        except FileExistsError as exc:
            raise _idempotency_conflict() from exc
        except Exception:
            if staged is not None and staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            raise


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
