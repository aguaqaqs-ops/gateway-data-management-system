"""Owned single-version five-step HTTP trial. The coordinator owns the total budget.

Start only after both versions, inputs and comparator are reviewed and frozen.
On any failure, leave the node marker and all stack resources for the coordinator.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import traceback
from datetime import UTC, datetime
from typing import Any, Sequence

from gateway_backend.bootstrap.compute_kernel import initialize_compute_kernel
from gateway_backend.capabilities.table_access import KernelExecutionContext, OperationMemoryBudget, NeverCancel, kernel_execution_scope

from benchmarks import preview_bundle_five_step as steps
from benchmarks import real_dump_journey as journey
from benchmarks.comparison_correctness_acceptance import (
    _RunState, _assert_execution_isolation, _check, _finish_stack, _git, _idle, _logged_compose,
)
from tests.support.compose_gate_harness import (
    BACKEND_URL, assert_running_backend_worker_images_match_build,
    capture_running_container_provenance, start_three_container_stack,
)


def _resource_snapshot(env: dict[str, str]) -> dict[str, Any]:
    snapshot = journey._s3_ready_resource_snapshot(env)
    worker = snapshot["services"]["worker"]
    inspected = subprocess.run(["docker", "inspect", worker["container_id"]], check=True,
                               capture_output=True, text=True, timeout=30)
    container = json.loads(inspected.stdout)[0]
    pid = container["State"]["Pid"]
    lines = (Path("/proc") / str(pid) / "cgroup").read_text(encoding="ascii").splitlines()
    paths = [line[3:] for line in lines if line.startswith("0::")]
    if len(paths) != 1:
        raise journey.JourneyFailure("worker cgroup path is unavailable")
    root = Path("/sys/fs/cgroup").resolve()
    directory = (root / paths[0].lstrip("/")).resolve()
    if not directory.is_relative_to(root):
        raise journey.JourneyFailure("worker cgroup escaped root")
    cpu_max = (directory / "cpu.max").read_text(encoding="ascii").strip()
    quota, period = cpu_max.split()
    if quota == "max" or int(quota) != 2 * int(period):
        raise journey.JourneyFailure("worker cgroup CPU limit differs from the fixed two CPUs")
    worker["cpu_max"] = cpu_max
    for name in ("memory.peak", "cpu.stat", "io.stat"):
        path = directory / name
        worker[name] = path.read_text(encoding="ascii").strip() if path.is_file() else None
    return snapshot


def _clean_expected(head: str) -> None:
    _check(re.fullmatch(r"[0-9a-f]{40}", head) is not None and _git("rev-parse", "HEAD") == head,
           "expected committed HEAD is required")
    status = _git("status", "--porcelain").splitlines()
    legacy = Path(_git("rev-parse", "--show-toplevel")) / "legacy"
    if status == ["?? legacy"] and legacy.is_symlink() and legacy.resolve() == Path("/home/dev/gateway-data-management-system/legacy"):
        return
    _check(not status, "tracked or unexpected untracked worktree changes")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--package", action="append", type=Path, required=True)
    parser.add_argument("--sha256", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    _check(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", args.session) is not None, "invalid session")
    _check(socket.gethostname().split(".")[0] in {"gw-dms-test-04", "gw-dms-test-05", "gw-dms-test", "gw-dms-06", "gw-dms-07"}, "dedicated node required")
    _clean_expected(args.expected_head)
    _check(os.environ.get("UV_OFFLINE") == "1" and os.environ.get("CARGO_NET_OFFLINE") == "true", "offline mode required")
    _check(os.environ.get("GATEWAY_DOCKER_BUILD_NETWORK") == "none"
           and os.environ.get("GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES") == "1"
           and os.environ.get("GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES") == "1", "preloaded offline builds required")
    _check(not any(os.environ.get(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
        "GATEWAY_RUNTIME_COMPOSE_OVERRIDE", "GATEWAY_BACKEND_IMAGE", "GATEWAY_WORKER_IMAGE", "GATEWAY_COMPOSE_GATE_PREBUILT")),
        "proxy and runtime/image overrides are forbidden")
    _check(args.timeout > 0, "positive operation timeout required")
    _check(bool(os.environ.get("TMPDIR")) and Path(os.environ["TMPDIR"]).is_dir(), "disk TMPDIR required")
    output = args.output.resolve()
    worktree = Path(_git("rev-parse", "--show-toplevel")).resolve()
    _check(not output.exists() and not output.is_relative_to(worktree), "fresh evidence directory outside worktree required")
    _check(all(not package.resolve().is_relative_to(output) for package in args.package), "output overlaps inputs")
    isolation = _assert_execution_isolation()
    busy = Path("/home/dev/gdds-node-busy.d")
    busy.mkdir()
    owner = {"session": args.session, "purpose": "preview-bundle-trial", "head": args.expected_head,
             "host": socket.gethostname(), "started_utc": datetime.now(UTC).isoformat(), "output": str(output)}
    steps._write(busy / "owner.json", owner)
    output.mkdir(parents=True, exist_ok=False)
    steps._write(output / "start.json", {**owner, "isolation": isolation, "os_cache": "not cleared",
        "scope": "one version; coordinator enforces 12-attempt total", "poll_seconds": 2,
        "bundle_read_counts_and_logical_bytes": "unknown", "resource_sampling": "start/end and cgroup peak; not per-operation peak"})
    env: dict[str, str] | None = None
    try:
        _idle()
        packages = steps._packages(args.package, args.sha256)
        env = journey._compose_environment(output / "secrets", f"gw08-p2-{args.session}")
        env["GATEWAY_BACKEND_REPOSITORY_BASE_URL"] = "http://repository-service:8000"
        for resource, listing in (("containers", ("ps", "-aq")), ("volumes", ("volume", "ls", "-q")),
                                  ("networks", ("network", "ls", "-q"))):
            result = subprocess.run(["docker", *listing, "--filter", "label=com.docker.compose.project=" + env["COMPOSE_PROJECT_NAME"]],
                                    check=True, capture_output=True, text=True, timeout=30)
            _check(not result.stdout.strip(), f"project has existing {resource}")
        repository_id, initial_commit = start_three_container_stack(env, output / "secrets")
        assert_running_backend_worker_images_match_build(env)
        steps._write(output / "containers.json", capture_running_container_provenance(env))
        steps._write(output / "repository.json", {"repository_id": repository_id, "initial_commit": initial_commit})
        journey._check_w1_w2_ready_resource_guard(env)
        steps._write(output / "resources-start.json", _resource_snapshot(env))
        initialize_compute_kernel(1)
        with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(24 * 1024**3), NeverCancel(), 1), new_operation=True):
            steps.run(base_url=BACKEND_URL, repo_url=journey._repository_service_url(env), repository_id=repository_id,
                      initial_commit=initial_commit, session=args.session, packages=packages, output=output / "journey", timeout=args.timeout)
        steps._write(output / "resources-end.json", _resource_snapshot(env))
        logs = _logged_compose(env, output, "worker-observation", "logs", "--no-color", "worker", timeout=120)
        _check(logs.returncode == 0, "worker metrics log capture failed")
        _clean_expected(args.expected_head)
        _finish_stack(env, output, _RunState(), None)
        _idle()
        _check(json.loads((busy / "owner.json").read_text()) == owner, "occupancy owner changed")
        steps._write(output / "finish.json", {"ended_utc": datetime.now(UTC).isoformat(), "exit_code": 0})
        (busy / "owner.json").unlink()
        busy.rmdir()
        return 0
    except BaseException:
        (output / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
        steps._write(output / "finish.json", {"ended_utc": datetime.now(UTC).isoformat(), "exit_code": 1,
            "occupancy": "retained", "stack": "retained for coordinator inspection"})
        if env is not None:
            try:
                _logged_compose(env, output, "failure-compose", "logs", "--no-color", timeout=120)
            except BaseException:
                (output / "failure-log-capture.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
