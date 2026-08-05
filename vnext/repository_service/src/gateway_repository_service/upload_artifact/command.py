"""UploadArtifact application command."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UploadArtifactResponse,
    UploadRequestHeaders,
    validate_upload_content_length,
)

from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    assert_upload_disk_admission,
)
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import upload_artifact_fingerprint_v1
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    DuplicateEffectClaim,
    EffectStatus,
    FingerprintConflict,
    IdempotencyScope,
    IdempotencyTerminalNotPublished,
    MutationStore,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.adapters import (
    ArtifactFilesystemPublicationAdapter,
    StreamingFileSinkAdapter,
)
from gateway_repository_service.upload_artifact.ports import (
    ArtifactBodySink,
    ArtifactPublicationPort,
    NoOpUploadArtifactFaultInjector,
    UploadArtifactFaultInjector,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path


class UploadArtifactCommand:
    """Orchestrates bounded raw artifact upload with idempotent replay."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        mutation_store: MutationStore,
        publication_port: ArtifactPublicationPort | None = None,
        fault_injector: UploadArtifactFaultInjector | None = None,
        sink_factory: type[StreamingFileSinkAdapter] = StreamingFileSinkAdapter,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._mutation_store = mutation_store
        self._publication_port = publication_port or ArtifactFilesystemPublicationAdapter()
        self._fault_injector = fault_injector or NoOpUploadArtifactFaultInjector()
        self._sink_factory = sink_factory

    async def execute(
        self,
        repository_id: UUID,
        headers: UploadRequestHeaders,
        body: AsyncIterator[bytes],
    ) -> UploadArtifactResponse:
        scope = IdempotencyScope.for_upload(repository_id)
        key_hash = MutationStore.hash_idempotency_key(headers.idempotency_key)
        fingerprint = upload_artifact_fingerprint_v1(
            media_type=headers.content_type,
            declared_size=headers.content_length,
            raw_sha256_hex=headers.artifact_sha256,
        )

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

        self._assert_pre_pending_guards(repository_id, headers)

        artifact_id = uuid4()
        staged_path: Path | None = None
        sink: ArtifactBodySink | None = None
        try:
            effect = self._mutation_store.allocate_pending(
                scope,
                key_hash=key_hash,
                fingerprint=fingerprint,
                resource_id=artifact_id,
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
                _status, body_dict = stored
                return UploadArtifactResponse.model_validate(body_dict)
            raise _idempotency_conflict() from exc

        if effect.status == EffectStatus.SUCCEEDED:
            return _response_from_effect(effect.response_body)

        self._fault_injector.after_pending()

        key = repository_key(repository_id)
        staging_dir, _ready_dir = self._layout.repository_artifact_directories(key)
        nonce = uuid4().hex[:12]
        staged_path = staging_dir / f"{artifact_id.hex}.{nonce}"
        sink = self._sink_factory(staged_path)
        partial_body_faulted = False
        try:
            async for chunk in body:
                if chunk:
                    sink.write_chunk(chunk)
                    if not partial_body_faulted:
                        partial_body_faulted = True
                        self._fault_injector.after_partial_body()
                received_so_far = _sink_received_bytes(sink)
                if received_so_far > headers.content_length:
                    raise _upload_body_mismatch("upload body exceeds declared Content-Length")

            received_bytes, computed_sha = sink.close()
            sink = None
            if received_bytes != headers.content_length:
                raise _upload_body_mismatch("upload body size does not match declared Content-Length")
            if computed_sha != headers.artifact_sha256:
                raise _upload_digest_mismatch()

            self._fault_injector.after_complete_close()

            ready_path = artifact_ready_path(self._layout, repository_id, artifact_id)
            self._layout.assert_publication_devices(staged_path, ready_path.parent)
            self._publication_port.publish_file(
                staged_path,
                ready_path,
                fault=self._fault_injector.publication_fault(),
            )
            staged_path = None

            response_body = {
                "artifact_ref": {
                    "artifact_id": str(artifact_id),
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": received_bytes,
                    "raw_sha256": headers.artifact_sha256,
                }
            }
            self._mutation_store.mark_succeeded(
                effect.effect_id,
                response_body=response_body,
                artifact_lifecycle=ArtifactLifecycleRecord(
                    artifact_id=artifact_id,
                    repository_id=repository_id,
                    media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
                    size_bytes=received_bytes,
                    raw_sha256=headers.artifact_sha256,
                ),
            )
            return UploadArtifactResponse.model_validate(response_body)
        except FingerprintConflict as exc:
            raise _idempotency_conflict() from exc
        except IdempotencyTerminalNotPublished as exc:
            raise _idempotency_conflict() from exc
        except FileExistsError as exc:
            if sink is not None:
                sink.abort()
            elif staged_path is not None and staged_path.exists():
                staged_path.unlink()
            raise _idempotency_conflict() from exc
        except Exception:
            if sink is not None:
                sink.abort()
            elif staged_path is not None and staged_path.exists():
                staged_path.unlink()
            raise

    def _assert_pre_pending_guards(
        self,
        repository_id: UUID,
        headers: UploadRequestHeaders,
    ) -> None:
        if not is_repository_visible(self._mutation_store, self._layout, repository_id):
            raise _repository_not_found()
        try:
            validate_upload_content_length(
                headers.content_length,
                max_upload_bytes=self._settings.max_upload_bytes,
            )
        except ValueError as exc:
            raise _payload_too_large() from exc
        try:
            assert_upload_disk_admission(
                self._layout.root,
                self._settings,
                declared_size=headers.content_length,
            )
        except CapacityAdmissionError as exc:
            raise _disk_admission_denied() from exc


def _sink_received_bytes(sink: ArtifactBodySink) -> int:
    received = getattr(sink, "_received_bytes", None)
    if isinstance(received, int):
        return received
    return 0


def _response_from_effect(response_body: dict[str, object] | None) -> UploadArtifactResponse:
    if response_body is None:
        raise ServiceError(
            code="INTERNAL_ERROR",
            message="stored upload response is missing",
            status_code=500,
        )
    return UploadArtifactResponse.model_validate(response_body)


def _idempotency_conflict() -> ServiceError:
    return ServiceError(
        code="IDEMPOTENCY_CONFLICT",
        message="idempotency key conflicts with a different request",
        status_code=409,
    )


def _repository_not_found() -> ServiceError:
    return ServiceError(
        code="REPOSITORY_NOT_FOUND",
        message="repository was not found",
        status_code=404,
    )


def _payload_too_large() -> ServiceError:
    return ServiceError(
        code="PAYLOAD_TOO_LARGE",
        message="declared upload size exceeds configured limit",
        status_code=413,
    )


def _disk_admission_denied() -> ServiceError:
    return ServiceError(
        code="DISK_ADMISSION_DENIED",
        message="durable root does not have enough free disk for upload",
        status_code=503,
    )


def _upload_body_mismatch(message: str) -> ServiceError:
    return ServiceError(
        code="UPLOAD_BODY_MISMATCH",
        message=message,
        status_code=422,
    )


def _upload_digest_mismatch() -> ServiceError:
    return ServiceError(
        code="UPLOAD_DIGEST_MISMATCH",
        message="upload body digest does not match X-Artifact-SHA256",
        status_code=422,
    )
