"""Filesystem-backed artifact store with location-independent minimal refs."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.serialize import artifact_ref_from_json, artifact_ref_to_json
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.validate import validate_artifact_ref_model


class LocalArtifactStore:
    """Persist bytes under a configured root without exposing the host path."""

    def __init__(self, artifact_root: Path) -> None:
        if not isinstance(artifact_root, Path):
            raise ValueError("artifact_root must be a Path")
        if not artifact_root.is_absolute():
            raise ValueError("artifact_root must be an absolute path")
        try:
            root = artifact_root.expanduser().resolve(strict=False)
            root.mkdir(parents=True, exist_ok=True)
        except (OSError, RuntimeError):
            raise ValueError("artifact_root initialization failed") from None
        self._artifact_root = root
        self._refs_by_artifact_id: dict[str, ArtifactRef] = {}

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        try:
            return self._put(raw_bytes, ref)
        except ManifestVerificationError:
            raise
        except (OSError, ValueError):
            raise ManifestVerificationError("artifact write failed") from None

    def _put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        validate_artifact_ref_model(ref)
        self._verify_raw(raw_bytes, ref)
        existing = self._refs_by_artifact_id.get(ref.artifact_id)
        if existing is not None and existing != ref:
            raise ManifestVerificationError("artifact_id already identifies a different artifact")
        target, sidecar = self._validated_paths(ref.artifact_id)
        self._reject_on_disk_identity_mismatch(sidecar, ref)
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
            sidecar_temp = self._write_ref_sidecar_atomic(sidecar, ref)
            sidecar_temp = None
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
            if sidecar_temp is not None and sidecar_temp.exists():
                sidecar_temp.unlink()
        self._refs_by_artifact_id[ref.artifact_id] = ref
        return ref

    def locate(self, ref: ArtifactRef) -> bytes:
        try:
            return self._locate(ref)
        except ManifestVerificationError:
            raise
        except (OSError, ValueError):
            raise ManifestVerificationError("artifact read failed") from None

    def _locate(self, ref: ArtifactRef) -> bytes:
        validate_artifact_ref_model(ref)
        stored_ref = self._load_stored_ref(ref.artifact_id)
        if stored_ref != ref:
            raise ManifestVerificationError("stored artifact identity mismatch")
        target, _sidecar = self._validated_paths(ref.artifact_id)
        if not target.is_file():
            raise ManifestVerificationError("artifact bytes are missing")
        raw_bytes = target.read_bytes()
        self._verify_raw(raw_bytes, ref)
        return raw_bytes

    @staticmethod
    def _verify_raw(raw_bytes: bytes, ref: ArtifactRef) -> None:
        if len(raw_bytes) != ref.size_bytes:
            raise ManifestVerificationError("stored size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != ref.raw_sha256.value:
            raise ManifestVerificationError("stored raw_sha256 mismatch")

    def _load_stored_ref(self, artifact_id: str) -> ArtifactRef:
        cached = self._refs_by_artifact_id.get(artifact_id)
        if cached is not None:
            return cached
        _target, sidecar = self._validated_paths(artifact_id)
        if not sidecar.is_file():
            raise ManifestVerificationError(f"unknown artifact_id: {artifact_id}")
        stored_ref = artifact_ref_from_json(sidecar.read_bytes())
        self._refs_by_artifact_id[artifact_id] = stored_ref
        return stored_ref

    def _validated_paths(self, artifact_id: str) -> tuple[Path, Path]:
        target = self._object_path(artifact_id)
        sidecar = self._ref_sidecar_path(target)
        self._ensure_within_root(target)
        self._ensure_within_root(target.parent)
        self._ensure_within_root(sidecar)
        return target, sidecar

    def _object_path(self, artifact_id: str) -> Path:
        digest = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()
        return self._artifact_root / digest[0:2] / digest[2:4] / digest

    @staticmethod
    def _ref_sidecar_path(target: Path) -> Path:
        return target.with_suffix(target.suffix + ".ref.jcs")

    def _ensure_within_root(self, target: Path) -> None:
        resolved = target.resolve(strict=False)
        root = self._artifact_root.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise ManifestVerificationError("resolved artifact path escapes artifact_root")

    def _reject_on_disk_identity_mismatch(self, sidecar: Path, ref: ArtifactRef) -> None:
        if not sidecar.is_file():
            return
        stored_ref = artifact_ref_from_json(sidecar.read_bytes())
        if stored_ref != ref:
            raise ManifestVerificationError("artifact_id already identifies a different artifact")

    def _write_ref_sidecar_atomic(self, sidecar: Path, ref: ArtifactRef) -> Path | None:
        payload = artifact_ref_to_json(ref).encode("utf-8")
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=sidecar.parent,
                prefix=".artifact-ref-",
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
