"""Complete tar transport owner: framing, published metadata and bounded lifetime."""

from __future__ import annotations

from tests.support.artifact_layout import open_test_store, make_artifact_layout

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import asyncio
import hashlib
import io
import json
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from starlette.requests import ClientDisconnect

from gateway_backend.artifacts import ArtifactRef, put_with_built_ref
from gateway_backend.artifacts.bounded_store import CleanupClassification, DeleteDisposition
from gateway_backend.application.bundle_download import prepare_bundle_download
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.tar_stream import TAR_END, TarMember, pax_record_chunks, pax_record_length
from gateway_backend.capabilities.bundle_assembly import (
    BundleArtifactBinding, BundleArtifactClosure, BundleArtifactKind,
    BundleAssemblyStatus, BundlePairInput, assemble_bundle,
)
from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
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
    store = open_test_store(root)
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
        return cast(dict[str, object], manifest)


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


def _publish_document(store: LocalArtifactStore, document: dict[str, object]) -> ArtifactRef:
    semantic = {key: value for key, value in document.items() if key not in {
        "bundle_digest", "closure_manifest_digest", "closure_entries",
    }}
    document["bundle_digest"] = raw_blob_digest(canonicalize_json_value(semantic)).value
    document["closure_manifest_digest"] = raw_blob_digest(canonicalize_json_value(document["closure"])).value
    raw = canonicalize_json_value(document)
    try:
        metadata = read_bundle_transport_metadata(raw)
    except BundleIntegrityError:
        pass  # Malformed manifest probes must fail before any closure lookup.
    else:
        store.put(metadata.expected_closure_bytes, metadata.closure_ref)
    return put_with_built_ref(
        store, raw, artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", "bundle-transport-test-manifest-" + raw_blob_digest(raw).value[7:]),
        media_type="application/vnd.gateway.comparison-bundle.manifest+json",
    )


def test_final_closure_same_ref_at_two_paths_sends_two_ordinary_members(tmp_path: Path) -> None:
    store, ref = published_bundle(tmp_path)
    document = json.loads(store.locate(ref))
    original = document["closure_entries"][0]
    extra = {**original, "logical_path": "shared/second-copy", "kind": "OTHER", "pair_id": None}
    document["closure_entries"].append(extra)
    document["closure"]["entries"].append({
        **document["closure"]["entries"][0],
        "logical_path": extra["logical_path"], "kind": "OTHER", "pair_id": None,
    })
    document["closure_entries"].sort(key=lambda item: item["logical_path"])
    document["closure"]["entries"].sort(key=lambda item: item["logical_path"])
    ref = _publish_document(store, document)
    prepared = prepare_bundle_download(store, ref.artifact_id)
    raw = b"".join(prepared.stream)
    assert_complete_tar(raw)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        first = archive.extractfile(original["logical_path"])
        second = archive.extractfile(extra["logical_path"])
        assert first is not None and second is not None
        assert first.read() == second.read()


@pytest.mark.parametrize("kind", (BundleArtifactKind.PROJECTION, BundleArtifactKind.DIAGNOSTICS, BundleArtifactKind.OTHER))
def test_business_json_payload_is_not_subject_to_metadata_read_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: BundleArtifactKind,
) -> None:
    import gateway_backend.application.bundle_download as downloads
    store = open_test_store(tmp_path)
    data = b'"' + b"x" * (64 * 1024 + 1) + b'"'
    source = put_with_built_ref(store, data, artifact_id="a1:durable:2fce63a0bc18d79ecd1ce65e765a09e5b7944e80193c7091c61fc9149985cf4f", media_type="application/json")
    result = assemble_bundle(_request(
        (BundlePairInput("pair", 0, 1, _surface_result()),),
        shared=BundleArtifactClosure((BundleArtifactBinding(source, "shared/data.json", kind, shared=True),)),
    ), source_store=store)
    assert result.bundle is not None
    # Keep the actual payload small; a reduced metadata budget exposes any
    # accidental whole-payload metadata reader without allocating a large input.
    monkeypatch.setattr(downloads, "MAX_BUNDLE_MANIFEST_JSON_BYTES", source.size_bytes - 1)
    prepared = prepare_bundle_download(store, result.bundle.manifest_ref.artifact_id)
    assert_complete_tar(b"".join(prepared.stream))


