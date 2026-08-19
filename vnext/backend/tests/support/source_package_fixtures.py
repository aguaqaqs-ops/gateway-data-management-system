"""Thin helpers for SourcePackage staging fixtures. Not a parser."""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "snapshot-materialization"
)


def load_bytes(relative_path: str) -> bytes:
    return (FIXTURE_ROOT / relative_path).read_bytes()


def load_expected(relative_path: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("expected.json must be an object")
    return payload


def pack_tar_gz(members: dict[str, bytes], *, mtime: int = 0) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = mtime
            info.type = tarfile.REGTYPE
            archive.addfile(info, io.BytesIO(payload))
    return gzip.compress(tar_buffer.getvalue(), mtime=mtime)


def pack_tar_gz_infos(infos: list[tuple[tarfile.TarInfo, bytes | None]], *, mtime: int = 0) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for info, payload in infos:
            info.mtime = mtime
            if payload is None:
                archive.addfile(info)
            else:
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    return gzip.compress(tar_buffer.getvalue(), mtime=mtime)


def pack_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def pack_zip_symlink(name: str, target: bytes = b"elsewhere") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        archive.writestr(info, target)
    return buffer.getvalue()
