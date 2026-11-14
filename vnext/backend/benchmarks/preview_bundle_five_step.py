"""Run one isolated five-step Preview trial against a prepared fresh HTTP stack.

The caller owns node exclusion, the stack, input hashes, and the cross-version
12-attempt budget. No automatic retries or resume are performed. A fresh output
is required; inspect any incomplete acceptance before taking further action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

import httpx

from benchmarks import real_dump_journey as journey
from benchmarks.bundle_tar import verify_bundle_tar
from benchmarks.comparison_correctness_acceptance import _read_review
from tests.support.compose_gate_harness import BASELINE_NODE_ID, compose_auth_headers


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class RecordingClient(httpx.Client):
    """Record intent before each Preview request and acceptance immediately after it."""

    def __init__(self, *, ledger: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ledger = ledger
        self.count = 0
        self.evidence_dir: Path | None = None
        self.audit_count = 0

    def post(self, url: Any, **kwargs: Any) -> httpx.Response:
        if not str(url).endswith("/preview-operations"):
            tracked = any(part in str(url) for part in ("upload-revisions", "submit-attempts", "review-events",
                "archive-plan-preview", "archive-confirmations", "archive-anomaly-resolutions", "/archives"))
            if not tracked or self.evidence_dir is None:
                return super().post(url, **kwargs)
            self.audit_count += 1
            prefix = self.evidence_dir / f"mutation-{self.audit_count}"
            _write(prefix.with_suffix(".json"), {"method": "POST", "url": str(url), "state": "response_unknown"})
            response = super().post(url, **kwargs)
            prefix.with_suffix(".body").write_bytes(response.content)
            _write(prefix.with_suffix(".json"), {"method": "POST", "url": str(url),
                                                "state": "response_received", "status": response.status_code})
            return response
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
        archived_submissions: list[str] = []
        for index, package in enumerate(packages, 1):
            if index == 2:
                stage = output / "F"
                stage.mkdir()
                full_client.evidence_dir = stage
                full_workspace = journey._workspace(full_client)
                primary_workspace = journey._workspace(client)
                if full_workspace["workspace_id"] == primary_workspace["workspace_id"]:
                    raise journey.JourneyFailure("FULL actor must own a distinct workspace")
                upload = journey._upload_revision(full_client, workspace=full_workspace, package=package,
                    initial_package=packages[0], idempotency_key=f"{session}-full-upload", token=journey.REPEAT_SUBMITTER_TOKEN)
                full_client.count = client.count
                _write(stage / "upload.json", upload)
                preview, manifest = _preview(full_client, workspace=full_workspace, upload=upload, output=stage,
                    baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                    idempotency_key=f"{session}-full-preview", stage="FULL 1 to 2", operation_timeout_seconds=timeout,
                    token=journey.REPEAT_SUBMITTER_TOKEN)
                client.count = full_client.count
                identity = journey._assert_identity_pair(preview, expected_status="SAME_PROJECT", expected_mode="DETAILED", input_completeness="FULL")
                summary = journey._assert_preview_summaries(manifest, unchanged=False, input_completeness="FULL")
                if summary["changed_table_count"] == 0:
                    raise journey.JourneyFailure("FULL initial-to-modified has no business changes")
                _write(stage / "assertions.json", {"identity": identity, "summary": summary})
            stage = output / f"M{index}"
            stage.mkdir()
            client.evidence_dir = stage
            workspace = journey._workspace(client)
            upload = journey._upload_revision(client, workspace=workspace, package=package,
                idempotency_key=f"{session}-m{index}-upload")
            _write(stage / "upload.json", upload)
            preview, manifest = _preview(client, workspace=workspace, upload=upload, output=stage,
                baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                idempotency_key=f"{session}-m{index}-preview", stage=f"M{index}",
                operation_timeout_seconds=timeout)
            identity = journey._assert_identity_pair(preview,
                expected_status="NOT_APPLICABLE" if index == 1 else "SAME_PROJECT", expected_mode="DETAILED")
            summary = journey._assert_preview_summaries(manifest, unchanged=False)
            if summary["changed_table_count"] == 0:
                raise journey.JourneyFailure(f"M{index} has no business changes; stop before Submit")
            _write(stage / "assertions.json", {"identity": identity, "summary": summary})
            submission = journey._submit(client, workspace=workspace, upload=upload, preview=preview,
                baseline_node_id=baseline_node, baseline_head_version=baseline_version,
                idempotency_key=f"{session}-m{index}-submit", stage=f"M{index} Submit",
                operation_timeout_seconds=timeout, collect_timing=True,
                verify_repository=(repo_url, repository_id, baseline_commit))
            _write(stage / "submission.json", submission)
            commit = str(submission["repository_commit_id"])
            journey._assert_business_baseline_head(client, node_id=baseline_node, commit_id=baseline_commit, version=baseline_version)
            reviewed = _read_review(client, str(submission["submission_id"]))
            _write(stage / "review-result.json", reviewed.model_dump(mode="json"))
            if (reviewed.preview_result_id != preview["result"]["preview_result_id"]
                    or reviewed.bundle_digest != preview["result"]["bundle_digest"]
                    or reviewed.input_completeness != "MODIFIED_ONLY"):
                raise journey.JourneyFailure("review result does not bind the submitted Preview")
            expected_pairs = manifest["pairs"]
            if [pair.pair_id for pair in reviewed.pairs] != [pair["pair_id"] for pair in expected_pairs]:
                raise journey.JourneyFailure("review result pair IDs differ")
            for pair, expected in zip(reviewed.pairs, expected_pairs, strict=True):
                if (pair.comparison_digest, pair.surface_digest, pair.risk_digest) != (
                        expected["comparison_digest"], expected["surface_digest"], expected["risk_evaluation_digest"]):
                    raise journey.JourneyFailure("review result pair digests differ")
            journey._approve(client, str(submission["submission_id"]), f"{session}-m{index}-review")
            archive = journey._archive(client, str(submission["submission_id"]), f"{session}-m{index}")
            _write(stage / "archive.json", archive)
            if archive.get("baseline_commit_id") != commit or archive.get("baseline_head_version") != baseline_version + 1:
                raise journey.JourneyFailure("Archive did not advance the expected baseline")
            baseline_node, baseline_version, baseline_commit = str(archive["baseline_node_id"]), int(archive["baseline_head_version"]), commit
            journey._assert_business_baseline_head(client, node_id=baseline_node, commit_id=baseline_commit, version=baseline_version)
            if journey._repository_main_commit(*repo) != commit:
                raise journey.JourneyFailure("technical main differs after Archive")
            archived_submissions.append(str(submission["submission_id"]))
            _check_history(base_url, stage, archived_submissions, baseline_node, baseline_commit, baseline_version)


def _check_history(base_url: str, output: Path, submissions: list[str], node: str,
                   commit: str, version: int) -> None:
    nodes: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    with httpx.Client(base_url=base_url, headers=compose_auth_headers(token=journey.HISTORY_READER_TOKEN),
                      timeout=120) as reader:
        while True:
            params: dict[str, Any] = {"limit": 1}
            if cursor is not None:
                params["cursor"] = cursor
            response = reader.get("/v1/history", params=params)
            payload = journey._require(response, 200, "history page")
            pages += 1
            _write(output / f"history-page-{pages}.json", payload)
            if payload.get("head") != {"node_id": node, "commit_id": commit, "version": version}:
                raise journey.JourneyFailure("history head differs from Archive")
            nodes.extend(payload["nodes"])
            cursor = payload.get("next_cursor")
            if cursor is None:
                break
            if pages > 50:
                raise journey.JourneyFailure("history pagination exceeded bounded scope")
    for submission_id in submissions:
        found = [item for item in nodes if item.get("ref_kind") == "submission" and item.get("ref_id") == submission_id]
        if len(found) != 1 or found[0].get("submission_disposition") != "ARCHIVED_BASELINE":
            raise journey.JourneyFailure("history does not contain the expected archived submission")


def _preview(client: RecordingClient, *, workspace: dict[str, Any], upload: dict[str, Any],
             output: Path, baseline_node_id: str, baseline_head_version: int, idempotency_key: str,
             stage: str, operation_timeout_seconds: int, token: str = journey.SESSION_TOKEN
             ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Observe this exact operation and save every result before interpreting it."""
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=compose_auth_headers(token=token, idempotency_key=idempotency_key),
        json={"expected_workspace_version": upload["optimistic_version"],
              "upload_revision_id": upload["upload_revision_id"], "generation": upload["generation"],
              "expected_baseline_node_id": baseline_node_id,
              "expected_baseline_head_version": baseline_head_version, "options": {}},
    )
    accepted_at = time.monotonic()
    (output / "acceptance-response.json").write_bytes(response.content)
    accepted = journey._require_one_of(response, {200, 202}, "preview acceptance")
    operation_id = str(accepted["operation_id"])
    deadline = accepted_at + operation_timeout_seconds
    visible_seconds: float | None = None
    while time.monotonic() < deadline:
        status_response = client.get(f"/v1/operations/{operation_id}")
        (output / "operation-response.json").write_bytes(status_response.content)
        if status_response.status_code == 503:
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
            continue
        status = journey._require(status_response, 200, "preview operation")
        if status.get("status") in journey.TERMINAL_OPERATION_STATES and status.get("status") != "SUCCEEDED":
            raise journey.JourneyFailure(f"{stage} Preview failed; see operation-response.json")
        refreshed = journey._workspace(client)
        result_id = refreshed.get("current_preview_result_id")
        if isinstance(result_id, str) and result_id:
            result_response = client.get(f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}")
            (output / "result-response.json").write_bytes(result_response.content)
            if result_response.status_code != 404:
                result = journey._require(result_response, 200, "preview result")
                if result.get("operation_id") == operation_id:
                    if visible_seconds is None:
                        visible_seconds = round(time.monotonic() - accepted_at, 3)
                        _write(output / "visibility.json", {"operation_id": operation_id,
                            "user_visible_seconds": visible_seconds, "poll_interval_seconds": 2.0})
                    if status.get("status") != "SUCCEEDED":
                        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
                        continue
                    preview = {"workspace": refreshed, "result": result, "operation_timing": {
                        "operation_id": operation_id, "user_visible_seconds": visible_seconds,
                        "visibility_observation": "first_successful_same_operation_result_read",
                        "visibility_poll_interval_seconds": 2.0}}
                    _write(output / "preview.json", preview)
                    manifest = _download_preserving_failure(client,
                        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}/bundle", output)
                    _write(output / "manifest.json", manifest)
                    return preview, manifest
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
    raise journey.JourneyFailure(f"{stage} Preview result was not readable before timeout")


