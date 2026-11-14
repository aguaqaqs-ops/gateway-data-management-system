"""Opt-in result replay and derived-clone terminal proof; no journey retries."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import socket
import sys
from typing import Any, Literal

import httpx
from pydantic import ConfigDict, TypeAdapter

from benchmarks import comparison_correctness_acceptance as a
from benchmarks import comparison_correctness_history_supplement as h
from benchmarks import real_dump_journey as journey
from benchmarks.bundle_tar import verify_bundle_tar
from gateway_backend.deployment_config import StorageLayoutConfig
from gateway_backend.http.schemas.review import ReviewAppliedResponse, SubmissionResultResponse
from gateway_backend.http.schemas.submit import SubmissionResponse
from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_from_row
from tests.support import compose_gate_harness as harness
from tests.support.container_input_files import write_container_readable_text


class DerivedInput(a._Document):
    derived_package: Literal["data1", "data2"]
    bytes: int
    sha256: str
    members: list[str]


class Transfer(a._Document):
    actual_bytes: int
    ordinary_member_count: int
    closure_member_count: int
    verified_reference_metadata_count: int
    verified_records_closure_count: int
    verified_logical_record_count: int
    bundle_digest: str
    logical_paths: list[str]
    manifest_fields: list[str]
    raw_tar_sha256: str
    content_length: int
    etag: str
    saved_tar_path: str
    get_to_complete_read_seconds: float
    timing_policy: str


class Operation(a._Document):
    operation_id: str
    job_kind: str
    status: str


class ReviewState(a._Document):
    submission_id: str
    status: str
    version: int
    sequence: int
    event_kinds: list[str]
    event_sequences: list[int]
    operations: list[Operation]


class Actor(a._Document):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    token: str
    actor_id: str
    gateway_device_external_key: str
    business_project_id: str
    permissions: list[str]


class Sessions(a._Document):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    sessions: list[Actor]


class SourceProof(a._Document):
    source_head: str
    source_run: str
    source_root: str
    input_root: str
    logs: list[h.TreeEntry]
    fixture: list[h.TreeEntry]
    inputs: list[h.FileRecord]
    repository: h.Repository
    submission: SubmissionResponse
    ready: a._Probe
    review: ReviewState
    device_key: str
    project_id: str


class ReplayComplete(a._Document):
    kind: Literal["number1-result-replay"]
    head: str
    source: SourceProof


INPUTS = TypeAdapter(list[h.FileRecord | DerivedInput])


@dataclass(frozen=True)
class Source:
    proof: SourceProof
    manifest: dict[str, Any]
    tar: Path


def check_files(directory: Path) -> None:
    records = h.FILES.validate_json((directory / "files.json").read_bytes(), strict=True)
    names = {record.path for record in records}
    a._check(len(names) == len(records) and bool(names),
             "source evidence manifest is empty or ambiguous")
    a._check({str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
             == names | {"files.json"}, "source evidence manifest is incomplete")
    for record in records:
        relative = Path(record.path)
        a._check(not relative.is_absolute() and ".." not in relative.parts, "source evidence path escapes")
        path = directory / relative
        a._check(not path.is_symlink() and path.resolve().is_relative_to(directory)
                 and path.is_file() and path.stat().st_size == record.bytes
                 and a._file_sha(path) == record.sha256, "source evidence integrity mismatch")


def input_records(root: Path) -> list[h.FileRecord]:
    expected = dict(a.NUMBER1_FILES)
    for side in ("data1", "data2"):
        marker = a._number1_marker(root / side)
        expected[str(marker.relative_to(root))] = a.EMPTY_MARKER_SHA
    a._check({str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} == set(expected),
             "number1 input file set differs")
    records = []
    for relative, digest in sorted(expected.items()):
        path = root / relative
        a._check(not path.is_symlink() and path.resolve().is_relative_to(root)
                 and path.stat().st_mode & 0o222 == 0 and a._file_sha(path) == digest,
                 "number1 input is changed, redirected or writable")
        records.append(h.FileRecord(path=str(path), bytes=path.stat().st_size, sha256=digest))
    return records


def separate(output: Path, *sources: Path) -> None:
    for source in sources:
        a._check(not output.is_relative_to(source) and not source.is_relative_to(output),
                 "supplement output overlaps a source")


def check_unchanged(proof: SourceProof) -> None:
    a._check(h.tree_manifest(Path(proof.source_run)) == proof.logs
             and h.tree_manifest(Path(proof.source_root)) == proof.fixture
             and input_records(Path(proof.input_root)) == proof.inputs, "supplement source changed")


def check_review_state(state: ReviewState, expected: ReviewState, *, rejected: bool) -> None:
    a._check(state.submission_id == expected.submission_id and state.operations == expected.operations,
             "supplement submission or operation identity changed")
    a._check((state.status, state.version, state.sequence, state.event_kinds, state.event_sequences)
             == (("REJECTED", 1, 1, ["SUBMISSION_FINALIZED", "REJECTED"], [0, 1]) if rejected else
                 ("PENDING", 0, 0, ["SUBMISSION_FINALIZED"], [0])), "supplement review state differs")


def load_source(input_root: Path, source_run: Path, source_root: Path, source_head: str) -> Source:
    a._check(re.fullmatch(r"[0-9a-f]{40}", source_head) is not None, "full source HEAD required")
    source_run, source_root = source_run.resolve(strict=True), source_root.resolve(strict=True)
    check_files(source_run)
    start = h.SourceStart.model_validate_json((source_run / "start.json").read_bytes())
    finish = h.SourceFinish.model_validate_json((source_run / "finish.json").read_bytes())
    a._check(start.head == finish.head == source_head and finish.exit_code == 1
             and start.hostname == "gw-dms-test-05" and start.purpose == "comparison correctness number1",
             "source number1 run identity differs")
    a._check((source_run / "business-exception.log").read_text().rstrip().endswith(
        "JourneyFailure: configuration comparison key mismatch"), "source failure is outside this supplement")
    for path in ("vnext/backend/src", "vnext/rust", "vnext/repository_service", "vnext/repository_client",
                 "vnext/repository_contracts", "vnext/shared_kernel", "vnext/deploy", "vnext/scripts",
                 "vnext/backend/Dockerfile", "vnext/backend/uv.lock", "vnext/backend/pyproject.toml",
                 "vnext/backend/.python-version", "vnext/backend/Dockerfile.dependency-base",
                 "vnext/backend/benchmarks/real_dump_journey.py",
                 "vnext/backend/benchmarks/bundle_tar.py", "vnext/backend/benchmarks/comparison_correctness_history_supplement.py",
                 "vnext/backend/tests/support/compose_gate_harness.py"):
        a._check(a._git("rev-parse", source_head + ":" + path) == a._git("rev-parse", "HEAD:" + path),
                 "source product or runtime composition differs")
    owner = h.FixtureOwner.model_validate_json((source_root / ".gateway-runtime-fixture-owner.json").read_bytes())
    info = source_root.stat()
    a._check(owner.directory == str(source_root) and owner.device == info.st_dev and owner.inode == info.st_ino
             and owner.schema_version == 1 and owner.owner.startswith("correctness-" + start.session + "-number1-"),
             "source fixture identity differs")
    inputs = input_records(input_root)
    original_inputs = INPUTS.validate_json((source_run / "inputs.json").read_bytes(), strict=True)
    a._check(sorted((item for item in original_inputs if isinstance(item, h.FileRecord)), key=lambda item: item.path)
             == inputs and {item.derived_package for item in original_inputs if isinstance(item, DerivedInput)}
             == {"data1", "data2"}, "source input provenance differs")
    repository = h.Repository.model_validate_json((source_run / "repository.json").read_bytes())
    submission = SubmissionResponse.model_validate_json((source_run / "submission.json").read_bytes(), strict=True)
    ready = a._Probe.model_validate_json((source_run / "ready-before.json").read_bytes())
    a._check(repository.repository_id == submission.repository_id
             and repository.empty_initial_commit == submission.business_baseline_commit_id
             and submission.based_on_baseline_node_id == harness.BASELINE_NODE_ID,
             "source repository or committed submission differs")
    tar = source_run / "preview.tar"
    with tar.open("rb") as stream:
        manifest, metrics = verify_bundle_tar(stream, total_bytes=tar.stat().st_size)
    for name in ("preview", "review-0", "review-1"):
        transfer = Transfer.model_validate_json((source_run / (name + "-transfer.json")).read_bytes())
        actual = source_run / (name + ".tar")
        a._check(a._file_sha(actual) == transfer.raw_tar_sha256 == a._file_sha(tar)
                 and actual.stat().st_size == transfer.actual_bytes == transfer.content_length
                 and transfer.saved_tar_path == str(actual)
                 and transfer.etag == '"' + transfer.bundle_digest + '"', "source bundle transfer differs")
        for key, value in metrics.items():
            a._check(transfer.model_dump()[key] == value, "source verified bundle metrics differ")
    with h._connection(source_root) as connection:
        row = connection.execute("SELECT * FROM preview_result_records WHERE preview_result_id=?",
                                 (submission.preview_result_id,)).fetchone()
        a._check(row is not None, "source accepted Preview is missing")
        preview = preview_result_from_row(dict(row))
        a._check(preview.repository_id == submission.repository_id and preview.workspace_id == submission.workspace_id
                 and preview.upload_revision_id == submission.upload_revision_id and preview.generation == submission.generation
                 and preview.business_baseline_commit_id == submission.business_baseline_commit_id
                 and preview.digests.bundle_digest == manifest["bundle_digest"], "source Preview binding differs")
        a._check([p.pair_id for p in preview.comparison_pairs] == ["baseline_to_initial", "initial_to_modified"],
                 "source Preview is not FULL")
        for pair, expected in zip(preview.comparison_pairs, manifest["pairs"], strict=True):
            a._check((pair.pair_id, pair.comparison_digest, pair.risk_digest, pair.surface_digest)
                     == (expected["pair_id"], expected["comparison_digest"], expected["risk_evaluation_digest"],
                         expected["surface_digest"]), "source Preview pair tuple differs")
        row = connection.execute("SELECT * FROM submission_records WHERE submission_id=?", (submission.submission_id,)).fetchone()
        a._check(row is not None and all(row[name] == getattr(submission, name) for name in (
            "submission_id", "workspace_id", "preview_result_id", "repository_id", "upload_revision_id",
            "business_baseline_commit_id", "repository_commit_id", "created_by")), "source durable submission differs")
        workspace = connection.execute("SELECT * FROM workspace_records WHERE workspace_id=?", (submission.workspace_id,)).fetchone()
        a._check(workspace is not None and workspace["owner_actor_id"] == submission.created_by,
                 "source submitting actor differs")
        operations = [Operation.model_validate(dict(row), strict=True) for row in connection.execute(
            "SELECT operation_id,job_kind,status FROM operation_records ORDER BY operation_id")]
        a._check(len(operations) == 2 and {op.job_kind for op in operations}
                 == {"backend-vnext/preview", "backend-vnext/submit"}
                 and all(op.status == "SUCCEEDED" for op in operations), "source operations differ")
        projection = connection.execute("SELECT * FROM review_projection_records WHERE submission_id=?", (submission.submission_id,)).fetchone()
        a._check(projection is not None, "source review projection is missing")
        state = ReviewState(submission_id=submission.submission_id, status=projection["status"],
            version=projection["optimistic_version"], sequence=projection["latest_sequence"],
            event_kinds=[r[0] for r in connection.execute("SELECT event_kind FROM review_event_records WHERE submission_id=? ORDER BY sequence",
                                                       (submission.submission_id,))],
            event_sequences=[r[0] for r in connection.execute("SELECT sequence FROM review_event_records WHERE submission_id=? ORDER BY sequence",
                                                           (submission.submission_id,))], operations=operations)
        check_review_state(state, state, rejected=False)
        held = sorted(r[0] for r in connection.execute("SELECT artifact_id FROM artifact_protection_intents WHERE owner_kind=? AND owner_id=?",
                                                      ("submission-review", submission.submission_id)))
        a._check(held == ready.protected_artifact_ids and bool(ready.ready_artifact_ids)
                 and set(ready.ready_artifact_ids) <= set(held),
                 "source submission protection differs")
        device, project = workspace["gateway_device_external_key"], workspace["business_project_id"]
    proof = SourceProof(source_head=source_head, source_run=str(source_run), source_root=str(source_root),
        input_root=str(input_root), logs=h.tree_manifest(source_run), fixture=h.tree_manifest(source_root),
        inputs=inputs, repository=repository, submission=submission, ready=ready, review=state, device_key=device, project_id=project)
    return Source(proof, manifest, tar)


def run_replay(input_root: Path, output: Path, source_run: Path, source_root: Path, source_head: str) -> None:
    a._check(socket.gethostname() == "gw-dms-test-05", "number1 supplement must remain on source node05")
    separate(output, source_run.resolve(), source_root.resolve())
    source = load_source(input_root, source_run, source_root, source_head)
    a._write(output / "source.json", source.proof.model_dump(mode="json"))
    try:
        a._number1(source.manifest, source.tar, source.proof.ready, output, input_root)
        a._write(output / "complete.json", ReplayComplete(kind="number1-result-replay", head=a._git("rev-parse", "HEAD"),
                                                          source=source.proof).model_dump(mode="json"))
    finally:
        check_unchanged(source.proof)


def require_replay(path: Path, source: Source) -> None:
    check_files(path)
    finish = h.SourceFinish.model_validate_json((path / "finish.json").read_bytes())
    start = h.SourceStart.model_validate_json((path / "start.json").read_bytes())
    complete = ReplayComplete.model_validate_json((path / "complete.json").read_bytes(), strict=True)
    a._check(finish.exit_code == 0 and start.head == finish.head == complete.head == a._git("rev-parse", "HEAD")
             and start.hostname == "gw-dms-test-05" and start.purpose == "comparison correctness number1-replay"
             and complete.source == source.proof, "successful same-HEAD result replay is required")


def check_result(result: SubmissionResultResponse, source: Source) -> None:
    a._check(result.submission_id == source.proof.submission.submission_id
             and result.preview_result_id == source.proof.submission.preview_result_id
             and result.bundle_digest == source.manifest["bundle_digest"] and result.input_completeness == "FULL"
             and result.default_pair_id == "initial_to_modified", "restored review result differs")
    a._check([pair.pair_id for pair in result.pairs] == ["baseline_to_initial", "initial_to_modified"],
             "restored review pair set differs")
    for pair, expected in zip(result.pairs, source.manifest["pairs"], strict=True):
        a._check((pair.comparison_digest, pair.surface_digest, pair.risk_digest)
                 == (expected["comparison_digest"], expected["surface_digest"], expected["risk_evaluation_digest"]),
                 "restored review pair tuple differs")


_STATE_PROBE = '''
import json,sqlite3,sys
with sqlite3.connect('file:/var/lib/gateway/be-metadata/control.sqlite3?mode=ro',uri=True) as c:
 c.row_factory=sqlite3.Row
 p=c.execute('SELECT * FROM review_projection_records WHERE submission_id=?',(sys.argv[1],)).fetchone()
 if p is None: raise RuntimeError('missing review projection')
 print(json.dumps(dict(submission_id=p['submission_id'],status=p['status'],version=p['optimistic_version'],sequence=p['latest_sequence'],
  event_kinds=[r[0] for r in c.execute('SELECT event_kind FROM review_event_records WHERE submission_id=? ORDER BY sequence',(sys.argv[1],))],
  event_sequences=[r[0] for r in c.execute('SELECT sequence FROM review_event_records WHERE submission_id=? ORDER BY sequence',(sys.argv[1],))],
  operations=[dict(r) for r in c.execute('SELECT operation_id,job_kind,status FROM operation_records ORDER BY operation_id')])))
'''


def runtime_state(env: dict[str, str], output: Path, name: str, submission_id: str) -> ReviewState:
    result = a._logged_compose(env, output, name, "exec", "-T", "backend", "python", "-c", _STATE_PROBE, submission_id)
    a._check(result.returncode == 0, "restored review state is unavailable")
    return ReviewState.model_validate_json(result.stdout)


def actor_bindings(env: dict[str, str], source: Source) -> dict[str, Any]:
    sessions = Sessions.model_validate_json(Path(env["GATEWAY_BACKEND_SESSION_FILE"]).read_bytes())
    submitters = [s for s in sessions.sessions if s.token == harness.SESSION_TOKEN]
    reviewers = [s for s in sessions.sessions if s.token == journey.ARCHIVER_TOKEN]
    a._check(len(submitters) == len(reviewers) == 1, "supplement actor credentials are ambiguous")
    submitter, reviewer = submitters[0], reviewers[0]
    a._check(submitter.actor_id == source.proof.submission.created_by and reviewer.actor_id != submitter.actor_id
             and all(s.gateway_device_external_key == source.proof.device_key and s.business_project_id == source.proof.project_id
                     for s in (submitter, reviewer)) and {"workspace_read", "review_submission"} <= set(reviewer.permissions),
             "supplement actor authorization differs")
    return {role: actor.model_dump(exclude={"token"}) for role, actor in (("submitter", submitter), ("reviewer", reviewer))}


def prepare_clone(env: dict[str, str], source: Source, output: Path, replay_run: Path) -> Path:
    source_root, source_run = Path(source.proof.source_root), Path(source.proof.source_run)
    harness.prepare_runtime_config(env)
    clone = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).parent
    original_config = StorageLayoutConfig.from_bytes((source_root / "storage-layout.json").read_bytes())
    config = StorageLayoutConfig.from_bytes((clone / "storage-layout.json").read_bytes())
    a._check(set(original_config.roots) == set(config.roots)
             and all(Path(item.source).resolve() == (clone / "roots" / slot).resolve() for slot, item in config.roots.items())
             and all(Path(item.source).resolve() == (source_root / "roots" / slot).resolve() for slot, item in original_config.roots.items()),
             "terminal storage includes an external root")
    h.clone_roots(source_root / "roots", clone / "roots")
    override = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).read_text()
    a._check(str(source_root) not in override and str(source_run) not in override and str(replay_run) not in override,
             "terminal Compose mounts a source")
    a._write(output / "clone.json", {"root": str(clone), "derived_from": str(source_root),
        "owner_sha256": a._file_sha(clone / ".gateway-runtime-fixture-owner.json"),
        "storage_sha256": a._file_sha(clone / "storage-layout.json"), "original_entry_still_failed": True,
        "original_review_still_pending": True})
    return clone


def complete_review(client: httpx.Client, source: Source, env: dict[str, str], output: Path, session: str,
                    *, reviewer_actor_id: str) -> None:
    submission = source.proof.submission
    check_review_state(runtime_state(env, output, "state-before", submission.submission_id), source.proof.review, rejected=False)
    before = a._probe(env, submission.preview_result_id, submission.submission_id, output, "probe-before")
    a._check(before == source.proof.ready, "restored READY/audit/protection differs")
    result = a._read_review(client, submission.submission_id)
    check_result(result, source)
    manifest, _tar = a._download(client, f"/v1/submissions/{submission.submission_id}/result/bundle", output, "review-before")
    a._check(manifest == source.manifest, "restored review bundle differs")
    check_review_state(runtime_state(env, output, "state-before-reject", submission.submission_id), source.proof.review, rejected=False)
    response = client.post(f"/v1/submissions/{submission.submission_id}/review-events",
        headers=harness.compose_auth_headers(token=journey.ARCHIVER_TOKEN, idempotency_key=session + "-reject"),
        json={"expected_review_version": 0, "action": "REJECT", "reason": "bounded correctness acceptance retention check"})
    a._check(response.status_code in (200, 201), "terminal rejection failed")
    applied = ReviewAppliedResponse.model_validate_json(response.content, strict=True)
    a._check(applied.submission_id == submission.submission_id and applied.status == "REJECTED" and applied.review_version == 1
             and applied.event.actor_id == reviewer_actor_id != submission.created_by
             and applied.event.event_kind == "REJECTED" and applied.event.sequence == 1
             and applied.event.from_status == "PENDING" and applied.event.to_status == "REJECTED",
             "terminal rejection identity differs")
    a._write(output / "rejected.json", applied.model_dump(mode="json"))
    after = a._read_review(client, submission.submission_id)
    a._check(after == result, "terminal immutable review result changed")
    manifest, _tar = a._download(client, f"/v1/submissions/{submission.submission_id}/result/bundle", output, "review-rejected")
    a._check(manifest == source.manifest, "terminal review bundle changed")
    a._check(a._probe(env, submission.preview_result_id, submission.submission_id, output, "probe-after") == before,
             "terminal READY/audit/protection changed")
    check_review_state(runtime_state(env, output, "state-after", submission.submission_id), source.proof.review, rejected=True)


def run_terminal(input_root: Path, output: Path, session: str, state: a._RunState, *,
                 source_run: Path, source_root: Path, source_head: str, replay_run: Path) -> None:
    a._check(socket.gethostname() == "gw-dms-test-05", "number1 supplement must remain on source node05")
    separate(output, source_run.resolve(), source_root.resolve(), replay_run.resolve())
    source = load_source(input_root, source_run, source_root, source_head)
    replay_run = replay_run.resolve(strict=True)
    require_replay(replay_run, source)
    a._write(output / "source.json", source.proof.model_dump(mode="json"))
    env = journey._compose_environment(output / "secrets", "correctness-" + session + "-terminal")
    env["GATEWAY_BACKEND_REPOSITORY_BASE_URL"] = "http://repository-service:8000"
    a._check(not env.get("GATEWAY_COMPOSE_GATE_PREBUILT"), "prebuilt override is forbidden")
    for listing in (("ps", "-aq"), ("volume", "ls", "-q"), ("network", "ls", "-q")):
        listed = a._command("docker", *listing, "--filter", "label=com.docker.compose.project=" + env["COMPOSE_PROJECT_NAME"])
        a._check(listed.returncode == 0 and not listed.stdout.strip(), "terminal project is not fresh")
    mapping = {"mappings": [{"gateway_device_external_key": source.proof.device_key,
        "business_project_id": source.proof.project_id, "repository_id": source.proof.repository.repository_id,
        "business_baseline_node_id": harness.BASELINE_NODE_ID,
        "business_baseline_commit_id": source.proof.repository.empty_initial_commit, "baseline_head_version": 0, "enabled": True}]}
    write_container_readable_text(Path(env["GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE"]), json.dumps(mapping))
    actors = actor_bindings(env, source)
    a._write(output / "actors.json", actors)
    state.cleanup_complete = False
    try:
        harness.acquire_compose_gate_lock()
        prepare_clone(env, source, output, replay_run)
        harness._assert_port_8000_available_for_gate(env["COMPOSE_PROJECT_NAME"])
        harness.build_compose_stack_images(env)
        up = a._logged_compose(env, output, "stack-up", "up", "-d", "--no-build", "repository-service", "backend", "worker")
        a._check(up.returncode == 0, "terminal clone stack failed to start")
        harness.wait_repository_service_ready(env)
        harness.wait_http_ok(harness.BACKEND_URL + "/readyz")
        harness.worker_ready(env)
        harness.assert_running_backend_worker_images_match_build(env)
        a._write(output / "containers.json", harness.capture_running_container_provenance(env))
        with httpx.Client(base_url=harness.BACKEND_URL,
                          headers=harness.compose_auth_headers(token=journey.ARCHIVER_TOKEN), timeout=120) as client:
            complete_review(client, source, env, output, session, reviewer_actor_id=actors["reviewer"]["actor_id"])
    finally:
        try:
            a._finish_stack(env, output, state, sys.exception())
        finally:
            check_unchanged(source.proof)