@pytest.mark.parametrize("fault", ("absolute", "traversal", "reserved", "reserved-child", "duplicate", "parent-child", "ref-size", "entry-size", "closure-semantic"))
def test_published_metadata_path_and_reference_contradictions_fail_preflight(tmp_path: Path, fault: str) -> None:
    store, ref = published_bundle(tmp_path)
    document = json.loads(store.locate(ref))
    entry = document["closure_entries"][0]
    semantic = document["closure"]["entries"][0]
    paths = {"absolute": "/escape", "traversal": "pairs/../escape", "reserved": "manifest.json", "reserved-child": "manifest.json/child"}
    if fault in paths:
        entry["logical_path"] = semantic["logical_path"] = paths[fault]
    elif fault == "duplicate":
        document["closure_entries"].append(dict(entry))
        document["closure"]["entries"].append(dict(semantic))
    elif fault == "parent-child":
        entry["logical_path"] = semantic["logical_path"] = "shared/a"
        document["closure_entries"].append({**entry, "logical_path": "shared/a/child", "kind": "OTHER", "pair_id": None})
        document["closure"]["entries"].append({**semantic, "logical_path": "shared/a/child", "kind": "OTHER", "pair_id": None})
    elif fault == "ref-size":
        entry["artifact_ref"]["size_bytes"] += 1
    elif fault == "entry-size":
        entry["size_bytes"] += 1
    else:
        semantic["integrity"]["size_bytes"] += 1
    ref = _publish_document(store, document)
    with pytest.raises(BundleIntegrityError):
        prepare_bundle_download(store, ref.artifact_id)


@pytest.mark.parametrize("fault", ("missing", "size", "digest", "symlink", "directory"))
def test_preflight_checks_last_member_before_returning_a_stream(tmp_path: Path, fault: str) -> None:
    store, manifest_ref = published_bundle(tmp_path / "artifacts")
    entry = json.loads(store.locate(manifest_ref))["closure_entries"][-1]
    path = store.payload_path(entry["artifact_ref"]["artifact_id"])
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
    with store.cleanup_session("a1:export:" + "0" * 64) as acquired:
        assert acquired


@pytest.mark.parametrize("consume", (False, True))
def test_unstarted_and_partially_consumed_downloads_release_cleanup_borrow(tmp_path: Path, consume: bool) -> None:
    store, manifest_ref = published_bundle(tmp_path)
    cleaner = BoundedArtifactStore(open_test_store(tmp_path), unpinned_ttl=timedelta(0))
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
    store = CountingStore(make_artifact_layout(tmp_path), staging_max_bytes=4 * 1024**3)
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
    with store.cleanup_session("a1:export:" + "0" * 64) as acquired:
        assert acquired
    assert not any(path.name.startswith(".lock") for path in tmp_path.iterdir())


@pytest.mark.parametrize("termination", ("disconnect", "cancel"))
def test_asgi_disconnect_and_task_cancellation_release_read_session(tmp_path: Path, termination: str) -> None:
    store, ref = published_bundle(tmp_path)
    prepared = prepare_bundle_download(store, ref.artifact_id)

    async def scenario() -> None:
        entered = asyncio.Event()
        wait_forever = asyncio.Event()

        async def receive() -> dict[str, object]:
            await entered.wait()
            if termination == "disconnect":
                return {"type": "http.disconnect"}
            await wait_forever.wait()
            raise AssertionError("unreachable")

        async def send(message: dict[str, object]) -> None:
            if message["type"] == "http.response.body":
                entered.set()
                await wait_forever.wait()

        scope = {"type": "http", "asgi": {"spec_version": "2.3"}, "method": "GET"}
        task = asyncio.create_task(BundleStreamingResponse(prepared)(scope, receive, send))  # type: ignore[arg-type]
        if termination == "cancel":
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    asyncio.run(scenario())
    with store.cleanup_session("a1:export:" + "0" * 64) as acquired:
        assert acquired
