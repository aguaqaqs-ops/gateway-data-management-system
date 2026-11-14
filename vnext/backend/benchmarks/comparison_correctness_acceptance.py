"""Bounded, opt-in real-input acceptance for comparison correctness.

Run once per scope through uv-consume on an idle dedicated node. Each invocation
owns a new Compose project/repository, never connects to an existing deployment,
and retains its input hashes, complete bundle tars and container logs. This is
functional acceptance, with no performance or capacity pass criterion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from benchmarks import real_dump_journey as journey
from benchmarks.bundle_tar import download_bundle_tar
from gateway_backend.application.comparison_audit import ComparisonStructureAudit
from gateway_backend.capabilities.business_navigation import validate_navigation
from gateway_backend.http.schemas.review import SubmissionResultResponse
from tests.support.compose_gate_harness import (
    BACKEND_URL, BASELINE_NODE_ID, SESSION_TOKEN,
    assert_running_backend_worker_images_match_build,
    capture_running_container_provenance, cleanup_compose_project_artifacts,
    compose_auth_headers, count_backend_operations, run_compose,
    start_three_container_stack,
)
from tests.support.source_package_fixtures import pack_tar_gz


# Frozen source-input oracles, checked before any stack is started. They identify
# the known inputs, not product versions; source/provenance is in the E card.
NUMBER1_FILES = {
    "data1/sql/dbcfg.sql": "78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f",
    "data1/comps/logic/logics.xml": "511b444d37eef8d31b67bcb5301ebaf492e0b4258de6ebd454abb93731260b2b",
    "data2/sql/dbcfg.sql": "f039dd6f03a492c3f9f4fcaebf798108457d719efacbdcb1ca2c02e838f1b70b",
    "data2/comps/logic/logics.xml": "f448e824c862225f595fe8a16755ee9220f05298288c0d49d4b0c4ac4f959d60",
}
T4_PACKAGE_SHA = "95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675"
CONFIG_TABLES = (
    "cnt_manage_cfg", "iec101_cfg", "iec104_cfg", "iec104gw_cfg", "iec61850c_cfg",
    "jdxx_cfg", "sc_cfg", "scada_cfg", "sg_manage_cfg", "vqc_cfg", "wave_cfg", "wf_cfg",
)
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class _Document(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _Counts(_Document):
    row_count_before: int | None
    row_count_current: int | None
    row_added_count: int
    row_deleted_count: int
    row_modified_count: int
    suppressed_added_count: int
    suppressed_deleted_count: int


class _Table(_Document):
    table_id: str
    table_name: str
    display_name: str
    table_status: str
    change_kind: str
    row_change_stats: _Counts
    schema_summary: dict[str, JsonValue] | None
    columns: list[dict[str, JsonValue]]
    table_refs: dict[str, JsonValue]
    records_refs: dict[str, JsonValue]
    risk_refs: dict[str, JsonValue]
    display: dict[str, JsonValue]
    compare: dict[str, JsonValue]
    diagnostics: dict[str, JsonValue]
    table_content_bindings: dict[str, JsonValue]
    row_locator_ref: dict[str, JsonValue] | None
    content_changed: bool
    replacement_summary: dict[str, JsonValue] | None
    ordered_extension: dict[str, JsonValue] | None


class _Surface(_Document):
    surface_contract_version: str
    surface_id: str
    surface_digest: str
    comparison_digest: str
    risk_evaluation_digest: str | None
    direction: str
    comparison_mode: str
    project_identity_status: str
    project_identity_assessment_digest: str | None
    requires_submit_confirmation: bool
    summary: dict[str, int]
    tables: list[_Table]
    projections: list[dict[str, JsonValue]]
    refs: dict[str, JsonValue]
    diagnostics: dict[str, JsonValue]
    reserved_extensions: list[JsonValue]


class _Probe(_Document):
    protected_artifact_ids: list[str]
    ready_artifact_ids: list[str]
    audits: dict[str, ComparisonStructureAudit]


class _HistoryDemands(_Document):
    demanded_tables: int
    export_cache_hits: int
    control_metadata_resolves: int


@dataclass
class _RunState:
    cleanup_complete: bool = True


# This probe only reads the invocation's newly created control DB/store. It uses
# the owning strict decoder and complete READY validator, including backend-only
# audits; it never changes a cache, protection row or current workspace pointer.
_REVIEW_PROBE = """
import json, sqlite3, sys
from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_from_row
from gateway_backend.bootstrap.storage_layout import local_store_from_config
from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.settings import BackendSettings
from gateway_backend.application.submission.review_result import load_preview_review_closure
from gateway_backend.application.comparison_audit import ComparisonStructureAudit
with sqlite3.connect('file:/var/lib/gateway/be-metadata/control.sqlite3?mode=ro', uri=True) as conn:
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM preview_result_records WHERE preview_result_id=?',
                       (sys.argv[1],)).fetchone()
    if row is None: raise RuntimeError('missing accepted Preview')
    preview = preview_result_from_row(dict(row))
    held = sorted(row[0] for row in conn.execute(
        'SELECT artifact_id FROM artifact_protection_intents WHERE owner_kind=? AND owner_id=?',
        ('submission-review', sys.argv[2])))
