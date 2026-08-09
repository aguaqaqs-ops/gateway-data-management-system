"""HTTP helper executed inside the repository-service Compose container."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast
from uuid import UUID


def _request(
    *,
    base_url: str,
    token: str,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    request_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
    else:
        status = response.status
    if not payload:
        return status, {}
    return status, json.loads(payload.decode("utf-8"))


def _create(base_url: str, token: str, idempotency_key: str) -> dict[str, Any]:
    status, body = _request(
        base_url=base_url,
        token=token,
        method="POST",
        path="/v1/repositories",
        headers={"Idempotency-Key": idempotency_key},
    )
    if status != 201:
        raise RuntimeError(f"create failed: {status} {body}")
    return body


def _upload(
    base_url: str,
    token: str,
    *,
    repository_id: UUID,
    payload_path: Path,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = payload_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    status, body = _request(
        base_url=base_url,
        token=token,
        method="POST",
        path=f"/v1/repositories/{repository_id}/artifacts",
        headers={
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/vnd.gateway.repository-import.v1+tar+zstd",
            "Content-Length": str(len(payload)),
            "X-Artifact-SHA256": digest,
        },
        body=payload,
    )
    if status != 201:
        raise RuntimeError(f"upload failed: {status} {body}")
    return body


def _import(
    base_url: str,
    token: str,
    *,
    repository_id: UUID,
    artifact_ref: dict[str, Any],
    expected_commit_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    request_body = {
        "repository_id": str(repository_id),
        "artifact_ref": artifact_ref,
        "target_ref": "main",
        "expected_commit_id": expected_commit_id,
        "verification_policy": "STRUCTURAL",
        "unknown_type_policy": "REJECT",
    }
    status, body = _request(
        base_url=base_url,
        token=token,
        method="POST",
        path=f"/v1/repositories/{repository_id}/versioned/imports",
        headers={
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        },
        body=json.dumps(request_body).encode("utf-8"),
    )
    if status != 202:
        raise RuntimeError(f"import failed: {status} {body}")
    return body


def _poll_operation(
    base_url: str,
    token: str,
    *,
    repository_id: UUID,
    operation_id: UUID,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = _request(
            base_url=base_url,
            token=token,
            method="GET",
            path=f"/v1/repositories/{repository_id}/operations/{operation_id}",
        )
        if status != 200:
            raise RuntimeError(f"poll failed: {status} {body}")
        operation = cast(dict[str, Any], body["operation"])
        if operation["status"] in {"SUCCEEDED", "FAILED"}:
            return operation
        time.sleep(1.0)
    raise TimeoutError(f"operation {operation_id} did not complete")


def _readyz(base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(f"{base_url}/readyz", method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    if not payload:
        return {}
    return cast(dict[str, Any], json.loads(payload.decode("utf-8")))


def _get_operation(
    base_url: str,
    token: str,
    *,
    repository_id: UUID,
    operation_id: UUID,
) -> dict[str, Any]:
    status, body = _request(
        base_url=base_url,
        token=token,
        method="GET",
        path=f"/v1/repositories/{repository_id}/operations/{operation_id}",
    )
    if status != 200:
        raise RuntimeError(f"get operation failed: {status} {body}")
    operation = body.get("operation")
    if not isinstance(operation, dict):
        raise RuntimeError(f"unexpected operation payload: {body}")
    return operation


def _replay_import(
    base_url: str,
    token: str,
    *,
    repository_id: UUID,
    artifact_ref: dict[str, Any],
    expected_commit_id: str,
    idempotency_key: str,
) -> UUID:
    submitted = _import(
        base_url,
        token,
        repository_id=repository_id,
        artifact_ref=artifact_ref,
        expected_commit_id=expected_commit_id,
        idempotency_key=idempotency_key,
    )
    return UUID(submitted["operation_id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("flow", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--payload-path")
    parser.add_argument("--state-path")
    parser.add_argument("--idempotency-prefix", default="compose-e2e")
    args = parser.parse_args(argv)
    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if args.command == "flow":
        if args.payload_path is None:
            raise SystemExit("flow requires --payload-path")
        created = _create(args.base_url, token, f"{args.idempotency_prefix}-create")
        repository_id = UUID(created["repository_id"])
        uploaded = _upload(
            args.base_url,
            token,
            repository_id=repository_id,
            payload_path=Path(args.payload_path),
            idempotency_key=f"{args.idempotency_prefix}-upload",
        )
        artifact_ref = uploaded["artifact_ref"]
        submitted = _import(
            args.base_url,
            token,
            repository_id=repository_id,
            artifact_ref=artifact_ref,
            expected_commit_id=created["initial_commit_id"],
            idempotency_key=f"{args.idempotency_prefix}-import",
        )
        operation_id = UUID(submitted["operation_id"])
        operation = _poll_operation(
            args.base_url,
            token,
            repository_id=repository_id,
            operation_id=operation_id,
            timeout=180.0,
        )
        if operation["status"] != "SUCCEEDED":
            raise RuntimeError(f"import did not succeed: {operation}")
        print(
            json.dumps(
                {
                    "repository_id": str(repository_id),
                    "operation_id": str(operation_id),
                    "result": operation["result"],
                    "artifact_ref": artifact_ref,
                    "expected_commit_id": created["initial_commit_id"],
                    "idempotency_key": f"{args.idempotency_prefix}-import",
                }
            )
        )
        return 0

    if args.state_path is None:
        raise SystemExit("verify requires --state-path")
    ready = _readyz(args.base_url)
    if ready.get("status") != "ready":
        raise RuntimeError(f"service is not ready after restart: {ready}")
    state = json.loads(Path(args.state_path).read_text(encoding="utf-8"))
    repository_id = UUID(state["repository_id"])
    operation_id = UUID(state["operation_id"])
    operation = _get_operation(
        args.base_url,
        token,
        repository_id=repository_id,
        operation_id=operation_id,
    )
    if operation["status"] != "SUCCEEDED":
        raise RuntimeError(f"operation not succeeded after restart: {operation}")
    if operation["result"] != state["result"]:
        raise RuntimeError("operation result changed after restart")
    replayed_id = _replay_import(
        args.base_url,
        token,
        repository_id=repository_id,
        artifact_ref=state["artifact_ref"],
        expected_commit_id=state["expected_commit_id"],
        idempotency_key=state["idempotency_key"],
    )
    if replayed_id != operation_id:
        raise RuntimeError("replay returned a different operation id")
    print(json.dumps({"operation_id": str(replayed_id), "status": operation["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
