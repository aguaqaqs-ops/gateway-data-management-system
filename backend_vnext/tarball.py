from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tarfile


@dataclass(frozen=True, slots=True)
class TarballMetadata:
    path: Path
    package_format: str
    size_bytes: int
    sha256: str
    entries: tuple[str, ...]


def create_stable_tarball(
    *,
    source_root: Path,
    tar_path: Path,
) -> TarballMetadata:
    if not isinstance(source_root, Path):
        raise TypeError("source_root must be a Path")
    if not isinstance(tar_path, Path):
        raise TypeError("tar_path must be a Path")
    if not source_root.is_dir():
        raise ValueError("source_root must be an existing directory")

    source_root = source_root.resolve()
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_tar_path = tar_path.resolve()
    entries = _bundle_entries(source_root=source_root, tar_path=resolved_tar_path)

    with tarfile.open(resolved_tar_path, mode="w") as archive:
        for entry in entries:
            file_path = source_root.joinpath(*entry.split("/"))
            data = file_path.read_bytes()
            info = tarfile.TarInfo(entry)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, _BytesReader(data))

    tar_bytes = resolved_tar_path.read_bytes()
    return TarballMetadata(
        path=resolved_tar_path,
        package_format="tar",
        size_bytes=len(tar_bytes),
        sha256=hashlib.sha256(tar_bytes).hexdigest(),
        entries=entries,
    )


def _bundle_entries(*, source_root: Path, tar_path: Path) -> tuple[str, ...]:
    entries: list[str] = []
    for path in source_root.rglob("*"):
        resolved_path = path.resolve()
        if resolved_path == tar_path:
            continue
        if not resolved_path.is_file():
            continue
        if resolved_path.is_symlink():
            raise ValueError("symlink entries are not supported in stable tarballs")
        relative = resolved_path.relative_to(source_root).as_posix()
        if relative.startswith("../") or relative.startswith("/"):
            raise ValueError("tar entry must stay under source_root")
        entries.append(relative)
    return tuple(sorted(entries))


class _BytesReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


__all__ = ["TarballMetadata", "create_stable_tarball"]
