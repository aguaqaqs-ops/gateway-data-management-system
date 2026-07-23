"""Filesystem-backed artifact store with location-independent identity."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.serialize import (
    _loads_strict_jcs_object,
    artifact_manifest_to_dict,
    artifact_manifest_to_json,
    artifact_ref_from_dict,
)
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactManifest, ArtifactRef
from gateway_backend.artifacts.validate import validate_artifact_manifest


class LocalArtifactStore:
    """Persist artifact bytes under a configured root without exposing host paths on the wire."""

    def __init__(self, artifact_root: Path) -> None:
        if not isinstance(artifact_root, Path):
            raise ValueError("artifact_root must be a Path")
        if not artifact_root.is_absolute():
            raise ValueError("artifact_root must be an absolute path")
        try:
            root = artifact_root.expanduser().resolve(strict=False)
            root.mkdir(parents=True, exist_ok=True)
        except OSError, RuntimeError:
            raise ValueError("artifact_root initialization failed") from None
        self._artifact_root = root
        self._refs_by_logical_ref: dict[str, ArtifactRef] = {}

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    def put(self, raw_bytes: bytes, manifest: ArtifactManifest) -> ArtifactRef:
        try:
            return self._put(raw_bytes, manifest)
        except ManifestVerificationError:
            raise
        except OSError, ValueError:
            raise ManifestVerificationError("artifact write failed") from None

    def _put(self, raw_bytes: bytes, manifest: ArtifactManifest) -> ArtifactRef:
        self.verify_manifest(manifest)
        if manifest.size_bytes != len(raw_bytes):
            raise ManifestVerificationError("size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != manifest.raw_sha256.value:
            raise ManifestVerificationError("raw_sha256 mismatch")
        ref = manifest.to_envelope()
        existing = self._refs_by_logical_ref.get(ref.logical_ref)
        if existing is not None and existing != ref:
            raise ManifestVerificationError("logical_ref already identifies a different artifact")
        target, sidecar = self._validated_paths(ref.logical_ref)
        self._reject_on_disk_identity_mismatch(target, sidecar, manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        sidecar_temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".artifact-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(raw_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
            temp_path = None
            sidecar_temp = self._write_manifest_sidecar_atomic(target, sidecar, manifest)
            sidecar_temp = None
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            if sidecar_temp is not None and sidecar_temp.exists():
                sidecar_temp.unlink()
        self._refs_by_logical_ref[ref.logical_ref] = ref
        return ref

    def locate(self, ref: ArtifactRef) -> bytes:
        try:
            return self._locate(ref)
        except ManifestVerificationError:
            raise
        except OSError, ValueError:
            raise ManifestVerificationError("artifact read failed") from None

    def _locate(self, ref: ArtifactRef) -> bytes:
        stored_ref = self._load_stored_ref(ref.logical_ref)
        if stored_ref != ref:
            raise ManifestVerificationError("stored artifact identity mismatch")
        target, _sidecar = self._validated_paths(ref.logical_ref)
        if not target.is_file():
            raise ManifestVerificationError("artifact bytes are missing")
        raw_bytes = target.read_bytes()
        if len(raw_bytes) != ref.size_bytes:
            raise ManifestVerificationError("stored size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != ref.raw_sha256.value:
            raise ManifestVerificationError("stored raw_sha256 mismatch")
        return raw_bytes

    def verify_manifest(self, manifest: ArtifactManifest) -> None:
        validate_artifact_manifest(artifact_manifest_to_dict(manifest))
        _ = manifest.to_envelope()

    def _load_stored_ref(self, logical_ref: str) -> ArtifactRef:
        cached = self._refs_by_logical_ref.get(logical_ref)
        if cached is not None:
            return cached
        target, sidecar = self._validated_paths(logical_ref)
        if not sidecar.is_file():
            raise ManifestVerificationError(f"unknown logical_ref: {logical_ref}")
        stored_ref = _ref_from_manifest_dict(_loads_strict_jcs_object(sidecar.read_bytes()))
        self._refs_by_logical_ref[logical_ref] = stored_ref
        return stored_ref

    def _validated_paths(self, logical_ref: str) -> tuple[Path, Path]:
        target = self._object_path(logical_ref)
        sidecar = self._manifest_sidecar_path(target)
        self._ensure_within_root(target)
        self._ensure_within_root(target.parent)
        self._ensure_within_root(sidecar)
        return target, sidecar

    def _object_path(self, logical_ref: str) -> Path:
        digest = hashlib.sha256(logical_ref.encode("utf-8")).hexdigest()
        return self._artifact_root / digest[0:2] / digest[2:4] / digest

    def _manifest_sidecar_path(self, target: Path) -> Path:
        return target.with_suffix(target.suffix + ".manifest.jcs")

    def _ensure_within_root(self, target: Path) -> None:
        resolved = target.resolve(strict=False)
        root = self._artifact_root.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise ManifestVerificationError("resolved artifact path escapes artifact_root")

    def _reject_on_disk_identity_mismatch(
        self,
        target: Path,
        sidecar: Path,
        manifest: ArtifactManifest,
    ) -> None:
        if not sidecar.is_file():
            return
        stored_dict = _loads_strict_jcs_object(sidecar.read_bytes())
        incoming_dict = artifact_manifest_to_dict(manifest)
        if stored_dict != incoming_dict:
            raise ManifestVerificationError("logical_ref already identifies a different artifact")

    def _write_manifest_sidecar_atomic(
        self,
        target: Path,
        sidecar: Path,
        manifest: ArtifactManifest,
    ) -> Path | None:
        _ = target
        payload = artifact_manifest_to_json(manifest).encode("utf-8")
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=sidecar.parent,
                prefix=".artifact-manifest-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, sidecar)
            return None
        except Exception:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            raise


def _ref_from_manifest_dict(payload: dict[str, object]) -> ArtifactRef:
    validate_artifact_manifest(payload)
    return artifact_ref_from_dict(
        {
            "artifact_ref_schema_version": 1,
            "logical_ref": payload["logical_ref"],
            "media_type": payload["media_type"],
            "size_bytes": payload["size_bytes"],
            "raw_sha256": payload["raw_sha256"],
            "content_digest": payload["content_digest"],
            "content_contract": payload["content_contract"],
            "content_schema_id": payload["content_schema_id"],
            "retention_class": payload["retention_class"],
            "access_metadata": payload["access_metadata"],
        }
    )
