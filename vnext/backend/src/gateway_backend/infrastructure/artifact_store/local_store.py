"""Multi-root immutable objects, directory publication and cooperative read lifetimes."""
from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
from gateway_shared_kernel import CanonicalEncodingError

from gateway_backend.artifacts.location import ArtifactLocation, parse_artifact_id
from gateway_backend.artifacts.serialize import artifact_ref_from_json, artifact_ref_to_json
from gateway_backend.artifacts.store import ArtifactFileSourcePort, ArtifactRepairBusyError, ArtifactUnavailableError, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.validate import validate_artifact_ref_model
from gateway_backend.infrastructure.artifact_store.atomic_publish import check_publication_support, fsync_directory, rename_noreplace
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout, descriptor_mount_id
from gateway_backend.infrastructure.artifact_store.scratch import ScratchFile

_CHUNK = 64 * 1024
_MAX_REF_BYTES = 4096


class LocalArtifactStore:
    def __init__(self, layout: ArtifactStoreLayout, *, staging_max_bytes: int) -> None:
        if not isinstance(layout, ArtifactStoreLayout):
            raise ValueError('artifact store requires an explicit four-root layout')
        if type(staging_max_bytes) is not int or staging_max_bytes <= 0:
            raise ValueError('staging_max_bytes must be positive')
        self.layout = layout
        self.staging_max_bytes = staging_max_bytes

    def check_publication_support(self) -> None:
        with self.read_session():
            for location in ArtifactLocation:
                check_publication_support(self.layout.root(location))

    @contextmanager
    def read_session(self) -> Iterator[None]:
        with self.layout.read_session():
            yield

    @contextmanager
    def cleanup_session(self, artifact_id: str) -> Iterator[bool]:
        with self.layout.cleanup_session(parse_artifact_id(artifact_id)) as acquired:
            yield acquired

    def object_directory(self, artifact_id: str) -> Path:
        """Infrastructure-only resolver. Never search a second root."""
        location = parse_artifact_id(artifact_id)
        self.layout.check(location)
        root = self.layout.root(location)
        digest = hashlib.sha256(artifact_id.encode('utf-8')).hexdigest()
        directory = root / 'objects' / digest[:2] / digest[2:4] / digest
        self._check_path(root, directory)
        return directory

    def payload_path(self, artifact_id: str) -> Path:
        directory = self.object_directory(artifact_id)
        path = directory / 'payload'
        self._check_path(self.layout.root(parse_artifact_id(artifact_id)), path)
        return path

    @staticmethod
    def _check_path(root: Path, path: Path) -> None:
        if not path.is_relative_to(root):
            raise ManifestVerificationError('artifact path escapes root')
        device = root.stat().st_dev
        root_fd = os.open(root, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            mount_id = descriptor_mount_id(root_fd)
        finally:
            os.close(root_fd)
        current = root
        for name in path.relative_to(root).parts:
            current = current / name
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or info.st_dev != device:
                raise ManifestVerificationError('artifact path cannot follow a symlink or child mount')
            descriptor = os.open(current, os.O_PATH | os.O_NOFOLLOW)
            try:
                if descriptor_mount_id(descriptor) != mount_id:
                    raise ManifestVerificationError('artifact path cannot follow a child mount')
            finally:
                os.close(descriptor)

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        return self.put_chunks((raw_bytes,), ref)

    def put_from_path(
        self, source: ArtifactFileSourcePort, ref: ArtifactRef, *, checkpoint: Callable[[], None], byte_limit: int,
    ) -> ArtifactRef:
        if not isinstance(source, ScratchFile):
            raise ValueError('artifact source must be an owned scratch file')
        try:
            with source.open_read() as handle:
                def chunks() -> Iterator[bytes]:
                    while chunk := handle.read(_CHUNK):
                        yield chunk
                return self.put_chunks(chunks(), ref, checkpoint=checkpoint, byte_limit=byte_limit)
        except (InterruptedError, TimeoutError, ManifestVerificationError):
            raise
        except (OSError, ValueError):
            raise ManifestVerificationError('artifact scratch source is not available') from None

    def put_chunks(
        self, chunks: Iterable[bytes], ref: ArtifactRef, *,
        checkpoint: Callable[[], None] | None = None, byte_limit: int | None = None,
    ) -> ArtifactRef:
        validate_artifact_ref_model(ref)
        if byte_limit is not None and (type(byte_limit) is not int or byte_limit <= 0):
            raise ValueError('byte_limit must be positive')
        limit = min(self.staging_max_bytes, self.staging_max_bytes if byte_limit is None else byte_limit)
        if ref.size_bytes > limit:
            raise ManifestVerificationError('artifact exceeds staging byte limit')
        try:
            with self.layout.read_session((parse_artifact_id(ref.artifact_id),)):
                with self._stage(chunks, ref, checkpoint) as staging:
                    target = self.object_directory(ref.artifact_id)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._sync_ancestors(target.parent, self.layout.root(parse_artifact_id(ref.artifact_id)))
                    try:
                        rename_noreplace(staging, target)
                    except FileExistsError:
                        self._verify_existing(ref, checkpoint)
                    fsync_directory(target.parent)
                    fsync_directory(staging.parent)
            return ref
        except (InterruptedError, TimeoutError, ManifestVerificationError):
            raise
        except (OSError, ValueError, CanonicalEncodingError):
            raise ManifestVerificationError('artifact write failed') from None

    def restore_canonical_from_exact_commit(
        self, raw_bytes: bytes, ref: ArtifactRef, *, checkpoint: Callable[[], None],
    ) -> ArtifactRef:
        """Only the exact-commit canonical owner may use this repair port.

        Stage outside EX; no caller may retain SH or a read handle here. A crash
        while replacing an invalid derived object is retried from the same commit.
        Protection records are never removed.
        """
        if parse_artifact_id(ref.artifact_id) is not ArtifactLocation.CANONICAL:
            raise ValueError('exact-commit repair only accepts canonical objects')
        validate_artifact_ref_model(ref)
        if ref.size_bytes > self.staging_max_bytes:
            raise ManifestVerificationError('artifact exceeds staging byte limit')
        staged = self._stage((raw_bytes,), ref, checkpoint)
        staging: Path | None = None
        try:
            with self.layout.read_session((ArtifactLocation.CANONICAL,)):
                staging = staged.__enter__()
                target = self.object_directory(ref.artifact_id)
                target.parent.mkdir(parents=True, exist_ok=True)
                self._sync_ancestors(target.parent, self.layout.canonical)
                try:
                    rename_noreplace(staging, target)
                except FileExistsError:
                    try:
                        self._verify_existing(ref, checkpoint)
                    except (InterruptedError, TimeoutError):
                        raise
                    except (ManifestVerificationError, OSError, CanonicalEncodingError, ValueError):
                        pass  # Only a damaged existing derived object requires EX.
                    else:
                        fsync_directory(target.parent)
                        fsync_directory(staging.parent)
                        return ref
                else:
                    fsync_directory(target.parent)
                    fsync_directory(staging.parent)
                    return ref
            # Writer flock retains staging, but all of this call's SH has closed.
            with self.layout.cleanup_session(ArtifactLocation.CANONICAL) as acquired:
                if not acquired:
                    raise ArtifactRepairBusyError('canonical repair busy; retry after readers close')
                checkpoint()
                target = self.object_directory(ref.artifact_id)
                try:
                    self._verify_existing(ref, checkpoint)
                except (InterruptedError, TimeoutError):
                    raise
                except (ManifestVerificationError, OSError, CanonicalEncodingError, ValueError):
                    if target.exists():
                        if not target.is_dir() or set(path.name for path in target.iterdir()) - {'payload', 'ref.jcs'}:
                            raise ManifestVerificationError('canonical repair requires a known object shape')
                        for path in target.iterdir():
                            self._check_path(self.layout.canonical, path)
                            if not stat.S_ISREG(path.lstat().st_mode):
                                raise ManifestVerificationError('canonical repair requires ordinary files')
                            path.unlink()
                        target.rmdir()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._sync_ancestors(target.parent, self.layout.canonical)
                    rename_noreplace(staging, target)
                fsync_directory(target.parent)
                fsync_directory(staging.parent)
                checkpoint()
            return ref
        finally:
            if staging is not None:
                staged.__exit__(None, None, None)

    @contextmanager
    def _stage(
        self, chunks: Iterable[bytes], ref: ArtifactRef, checkpoint: Callable[[], None] | None,
    ) -> Iterator[Path]:
        root = self.layout.root(parse_artifact_id(ref.artifact_id))
        parent = root / '.staging'
        self._check_path(root, parent)
        parent.mkdir(exist_ok=True)
        fsync_directory(root)
        staging = Path(tempfile.mkdtemp(prefix='object-', dir=parent))
        descriptor = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            total = 0
            hasher = hashlib.sha256()
            with (staging / 'payload').open('xb') as handle:
                for chunk in chunks:
                    if checkpoint is not None:
                        checkpoint()
                    if type(chunk) is not bytes:
                        raise ManifestVerificationError('stream chunks must be bytes')
                    total += len(chunk)
                    if total > ref.size_bytes:
                        raise ManifestVerificationError('stream exceeds declared_size')
                    for offset in range(0, len(chunk), _CHUNK):
                        if checkpoint is not None:
                            checkpoint()
                        block = memoryview(chunk)[offset:offset + _CHUNK]
                        hasher.update(block)
                        handle.write(block)
                    del chunk
                if total != ref.size_bytes:
                    raise ManifestVerificationError('stream shorter than declared_size')
                if 'sha256:' + hasher.hexdigest() != ref.raw_sha256.value:
                    raise ManifestVerificationError('declared_raw_sha256 mismatch')
                handle.flush()
                os.fsync(handle.fileno())
            if checkpoint is not None:
                checkpoint()
            with (staging / 'ref.jcs').open('xb') as handle:
                handle.write(artifact_ref_to_json(ref).encode('utf-8'))
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(staging)
            if checkpoint is not None:
                checkpoint()
            yield staging
        finally:
            os.close(descriptor)
            if staging.exists():
                shutil.rmtree(staging)

    @staticmethod
    def _sync_ancestors(path: Path, root: Path) -> None:
        while path != root:
            fsync_directory(path)
            path = path.parent
        fsync_directory(root)

    def _verify_existing(self, ref: ArtifactRef, checkpoint: Callable[[], None] | None) -> None:
        if self._stored_ref(ref.artifact_id) != ref:
            raise ManifestVerificationError('artifact_id already identifies a different artifact')
        for _chunk in self._read_exact(ref):
            if checkpoint is not None:
                checkpoint()

    def get_ref(self, artifact_id: str) -> ArtifactRef:
        try:
            with self.layout.read_session((parse_artifact_id(artifact_id),)):
                return self._stored_ref(artifact_id)
        except ManifestVerificationError:
            raise
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.EACCES, errno.EPERM}:
                raise ArtifactUnavailableError('artifact ref is not available') from None
            raise ManifestVerificationError('artifact ref lookup failed') from None
        except (ValueError, CanonicalEncodingError):
            raise ManifestVerificationError('artifact ref lookup failed') from None

    def _stored_ref(self, artifact_id: str) -> ArtifactRef:
        directory = self.object_directory(artifact_id)
        path = directory / 'ref.jcs'
        self._check_path(self.layout.root(parse_artifact_id(artifact_id)), path)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if directory.exists():
                raise ManifestVerificationError('incomplete stored artifact directory') from None
            raise ArtifactUnavailableError('artifact ref is not available') from None
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_REF_BYTES:
                raise ManifestVerificationError('invalid stored artifact ref')
            ref = artifact_ref_from_json(handle.read(_MAX_REF_BYTES + 1))
        if ref.artifact_id != artifact_id:
            raise ManifestVerificationError('stored artifact identity mismatch')
        return ref

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        try:
            validate_artifact_ref_model(ref)
            with self.layout.read_session((parse_artifact_id(ref.artifact_id),)):
                yield from self._read_exact(ref)
        except ManifestVerificationError:
            raise
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.EACCES, errno.EPERM}:
                raise ArtifactUnavailableError('artifact is not available') from None
            raise ManifestVerificationError('artifact read failed') from None
        except (ValueError, CanonicalEncodingError):
            raise ManifestVerificationError('artifact read failed') from None

    def _read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        if self._stored_ref(ref.artifact_id) != ref:
            raise ManifestVerificationError('stored artifact identity mismatch')
        path = self.payload_path(ref.artifact_id)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != ref.size_bytes:
                raise ManifestVerificationError('stored size_bytes mismatch')
            hasher = hashlib.sha256()
            total = 0
            while chunk := handle.read(_CHUNK):
                total += len(chunk)
                if total > ref.size_bytes:
                    raise ManifestVerificationError('stored size_bytes mismatch')
                hasher.update(chunk)
                yield chunk
            if total != ref.size_bytes or 'sha256:' + hasher.hexdigest() != ref.raw_sha256.value:
                raise ManifestVerificationError('stored raw_sha256 mismatch')

    def locate(self, ref: ArtifactRef) -> bytes:
        return b''.join(self.read_exact(ref))

    @contextmanager
    def open_buffer(self, ref: ArtifactRef, *, checkpoint: Callable[[], None] | None = None) -> Iterator[pa.Buffer]:
        validate_artifact_ref_model(ref)
        with self.layout.read_session((parse_artifact_id(ref.artifact_id),)):
            source = None
            buffer = None
            try:
                if self._stored_ref(ref.artifact_id) != ref:
                    raise ManifestVerificationError('stored artifact identity mismatch')
                target = self.payload_path(ref.artifact_id)
                if not stat.S_ISREG(target.lstat().st_mode):
                    raise ManifestVerificationError('artifact mapping requires a regular file')
                source = pa.memory_map(str(target), 'r')
                if source.size() != ref.size_bytes:
                    raise ManifestVerificationError('stored size_bytes mismatch')
                buffer = source.read_buffer(ref.size_bytes)
                hasher = hashlib.sha256()
                view = memoryview(buffer)
                try:
                    for offset in range(0, len(view), _CHUNK):
                        if checkpoint is not None:
                            checkpoint()
                        hasher.update(view[offset:offset + _CHUNK])
                    if checkpoint is not None:
                        checkpoint()
                finally:
                    view.release()
                if 'sha256:' + hasher.hexdigest() != ref.raw_sha256.value:
                    raise ManifestVerificationError('stored raw_sha256 mismatch')
                source.close()
            except BaseException as exc:
                buffer = None
                if source is not None:
                    source.close()
                if isinstance(exc, (InterruptedError, TimeoutError, ManifestVerificationError)):
                    raise
                if isinstance(exc, (OSError, ValueError, pa.ArrowException)):
                    raise ManifestVerificationError('artifact mapping failed') from exc
                raise
            try:
                assert buffer is not None
                yield buffer
            finally:
                buffer = None
                if source is not None:
                    source.close()

    def published_at(self, ref: ArtifactRef) -> datetime:
        path = self.payload_path(ref.artifact_id)
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    def delete_object(self, ref: ArtifactRef) -> bool:
        """Caller holds this root EX and the protection transaction."""
        directory = self.object_directory(ref.artifact_id)
        if not directory.exists():
            return False
        names = set(path.name for path in directory.iterdir())
        if names - {'payload', 'ref.jcs'}:
            raise ManifestVerificationError('invalid cleanup object shape')
        if names and ('ref.jcs' not in names or self._stored_ref(ref.artifact_id) != ref):
            raise ManifestVerificationError('invalid cleanup object identity')
        for path in directory.iterdir():
            self._check_path(self.layout.root(parse_artifact_id(ref.artifact_id)), path)
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ManifestVerificationError('cleanup requires ordinary object files')
        # The identity file is removed last. A failed unlink/rmdir leaves a known
        # ref-only or empty directory that a later attempt can safely finish.
        (directory / 'payload').unlink(missing_ok=True)
        (directory / 'ref.jcs').unlink(missing_ok=True)
        directory.rmdir()
        fsync_directory(directory.parent)
        return True
