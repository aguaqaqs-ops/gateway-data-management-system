"""Fresh S2b public-entry real t1 chain; the other group is explicitly synthetic.

Run on the approved dedicated node in a clean checkout with offline build caches.
This is a functional input journey, not a timing/capacity measurement. Set
GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON to the approved issue/subject reason map;
missing or unexpected source/identity facts stop the journey before Archive. The node
executor owns the ordinary node marker and records hostname/HEAD/UTC/exit/SHA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.support.processing_groups_harness import ProcessingGroupsStack
from tests.support.compose_gate_harness import REPO_ROOT
from benchmarks import real_dump_journey as real
from tests.support.compose_gate_harness import compose_auth_headers

SOURCE_NAME = "rd-t1-a-v1.tar.gz"
SOURCE_BYTES = 107115
SOURCE_SHA256 = "42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2"


def _run_real_chain(client: httpx.Client, package: bytes, registration: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reuse the established t1-v1 consumer and its explicit anomaly policy."""
    # These are freshly published test sessions in this run's new group. They
    # are not sessions carried from any earlier S2a deployment.
    submitter, reviewer = "compose-device-token", "compose-device-reviewer"
    workspace = real._workspace(client)
    upload = real._upload_revision(client, workspace=workspace, package=package,
        idempotency_key="processing-groups-real-v1-upload", token=submitter)
    preview, manifest = real._preview(client, workspace=workspace, upload=upload,
        baseline_node_id=registration["initial_node_id"], baseline_head_version=0,
        idempotency_key="processing-groups-real-v1-preview", stage="S2b real t1 v1 Preview",
        operation_timeout_seconds=real._operation_timeout_seconds("t1", "v1-preview"), token=submitter)
    # Check before Submit. An unexpected identity must not receive an automatic
    # dataset-replacement/unverifiable confirmation from the synthetic harness.
    identity = real._assert_identity_pair(preview, expected_status="NOT_APPLICABLE", expected_mode="DETAILED")
    summary = real._assert_preview_summaries(manifest, unchanged=False)
    real._assert_s1b_preview_summary(summary, dataset_id="rd-t1-a-v1", expected_changed=125)
    submission = real._submit(client, workspace=workspace, upload=upload, preview=preview,
        baseline_node_id=registration["initial_node_id"], baseline_head_version=0,
        idempotency_key="processing-groups-real-v1-submit", stage="S2b real t1 v1 Submit",
        operation_timeout_seconds=real._operation_timeout_seconds("t1", "v1-submit"),
        identity_confirmations=(), token=submitter)
    real._canonical_state_digest_from_submission(submission, stage="S2b real t1 v1 Submit")
    real._approve(client, submission["submission_id"], "processing-groups-real-v1-review", token=reviewer)
    # No project-identity exception has been authorized for this real chain.
    # _archive prechecks every reason by exact issue/subject before any ACK.
    archived = real._archive(client, submission["submission_id"], "processing-groups-real-v1", token=reviewer)
    if archived.get("baseline_commit_id") != submission["repository_commit_id"]:
        raise real.JourneyFailure("real Archive did not promote the reported Submit commit")
    current = real._require(client.get("/v1/archive-candidates", headers=compose_auth_headers(token=reviewer)),
                            200, "archived real baseline")
    if current.get("head") != dict(business_baseline_node_id=archived["baseline_node_id"],
            business_baseline_commit_id=submission["repository_commit_id"], baseline_head_version=1):
        raise real.JourneyFailure("real Archive baseline Head differs from the expected binding")
    return dict(workspace_id=workspace["workspace_id"], preview_identity=identity,
                preview_summary=summary, submission=submission), archived


def run_journey(package: Path, output: Path) -> dict[str, Any]:
    if not package.is_absolute() or package.name != SOURCE_NAME:
        raise ValueError("use the inventoried original t1 source package")
    if not output.is_absolute() or REPO_ROOT in output.resolve().parents or output.exists():
        raise ValueError("fresh absolute evidence output outside the checkout is required")
    reasons = real._archive_business_reasons()
    if not reasons:
        raise real.JourneyFailure("real journey requires the approved archive issue/subject reason table")
    payload = package.read_bytes()
    if len(payload) != SOURCE_BYTES or hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError("real input differs from the accepted original package")
    directory = Path(tempfile.mkdtemp(prefix="s2b-real-groups-"))
    stack = ProcessingGroupsStack(directory, a_workers=1)
    try:
        stack.start()
        # Original source scope, with a newly registered INITIAL and newly
        # published sessions. The input archive and its source identity stay exact.
        registration = stack.add("group-a", "compose-device", project="compose-project")
        stack.add("group-b", "synthetic-real-boundary-b")
        before = stack.snapshot()
        with stack.client("compose-device") as client:
            result, archived = _run_real_chain(client, payload, registration)
        assert stack.snapshot() == before
        assert stack.registration("group-a", "compose-device") == registration
        with stack.client("synthetic-real-boundary-b") as client:
            context = client.get("/v1/device-context")
            assert context.status_code == 200, context.text
            assert context.json()["group_id"] == "group-b"
            assert client.get("/v1/workspaces/" + result["workspace_id"]).status_code == 404
        deployment = stack.inspect()
        record = dict(candidate=stack.revision, classification="one real chain plus synthetic group boundary",
            source=dict(path=str(package), name=SOURCE_NAME, size_bytes=SOURCE_BYTES, sha256=SOURCE_SHA256,
                gateway_device_external_key="compose-device", business_project_id="compose-project", group_id="group-a"),
            synthetic_boundary=dict(group_id="group-b", device="synthetic-real-boundary-b", real_device=False),
            profile=dict(a_workers=1, b_workers=1, kernel_threads=1, worker_envelope_bytes=12 * 1024**3,
                worker_reserve_bytes=8 * 1024**3, kernel_memory_bytes=4 * 1024**3,
                total_memory_bytes=int(44.5 * 1024**3), total_cpu=13, timing_measurement=False),
            archive_reason_keys=sorted(reasons), effective_archive_reasons_sha256=hashlib.sha256(
                json.dumps(reasons, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            initial=registration, journey=result, archive=archived, deployment=deployment,
            container_generation_unchanged=True)
        output.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
        print(json.dumps(dict(real_journey="passed", candidate=stack.revision,
                             input_sha256=SOURCE_SHA256, output=str(output)), sort_keys=True), flush=True)
        return record
    finally:
        stack.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_journey(args.package, args.output)


if __name__ == "__main__":
    main()
