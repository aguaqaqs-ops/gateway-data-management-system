"""Owner-authorized, two-key History supplement; never resumes a failed journey.

Only this opt-in test entry clones a stopped fixture. Source roots stay intact;
only the clone's two derived cache registrations are discarded through the owner
port. The worker observer forwards real calls and records their real results.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import socket
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from typing import Any

import httpx
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from benchmarks import comparison_correctness_acceptance as a
from benchmarks import real_dump_journey as journey
from benchmarks.comparison_correctness_cache_probe import (
    Event as Event, Target as Target, Reference, _PREFIX as TRACE_PREFIX,
    observed_cache_type as observed_cache_type, observe_history as observe_history,
)
from gateway_backend.capabilities.bundle_assembly import BundleArtifactKind, BundleTableSide, read_bundle_transport_metadata
from gateway_backend.capabilities.snapshot_materialization.client_parquet import _LAYOUT, _REPOSITORY
from gateway_backend.deployment_config import StorageLayoutConfig
from gateway_backend.http.schemas.submit import SubmissionResponse
from tests.support import compose_gate_harness as harness
from tests.support.container_input_files import write_container_readable_text


class FileRecord(a._Document):
    path: str
    sha256: str
    bytes: int


class SourceStart(a._Document):
    session: str
    purpose: str
    started_at: str
    hostname: str
    worktree: str
    head: str


class SourceFinish(a._Document):
    head: str
    ended_at: str
    exit_code: int


class Repository(a._Document):
    repository_id: str
    empty_initial_commit: str


class FixtureOwner(a._Document):
    device: int
    directory: str
    inode: int
    owner: str
    schema_version: int


TARGETS = TypeAdapter(list[Target])
FILES = TypeAdapter(list[FileRecord])
_PREFIX = TRACE_PREFIX


def validate_trace(raw: str, targets: list[Target], operations: list[str], commits: list[str]) -> list[dict[str, Any]]:
    a._check(len(operations) == 2 and len(set(operations)) == 2, "two distinct History operations required")
    by_name = {target.table_name: target for target in targets}
    events: list[Event] = []
    claimed: str | None = None
    for line in raw.splitlines():
        if match := re.search(r"code=claim_succeeded operation_id=(\S+)", line):
            claimed = match[1]
        if _PREFIX not in line:
            continue
        event = Event.model_validate_json(line.split(_PREFIX, 1)[1])
        a._check(event.phase in (1, 2) and event.repository_id == targets[0].repository_id
                 and event.commits == sorted(commits), "History trace scope mismatch")
        if event.event in ("lookup", "store"):
            a._check(event.table_name in by_name, "History trace names an unauthorized table")
        else:
            a._check(event.table_name is None and event.row_layout_digest is None
                     and event.writer_version is None and event.ref is None, "History trace phase metadata is malformed")
        a._check(claimed == operations[event.phase - 1], "History trace does not belong to the requested operation")
        events.append(event)
    for phase in (1, 2):
        phase_events = [event for event in events if event.phase == phase]
        a._check(bool(phase_events) and phase_events[0].event == "begin" and phase_events[-1].event == "end"
                 and sum(event.event == "begin" for event in phase_events) == 1
                 and sum(event.event == "end" for event in phase_events) == 1, "History trace phase is incomplete")
        for target in targets:
            scoped = [event for event in phase_events if event.table_name == target.table_name]
            a._check(all(event.row_layout_digest == target.row_layout_digest and event.writer_version == target.writer_version
                         for event in scoped), "History trace key mismatch")
            lookups = [event for event in scoped if event.event == "lookup"]
            stores = [event for event in scoped if event.event == "store"]
            a._check(bool(lookups), "representative actual cache lookup was not observed")
            if phase == 1:
                a._check(lookups[0].ref is None and bool(stores), "representative cold miss/export was not observed")
            else:
                a._check(not stores and all(event.ref == target.cache_ref for event in lookups),
                         "representative warm hit was not observed")
            a._check(all(event.ref == target.cache_ref for event in stores), "representative export ref changed")
    return [event.model_dump(mode="json") for event in events]


def tree_manifest(root: Path) -> list[FileRecord]:
    result = []
    a._check(root.is_dir() and not root.is_symlink(), "source root is not an ordinary directory")
    for path in sorted(root.rglob("*")):
        a._check(not path.is_symlink(), "fixture source contains a symlink")
        if path.is_file():
            result.append(FileRecord(path=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=a._file_sha(path)))
        else:
            a._check(path.is_dir(), "fixture source contains a special file")
    return result


def clone_roots(source: Path, destination: Path) -> list[FileRecord]:
    a._check(not source.resolve().is_relative_to(destination.resolve())
             and not destination.resolve().is_relative_to(source.resolve()), "fixture clone overlaps source")
    before = tree_manifest(source)
    existing = tree_manifest(destination)
    source_by_path = {item.path: item for item in before}
    a._check(all(Path(item.path).name == ".gateway-storage.json" and len(Path(item.path).parts) == 2
                 and source_by_path.get(item.path) == item for item in existing),
             "fixture clone destination contains prior data or different storage identities")
    shutil.copytree(source, destination, dirs_exist_ok=True,
        ignore=lambda directory, names: [".gateway-storage.json"] if Path(directory).parent == source else [])
    a._check(tree_manifest(destination) == before and tree_manifest(source) == before,
             "fixture clone bytes differ or source changed")
    return before


def _source(source: Path, source_root: Path, head: str) -> tuple[SourceStart, Repository, SubmissionResponse]:
    source = source.resolve(strict=True)
    a._check(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "explicit full source SHA required")
    files = FILES.validate_json((source / "files.json").read_bytes(), strict=True)
    names = {item.path for item in files}
    a._check(len(names) == len(files) and {"start.json", "finish.json", "business-exception.log", "repository.json",
        "submission.json", "ready-before.json", "inputs.json", "t4-cold.tar"} <= names, "source manifest is incomplete")
    input_identity = FileRecord.model_validate_json((source / "inputs.json").read_bytes())
    a._check(input_identity.sha256 == a.T4_PACKAGE_SHA, "source real input differs")
    for item in files:
        relative = Path(item.path)
        a._check(not relative.is_absolute() and ".." not in relative.parts, "source manifest path escapes")
        path = source / relative
        a._check(path.resolve().is_relative_to(source) and path.is_file() and not path.is_symlink()
                 and path.stat().st_size == item.bytes and a._file_sha(path) == item.sha256, "source run integrity mismatch")
    start = SourceStart.model_validate_json((source / "start.json").read_bytes())
    finish = SourceFinish.model_validate_json((source / "finish.json").read_bytes())
    a._check(start.head == finish.head == head and finish.exit_code == 1 and start.hostname == "gw-dms-test-05"
             and start.purpose == "comparison correctness t4", "source run identity mismatch")
    a._check((source / "business-exception.log").read_text().rstrip().endswith("JourneyFailure: first History was not cold"),
             "source failure is outside the authorized reuse")
    for product_path in ("vnext/backend/src", "vnext/rust"):
        a._check(a._git("rev-parse", head + ":" + product_path) == a._git("rev-parse", "HEAD:" + product_path),
                 "source product tree differs from current candidate")
    owner = FixtureOwner.model_validate_json((source_root / ".gateway-runtime-fixture-owner.json").read_bytes())
    stat = source_root.stat()
    a._check(owner.directory == str(source_root) and owner.device == stat.st_dev and owner.inode == stat.st_ino
             and owner.schema_version == 1 and owner.owner.startswith("correctness-" + start.session + "-t4-"),
             "source fixture ownership mismatch")
    repository = Repository.model_validate_json((source / "repository.json").read_bytes())
    submission = SubmissionResponse.model_validate_json((source / "submission.json").read_bytes(), strict=True)
    a._check(repository.repository_id == submission.repository_id and repository.empty_initial_commit == submission.business_baseline_commit_id
             and submission.based_on_baseline_node_id == harness.BASELINE_NODE_ID, "source submission binding mismatch")
    return start, repository, submission


@contextmanager
def _connection(root: Path) -> Iterator[sqlite3.Connection]:
    db = root / "roots/be-metadata/control.sqlite3"
    wal = Path(str(db) + "-wal")
    a._check(not wal.exists() or wal.stat().st_size == 0, "stopped source has a nonempty WAL")
    with sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        a._check(connection.execute("SELECT count(*) FROM operation_records WHERE status NOT IN "
            "('SUCCEEDED','FAILED','CANCELLED','SUPERSEDED')").fetchone()[0] == 0,
            "source fixture has unfinished operations")
        yield connection


def source_targets(source: Path, source_root: Path, repository: Repository) -> list[Target]:
    tar = source / "t4-cold.tar"
    metadata = read_bundle_transport_metadata(a._member(tar, "manifest.json"))
    manifest = json.loads(a._member(tar, "manifest.json"))
    surface = a._surfaces(tar, manifest)["left_to_right"]
    tables = {table.table_name: table for table in surface.tables}
    targets = []
    with _connection(source_root) as connection:
        for name, rows in (("iec104_cfg", 334), ("b1_n11_iec104_syx_list", 9822)):
            table = tables[name]
            document = table.table_refs["current_table_ref"]
            ref = a._ArtifactReference.model_validate(document).to_ref()
            a._payload_entry(metadata, ref, BundleArtifactKind.SNAPSHOT_TABLE, "left_to_right",
                             table=name, side=BundleTableSide.CURRENT)
            with a._payload_file(tar, document, BundleArtifactKind.SNAPSHOT_TABLE, "left_to_right",
                                 table=name, side=BundleTableSide.CURRENT) as payload:
                file = pq.ParquetFile(payload)
                footer = file.schema_arrow.metadata or {}
                a._check(file.metadata.num_rows == rows and footer[_REPOSITORY].decode() == repository.repository_id,
                         "source representative payload binding mismatch")
                layout = footer[_LAYOUT].decode()
            cache = connection.execute("SELECT artifact_id,media_type,size_bytes,raw_sha256,parquet_writer_contract_version "
                "FROM snapshot_table_export_cache WHERE repository_id=? AND row_layout_digest=?",
                (repository.repository_id, layout)).fetchall()
            a._check(len(cache) == 1, "source representative cache key is missing or ambiguous")
            row = cache[0]
            cache_ref = Reference(artifact_id=row["artifact_id"], media_type=row["media_type"],
                                            size_bytes=row["size_bytes"], raw_sha256=row["raw_sha256"])
            a._check(cache_ref.to_ref().integrity_identity == ref.integrity_identity
                     and cache_ref.media_type == ref.media_type, "source cache ref differs from bundle payload")
            targets.append(Target(table_name=name, repository_id=repository.repository_id, row_layout_digest=layout,
                writer_version=row["parquet_writer_contract_version"], cache_ref=cache_ref, row_count=rows))
    a._check(len({target.key() for target in targets}) == 2, "source representative keys collide")
    return targets


def _cache_command(env: dict[str, str], output: Path, name: str, *, discard: bool) -> None:
    command = ["exec", "-T", "backend", "python", "/run/gateway/history-cache-probe.py", "cache", "/run/gateway/history-targets.json"]
    if discard:
        command.append("--discard")
    result = a._logged_compose(env, output, name, *command)
    a._check(result.returncode == 0, "exact-key cache preparation/verification failed")


def run_supplement(root: Path, output: Path, session: str, state: a._RunState,
                   *, source_run: Path, source_root: Path, source_head: str) -> None:
    a._check(socket.gethostname() == "gw-dms-test-05", "supplement must stay on source node05")
    a._inputs("t4", root, output)
    source_run, source_root = source_run.resolve(strict=True), source_root.resolve(strict=True)
    a._check(not output.is_relative_to(source_run) and not output.is_relative_to(source_root)
             and not source_run.is_relative_to(output) and not source_root.is_relative_to(output), "output overlaps source")
    start, repository, submission = _source(source_run, source_root, source_head)
    targets = source_targets(source_run, source_root, repository)
    original = tree_manifest(source_root / "roots")
    a._write(output / "source.json", {"source_head": source_head, "source_run": str(source_run),
        "source_root": str(source_root), "source_start": start.model_dump(), "repository": repository.model_dump(),
        "submission_id": submission.submission_id, "source_data": [item.model_dump() for item in original]})
    env = journey._compose_environment(output / "secrets", f"correctness-{session}-history")
    env["GATEWAY_BACKEND_REPOSITORY_BASE_URL"] = "http://repository-service:8000"
    a._check(not os.environ.get("GATEWAY_COMPOSE_GATE_PREBUILT"), "prebuilt override is forbidden")
    for listing in (("ps", "-aq"), ("volume", "ls", "-q"), ("network", "ls", "-q")):
        existing = a._command("docker", *listing, "--filter", "label=com.docker.compose.project=" + env["COMPOSE_PROJECT_NAME"])
        a._check(existing.returncode == 0 and not existing.stdout.strip(), "supplement project is not fresh")
    # Keep the restored repository/empty-baseline identity; never call the
    # ordinary harness seed_repository_and_mapping, Preview or Submit.
    mapping = {"mappings": [{"gateway_device_external_key": harness.DEVICE_KEY, "business_project_id": harness.PROJECT_ID,
        "repository_id": repository.repository_id, "business_baseline_node_id": harness.BASELINE_NODE_ID,
        "business_baseline_commit_id": repository.empty_initial_commit, "baseline_head_version": 0, "enabled": True}]}
    write_container_readable_text(Path(env["GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE"]), json.dumps(mapping))
    state.cleanup_complete = False
    try:
        harness.acquire_compose_gate_lock()
        harness.prepare_runtime_config(env)
        clone = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).parent
        source_config = StorageLayoutConfig.from_bytes((source_root / "storage-layout.json").read_bytes())
        clone_config = StorageLayoutConfig.from_bytes((clone / "storage-layout.json").read_bytes())
        a._check(set(source_config.roots) == set(clone_config.roots)
                 and all(Path(value.source).resolve() == (clone / "roots" / slot).resolve()
                         for slot, value in clone_config.roots.items())
                 and all(Path(value.source).resolve() == (source_root / "roots" / slot).resolve()
                         for slot, value in source_config.roots.items()), "source storage uses an external root")
        clone_roots(source_root / "roots", clone / "roots")
        targets_path = clone / "history-targets.json"
        targets_path.write_bytes(TARGETS.dump_json(targets))
        targets_path.chmod(0o444)
        probe_path = clone / "history-cache-probe.py"
        probe_source = Path(__file__).with_name("comparison_correctness_cache_probe.py")
        probe_path.write_bytes(probe_source.read_bytes())
        probe_path.chmod(0o444)
        a._check(a._file_sha(probe_path) == a._file_sha(probe_source), "mounted probe differs from committed source")
        compose = json.loads(Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).read_bytes())
        for service in ("backend", "worker"):
            for host_path, container_path in ((targets_path, "/run/gateway/history-targets.json"),
                                               (probe_path, "/run/gateway/history-cache-probe.py")):
                compose["services"][service].setdefault("volumes", []).append({"type": "bind", "source": str(host_path),
                    "target": container_path, "read_only": True, "bind": {"create_host_path": False}})
        compose["services"]["worker"]["command"] = ["python", "/run/gateway/history-cache-probe.py", "worker", "/run/gateway/history-targets.json"]
        a._check(str(source_root) not in json.dumps(compose) and str(source_run) not in json.dumps(compose),
                 "supplement Compose still mounts a source path")
        a._write(Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]), compose)
        a._write(output / "clone.json", {"root": str(clone), "targets": [target.model_dump() for target in targets],
            "source_storage_sha256": a._file_sha(source_root / "storage-layout.json"),
            "clone_storage_sha256": a._file_sha(clone / "storage-layout.json"), "probe_sha256": a._file_sha(probe_path), "owner_sha256": a._file_sha(clone / ".gateway-runtime-fixture-owner.json")})
        harness._assert_port_8000_available_for_gate(env["COMPOSE_PROJECT_NAME"])
        harness.build_compose_stack_images(env)
        up = a._logged_compose(env, output, "stack-up", "up", "-d", "--no-build", "repository-service", "backend", "worker")
        a._check(up.returncode == 0, "restored supplement stack did not start")
        harness.wait_repository_service_ready(env)
        harness.wait_http_ok(f"{harness.BACKEND_URL}/readyz")
        harness.worker_ready(env)
        harness.assert_running_backend_worker_images_match_build(env)
        a._write(output / "containers.json", harness.capture_running_container_provenance(env))
        ready = a._probe(env, submission.preview_result_id, submission.submission_id, output, "probe-before")
        a._check(ready == a._Probe.model_validate_json((source_run / "ready-before.json").read_bytes()), "restored READY changed")
        operations_before = harness.count_backend_operations(env)
        _cache_command(env, output, "cache-cold-prepared", discard=True)
        a._check(a._probe(env, submission.preview_result_id, submission.submission_id, output, "probe-after-discard") == ready,
                 "derived cache eviction changed submission READY/protection")
        observations, statuses = [], []
        with httpx.Client(base_url=harness.BACKEND_URL, headers=harness.compose_auth_headers(token=harness.SESSION_TOKEN), timeout=120) as client:
            for temperature in ("cold", "warm"):
                manifest, tar = a._history(client, submission.model_dump(mode="json"), output, "supplement-" + temperature)
                observations.append(a._t4_representatives(manifest, tar))
                statuses.append(json.loads((output / ("supplement-" + temperature + "-status.json")).read_bytes()))
                _cache_command(env, output, "cache-after-" + temperature, discard=False)
        a._check(observations[0] == observations[1], "supplement representative semantics differ")
        logs = a._logged_compose(env, output, "history-worker", "logs", "--no-color", "worker")
        a._check(logs.returncode == 0, "supplement worker logs unavailable")
        operations = [value["operation_id"] for value in statuses]
        trace = validate_trace(logs.stdout, targets, operations, [repository.empty_initial_commit, submission.repository_commit_id])
        a._write(output / "exact-key-proof.json", {"targets": [target.model_dump() for target in targets], "operations": operations, "trace": trace})
        a._write(output / "representatives.json", observations)
        a._check(harness.count_backend_operations(env) == operations_before + 2, "supplement created extra operations")
        a._check(a._probe(env, submission.preview_result_id, submission.submission_id, output, "probe-after") == ready,
                 "supplement changed submission READY/protection")
    finally:
        try:
            a._finish_stack(env, output, state, sys.exception())
        finally:
            a._check(tree_manifest(source_root / "roots") == original, "source fixture changed during supplement")