settings = BackendSettings()
config = DeploymentConfig.load(settings.storage_layout_file, settings.resource_profile_file)
store = local_store_from_config(config)
refs = load_preview_review_closure(preview, lookup=store, store=store)
required = sorted(ref.artifact_id for ref in refs)
if not set(required).issubset(held): raise RuntimeError('submission protection is incomplete')
audits = {}
for pair in preview.comparison_pairs:
    if pair.structure_audit_artifact_id is not None:
        ref = store.lookup_ref(pair.structure_audit_artifact_id)
        if ref is None: raise RuntimeError('audit is unavailable')
        audits[pair.pair_id] = ComparisonStructureAudit.model_validate_json(
            store.locate(ref)).model_dump(mode='json')
print(json.dumps(dict(protected_artifact_ids=held, ready_artifact_ids=required, audits=audits)))
"""


def _check(condition: bool, label: str) -> None:
    if not condition:
        raise journey.JourneyFailure(label)


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write("\n")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _file_sha(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, timeout=60)


def _idle() -> None:
    running = _command("docker", "ps", "-q")
    _check(running.returncode == 0 and not running.stdout.strip(), "node has running containers")
    _check(_command("pgrep", "-x", "dolt").returncode == 1, "node has Dolt processes")
    with socket.socket() as probe:
        _check(probe.connect_ex(("127.0.0.1", 8000)) != 0, "port 8000 is occupied")


def _inputs(scope: str, root: Path, output: Path) -> tuple[bytes, bytes | None]:
    if scope == "t4":
        source = root / "packages/rd-t4-d-v1.tar.gz"
        raw = source.read_bytes()
        _check(hashlib.sha256(raw).hexdigest() == T4_PACKAGE_SHA, "t4 v1 input identity mismatch")
        _write(output / "inputs.json", {"path": str(source), "bytes": len(raw), "sha256": T4_PACKAGE_SHA})
        return raw, None
    records = []
    packages = []
    for side in ("data1", "data2"):
        members = {}
        for relative in ("sql/dbcfg.sql", "comps/logic/logics.xml"):
            source = root / side / relative
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            _check(digest == NUMBER1_FILES[f"{side}/{relative}"], "number1 source identity mismatch")
            members[relative] = raw
            records.append({"path": str(source), "bytes": len(raw), "sha256": digest})
        # Same accepted source file set as the package ingestion Contract. The
        # marker is not a fabricated configuration; it is an empty project marker.
        members["number1.pmc"] = b""
        package = pack_tar_gz(members)
        packages.append(package)
        records.append({"derived_package": side, "bytes": len(package),
                        "sha256": hashlib.sha256(package).hexdigest(),
                        "members": sorted(members)})
    _write(output / "inputs.json", records)
    return packages[1], packages[0]


def _member(tar: Path, name: str) -> bytes:
    with tarfile.open(tar, "r:") as archive:
        member = archive.getmember(name)
        _check(member.isfile() and member.size <= 16 * 1024**2, "invalid metadata member")
        stream = archive.extractfile(member)
        assert stream is not None
        return stream.read()


def _surfaces(tar: Path, manifest: dict[str, Any]) -> dict[str, _Surface]:
    return {entry["pair_id"]: _Surface.model_validate_json(_member(tar, entry["logical_path"]))
            for entry in manifest["closure"]["entries"] if entry["kind"] == "SURFACE"}


def _browse_count(tar: Path, pair: str, table: str) -> int:
    name = f"pairs/{pair}/tables/current/{table}.parquet"
    with tarfile.open(tar, "r:") as archive, tempfile.TemporaryFile() as scratch:
        stream = archive.extractfile(name)
        assert stream is not None
        while chunk := stream.read(64 * 1024):
            scratch.write(chunk)
        scratch.seek(0)
        return int(pq.read_metadata(scratch).num_rows)


def _download(client: httpx.Client, url: str, output: Path, name: str) -> tuple[dict[str, Any], Path]:
    tar = output / f"{name}.tar"
    manifest, metrics = download_bundle_tar(client, url, destination=tar)
    _write(output / f"{name}-transfer.json", metrics)
    return manifest, tar


def _probe(env: dict[str, str], preview_id: str, submission_id: str) -> _Probe:
    result = run_compose(env, "exec", "-T", "backend", "python", "-c",
                         _REVIEW_PROBE, preview_id, submission_id, timeout=600)
    _check(result.returncode == 0, "complete submission READY/audit/protection probe failed")
    return _Probe.model_validate_json(result.stdout)


def _read_review(client: httpx.Client, submission_id: str) -> SubmissionResultResponse:
    response = client.get(f"/v1/submissions/{submission_id}/result")
    _check(response.status_code == 200, "submission-bound result read failed")
    return SubmissionResultResponse.model_validate_json(response.content)


def _history(client: httpx.Client, submission: dict[str, Any], output: Path,
             name: str) -> tuple[dict[str, Any], Path]:
    accepted = journey._require_one_of(client.post("/v1/history-compares",
        headers=compose_auth_headers(token=journey.HISTORY_READER_TOKEN, idempotency_key=name),
        json={"nodes": [{"ref_kind": "baseline_node", "ref_id": BASELINE_NODE_ID},
                        {"ref_kind": "submission", "ref_id": submission["submission_id"]}]}),
        {200, 202}, "empty baseline History acceptance")
    operation_id = str(accepted["operation_id"])
    deadline = time.monotonic() + journey._operation_timeout_seconds("t4", "history")
    while time.monotonic() < deadline:
        status = journey._require(client.get(f"/v1/history-compares/{operation_id}",
            headers=compose_auth_headers(token=journey.HISTORY_READER_TOKEN)), 200, "History status")
        if status["status"] in journey.TERMINAL_OPERATION_STATES:
            break
        time.sleep(2)
    else:
        raise journey.JourneyFailure("History timed out")
    _write(output / f"{name}-status.json", status)
    _check(status["status"] == "SUCCEEDED", "History did not succeed")
    pairs = status["result"]["pairs"]
    _check(len(pairs) == 1 and pairs[0]["current_commit"] == submission["repository_commit_id"],
           "History exact submitted commit binding mismatch")
    with httpx.Client(base_url=BACKEND_URL,
                      headers=compose_auth_headers(token=journey.HISTORY_READER_TOKEN), timeout=120) as reader:
        return _download(reader, f"/v1/history-compares/{operation_id}/bundle", output, name)


def _t4(client: httpx.Client, submission: dict[str, Any], env: dict[str, str],
        output: Path) -> None:
    observed = []
    for temperature in ("cold", "warm"):
        manifest, tar = _history(client, submission, output, f"t4-{temperature}")
        surfaces = _surfaces(tar, manifest)
        _check(len(surfaces) == 1, "MO History must have one pair")
        pair_id, surface = next(iter(surfaces.items()))
        tables = {table.table_name: table for table in surface.tables}
        representatives = {}
        for name, count in (("iec104_cfg", 334), ("b1_n11_iec104_syx_list", 9822)):
            table = tables[name]
            stats = table.row_change_stats
            _check(table.table_status == "ADDED_TABLE" and table.change_kind == "ADDED",
                   "single-side real table was not added")
            _check(stats.row_count_before is None and stats.row_count_current == count,
                   "single-side table row counts differ from the known source")
            _check((stats.row_added_count, stats.row_deleted_count, stats.row_modified_count,
                    stats.suppressed_added_count, stats.suppressed_deleted_count) == (0, 0, 0, 0, 0),
                   "whole-table addition was converted to row differences")
            _check(table.ordered_extension is None, "single-side table has an ordered extension")
            _check(table.records_refs["records_ref"] is None
                   and table.records_refs["records_manifest_ref"] is None, "single-side row records emitted")
            _check(_browse_count(tar, pair_id, name) == count,
                   "single-side browse parquet count mismatch")
            representatives[name] = table.model_dump(mode="json")
        observed.append(representatives)
    _check(observed[0] == observed[1], "cold/warm representative semantics differ")
    logs = run_compose(env, "logs", "--no-color", "worker")
    _check(logs.returncode == 0, "worker logs unavailable")
    demands = [_HistoryDemands.model_validate_json(match) for match in
               re.findall(r"s5_history_demands (\{[^\n]+\})", logs.stdout)]
    _check(len(demands) == 2, "expected exactly two History demand observations")
    _write(output / "history-cache-observations.json", [item.model_dump() for item in demands])
    # The actual producer's observations distinguish a cold committed export
    # cache from warm hits; no cache rows/artifacts are manually deleted.
    _check(demands[0].export_cache_hits == 0, "first History was not cold")
    _check(demands[1].export_cache_hits >= 2,
           "second History did not reuse exported tables")
    _write(output / "t4-representatives.json", observed)


def _number1(manifest: dict[str, Any], tar: Path, probe: _Probe, output: Path) -> None:
    surfaces = _surfaces(tar, manifest)
    _check(set(surfaces) == {"baseline_to_initial", "initial_to_modified"}, "FULL pair set mismatch")
    surface = surfaces["initial_to_modified"]
    tables = {table.table_name: table for table in surface.tables}
    _check(surface.summary["failed_table_count"] == 0
           and surface.summary["degraded_table_count"] == 0, "number1 comparison failed or degraded")
    audit = probe.audits["initial_to_modified"]
    hidden = {fact.table_name: fact for fact in audit.tables}
    for name in CONFIG_TABLES:
        table = tables[name]
        _check(table.compare["compare_key_columns"] == ["page_no", "no"], "configuration comparison key mismatch")
        _check(table.change_kind == "UNCHANGED" and not table.risk_refs["reason_codes"],
               "pure configuration structure change remains visible or risky")
        fact = hidden[name]
        _check(set(fact.raw_fact.schema_changes.current_only_columns) == {"config_type", "tips"},
               "number1 configuration audit lost its original added columns")
    for name in ("device", "device_st", "b1_n1_iec61850c_dev_cfg"):
        _check(tables[name].row_change_stats.row_modified_count == 1, "known shared value update missing")
    for index in range(2, 8):
        stats = tables[f"b1_n{index}_iec104_syx_list"].row_change_stats
        # Counts are raw; suppressed counts are subsets, never added again.
        _check((stats.row_added_count, stats.row_modified_count, stats.row_deleted_count) == (2, 55, 2),
               "known ordered real row counts mismatch")
    composite = tables["composite_signal_point"]
    _check(composite.change_kind == "UNCHANGED"
           and composite.row_change_stats.row_count_before == 201
           and composite.row_change_stats.row_count_current == 201
           and composite.row_change_stats.row_modified_count == 0, "false composite point/formula updates")
    _check(_browse_count(tar, "initial_to_modified", "composite_signal_point") == 201,
           "composite browse is incomplete")
    navigation = validate_navigation(JSON.validate_json(_member(tar,
        "pairs/initial_to_modified/projections/business_navigation.json"), strict=True), replacement=False)
    items = [item for group in navigation["groups"] for item in group["items"]]
    composite_items = [item for item in items if item["item_kind"] == "COMPOSITE_SIGNAL_DEVICE"]
    _check(len(composite_items) == 1 and any(tab["table_id"] == "composite_signal_point"
        for tab in composite_items[0]["tabs"]), "composite device navigation/browse entry missing")
    config_tabs = [tab for item in items for tab in item["tabs"] if tab["table_id"] in CONFIG_TABLES]
    _check({tab["table_id"] for tab in config_tabs} == set(CONFIG_TABLES)
           and all(not tab["empty"] for tab in config_tabs),
           "original configuration structure changes lost their nonempty navigation tabs")
    _write(output / "number1-navigation.json", navigation)
    _write(output / "number1-pair-summaries.json",
           {pair: value.summary for pair, value in surfaces.items()})
    _write(output / "number1-audits.json", {pair: value.model_dump(mode="json")
                                             for pair, value in probe.audits.items()})


def _run(scope: Literal["t4", "number1"], root: Path, output: Path, session: str,
         state: _RunState) -> None:
    package, initial = _inputs(scope, root, output)
    env = journey._compose_environment(output / "secrets", f"correctness-{session}-{scope}")
    _check(not os.environ.get("GATEWAY_COMPOSE_GATE_PREBUILT"), "prebuilt override is forbidden")
    for resource, listing in (("containers", ("ps", "-aq")),
                              ("volumes", ("volume", "ls", "-q")),
                              ("networks", ("network", "ls", "-q"))):
        existing = _command("docker", *listing, "--filter",
                            "label=com.docker.compose.project=" + env["COMPOSE_PROJECT_NAME"])
        _check(existing.returncode == 0 and not existing.stdout.strip(),
               "fresh acceptance project has existing " + resource)
    state.cleanup_complete = False
    try:
        repository_id, initial_commit = start_three_container_stack(env, output / "secrets")
        assert_running_backend_worker_images_match_build(env)
        _write(output / "containers.json", capture_running_container_provenance(env))
        _write(output / "repository.json", {"repository_id": repository_id, "empty_initial_commit": initial_commit})
        with httpx.Client(base_url=BACKEND_URL, headers=compose_auth_headers(token=SESSION_TOKEN),
                          timeout=120) as client, httpx.Client(base_url=BACKEND_URL,
                          headers=compose_auth_headers(token=journey.ARCHIVER_TOKEN), timeout=120) as reviewer:
            workspace = journey._workspace(client)
            reviewer_workspace = journey._workspace(reviewer)
            _check(workspace["workspace_id"] != reviewer_workspace["workspace_id"], "reviewer shares submitter workspace")
            upload = journey._upload_revision(client, workspace=workspace, package=package,
                initial_package=initial, idempotency_key=session + "-upload")
            preview, _ = journey._preview(client, workspace=workspace, upload=upload,
                baseline_node_id=BASELINE_NODE_ID, baseline_head_version=0,
                idempotency_key=session + "-preview", stage=scope + " Preview",
                operation_timeout_seconds=journey._operation_timeout_seconds("t4", "v1-preview"))
            preview_id = str(preview["result"]["preview_result_id"])
            expected_manifest, preview_tar = _download(client,
                f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{preview_id}/bundle", output, "preview")
            submission = journey._submit(client, workspace=workspace, upload=upload, preview=preview,
                baseline_node_id=BASELINE_NODE_ID, baseline_head_version=0,
                idempotency_key=session + "-submit", stage=scope + " Submit",
                operation_timeout_seconds=journey._operation_timeout_seconds("t4", "v1-submit"))
            submission_id = str(submission["submission_id"])
            _write(output / "submission.json", submission)
            operations = count_backend_operations(env)
            first = _read_review(reviewer, submission_id)
            _check(first.preview_result_id == preview_id
                   and first.bundle_digest == preview["result"]["bundle_digest"]
                   and first.default_pair_id == "initial_to_modified"
                   and first.input_completeness == ("FULL" if initial is not None else "MODIFIED_ONLY"),
                   "review summary does not bind the submitted Preview")
            expected_pair_ids = [pair["pair_id"] for pair in expected_manifest["pairs"]]
            _check([pair.pair_id for pair in first.pairs] == expected_pair_ids, "review ordered pair identity mismatch")
            for pair, expected in zip(first.pairs, expected_manifest["pairs"], strict=True):
                _check((pair.comparison_digest, pair.surface_digest, pair.risk_digest) == (
                    expected["comparison_digest"], expected["surface_digest"], expected["risk_evaluation_digest"]),
                    "review comparison/surface/risk tuple mismatch")
            for index in range(2):
                _check(_read_review(reviewer, submission_id) == first, "repeated review result changed")
                manifest, _tar = _download(reviewer, f"/v1/submissions/{submission_id}/result/bundle",
                                          output, f"review-{index}")
                _check(manifest == expected_manifest, "review bundle differs from immutable Preview")
            probe = _probe(env, preview_id, submission_id)
            _write(output / "ready-before.json", probe.model_dump(mode="json"))
            _check(count_backend_operations(env) == operations, "review reads created a comparison operation")
            if scope == "t4":
                _t4(client, submission, env, output)
            else:
                _number1(expected_manifest, preview_tar, probe, output)
                rejected = journey._require_one_of(reviewer.post(
                    f"/v1/submissions/{submission_id}/review-events",
                    headers=compose_auth_headers(token=journey.ARCHIVER_TOKEN, idempotency_key=session + "-reject"),
                    json={"expected_review_version": 0, "action": "REJECT",
                          "reason": "bounded correctness acceptance retention check"}),
                    {200, 201}, "terminal rejection")
                _check(rejected["status"] == "REJECTED", "submission did not reach rejected terminal state")
                _check(_read_review(reviewer, submission_id) == first, "terminal result binding changed")
                manifest, _tar = _download(reviewer, f"/v1/submissions/{submission_id}/result/bundle", output, "review-rejected")
                _check(manifest == expected_manifest, "terminal review bundle changed")
                after = _probe(env, preview_id, submission_id)
                _check(after == probe, "terminal state released or changed READY/audit protection")
                _write(output / "ready-after-rejected.json", after.model_dump(mode="json"))
                _check(count_backend_operations(env) == operations, "review/terminal reads created operations")
    finally:
        try:
            logs = run_compose(env, "logs", "--no-color", timeout=120)
            (output / "compose.log").write_text(logs.stdout + logs.stderr, encoding="utf-8")
        finally:
            cleanup_compose_project_artifacts(env)
            shutil.rmtree(output / "secrets")
            state.cleanup_complete = True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("t4", "number1"), required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    def interrupted(_number: int, _frame: object) -> None:
        raise KeyboardInterrupt("acceptance interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    _check(socket.gethostname().split(".")[0] in {"gw-dms-test-04", "gw-dms-test-05", "gw-dms-06", "gw-dms-07"},
           "acceptance requires a dedicated test node")
    _check(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", args.session) is not None, "invalid session")
    _check(re.fullmatch(r"[0-9a-f]{40}", args.expected_head) is not None, "full candidate SHA required")
    _check(_git("rev-parse", "HEAD") == args.expected_head and not _git("status", "--porcelain"),
           "acceptance requires the clean committed expected HEAD")
    _check(os.environ.get("UV_OFFLINE") == "1" and os.environ.get("CARGO_NET_OFFLINE") == "true",
           "offline execution is required")
    _check(os.environ.get("GATEWAY_DOCKER_BUILD_NETWORK") == "none"
           and os.environ.get("GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES") == "1"
           and os.environ.get("GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES") == "1",
           "offline preloaded container dependencies are required")
    _check(not any(os.environ.get(name) for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
        "GATEWAY_RUNTIME_COMPOSE_OVERRIDE", "GATEWAY_BACKEND_IMAGE", "GATEWAY_WORKER_IMAGE")),
        "proxy or existing runtime/image overrides are forbidden")
    worktree = Path(_git("rev-parse", "--show-toplevel")).resolve()
    root, output = args.input_root.resolve(strict=True), args.output.resolve()
    _check(not output.is_relative_to(worktree) and not output.is_relative_to(root)
           and not root.is_relative_to(output), "output must be outside source and input roots")
    _check(not output.exists(), "output already exists; choose a new evidence directory")
    _check(bool(os.environ.get("TMPDIR")) and Path(os.environ["TMPDIR"]).is_dir(), "on-disk TMPDIR required")
    busy = Path("/home/dev/gdds-node-busy.d")
    busy.mkdir()  # Atomic occupancy; a conflict is never taken over.
    owner = {"session": args.session, "purpose": "comparison correctness " + args.scope,
             "started_at": datetime.now(UTC).isoformat(), "hostname": socket.gethostname(),
             "worktree": str(worktree), "head": args.expected_head}
    _write(busy / "owner.json", owner)
    exit_code = 1
    state = _RunState()
    output_created = False
    try:
        _idle()
        output.mkdir(parents=True, exist_ok=False)
        output_created = True
        _write(output / "start.json", owner)
        _run(args.scope, root, output, args.session, state)
        _check(_git("rev-parse", "HEAD") == args.expected_head and not _git("status", "--porcelain"),
               "source changed during acceptance")
        exit_code = 0
        return 0
    except KeyboardInterrupt:
        exit_code = 130
        raise
    finally:
        # Failed assertions remain failed even when cleanup succeeds. If cleanup
        # cannot establish idle state, keep the occupancy for human diagnosis.
        if output_created:
            _write(output / "finish.json", {"head": _git("rev-parse", "HEAD"),
                "ended_at": datetime.now(UTC).isoformat(), "exit_code": exit_code})
            _write(output / "files.json", [{"path": str(path.relative_to(output)),
                "sha256": _file_sha(path), "bytes": path.stat().st_size}
                for path in sorted(output.rglob("*")) if path.is_file() and "secrets" not in path.parts])
        _check(state.cleanup_complete, "cleanup failed; node occupancy retained")
        if output_created:
            _idle()
        _check(JSON.validate_json((busy / "owner.json").read_bytes(), strict=True) == owner,
               "node occupancy owner changed")
        (busy / "owner.json").unlink()
        busy.rmdir()
        print("node_released_at=" + datetime.now(UTC).isoformat(), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
