"""Bounded supplement guards with owning bundle bytes and actual HTTP consumers."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import os
import socket
import subprocess
import traceback
from typing import Any

import httpx
import pytest

from benchmarks import comparison_correctness_acceptance as a
from benchmarks import comparison_correctness_number1_supplement as n
from benchmarks import comparison_correctness_history_supplement as h
from benchmarks import real_dump_journey as journey
from benchmarks.real_dump_journey import JourneyFailure
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.tar_stream import TAR_END, TarMember
from gateway_backend.capabilities.bundle_assembly import (
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    assemble_bundle,
    read_bundle_transport_metadata,
)
from gateway_backend.http.schemas.submit import SubmissionResponse
from tests.support import compose_gate_harness as harness
from tests.support.surface_navigation import seed_navigation
from tests.test_bundle_assembly import _request, _surface_result
from tests.test_history_supplement_fixture_permissions import _runtime_fixture, _gateway_data

pytestmark = pytest.mark.unit
BEFORE_FAULTS = ("none", "state", "operations", "protection", "pair")
AFTER_FAULTS = ("http", "result", "protection", "operations")
FILE_FAULTS = ("escape", "symlink", "digest", "extra", "duplicate")
REPLAY_FAULTS = ("none", "failure", "head", "source", "files")
ACTOR_FAULTS = ("none", "same-actor", "scope", "permission", "duplicate")
PREPARATION_FAULTS = (
    "environment",
    "prebuilt",
    "containers",
    "volumes",
    "networks",
    "mapping",
    "actor",
    "evidence",
    "lock",
    "registered-fixture",
    "clone-before-ownership",
    "clone-after-ownership",
)


@pytest.fixture
def source(tmp_path: Path) -> n.Source:
    store = seed_navigation(InMemoryArtifactStore())
    pairs = tuple(
        BundlePairInput(pair, i, i + 1, _surface_result())
        for i, pair in enumerate(("baseline_to_initial", "initial_to_modified"))
    )
    result = assemble_bundle(
        _request(
            pairs,
            profile=BundleProfile.MULTI_PAIR,
            inputs=tuple(
                BundleInput(i, role, role) for i, role in enumerate(("left", "middle", "right"))
            ),
        ),
        source_store=store,
    )
    assert result.status is BundleAssemblyStatus.READY and result.bundle is not None
    raw = store.locate(result.bundle.manifest_ref)
    metadata = read_bundle_transport_metadata(raw)
    directory, fixture, inputs = (tmp_path / name for name in ("source", "fixture", "inputs"))
    for folder in (directory, fixture, inputs):
        folder.mkdir()
    tar = directory / "preview.tar"
    # Match the production transport's exact framing. stdlib tar writers add
    # record padding after EOF, which the owning complete consumer rejects.
    with tar.open("wb") as archive:
        for path, payload in (
            ("manifest.json", raw),
            ("artifact-closure.json", metadata.expected_closure_bytes),
            *((e.logical_path, store.locate(e.artifact_ref)) for e in metadata.entries),
        ):
            member = TarMember(path, len(payload))
            for block in member.prefix():
                archive.write(block)
            archive.write(payload)
            for block in member.suffix():
                archive.write(block)
        archive.write(TAR_END)
    submission = SubmissionResponse(
        submission_id="submission",
        submit_attempt_id="attempt",
        workspace_id="workspace",
        upload_revision_id="upload",
        preview_result_id="preview",
        generation=1,
        repository_id="repository",
        based_on_baseline_node_id=harness.BASELINE_NODE_ID,
        business_baseline_commit_id="before",
        repository_commit_id="after",
        canonical_business_digest="sha256:" + "1" * 64,
        canonicalization_manifest_digest="sha256:" + "2" * 64,
        created_by="s2b-realdata-submitter",
        created_at=datetime(2026, 11, 14, tzinfo=UTC),
    )
    protected = build_artifact_id(ArtifactLocation.EXPORT, "terminal-proof", "protected")
    proof = n.SourceProof(
        source_head="a" * 40,
        source_run=str(directory),
        source_root=str(fixture),
        input_root=str(inputs),
        logs=h.tree_manifest(directory),
        fixture=h.tree_manifest(fixture),
        inputs=[],
        repository=h.Repository(
            repository_id=submission.repository_id, empty_initial_commit="before"
        ),
        submission=submission,
        ready=a._Probe(
            protected_artifact_ids=[protected], ready_artifact_ids=[protected], audits={}
        ),
        review=n.ReviewState(
            submission_id="submission",
            status="PENDING",
            version=0,
            sequence=0,
            event_kinds=["SUBMISSION_FINALIZED"],
            event_sequences=[0],
            operations=[
                n.Operation(
                    operation_id="preview-op", job_kind="backend-vnext/preview", status="SUCCEEDED"
                ),
                n.Operation(
                    operation_id="submit-op", job_kind="backend-vnext/submit", status="SUCCEEDED"
                ),
            ],
        ),
        device_key=harness.DEVICE_KEY,
        project_id=harness.PROJECT_ID,
    )
    return n.Source(proof, json.loads(raw), tar)


def _result(source: n.Source) -> dict[str, Any]:
    return {
        "submission_id": source.proof.submission.submission_id,
        "preview_result_id": "preview",
        "bundle_digest": source.manifest["bundle_digest"],
        "default_pair_id": "initial_to_modified",
        "input_completeness": "FULL",
        "pairs": [
            {
                "pair_id": p["pair_id"],
                "comparison_digest": p["comparison_digest"],
                "surface_digest": p["surface_digest"],
                "risk_digest": p["risk_evaluation_digest"],
            }
            for p in source.manifest["pairs"]
        ],
    }


def _terminal_state(source: n.Source) -> n.ReviewState:
    return source.proof.review.model_copy(
        update={
            "status": "REJECTED",
            "version": 1,
            "sequence": 1,
            "event_kinds": ["SUBMISSION_FINALIZED", "REJECTED"],
            "event_sequences": [0, 1],
        }
    )


def _exercise(
    source: n.Source, monkeypatch: pytest.MonkeyPatch, output: Path, fault: str
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    rejected = False

    def state(_env: object, _output: object, name: str, _submission: object) -> n.ReviewState:
        current = _terminal_state(source) if name == "state-after" else source.proof.review
        if fault == "state" and name == "state-before":
            return current.model_copy(update={"version": 1})
        if (fault == "operations" and name == "state-before-reject") or (
            fault == "after-operations" and name == "state-after"
        ):
            return current.model_copy(update={"operations": []})
        return current

    def probe(*_args: object, **_kwargs: object) -> a._Probe:
        if fault == "protection" or fault == "after-protection" and rejected:
            return source.proof.ready.model_copy(update={"protected_artifact_ids": []})
        return source.proof.ready

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal rejected
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/submissions/submission/review-events"
            assert json.loads(request.content) == {
                "expected_review_version": 0,
                "action": "REJECT",
                "reason": "bounded correctness acceptance retention check",
            }
            assert request.headers["idempotency-key"] == "supplement-reject"
            rejected = True
            if fault == "after-http":
                return httpx.Response(500)
            return httpx.Response(
                201,
                json={
                    "submission_id": "submission",
                    "status": "REJECTED",
                    "review_version": 1,
                    "event": {
                        "sequence": 1,
                        "event_kind": "REJECTED",
                        "from_status": "PENDING",
                        "to_status": "REJECTED",
                        "actor_id": "reviewer",
                        "occurred_at": "2026-11-14T00:00:00Z",
                    },
                },
            )
        if request.url.path.endswith("/bundle"):
            raw = source.tar.read_bytes()
            return httpx.Response(
                200,
                content=raw,
                headers={
                    "content-type": "application/x-tar",
                    "content-length": str(len(raw)),
                    "etag": '"' + source.manifest["bundle_digest"] + '"',
                },
            )
        result = _result(source)
        if fault == "pair":
            result["pairs"][0]["surface_digest"] = "sha256:" + "0" * 64
        if fault == "after-result" and rejected:
            result["bundle_digest"] = "sha256:" + "0" * 64
        return httpx.Response(200, json=result)

    monkeypatch.setattr(n, "runtime_state", state)
    monkeypatch.setattr(a, "_probe", probe)
    with httpx.Client(transport=httpx.MockTransport(transport), base_url="http://test") as client:
        if fault == "none":
            n.complete_review(
                client, source, {}, output, "supplement", reviewer_actor_id="reviewer"
            )
        else:
            with pytest.raises(JourneyFailure):
                n.complete_review(
                    client, source, {}, output, "supplement", reviewer_actor_id="reviewer"
                )
    return requests


@pytest.mark.parametrize("fault", BEFORE_FAULTS)
def test_terminal_checks_preconditions_before_single_reject_and_validates_real_bundle(
    source: n.Source,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    before = h.tree_manifest(Path(source.proof.source_run))
    requests = _exercise(source, monkeypatch, output, fault)
    posts = [request for request in requests if request.method == "POST"]
    assert len(posts) == int(fault == "none")
    assert all(request.method == "POST" or "/result" in request.url.path for request in requests)
    assert h.tree_manifest(Path(source.proof.source_run)) == before
    if fault == "none":
        assert (
            (output / "review-before.tar").read_bytes()
            == (output / "review-rejected.tar").read_bytes()
            == source.tar.read_bytes()
        )


@pytest.mark.parametrize("fault", AFTER_FAULTS)
def test_terminal_failure_is_not_retried_after_the_only_post(
    source: n.Source,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    requests = _exercise(source, monkeypatch, output, "after-" + fault)
    assert len([request for request in requests if request.method == "POST"]) == 1


@pytest.mark.parametrize("fault", FILE_FAULTS)
def test_source_manifest_rejects_changed_escaped_or_ambiguous_files(
    tmp_path: Path, fault: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    original = source / "data"
    original.write_bytes(b"source")
    record = h.FileRecord(path="data", bytes=6, sha256=a._file_sha(original))
    records = [record]
    (source / "files.json").write_bytes(h.FILES.dump_json(records))
    n.check_files(source)
    if fault == "escape":
        records = [record.model_copy(update={"path": "../source/data"})]
    elif fault == "symlink":
        target = tmp_path / "target"
        original.rename(target)
        original.symlink_to(target)
    elif fault == "digest":
        original.write_bytes(b"change")
    elif fault == "extra":
        (source / "extra").write_bytes(b"extra")
    else:
        records.append(record)
    (source / "files.json").write_bytes(h.FILES.dump_json(records))
    with pytest.raises(JourneyFailure):
        n.check_files(source)


def test_replay_calls_all_existing_result_assertions_and_preserves_sources(
    source: n.Source,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(n, "load_source", lambda *_args: source)
    monkeypatch.setattr(socket, "gethostname", lambda: "gw-dms-test-05")
    monkeypatch.setattr(n, "input_records", lambda *_args: source.proof.inputs)
    monkeypatch.setattr(a, "_git", lambda *_args: "b" * 40)
    calls = []

    def check(*args: object) -> None:
        calls.append(args)

    monkeypatch.setattr(a, "_number1", check)
    output = tmp_path / "replay"
    output.mkdir()
    n.run_replay(
        Path(source.proof.input_root),
        output,
        Path(source.proof.source_run),
        Path(source.proof.source_root),
        "a" * 40,
    )
    assert calls == [
        (source.manifest, source.tar, source.proof.ready, output, Path(source.proof.input_root))
    ]
    complete = n.ReplayComplete.model_validate_json((output / "complete.json").read_bytes())
    assert complete.source == source.proof and complete.head == "b" * 40
    with pytest.raises(JourneyFailure, match="overlaps"):
        n.run_replay(
            Path(source.proof.input_root),
            Path(source.proof.source_run),
            Path(source.proof.source_run),
            Path(source.proof.source_root),
            "a" * 40,
        )


@pytest.mark.parametrize("fault", REPLAY_FAULTS)
def test_terminal_requires_successful_integrity_checked_same_head_replay(
    source: n.Source,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    path = tmp_path / "replay"
    path.mkdir()
    head = "b" * 40
    a._write(
        path / "start.json",
        h.SourceStart(
            session="replay",
            purpose="comparison correctness number1-replay",
            started_at="2026-11-14T00:00:00Z",
            hostname="gw-dms-test-05",
            worktree="test",
            head=head,
        ).model_dump(),
    )
    a._write(
        path / "finish.json",
        h.SourceFinish(
            head=head, ended_at="2026-11-14T00:00:01Z", exit_code=1 if fault == "failure" else 0
        ).model_dump(),
    )
    complete = n.ReplayComplete(
        kind="number1-result-replay",
        head="c" * 40 if fault == "head" else head,
        source=source.proof.model_copy(update={"source_head": "d" * 40})
        if fault == "source"
        else source.proof,
    )
    a._write(path / "complete.json", complete.model_dump(mode="json"))
    records = [
        h.FileRecord(path=p.name, bytes=p.stat().st_size, sha256=a._file_sha(p))
        for p in sorted(path.iterdir())
    ]
    (path / "files.json").write_bytes(h.FILES.dump_json(records))
    monkeypatch.setattr(a, "_git", lambda *_args: head)
    if fault == "files":
        (path / "finish.json").write_bytes(b"changed")
    if fault == "none":
        n.require_replay(path, source)
    else:
        with pytest.raises(JourneyFailure):
            n.require_replay(path, source)


@pytest.mark.parametrize("fault", ACTOR_FAULTS)
def test_actor_binding_is_distinct_scoped_authorized_and_never_emits_tokens(
    source: n.Source,
    tmp_path: Path,
    fault: str,
) -> None:
    submitter = n.Actor(
        token=harness.SESSION_TOKEN,
        actor_id=source.proof.submission.created_by,
        gateway_device_external_key=source.proof.device_key,
        business_project_id=source.proof.project_id,
        permissions=["workspace_read", "review_submission"],
    )
    reviewer = submitter.model_copy(
        update={"token": journey.ARCHIVER_TOKEN, "actor_id": "reviewer"}
    )
    if fault == "same-actor":
        reviewer = reviewer.model_copy(update={"actor_id": submitter.actor_id})
    elif fault == "scope":
        reviewer = reviewer.model_copy(update={"business_project_id": "other"})
    elif fault == "permission":
        reviewer = reviewer.model_copy(update={"permissions": ["workspace_read"]})
    sessions = [submitter, reviewer, *([reviewer] if fault == "duplicate" else [])]
    path = tmp_path / "sessions.json"
    path.write_bytes(n.Sessions(sessions=sessions).model_dump_json().encode())
    if fault == "none":
        bindings = n.actor_bindings({"GATEWAY_BACKEND_SESSION_FILE": str(path)}, source)
        assert all("token" not in item for item in bindings.values())
    else:
        with pytest.raises(JourneyFailure):
            n.actor_bindings({"GATEWAY_BACKEND_SESSION_FILE": str(path)}, source)


def test_terminal_prepare_only_clones_into_owned_fixture_with_original_numeric_permissions(
    source: n.Source,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _runtime_fixture(tmp_path, monkeypatch) as (_env, original):
        manifest, _lock, database = _gateway_data(original)
        before = h.tree_manifest(original)
        proof = source.proof.model_copy(update={"source_root": str(original), "fixture": before})
        restored = n.Source(proof, source.manifest, source.tar)
        env = journey._compose_environment(tmp_path / "new-secrets", "terminal-new-fixture")
        output = tmp_path / "new-output"
        output.mkdir()
        clone = n.prepare_clone(env, restored, output, tmp_path / "replay")
        try:
            assert clone != original and h.tree_manifest(original) == before
            assert h.tree_manifest(clone / "roots") == h.tree_manifest(original / "roots")
            for path in (manifest, database):
                copied = clone / path.relative_to(original)
                assert (copied.stat().st_uid, copied.stat().st_gid) == (100, 101)
                assert copied.stat().st_mode & 0o777 == path.stat().st_mode & 0o777
            assert str(original) not in Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).read_text()
        finally:
            harness._runtime_fixtures.pop(env["COMPOSE_PROJECT_NAME"], None)
    assert os.geteuid() == 0  # The real gateway identity vector must not be skipped.


@pytest.mark.parametrize("fault", PREPARATION_FAULTS)
def test_terminal_preparation_failure_cleans_only_own_secrets_and_keeps_original_error(
    source: n.Source,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    output = tmp_path / "terminal"
    output.mkdir()
    replay = tmp_path / "replay"
    replay.mkdir()
    monkeypatch.setattr(socket, "gethostname", lambda: "gw-dms-test-05")
    monkeypatch.setattr(n, "load_source", lambda *_args: source)
    monkeypatch.setattr(n, "require_replay", lambda *_args: None)
    monkeypatch.setattr(n, "input_records", lambda *_args: source.proof.inputs)
    monkeypatch.setattr(harness, "COMPOSE_GATE_LOCK_PATH", tmp_path / "compose.lock")
    original_environment = journey._compose_environment
    project = "correctness-prepare-failure-terminal"
    foreign = tmp_path / "foreign-resource"
    foreign.write_text("existing project must survive")
    teardowns: list[str] = []

    def environment(secret: Path, name: str) -> dict[str, str]:
        assert secret.is_dir()
        if fault == "environment":
            (secret / "partial").write_text("new test secret")
            raise JourneyFailure("original environment failure")
        env = original_environment(secret, name)
        if fault == "prebuilt":
            env["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"
        return env

    def command(*args: str) -> subprocess.CompletedProcess[str]:
        kind = {"ps": "containers", "volume": "volumes", "network": "networks"}.get(args[1])
        return subprocess.CompletedProcess(args, 0, "foreign-id\n" if kind == fault else "", "")

    def fail_mapping(*_args: object, **_kwargs: object) -> None:
        raise JourneyFailure("original mapping failure")

    def fail_actor(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise JourneyFailure("original actor failure")

    original_write = a._write

    def write(path: Path, value: object) -> None:
        if fault == "evidence" and path.name == "actors.json":
            raise JourneyFailure("original evidence failure")
        original_write(path, value)

    def clone(env: dict[str, str], *_args: object) -> Path:
        if fault == "clone-after-ownership":
            own = tmp_path / "own-fixture"
            own.mkdir()
            harness._runtime_fixtures[env["COMPOSE_PROJECT_NAME"]] = (own, "test-owned")
        raise JourneyFailure("original clone preparation failure")

    def finish(
        env: dict[str, str], path: Path, state: a._RunState, primary: BaseException | None
    ) -> None:
        assert fault == "clone-after-ownership", "must not teardown an unowned project"
        teardowns.append(env["COMPOSE_PROJECT_NAME"])
        assert primary is not None
        (path / "business-exception.log").write_text("".join(traceback.format_exception(primary)))
        harness._runtime_fixtures.pop(env["COMPOSE_PROJECT_NAME"])
        state.cleanup_complete = True

    def no_post(*_args: object, **_kwargs: object) -> None:
        pytest.fail("preparation failure must not enter the HTTP phase")

    monkeypatch.setattr(journey, "_compose_environment", environment)
    monkeypatch.setattr(a, "_command", command)
    monkeypatch.setattr(a, "_write", write)
    monkeypatch.setattr(a, "_finish_stack", finish)
    monkeypatch.setattr(n, "prepare_clone", clone)
    monkeypatch.setattr(n, "complete_review", no_post)
    if fault == "mapping":
        monkeypatch.setattr(n, "write_container_readable_text", fail_mapping)
    if fault == "actor":
        monkeypatch.setattr(n, "actor_bindings", fail_actor)
    if fault == "lock":

        def fail_lock() -> None:
            raise JourneyFailure("original lock failure")

        monkeypatch.setattr(harness, "acquire_compose_gate_lock", fail_lock)
    if fault == "registered-fixture":
        monkeypatch.setitem(harness._runtime_fixtures, project, (foreign, "foreign-owner"))
    state = a._RunState()
    with pytest.raises(JourneyFailure) as raised:
        n.run_terminal(
            Path(source.proof.input_root),
            output,
            "prepare-failure",
            state,
            source_run=Path(source.proof.source_run),
            source_root=Path(source.proof.source_root),
            source_head=source.proof.source_head,
            replay_run=replay,
        )
    assert str(raised.value) in (output / "business-exception.log").read_text()
    assert not (output / "secrets").exists() and state.cleanup_complete
    assert harness._gate_lock_file is None
    assert teardowns == ([project] if fault == "clone-after-ownership" else [])
    assert foreign.read_text() == "existing project must survive"
    if fault == "registered-fixture":
        assert harness._runtime_fixtures[project] == (foreign, "foreign-owner")


def test_terminal_does_not_clean_an_existing_secret_directory(
    source: n.Source,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    secret = output / "secrets"
    secret.mkdir(parents=True)
    (secret / "foreign").write_text("keep")
    replay = tmp_path / "replay"
    replay.mkdir()
    monkeypatch.setattr(socket, "gethostname", lambda: "gw-dms-test-05")
    monkeypatch.setattr(n, "load_source", lambda *_args: source)
    monkeypatch.setattr(n, "require_replay", lambda *_args: None)
    with pytest.raises(FileExistsError):
        n.run_terminal(
            Path(source.proof.input_root),
            output,
            "existing-secret",
            a._RunState(),
            source_run=Path(source.proof.source_run),
            source_root=Path(source.proof.source_root),
            source_head=source.proof.source_head,
            replay_run=replay,
        )
    assert (secret / "foreign").read_text() == "keep"
