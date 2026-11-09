"""Complete tar consumer for real journeys and container smoke checks.

Downloads and extracted artifacts live in caller-owned temporary storage. Nothing
is unpacked by a caller-controlled tar pathname and no row payload is reported.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, cast

import httpx

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.capabilities.bundle_assembly.contracts import BundleArtifactKind
from gateway_backend.capabilities.bundle_assembly.transport import (
    BUNDLE_REFERENCE_METADATA_KINDS, read_bundle_transport_metadata, validate_bundle_member_metadata,
)
from gateway_backend.capabilities.comparison.artifacts import open_records_closure


class _DownloadedArtifactStore:
    def __init__(self, paths: Mapping[ArtifactRef, Path]) -> None:
        self.paths = paths

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        raise NotImplementedError("download consumer is read-only")

    def locate(self, ref: ArtifactRef) -> bytes:
        return self.paths[ref].read_bytes()


def verify_bundle_tar(source: BinaryIO, *, total_bytes: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify original metadata, every ordinary member, refs and owner logical records digests."""
    source.seek(-1024, 2)
    if source.read(1024) != bytes(1024):
        raise BundleIntegrityError("bundle tar has no complete termination blocks")
    source.seek(0)
    with tempfile.TemporaryDirectory(prefix="bundle-verify-") as temporary, tarfile.open(fileobj=source, mode="r:") as archive:
        members = archive.getmembers()
        if archive.offset + 1024 != total_bytes:
            raise BundleIntegrityError("bundle tar contains unexpected trailing bytes")
        if len(members) < 2 or [member.name for member in members[:2]] != ["manifest.json", "artifact-closure.json"]:
            raise BundleIntegrityError("bundle tar metadata order is invalid")
        if any(not member.isfile() or member.islnk() or member.issym() for member in members):
            raise BundleIntegrityError("bundle tar members must be ordinary files")
        if any(member.size > 16 * 1024 * 1024 for member in members[:2]):
            raise BundleIntegrityError("bundle metadata exceeds its JSON budget")
        manifest_file, closure_file = (archive.extractfile(member) for member in members[:2])
        assert manifest_file is not None and closure_file is not None
        manifest_raw, closure_raw = manifest_file.read(), closure_file.read()
        metadata = read_bundle_transport_metadata(manifest_raw)
        if closure_raw != metadata.expected_closure_bytes:
            raise BundleIntegrityError("bundle original closure disagrees with its manifest")
        if [member.name for member in members[2:]] != [entry.logical_path for entry in metadata.entries]:
            raise BundleIntegrityError("bundle tar members do not match the ordered final closure")
        paths: dict[ArtifactRef, Path] = {}
        for index, (member, entry) in enumerate(zip(members[2:], metadata.entries, strict=True)):
            if member.size != entry.size_bytes:
                raise BundleIntegrityError("bundle member size mismatch")
            path = Path(temporary) / str(index)
            file = archive.extractfile(member)
            assert file is not None
            digest = hashlib.sha256()
            count = 0
            with path.open("wb") as target:
                while chunk := file.read(64 * 1024):
                    digest.update(chunk)
                    count += len(chunk)
                    target.write(chunk)
            if count != entry.size_bytes or "sha256:" + digest.hexdigest() != entry.raw_sha256.value:
                raise BundleIntegrityError("bundle member raw digest mismatch")
            paths[entry.artifact_ref] = path
        # Verify all reference metadata and the records owner's logical (rather
        # than compressed Parquet) digest using the production public validator.
        refs = set(paths)
        store = _DownloadedArtifactStore(paths)
        record_count = 0
        record_closures = 0
        metadata_count = 0
        for entry in metadata.entries:
            if "json" in entry.artifact_ref.media_type.casefold() and entry.kind in BUNDLE_REFERENCE_METADATA_KINDS:
                if entry.size_bytes > 16 * 1024 * 1024:
                    raise BundleIntegrityError("bundle reference metadata exceeds its JSON budget")
                validate_bundle_member_metadata(
                    entry, paths[entry.artifact_ref].read_bytes(), refs=refs, pair_digests=metadata.pair_digests,
                )
                metadata_count += 1
            if entry.kind is BundleArtifactKind.RECORDS_CLOSURE:
                closure = open_records_closure(store, entry.artifact_ref)
                record_count += sum(item.record_count for item in closure.records)
                record_closures += 1
        manifest = cast(dict[str, Any], json.loads(manifest_raw))
        metrics = {
            "actual_bytes": total_bytes,
            "ordinary_member_count": len(members),
            "closure_member_count": len(metadata.entries),
            "verified_reference_metadata_count": metadata_count,
            "verified_records_closure_count": record_closures,
            "verified_logical_record_count": record_count,
            "bundle_digest": metadata.bundle_digest,
        }
        return manifest, metrics


def download_bundle_tar(
    client: httpx.Client, url: str, *, headers: Mapping[str, str] | None = None,
    destination: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    actual = 0
    raw_digest = hashlib.sha256()
    with tempfile.TemporaryFile("w+b") as source:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code != 200:
                raise BundleIntegrityError(f"bundle download HTTP {response.status_code}")
            if response.headers.get("content-type") != "application/x-tar":
                raise BundleIntegrityError("bundle response is not application/x-tar")
            declared = response.headers.get("content-length", "")
            if not declared.isascii() or not declared.isdecimal():
                raise BundleIntegrityError("bundle Content-Length is missing or invalid")
            expected = int(declared)
            etag = response.headers.get("etag")
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                source.write(chunk)
                raw_digest.update(chunk)
                actual += len(chunk)
            finished = time.monotonic()
        if actual != expected or actual < 2048:
            raise BundleIntegrityError("complete bundle length disagrees with Content-Length")
        manifest, metrics = verify_bundle_tar(source, total_bytes=actual)
        if etag != f'"{manifest["bundle_digest"]}"':
            raise BundleIntegrityError("bundle ETag disagrees with the published digest")
        if destination is not None:
            source.seek(0)
            with destination.open("xb") as target:
                shutil.copyfileobj(source, target, length=64 * 1024)
        metrics["raw_tar_sha256"] = raw_digest.hexdigest()
        metrics["content_length"] = expected
        metrics["etag"] = etag
        metrics["saved_tar_path"] = None if destination is None else str(destination)
        metrics["get_to_complete_read_seconds"] = round(finished - started, 3)
        metrics["timing_policy"] = "report_only; GET start through complete response read"
        return manifest, metrics
