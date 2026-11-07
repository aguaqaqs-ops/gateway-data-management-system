"""Complete tar transport owner: framing, published metadata and bounded lifetime."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.requests import ClientDisconnect

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.bounded_store import CleanupClassification, DeleteDisposition
from gateway_backend.artifacts.bundle_download import prepare_bundle_download
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.tar_stream import TAR_END, TarMember, pax_record_chunks, pax_record_length
from gateway_backend.capabilities.bundle_assembly import (
    BundleAssemblyStatus, BundlePairInput, assemble_bundle,
)
from gateway_backend.capabilities.bundle_assembly.transport import BundleIntegrityError
from gateway_backend.http.bundle_response import BundleStreamingResponse
from gateway_backend.infrastructure.artifact_store import BoundedArtifactStore, LocalArtifactStore
from tests.test_bundle_assembly import _request, _surface_result

pytestmark = pytest.mark.unit

PAX_PATHS = (
    "dir/" * 70 + "rows.parquet",
    "目录/" * 60 + "表.parquet",
    "😀/" * 60 + "表.parquet",
)


def published_bundle(root: Path) -> tuple[LocalArtifactStore, ArtifactRef]:
    store = LocalArtifactStore(root)
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result()),)), source_store=store,
    )
    assert result.status is BundleAssemblyStatus.READY and result.bundle is not None
    return store, result.bundle.manifest_ref


def assert_complete_tar(raw: bytes, *, expected_digest: str | None = None) -> dict[str, object]:
    """Independent stdlib consumer checks every ordinary member against original metadata."""
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = archive.getmembers()
        assert all(member.isfile() and not member.islnk() for member in members)
        assert [member.name for member in members[:2]] == ["manifest.json", "artifact-closure.json"]
        manifest_file = archive.extractfile(members[0])
        closure_file = archive.extractfile(members[1])
        assert manifest_file is not None and closure_file is not None
        manifest = json.loads(manifest_file.read())
        closure = json.loads(closure_file.read())
        assert manifest["closure_entries"] == closure["closure_entries"]
        assert manifest["bundle_digest"] == closure["bundle_digest"]
        if expected_digest is not None:
            assert manifest["bundle_digest"] == expected_digest
        entries = closure["closure_entries"]
        assert [member.name for member in members[2:]] == [entry["logical_path"] for entry in entries]
        for member, entry in zip(members[2:], entries, strict=True):
            file = archive.extractfile(member)
            assert file is not None
            payload = file.read()
            assert len(payload) == member.size == entry["size_bytes"] == entry["artifact_ref"]["size_bytes"]
            assert "sha256:" + hashlib.sha256(payload).hexdigest() == entry["raw_sha256"]
        return manifest


@pytest.mark.parametrize("path", ("rows.parquet", *PAX_PATHS))
@pytest.mark.parametrize("size", (0, 511, 512, 513))
def test_tar_member_length_and_unicode_path_interoperate(path: str, size: int) -> None:
    member = TarMember(path, size)
    payload = b"x" * size
    raw = b"".join((*member.prefix(), payload, *member.suffix(), TAR_END))
    assert len(raw) == member.framed_size + 1024
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        files = archive.getmembers()
        assert len(files) == 1
        file = files[0]
        assert file.name == path and file.isfile()
        assert (file.uid, file.gid, file.mtime, file.mode, file.uname, file.gname) == (0, 0, 0, 0o644, "", "")
        source = archive.extractfile(file)
        assert source is not None and source.read() == payload


@pytest.mark.parametrize(("value", "expected"), (
    ("中", b"12 path=\xe4\xb8\xad\n"),
    ("a" * 90, b"99 path=" + b"a" * 90 + b"\n"),
    ("a" * 91, b"101 path=" + b"a" * 91 + b"\n"),
))
def test_pax_record_has_independent_fixed_byte_vectors(value: str, expected: bytes) -> None:
    raw = b"".join(pax_record_chunks("path", value))
    assert raw == expected
    assert len(raw) == pax_record_length("path", value)
    # Adjacent records remain byte-delimited across Unicode and digit boundaries.
    records = raw + b"12 path=\xe4\xb8\xad\n"
    first_length = int(records.split(b" ", 1)[0])
    assert records[first_length:] == b"12 path=\xe4\xb8\xad\n"


@pytest.mark.parametrize("size", (8**11 - 1, 8**11, 2**53 - 1))
def test_tar_size_preserves_full_artifact_range_without_allocating_payload(size: int) -> None:
    member = TarMember("rows.parquet", size)
    prefix = b"".join(member.prefix())
    if size < 8**11:
        assert len(prefix) == 512
        assert int(prefix[124:136].rstrip(b"\0"), 8) == size
    else:
        assert prefix[156:157] == b"x"
        pax_size = int(prefix[124:136].rstrip(b"\0"), 8)
        body = prefix[512:512 + pax_size]
        assert body == f"{len(body)} size={size}\n".encode("ascii")
        assert prefix[-512 + 124:-512 + 136] == b"00000000000\0"
    assert member.framed_size == len(prefix) + size + (-size) % 512


def test_prepared_bundle_keeps_original_metadata_and_exact_complete_length(tmp_path: Path) -> None:
    store, manifest_ref = published_bundle(tmp_path)
    prepared = prepare_bundle_download(store, manifest_ref.artifact_id)
    raw = b"".join(prepared.stream)
    prepared.close()
    prepared.close()
    assert len(raw) == prepared.content_length
    assert prepared.etag == f'"{prepared.bundle_digest}"'
    assert prepared.filename == f"bundle-{prepared.bundle_digest[7:]}.tar"
    assert_complete_tar(raw, expected_digest=prepared.bundle_digest)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        source = archive.extractfile("manifest.json")
        assert source is not None and source.read() == store.locate(manifest_ref)


@pytest.mark.parametrize("fault", ("missing", "size", "digest", "symlink", "directory"))
def test_preflight_checks_last_member_before_returning_a_stream(tmp_path: Path, fault: str) -> None:
    store, manifest_ref = published_bundle(tmp_path / "artifacts")
    entry = json.loads(store.locate(manifest_ref))["closure_entries"][-1]
    path = store._object_path(entry["artifact_ref"]["artifact_id"])
    original = path.read_bytes()
    path.unlink()
    if fault == "size":
        path.write_bytes(original + b"x")
    elif fault == "digest":
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    elif fault == "symlink":
        other = tmp_path / "ordinary"
        other.write_bytes(original)
        path.symlink_to(other)
    elif fault == "directory":
        path.mkdir()
    error = ArtifactUnavailableError if fault == "missing" else BundleIntegrityError
    with pytest.raises(error):
        prepare_bundle_download(store, manifest_ref.artifact_id)
    # Failed preflight has released the read session even without an iterator.
    with store.cleanup_session() as acquired:
        assert acquired


@pytest.mark.parametrize("consume", (False, True))
def test_unstarted_and_partially_consumed_downloads_release_cleanup_borrow(tmp_path: Path, consume: bool) -> None:
    store, manifest_ref = published_bundle(tmp_path)
    cleaner = BoundedArtifactStore(LocalArtifactStore(tmp_path), unpinned_ttl=timedelta(0))
    prepared = prepare_bundle_download(store, manifest_ref.artifact_id)
    if consume:
        next(prepared.stream)
    assert cleaner.delete_eligible(
        manifest_ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER, now=datetime.now(UTC),
    ) is DeleteDisposition.RETRYABLE_FAILURE
    prepared.close()
    assert cleaner.delete_eligible(
        manifest_ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER, now=datetime.now(UTC),
    ) is DeleteDisposition.DELETED


class CountingStore(LocalArtifactStore):
    active_files = 0
    active_sessions = 0
    max_handles = 0
    max_chunk = 0
    fail_during_send = False

    @contextmanager
    def read_session(self) -> Iterator[None]:
        with super().read_session():
            self.active_sessions += 1
            try:
                yield
            finally:
                self.active_sessions -= 1

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        self.active_files += 1
        self.max_handles = max(self.max_handles, self.active_files + self.active_sessions)
        try:
            for chunk in super().read_exact(ref):
                self.max_chunk = max(self.max_chunk, len(chunk))
                if self.fail_during_send:
                    raise OSError("representative post-header read failure")
                yield chunk
        finally:
            self.active_files -= 1


def test_bounded_read_failure_aborts_tar_and_closes_current_handle(tmp_path: Path) -> None:
    _store, ref = published_bundle(tmp_path)
    store = CountingStore(tmp_path)
    prepared = prepare_bundle_download(store, ref.artifact_id)
    store.fail_during_send = True
    partial: list[bytes] = []
    with pytest.raises(OSError):
        for chunk in prepared.stream:
            partial.append(chunk)
    prepared.close()
    assert len(b"".join(partial)) < prepared.content_length
    assert store.active_files == store.active_sessions == 0
    assert store.max_handles <= 2 and store.max_chunk <= 64 * 1024


@pytest.mark.parametrize("fail_on", ("start", "body"))
def test_response_send_failure_closes_even_unstarted_stream(tmp_path: Path, fail_on: str) -> None:
    store, ref = published_bundle(tmp_path)
    prepared = prepare_bundle_download(store, ref.artifact_id)

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        if message["type"] == f"http.response.{fail_on}":
            raise OSError("client disconnected")

    scope = {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "GET"}
    with pytest.raises((OSError, ClientDisconnect)):
        asyncio.run(BundleStreamingResponse(prepared)(scope, receive, send))  # type: ignore[arg-type]
    with store.cleanup_session() as acquired:
        assert acquired
    assert not any(path.name.startswith(".lock") for path in tmp_path.iterdir())
