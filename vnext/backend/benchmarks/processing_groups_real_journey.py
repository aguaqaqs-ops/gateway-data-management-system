"""Fresh S2b public-entry real t1 chain; the other group is explicitly synthetic.

Run on the approved dedicated node in a clean checkout with offline build caches.
This is a functional input journey, not a timing/capacity measurement. The node
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.support.processing_groups_harness import ProcessingGroupsStack
from tests.support.upload_http_packages import upload_files

SOURCE_NAME = "rd-t1-a-v1.tar.gz"
SOURCE_BYTES = 107115
SOURCE_SHA256 = "42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2"


def run_journey(package: Path, output: Path, *, review_reason: str) -> dict[str, Any]:
    if not package.is_absolute() or package.name != SOURCE_NAME:
        raise ValueError("use the inventoried original t1 source package")
    if not output.is_absolute() or output.exists() or not review_reason.strip():
        raise ValueError("fresh absolute evidence output and explicit review reason are required")
    payload = package.read_bytes()
    if len(payload) != SOURCE_BYTES or hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError("real input differs from the accepted original package")
    directory = Path(tempfile.mkdtemp(prefix="s2b-real-groups-"))
    stack = ProcessingGroupsStack(directory, a_workers=1)
    try:
        stack.start()
        # This is the source scope established by the real-input handoff. The
        # source archive is never rewritten or copied into a second identity.
        registration = stack.add("group-a", "compose-device", project="compose-project")
        stack.add("group-b", "synthetic-real-boundary-b")
        before = stack.snapshot()
        result = stack.journey("group-a", "compose-device", registration,
            identity_confirmation_reason=review_reason,
            upload_files_factory=lambda version: upload_files(expected_version=version,
                include_initial=False, completeness="MODIFIED_ONLY", modified_bytes=payload))
        archived = stack.archive("compose-device", result["submission_id"], reason=review_reason)
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
    parser.add_argument("--review-reason", required=True,
                        help="explicit operator reason for observed source/identity/time exceptions")
    args = parser.parse_args()
    run_journey(args.package, args.output, review_reason=args.review_reason)


if __name__ == "__main__":
    main()
