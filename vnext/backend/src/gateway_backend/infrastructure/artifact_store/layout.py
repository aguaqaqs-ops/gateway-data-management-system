"""Explicit artifact roots and ordered cooperative borrows; paths stay in infrastructure."""
from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from _thread import RLock
from dataclasses import dataclass, field
from pathlib import Path

from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.deployment_config import StorageLayoutConfig

ROOT_ORDER = tuple(ArtifactLocation)


def _directory_identity(path: Path) -> tuple[int, int, str]:
    if not path.is_absolute() or path == Path('/') or '..' in path.parts:
        raise ValueError("artifact root must be an absolute non-root directory")
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ValueError("artifact root cannot follow a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or not info.st_mode & 0o222 or not os.access(path, os.W_OK | os.X_OK):
            raise ValueError("artifact root must be writable")
        mount_id = descriptor_mount_id(descriptor)
        return info.st_dev, info.st_ino, mount_id
    finally:
        os.close(descriptor)


def descriptor_mount_id(descriptor: int) -> str:
    return next(line for line in Path(f'/proc/self/fdinfo/{descriptor}').read_text().splitlines()
        if line.startswith('mnt_id:'))


@dataclass(frozen=True)
class ArtifactStoreLayout:
    durable: Path
    canonical: Path
    comparison: Path
    export: Path
    _identities: dict[ArtifactLocation, tuple[int, int, str]] = field(init=False, repr=False, compare=False)
    _borrows: dict[ArtifactLocation, tuple[int, int]] = field(init=False, repr=False, compare=False)
    _mutex: RLock = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        paths = [self.root(location) for location in ROOT_ORDER]
        for index, path in enumerate(paths):
            if not isinstance(path, Path):
                raise ValueError("artifact roots must be Paths")
            for other in paths[index + 1:]:
                if path == other or path in other.parents or other in path.parents:
                    raise ValueError("artifact roots must be distinct and non-nested")
        try:
            identities = {location: _directory_identity(self.root(location)) for location in ROOT_ORDER}
        except (OSError, ValueError, StopIteration):
            raise ValueError('artifact root must be an existing writable directory without symlinks') from None
        object.__setattr__(self, '_identities', identities)
        object.__setattr__(self, '_borrows', {})
        object.__setattr__(self, '_mutex', RLock())

    @classmethod
    def from_config(cls, config: StorageLayoutConfig) -> ArtifactStoreLayout:
        return cls(**{location.value: Path(config.roots[f'be-{location.value}'].path) for location in ROOT_ORDER})

    def root(self, location: ArtifactLocation) -> Path:
        if type(location) is not ArtifactLocation:
            raise ValueError("location must be ArtifactLocation")
        return {ArtifactLocation.DURABLE: self.durable, ArtifactLocation.CANONICAL: self.canonical,
            ArtifactLocation.COMPARISON: self.comparison, ArtifactLocation.EXPORT: self.export}[location]

    def check(self, location: ArtifactLocation) -> None:
        try:
            if _directory_identity(self.root(location)) != self._identities[location]:
                raise ValueError("artifact root identity changed")
        except (OSError, ValueError, StopIteration):
            raise ManifestVerificationError("artifact root unavailable; preflight/restart required") from None

    @contextmanager
    def read_session(self, locations: tuple[ArtifactLocation, ...] = ROOT_ORDER) -> Iterator[None]:
        # A shared FD plus a count per root supports nested users and streaming
        # contexts that enter and close on different HTTP thread-pool threads.
        # Cleanup is nonblocking, so acquiring SH never waits behind a held EX.
        selected = tuple(location for location in ROOT_ORDER if location in locations)
        entered: list[ArtifactLocation] = []
        try:
            with self._mutex:
                for location in selected:
                    self.check(location)
                    current = self._borrows.get(location)
                    if current is None:
                        descriptor = os.open(self.root(location), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_SH)
                            self.check(location)
                        except BaseException:
                            os.close(descriptor)
                            raise
                        self._borrows[location] = (descriptor, 1)
                    else:
                        self._borrows[location] = (current[0], current[1] + 1)
                    entered.append(location)
            yield
        finally:
            with self._mutex:
                for location in reversed(entered):
                    descriptor, count = self._borrows[location]
                    if count == 1:
                        del self._borrows[location]
                        os.close(descriptor)
                    else:
                        self._borrows[location] = (descriptor, count - 1)

    @contextmanager
    def cleanup_session(self, location: ArtifactLocation) -> Iterator[bool]:
        self.check(location)
        with self._mutex:
            if location in self._borrows:
                descriptor = None
            else:
                descriptor = os.open(self.root(location), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.check(location)
                except BlockingIOError:
                    os.close(descriptor)
                    descriptor = None
                except BaseException:
                    os.close(descriptor)
                    raise
        try:
            yield descriptor is not None
        finally:
            if descriptor is not None:
                os.close(descriptor)