def _download_preserving_failure(client: httpx.Client, url: str, output: Path) -> dict[str, Any]:
    started = time.monotonic()
    digest = hashlib.sha256()
    count = 0
    with client.stream("GET", url) as response:
        _write(output / "bundle-response.json", {"http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "content_length": response.headers.get("content-length"), "etag": response.headers.get("etag")})
        # Write the untrusted original before verification; a partial response remains evidence.
        with (output / "preview.tar").open("xb") as target:
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                target.write(chunk)
                count += len(chunk)
                digest.update(chunk)
        finished = time.monotonic()
        declared = response.headers.get("content-length", "")
        if response.status_code != 200 or response.headers.get("content-type") != "application/x-tar":
            raise journey.JourneyFailure("bundle response status or content type is invalid")
        if not declared.isascii() or not declared.isdecimal() or count != int(declared) or count < 2048:
            raise journey.JourneyFailure("bundle response length is invalid")
        with (output / "preview.tar").open("rb") as stream:
            manifest, metrics = verify_bundle_tar(stream, total_bytes=count)
        if response.headers.get("etag") != f'"{manifest["bundle_digest"]}"':
            raise journey.JourneyFailure("bundle ETag disagrees with the verified manifest")
    _write(output / "preview-transfer.json", {**metrics, "raw_tar_sha256": digest.hexdigest(),
        "get_to_complete_read_seconds": round(finished - started, 3)})
    return manifest


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
