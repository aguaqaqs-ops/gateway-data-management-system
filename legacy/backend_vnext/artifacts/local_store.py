from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from pathlib import Path
import uuid

from ..core.digests import DigestRef, canonical_json_bytes, stable_sha256
from ..core.versions import LOCAL_ARTIFACT_STORE_SCHEMA_VERSION
from .manifest import ArtifactManifest, ArtifactRef


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    ref: ArtifactRef
    manifest: ArtifactManifest
    manifest_path: Path
    content_path: Path
    reused: bool = False

    @property
    def artifact_dir(self) -> Path:
        return self.manifest_path.parent


class LocalArtifactStore:
    schema_version = LOCAL_ARTIFACT_STORE_SCHEMA_VERSION

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def put_bytes(self, manifest: ArtifactManifest, content: bytes) -> StoredArtifact:
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("artifact content must be bytes-like")
        content_bytes = bytes(content)
        expected_content_digest = manifest.content_digest.to_payload()
        actual_content_digest = stable_sha256(content_bytes)
        if expected_content_digest != actual_content_digest:
            raise ValueError("artifact content digest mismatch")
        if manifest.content_size_bytes != len(content_bytes):
            raise ValueError("artifact content size mismatch")

        manifest_payload = manifest.to_payload()
        manifest_digest = DigestRef.from_payload(manifest_payload)
        ref = manifest.to_ref(manifest_digest)
        artifact_dir = self._artifact_dir(ref)
        manifest_path = artifact_dir / "manifest.json"
        content_path = artifact_dir / "content.bin"

        if manifest_path.exists() or content_path.exists():
            existing = self._read_stored_artifact(manifest_digest)
            if existing.manifest.to_payload() != manifest_payload:
                raise ValueError("artifact manifest already exists with different payload")
            if existing.content_path.read_bytes() != content_bytes:
                raise ValueError("artifact content already exists with different payload")
            return StoredArtifact(
                ref=ref,
                manifest=existing.manifest,
                manifest_path=existing.manifest_path,
                content_path=existing.content_path,
                reused=True,
            )

        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._write_bytes(manifest_path, canonical_json_bytes(manifest_payload))
        self._write_bytes(content_path, content_bytes)
        return StoredArtifact(
            ref=ref,
            manifest=manifest,
            manifest_path=manifest_path,
            content_path=content_path,
        )

    def put_file(self, manifest: ArtifactManifest, source_path: Path) -> StoredArtifact:
        if not isinstance(source_path, Path):
            raise TypeError("source_path must be a Path")
        if not source_path.is_file():
            raise FileNotFoundError(str(source_path))

        tmp_dir = self._root / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{uuid.uuid4().hex}.content.tmp"
        hasher = hashlib.sha256()
        size_bytes = 0
        try:
            with source_path.open("rb") as source, tmp_path.open("wb") as target:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    size_bytes += len(chunk)
                    target.write(chunk)

            actual_content_digest = f"sha256:{hasher.hexdigest()}"
            if manifest.content_digest.to_payload() != actual_content_digest:
                raise ValueError("artifact content digest mismatch")
            if manifest.content_size_bytes != size_bytes:
                raise ValueError("artifact content size mismatch")

            manifest_payload = manifest.to_payload()
            manifest_digest = DigestRef.from_payload(manifest_payload)
            ref = manifest.to_ref(manifest_digest)
            artifact_dir = self._artifact_dir(ref)
            manifest_path = artifact_dir / "manifest.json"
            content_path = artifact_dir / "content.bin"

            if manifest_path.exists() or content_path.exists():
                existing = self._read_stored_artifact(
                    manifest_digest,
                    verify_content_digest=False,
                )
                if existing.manifest.to_payload() != manifest_payload:
                    raise ValueError("artifact manifest already exists with different payload")
                if existing.content_path.stat().st_size != size_bytes:
                    raise ValueError("artifact content already exists with different size")
                return StoredArtifact(
                    ref=ref,
                    manifest=existing.manifest,
                    manifest_path=existing.manifest_path,
                    content_path=existing.content_path,
                    reused=True,
                )

            artifact_dir.mkdir(parents=True, exist_ok=True)
            self._write_bytes(manifest_path, canonical_json_bytes(manifest_payload))
            tmp_path.replace(content_path)
            return StoredArtifact(
                ref=ref,
                manifest=manifest,
                manifest_path=manifest_path,
                content_path=content_path,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def read_bytes(self, ref: ArtifactRef | DigestRef | str) -> bytes:
        stored = self.read(ref)
        return stored.content_path.read_bytes()

    def read(self, ref: ArtifactRef | DigestRef | str) -> StoredArtifact:
        if isinstance(ref, ArtifactRef):
            stored = self._read_stored_artifact(ref.manifest_digest)
            if stored.ref != ref:
                raise ValueError("artifact ref does not match stored artifact")
            return stored
        manifest_digest = _coerce_manifest_digest(ref)
        return self._read_stored_artifact(manifest_digest)

    def manifest_path(self, ref: ArtifactRef | DigestRef | str) -> Path:
        return self.read(ref).manifest_path

    def content_path(self, ref: ArtifactRef | DigestRef | str) -> Path:
        return self.read(ref).content_path

    def content_path_unverified(self, ref: ArtifactRef) -> Path:
        if not isinstance(ref, ArtifactRef):
            raise TypeError("ref must be an ArtifactRef")
        stored = self._read_stored_artifact(
            ref.manifest_digest,
            verify_content_digest=False,
        )
        if stored.ref != ref:
            raise ValueError("artifact ref does not match stored artifact")
        return stored.content_path

    def exists(self, ref: ArtifactRef | DigestRef | str) -> bool:
        try:
            self.read(ref)
        except KeyError:
            return False
        return True

    def _read_stored_artifact(
        self,
        manifest_digest: DigestRef,
        *,
        verify_content_digest: bool = True,
    ) -> StoredArtifact:
        artifact_dir = self._artifact_dir_from_digest(manifest_digest)
        manifest_path = artifact_dir / "manifest.json"
        content_path = artifact_dir / "content.bin"
        if not manifest_path.is_file() or not content_path.is_file():
            raise KeyError("artifact not found")
        loaded_manifest_payload = json_loads(manifest_path.read_bytes())
        manifest = ArtifactManifest.from_payload(loaded_manifest_payload)
        if DigestRef.from_payload(manifest.to_payload()) != manifest_digest:
            raise ValueError("artifact manifest digest mismatch")
        if verify_content_digest and stable_sha256(content_path.read_bytes()) != manifest.content_digest.to_payload():
            raise ValueError("artifact content digest mismatch")
        return StoredArtifact(
            ref=manifest.to_ref(manifest_digest),
            manifest=manifest,
            manifest_path=manifest_path,
            content_path=content_path,
        )

    def _artifact_dir(self, ref: ArtifactRef) -> Path:
        return self._artifact_dir_from_digest(ref.manifest_digest, ref.artifact_kind)

    def _artifact_dir_from_digest(
        self,
        manifest_digest: DigestRef,
        artifact_kind: str | None = None,
    ) -> Path:
        del artifact_kind
        return self._root / "artifacts" / manifest_digest.hex_digest

    def _write_bytes(self, path: Path, data: bytes) -> None:
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)


def _coerce_manifest_digest(ref: ArtifactRef | DigestRef | str) -> DigestRef:
    if isinstance(ref, ArtifactRef):
        return ref.manifest_digest
    if isinstance(ref, DigestRef):
        return ref
    return DigestRef.parse(ref)


def json_loads(raw: bytes) -> Mapping[str, object]:
    import json

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("artifact manifest payload must be a mapping")
    return payload
