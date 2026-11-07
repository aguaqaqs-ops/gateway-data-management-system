"""Prepare a complete bundle before response headers, then stream bounded tar bytes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field

from gateway_backend.artifacts.store import (
    ArtifactStreamingStorePort,
    ArtifactUnavailableError,
    ManifestVerificationError,
)
from gateway_backend.artifacts.tar_stream import STREAM_CHUNK_BYTES, TAR_END, TarMember
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.bundle_assembly.contracts import (
    BUNDLE_MANIFEST_MEDIA_TYPE,
    MAX_BUNDLE_MANIFEST_JSON_BYTES,
    BundleArtifactKind,
)
from gateway_backend.capabilities.bundle_assembly.transport import (
    BundleIntegrityError,
    BundleTransportMetadata,
    read_bundle_transport_metadata,
    validate_bundle_member_metadata,
)


@dataclass(slots=True)
class PreparedBundleDownload:
    bundle_digest: str
    content_length: int
    filename: str
    etag: str
    stream: Iterator[bytes]
    _resources: ExitStack = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            close_stream = getattr(self.stream, "close", None)
            if close_stream is not None:
                close_stream()
        finally:
            self._resources.close()


@contextmanager
def _read_chunks(store: ArtifactStreamingStorePort, ref: ArtifactRef) -> Iterator[Iterator[bytes]]:
    chunks = store.read_exact(ref)
    try:
        yield chunks
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()


def _metadata_bytes(store: ArtifactStreamingStorePort, ref: ArtifactRef) -> bytes:
    if ref.size_bytes > MAX_BUNDLE_MANIFEST_JSON_BYTES:
        raise BundleIntegrityError("bundle metadata exceeds its JSON budget")
    # Only bounded metadata is materialized; artifact payloads use read_exact.
    with _read_chunks(store, ref) as chunks:
        return b"".join(chunks)


def _preflight_members(store: ArtifactStreamingStorePort, metadata: BundleTransportMetadata) -> None:
    refs = {entry.artifact_ref for entry in metadata.entries}
    # These JSON documents carry references; row annotation payloads are data,
    # and may legally be much larger than the metadata budget.
    metadata_kinds = {
        BundleArtifactKind.SURFACE, BundleArtifactKind.RECORDS_MANIFEST,
        BundleArtifactKind.RECORDS_CLOSURE, BundleArtifactKind.RISK_REPORT,
        BundleArtifactKind.RISK_ANNOTATION_MANIFEST, BundleArtifactKind.RISK_ANNOTATION_CLOSURE,
        BundleArtifactKind.PROJECTION, BundleArtifactKind.DIAGNOSTICS, BundleArtifactKind.OTHER,
    }
    for entry in metadata.entries:
        if "json" in entry.artifact_ref.media_type.casefold() and entry.kind in metadata_kinds:
            validate_bundle_member_metadata(
                entry, _metadata_bytes(store, entry.artifact_ref),
                refs=refs, pair_digests=metadata.pair_digests,
            )
        else:
            with _read_chunks(store, entry.artifact_ref) as chunks:
                for _chunk in chunks:
                    pass


def prepare_bundle_download(store: ArtifactStreamingStorePort, artifact_id: str) -> PreparedBundleDownload:
    resources = ExitStack()
    try:
        resources.enter_context(store.read_session())
        manifest_ref = store.get_ref(artifact_id)
        if manifest_ref.media_type != BUNDLE_MANIFEST_MEDIA_TYPE:
            raise BundleIntegrityError("bundle manifest media type is invalid")
        manifest_raw = _metadata_bytes(store, manifest_ref)
        metadata = read_bundle_transport_metadata(manifest_raw)
        closure_raw = _metadata_bytes(store, metadata.closure_ref)
        if closure_raw != metadata.expected_closure_bytes:
            raise BundleIntegrityError("published bundle closure disagrees with its manifest")
        _preflight_members(store, metadata)
        entries = metadata.entries
        digest = metadata.bundle_digest
        del metadata
        members = (
            TarMember("manifest.json", len(manifest_raw)),
            TarMember("artifact-closure.json", len(closure_raw)),
            *(TarMember(entry.logical_path, entry.size_bytes) for entry in entries),
        )
        length = sum(member.framed_size for member in members) + len(TAR_END)
        filename = f"bundle-{digest.removeprefix('sha256:')}.tar"

        def stream() -> Iterator[bytes]:
            try:
                for member, raw in zip(members[:2], (manifest_raw, closure_raw), strict=True):
                    yield from member.prefix()
                    for offset in range(0, len(raw), STREAM_CHUNK_BYTES):
                        yield raw[offset:offset + STREAM_CHUNK_BYTES]
                    yield from member.suffix()
                for member, entry in zip(members[2:], entries, strict=True):
                    yield from member.prefix()
                    with _read_chunks(store, entry.artifact_ref) as chunks:
                        yield from chunks
                    yield from member.suffix()
                yield TAR_END
            finally:
                resources.close()

        return PreparedBundleDownload(
            bundle_digest=digest,
            content_length=length,
            filename=filename,
            etag=f'"{digest}"',
            stream=stream(),
            _resources=resources,
        )
    except ArtifactUnavailableError:
        resources.close()
        raise
    except (ManifestVerificationError, OSError, ValueError, TypeError, KeyError) as exc:
        resources.close()
        raise BundleIntegrityError("bundle failed integrity verification") from exc
    except BaseException:
        resources.close()
        raise
