"""Run one isolated five-step Preview trial against a prepared fresh HTTP stack.

The caller owns node exclusion, the stack, input hashes, and the cross-version
12-attempt budget. No automatic retries or resume are performed. A fresh output
is required; inspect any incomplete acceptance before taking further action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import httpx

from benchmarks import real_dump_journey as journey
from benchmarks.comparison_correctness_acceptance import _download
from tests.support.compose_gate_harness import BASELINE_NODE_ID, compose_auth_headers


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class RecordingClient(httpx.Client):
    """Record intent before each Preview request and acceptance immediately after it."""

    def __init__(self, *, ledger: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ledger = ledger
        self.count = 0

    def post(self, url: Any, **kwargs: Any) -> httpx.Response:
        if not str(url).endswith("/preview-operations"):
            return super().post(url, **kwargs)
        if self.count >= 6:
            raise journey.JourneyFailure("per-version Preview attempt limit reached")
        self.count += 1
        entry = self.ledger / f"attempt-{self.count}.json"
        record: dict[str, Any] = {"attempt": self.count, "state": "acceptance_unknown", "url": str(url)}
        with entry.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")
        response = super().post(url, **kwargs)
        record["http_status"] = response.status_code
        if response.status_code in {200, 202}:
            payload = response.json()
            record["operation_id"] = payload.get("operation_id")
            record["state"] = "accepted" if record["operation_id"] else "acceptance_unknown"
        else:
            record["state"] = "response_received_check_acceptance"
        _write(entry, record)
        return response


def _packages(paths: Sequence[Path], hashes: Sequence[str]) -> list[bytes]:
    if len(paths) != 5 or len(hashes) != 5:
        raise ValueError("exactly five ordered packages and hashes are required")
    result = []
    for path, digest in zip(paths, hashes, strict=True):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"package hash mismatch: {path}")
        result.append(raw)
    return result


def run(*, base_url: str, repo_url: str, repository_id: str, initial_commit: str,
        session: str, packages: Sequence[bytes], output: Path, timeout: int) -> None:
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / "attempts"
    ledger.mkdir()
    _write(output / "inputs.json", [{"bytes": len(p), "sha256": hashlib.sha256(p).hexdigest()} for p in packages])
    repo = (repo_url, repository_id)
    if journey._repository_main_commit(*repo) != initial_commit:
        raise journey.JourneyFailure("initial technical main does not match the supplied initial commit")
    with RecordingClient(base_url=base_url, headers=compose_auth_headers(token=journey.SESSION_TOKEN),
                         timeout=600, ledger=ledger) as client, RecordingClient(
            base_url=base_url, headers=compose_auth_headers(token=journey.REPEAT_SUBMITTER_TOKEN),
            timeout=600, ledger=ledger) as full_client:
        # A shared ledger means both clients must draw from a single attempt sequence.
        full_client.count = 1
        baseline_node, baseline_version, baseline_commit = BASELINE_NODE_ID, 0, initial_commit
        journey._assert_business_baseline_head(client, node_id=baseline_node, commit_id=baseline_commit, version=baseline_version)
        for index, package in enumerate(packages, 1):
            if index == 2:
                full_workspace = journey._workspace(full_client)
                primary_workspace = journey._workspace(client)
                if full_workspace["workspace_id"] == primary_workspace["workspace_id"]:
                    raise journey.JourneyFailure("FULL actor must own a distinct workspace")
                upload = journey._upload_revision(full_client, workspace=full_workspace, package=package,
                    initial_package=packages[0], idempotency_key=f"{session}-full-upload", token=journey.REPEAT_SUBMITTER_TOKEN)
                full_client.count = client.count
                preview, manifest = journey._preview(full_client, workspace=full_workspace, upload=upload,
                    baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                    idempotency_key=f"{session}-full-preview", stage="FULL 1 to 2", operation_timeout_seconds=timeout,
                    collect_timing=True, token=journey.REPEAT_SUBMITTER_TOKEN)
                client.count = full_client.count
                identity = journey._assert_identity_pair(preview, expected_status="SAME_PROJECT", expected_mode="DETAILED", input_completeness="FULL")
                summary = journey._assert_preview_summaries(manifest, unchanged=False, input_completeness="FULL")
                if summary["changed_table_count"] == 0:
                    raise journey.JourneyFailure("FULL initial-to-modified has no business changes")
                _capture(full_client, full_workspace, preview, manifest, output / "F", identity, summary)
            workspace = journey._workspace(client)
            upload = journey._upload_revision(client, workspace=workspace, package=package,
                idempotency_key=f"{session}-m{index}-upload")
            preview, manifest = journey._preview(client, workspace=workspace, upload=upload,
                baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                idempotency_key=f"{session}-m{index}-preview", stage=f"M{index}",
                operation_timeout_seconds=timeout, collect_timing=True)
            identity = journey._assert_identity_pair(preview,
                expected_status="NOT_APPLICABLE" if index == 1 else "SAME_PROJECT", expected_mode="DETAILED")
            summary = journey._assert_preview_summaries(manifest, unchanged=False)
            if summary["changed_table_count"] == 0:
                raise journey.JourneyFailure(f"M{index} has no business changes; stop before Submit")
            stage = output / f"M{index}"
            _capture(client, workspace, preview, manifest, stage, identity, summary)
            submission = journey._submit(client, workspace=workspace, upload=upload, preview=preview,
                baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                idempotency_key=f"{session}-m{index}-submit", stage=f"M{index} Submit",
                operation_timeout_seconds=timeout, collect_timing=True,
                verify_repository=(repo_url, repository_id, baseline_commit))
            _write(stage / "submission.json", submission)
            commit = str(submission["repository_commit_id"])
            journey._assert_business_baseline_head(client, node_id=baseline_node, commit_id=baseline_commit, version=baseline_version)
            journey._approve(client, str(submission["submission_id"]), f"{session}-m{index}-review")
            archive = journey._archive(client, str(submission["submission_id"]), f"{session}-m{index}")
            _write(stage / "archive.json", archive)
            if archive.get("baseline_commit_id") != commit or archive.get("baseline_head_version") != baseline_version + 1:
                raise journey.JourneyFailure("Archive did not advance the expected baseline")
            baseline_node, baseline_version, baseline_commit = str(archive["baseline_node_id"]), int(archive["baseline_head_version"]), commit
            journey._assert_business_baseline_head(client, node_id=baseline_node, commit_id=baseline_commit, version=baseline_version)
            if journey._repository_main_commit(*repo) != commit:
                raise journey.JourneyFailure("technical main differs after Archive")


def _capture(client: httpx.Client, workspace: dict[str, Any], preview: dict[str, Any],
             manifest: dict[str, Any], output: Path, identity: dict[str, Any], summary: dict[str, Any]) -> None:
    output.mkdir()
    result_id = preview["result"]["preview_result_id"]
    downloaded, _ = _download(client, f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}/bundle", output, "preview")
    if downloaded != manifest:
        raise journey.JourneyFailure("downloaded bundle differs from the verified Preview")
    _write(output / "preview.json", preview)
    _write(output / "manifest.json", manifest)
    _write(output / "assertions.json", {"identity": identity, "summary": summary})


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--initial-commit", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--sha256", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    packages = _packages(args.package, args.sha256)
    run(base_url=args.base_url, repo_url=args.repository_url, repository_id=args.repository_id,
        initial_commit=args.initial_commit, session=args.session, packages=packages,
        output=args.output, timeout=args.timeout)


if __name__ == "__main__":
    main()
