"""Run one fixed S4 full journey on an occupied dedicated test node.

This is a measurement harness, not a product entrypoint. The controller pins
this file, the committed source, input manifest, census and prepared images
before execution. A failed sample remains failed; the next sample is not run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

GIB = 1024**3
WORKER_ENVELOPE = 48 * GIB
WORKER_RESERVE = 8 * GIB
OPERATION_BUDGET = 40 * GIB
START_AVAILABLE = 56 * GIB
END_AVAILABLE = 8 * GIB
SERVICES = {"backend", "worker", "repository-service"}
RESOURCE_PROFILE = {
    "kernel_threads": 1,
    "kernel_memory_bytes": OPERATION_BUDGET,
    "memory_envelope_bytes": WORKER_ENVELOPE,
    "memory_reserve_bytes": WORKER_RESERVE,
}
LOADS = {"w3": "2x", "w4": "w4-10pct", "w4-pressure": "w4-100pct"}
SYNTHETIC_MANIFEST_SHA = "cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3"
OFFICIAL_TIERS = {"t1", "t2", "t3", "t4"}
SAMPLES = {"warm", "r1", "r2", "r3"}
PROCESS_NAMES = {
    b"dolt", b"cargo", b"rustc", b"rustfmt", b"clippy-driver", b"pytest",
    b"uv", b"uvicorn", b"mypy", b"ruff", b"docker", b"docker-compose",
    b"docker-proxy", b"run-tests.sh", b"real_dump_journey.py",
}


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(args: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 60) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[:1000]}")
    return result.stdout


def _json_command(args: list[str], *, cwd: Path, env: dict[str, str]) -> Any:
    return json.loads(command(args, cwd=cwd, env=env))


def _running_processes() -> list[int]:
    result = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            arguments = (path / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(argument.rsplit(b"/", 1)[-1] in PROCESS_NAMES for argument in arguments):
            result.append(int(path.name))
    return result


def _host_idle(worktree: Path, env: dict[str, str]) -> None:
    if command(["docker", "ps", "-q"], cwd=worktree, env=env).strip():
        raise RuntimeError("another Docker container is running")
    if _running_processes():
        raise RuntimeError("whole-host test or Dolt process remains")
    if command(["ss", "-H", "-ltn", "sport", "=", ":8000"], cwd=worktree, env=env).strip():
        raise RuntimeError("host port 8000 is occupied")


def _owned_containers(project: str, worktree: Path, env: dict[str, str]) -> list[str]:
    return command(
        ["docker", "container", "ls", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
        cwd=worktree, env=env,
    ).split()


def _owned_ids(kind: str, project: str, worktree: Path, env: dict[str, str]) -> list[str]:
    if kind not in {"volume", "network"}:
        raise ValueError("only own project volume/network inventory is supported")
    return command(["docker", kind, "ls", "-q", "--filter",
                    f"label=com.docker.compose.project={project}"], cwd=worktree, env=env).split()


def _archive_stopped_volumes(
    *, project: str, containers: list[str], docker_root: Path,
    evidence: Path, worktree: Path, env: dict[str, str],
) -> dict[str, Any]:
    volumes = _owned_ids("volume", project, worktree, env)
    expected_names = {project + suffix for suffix in (
        "_backend-control", "_backend-artifacts", "_repository-service-data")}
    if len(containers) != 3 or set(volumes) != expected_names:
        raise RuntimeError("owned stopped stack volume inventory is incomplete")
    container_ids = {_inspect(cid, worktree, env)["Id"] for cid in containers}
    locations: dict[str, str] = {}
    sources = []
    source_bytes = 0
    for volume in sorted(volumes):
        details = _json_command(["docker", "volume", "inspect", volume], cwd=worktree, env=env)
        if type(details) is not list or len(details) != 1:
            raise RuntimeError("owned volume inspection shape is invalid")
        item = details[0]
        if item["Labels"].get("com.docker.compose.project") != project:
            raise RuntimeError("volume is not owned by the measured project")
        consumers = set(command(["docker", "ps", "-aq", "--no-trunc", "--filter",
                                 "volume=" + volume], cwd=worktree, env=env).split())
        if not consumers <= container_ids:
            raise RuntimeError("a volume has another project's consumer")
        location = Path(item["Mountpoint"])
        if (not location.is_dir() or location.is_symlink() or location.resolve() != location
                or location != docker_root / "volumes" / volume / "_data"):
            raise RuntimeError("volume mountpoint differs from the owned Docker root")
        locations[volume] = str(location)
        sources.append(volume + "/_data")
        source_bytes += sum(path.stat().st_size for path in location.rglob("*")
                            if path.is_file() and not path.is_symlink())
    if shutil.disk_usage(evidence).free <= source_bytes * 2 + 256 * 1024**2:
        raise RuntimeError("insufficient free storage to preserve stopped volumes")
    archive = evidence / "stopped-volumes.tar"
    if archive.exists():
        raise RuntimeError("stopped volume archive already exists")
    command(["tar", "--create", "--file", str(archive), "--directory",
             str(docker_root / "volumes"), "--one-file-system", "--", *sources],
            cwd=worktree, env=env, timeout=1800)
    return {"archive": str(archive), "sha256": sha(archive), "bytes": archive.stat().st_size,
            "source_file_bytes": source_bytes, "volumes": locations}


def _inspect(container_id: str, worktree: Path, env: dict[str, str]) -> dict[str, Any]:
    result = _json_command(["docker", "inspect", container_id], cwd=worktree, env=env)
    if type(result) is not list or len(result) != 1 or type(result[0]) is not dict:
        raise RuntimeError("container inspection shape is invalid")
    return result[0]


def _available_memory() -> int:
    matches = re.findall(r"^MemAvailable:\s+(\d+) kB$", Path("/proc/meminfo").read_text(), re.M)
    if len(matches) != 1:
        raise RuntimeError("host MemAvailable is unavailable")
    return int(matches[0]) * 1024


def _resource_snapshot(
    containers: list[str], project: str, worktree: Path, env: dict[str, str],
) -> dict[str, Any]:
    root = Path("/sys/fs/cgroup").resolve()
    services: dict[str, Any] = {}
    for container_id in containers:
        raw = _inspect(container_id, worktree, env)
        labels = raw["Config"]["Labels"]
        service = labels.get("com.docker.compose.service")
        if labels.get("com.docker.compose.project") != project or service not in SERVICES or service in services:
            raise RuntimeError("service container identity is invalid")
        state = raw["State"]
        pid = state["Pid"]
        if state["Running"] is not True or type(pid) is not int or pid <= 0:
            raise RuntimeError("service was not running at the resource endpoint")
        cgroups = [line.partition("::")[2] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                   if line.startswith("0::")]
        if len(cgroups) != 1 or not cgroups[0]:
            raise RuntimeError("service cgroup identity is invalid")
        directory = (root / cgroups[0].lstrip("/")).resolve()
        if not directory.is_relative_to(root):
            raise RuntimeError("service cgroup escaped host root")
        events = dict(line.split() for line in (directory / "memory.events").read_text().splitlines())
        if not {"oom", "oom_kill", "oom_group_kill"} <= events.keys():
            raise RuntimeError("service OOM counters are incomplete")
        status = Path(f"/proc/{pid}/status").read_text()
        rss = re.findall(r"^VmHWM:\s+(\d+) kB$", status, re.M)
        resources: dict[str, Any] = {}
        if service == "worker":
            resources = json.loads(command(["docker", "exec", container_id, "python", "-c",
                "import json,os; from pathlib import Path; print(json.dumps(json.loads(Path(os.environ['GATEWAY_RESOURCE_PROFILE_FILE']).read_bytes())['worker']))"],
                cwd=worktree, env=env))
        services[service] = {
            "id": raw["Id"], "image_id": raw["Image"], "started_at": state["StartedAt"],
            "restart_count": raw["RestartCount"], "oom_killed": state["OOMKilled"],
            "host_memory_limit": raw["HostConfig"]["Memory"],
            "host_nano_cpus": raw["HostConfig"].get("NanoCpus"),
            "host_cpuset_cpus": raw["HostConfig"].get("CpusetCpus"),
            "memory_max": (directory / "memory.max").read_text().strip(),
            "memory_peak": int((directory / "memory.peak").read_text().strip()),
            "memory_events": {key: int(value) for key, value in events.items()},
            "rss_hwm_bytes": int(rss[0]) * 1024 if len(rss) == 1 else None,
            "resource_profile": resources,
        }
    if set(services) != SERVICES:
        raise RuntimeError("three-service resource endpoint is incomplete")
    return {"timestamp_utc": utc(), "mem_available_bytes": _available_memory(), "services": services}


def _resource_pass(start: dict[str, Any], end: dict[str, Any]) -> bool:
    if start.get("status") != "PASS" or start.get("mem_available_bytes", -1) < START_AVAILABLE:
        return False
    if end["mem_available_bytes"] < END_AVAILABLE:
        return False
    before, after = start["services"], end["services"]
    if set(before) != SERVICES or set(after) != SERVICES:
        return False
    for service in SERVICES:
        old, current = before[service], after[service]
        if old["container_id"] != current["id"][:len(old["container_id"])]:
            return False
        if current["restart_count"] != 0 or current["oom_killed"] is not False:
            return False
        if any(current["memory_events"][key] != 0 for key in ("oom", "oom_kill", "oom_group_kill")):
            return False
        if current["rss_hwm_bytes"] is None or current["memory_peak"] < 0:
            return False
    worker = after["worker"]
    return bool(worker["memory_max"] == str(WORKER_ENVELOPE)
                and worker["host_memory_limit"] == WORKER_ENVELOPE
                and worker["memory_peak"] <= WORKER_ENVELOPE
                and {key: worker["resource_profile"].get(key) for key in RESOURCE_PROFILE} == RESOURCE_PROFILE)


def _input_manifest(manifest: Path, input_source: Path) -> dict[str, str]:
    document = json.loads(manifest.read_text())
    files = document["files"]
    if type(files) is not list or not files or len(files) > 64:
        raise RuntimeError("fixed input manifest has an invalid file count")
    identities: dict[str, str] = {}
    for row in files:
        relative = Path(row["path"])
        target = (input_source / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(input_source.resolve()) or not target.is_file():
            raise RuntimeError("fixed input path is invalid")
        if target.stat().st_size != row["bytes"] or sha(target) != row["sha256"]:
            raise RuntimeError("fixed input differs from its manifest")
        if str(relative) in identities:
            raise RuntimeError("fixed input manifest repeats a file path")
        identities[str(relative)] = row["sha256"]
    return identities


def _disk_used(path: Path) -> int:
    stat = os.statvfs(path)
    return (stat.f_blocks - stat.f_bfree) * stat.f_frsize


def _sample_disk_usage(paths: dict[str, Path], stop: threading.Event, output: dict[str, Any]) -> None:
    """Record a sampled host-filesystem high water during the journey."""
    output["interval_seconds"] = 2
    output["meaning"] = "whole-filesystem used high-water; sampled, not exact per-project temp peak"
    output["samples"] = 0
    output["start_used_bytes"] = {name: _disk_used(path) for name, path in paths.items()}
    output["peak_used_bytes"] = dict(output["start_used_bytes"])
    while not stop.wait(2):
        current = {name: _disk_used(path) for name, path in paths.items()}
        output["samples"] += 1
        for name, used in current.items():
            output["peak_used_bytes"][name] = max(output["peak_used_bytes"][name], used)
    output["end_used_bytes"] = {name: _disk_used(path) for name, path in paths.items()}
    for name, used in output["end_used_bytes"].items():
        output["peak_used_bytes"][name] = max(output["peak_used_bytes"][name], used)


def _completed_result(log: Path, head: str, profile: str, mode: str) -> dict[str, Any]:
    results = []
    for line in log.read_text().splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("head") == head and value.get("conclusion") == "PASS":
            results.append(value)
    if len(results) != 1 or len(results[0].get("datasets", [])) != 1:
        raise RuntimeError("one successful full-journey result is required")
    dataset = results[0]["datasets"][0]
    versions = dataset.get("datasets", [])
    tier = profile if profile in OFFICIAL_TIERS else "t4"
    if (dataset.get("tier") != tier or dataset.get("conclusion") != "PASS"
            or type(versions) is not list or len(versions) != 2
            or versions[1].get("input_completeness") != mode):
        raise RuntimeError("journey scope or input completeness differs from the sample")
    repeat = dataset.get("repeat_v1", {})
    cold_modified_only = profile in LOADS and mode == "MODIFIED_ONLY"
    if cold_modified_only:
        if repeat != {"status": "SKIPPED_FOR_S4_COLD_MODIFIED_ONLY"}:
            raise RuntimeError("cold modified-only sample warmed the v1 baseline")
        if {"repeat_v1_preview", "repeat_v1_submit"} & set(dataset.get("operation_timings", {})):
            raise RuntimeError("cold modified-only sample recorded repeated v1 operations")
        if any(item.get("step_id") in {"repeat-v1-workspace", "repeat-v1-upload", "repeat-v1-preview", "repeat-v1-submit"}
               for item in dataset.get("step_metrics", [])):
            raise RuntimeError("cold modified-only sample ran a repeated v1 step")
    else:
        mutation = repeat.get("repository_mutations", {})
        if (repeat.get("submit", {}).get("result") != "NO_CANONICAL_CHANGE"
                or mutation.get("new_operation_count") != 0
                or mutation.get("before") != mutation.get("after")):
            raise RuntimeError("repeated upload/Preview/Submit changed Repository mutations")
    timings = dataset.get("operation_timings", {})
    v2_target = {"w3": 120, "w4": 300, "w4-pressure": None}.get(profile, 600)
    target_results: dict[str, dict[str, int | float | bool | None]] = {}
    for name in ("v1_submit", "v2_submit"):
        timing = timings.get(name, {})
        elapsed = timing.get("request_to_main_verified_seconds")
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise RuntimeError(f"{name} has no verified technical-main completion clock")
        if timing.get("technical_main_before") == timing.get("technical_main_after"):
            raise RuntimeError(f"{name} did not advance technical main")
        if timing.get("reconciliation", {}).get("repository_import_status") != "SUCCEEDED":
            raise RuntimeError(f"{name} lacks successful Repository import reconciliation")
        target = (None if profile == "w4-pressure" else
                  300 if name == "v1_submit" and tier == "t4" else
                  v2_target if name == "v2_submit" else 600)
        target_results[name] = {"elapsed_seconds": elapsed, "target_seconds": target,
                                "met": None if target is None else elapsed <= target}
    dataset["submit_target_results"] = target_results
    return results[0]


def _submit_event_phases(events: list[dict[str, Any]]) -> list[dict[str, int]]:
    """Bind ordered worker attribution to each fresh Submit; recovery verify is optional."""
    names = ("submit_storage_table", "submit_storage_summary", "submit_package_publish",
             "submit_package_readback", "submit_checkpoint_verify")
    phases: list[dict[str, int]] = []
    current = dict.fromkeys(names, 0)
    for event in events:
        name = event.get("event")
        if name not in current:
            continue
        if name == "submit_storage_table":
            if current["submit_storage_summary"]:
                if not current["submit_package_readback"]:
                    raise RuntimeError("next Submit table preceded previous package readback")
                phases.append(current)
                current = dict.fromkeys(names, 0)
        elif name == "submit_storage_summary":
            if not current["submit_storage_table"] or current[name]:
                raise RuntimeError("Submit storage summary lacks its distinct table segment")
        elif name == "submit_package_publish":
            if not current["submit_storage_summary"] or current[name]:
                raise RuntimeError("Submit package publish lacks its storage summary")
        elif name == "submit_package_readback":
            if not current["submit_package_publish"]:
                raise RuntimeError("Submit package readback lacks its publication")
        elif not current["submit_package_readback"]:
            raise RuntimeError("checkpoint verification lacks package readback")
        current[name] += 1
    if any(current.values()):
        phases.append(current)
    required = names[:4]
    if len(phases) != 2 or any(any(not phase[name] for name in required) for phase in phases):
        raise RuntimeError("both Submit operations need table, summary, publish and readback events")
    return phases


def _stop_normally(container_id: str, worktree: Path, env: dict[str, str]) -> None:
    if not _inspect(container_id, worktree, env)["State"]["Running"]:
        return
    command(["docker", "kill", "--signal=TERM", container_id], cwd=worktree, env=env)
    deadline = time.monotonic() + 240
    while _inspect(container_id, worktree, env)["State"]["Running"]:
        if time.monotonic() > deadline:
            raise RuntimeError("owned container did not stop after SIGTERM")
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--input-source", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=tuple(LOADS) + tuple(sorted(OFFICIAL_TIERS)), required=True)
    parser.add_argument("--mode", choices=("MODIFIED_ONLY", "FULL"), required=True)
    parser.add_argument("--sample", choices=tuple(sorted(SAMPLES)), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--runtime-compose-override", type=Path, required=True,
                        help="external override rendered from the explicit storage/resource JSON; no resource env aliases")
    parser.add_argument("--prepared-image-ids", type=Path, required=True,
                        help="fixed JSON mapping Compose service name to same-node image ID")
    parser.add_argument("--expected-repository", type=Path, required=True,
                        help="independent fixed B-source schema and selected table digests")
    parser.add_argument("--expected-repository-sha256", required=True)
    parser.add_argument("--dataset-root", type=Path,
                        help="fresh worktree-external copy of the official eight-package root")
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    evidence = args.evidence.resolve()
    source = args.input_source.resolve()
    synthetic = args.profile in LOADS
    workload = LOADS.get(args.profile)
    if synthetic:
        if args.dataset_root is not None:
            raise RuntimeError("synthetic profile selects its frozen input root")
        root = source / "roots" / str(workload)
        census = source / "census" / f"{workload}.json"
    else:
        if args.dataset_root is None or args.mode != "FULL":
            raise RuntimeError("official fresh tiers require --dataset-root and FULL v2")
        root = args.dataset_root.resolve()
        census = worktree / "docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json"
    project = f"s4-{args.profile}-{args.mode.lower()}-{args.sample}-{args.head[:10]}"
    if not re.fullmatch(r"[0-9a-f]{40}", args.head) or evidence.is_relative_to(worktree):
        raise RuntimeError("candidate or worktree-external evidence path is invalid")
    if evidence.exists():
        raise RuntimeError("sample evidence already exists")
    env = dict(os.environ)
    env.update({"PATH": "/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "UV_OFFLINE": "1", "CARGO_NET_OFFLINE": "true", "TMPDIR": "/home/dev/gdds-test-tmp",
                "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C.UTF-8",
                "GATEWAY_REAL_DUMP_ROOT": str(root),
                "GATEWAY_REAL_DUMP_LOG_DIR": str(evidence / "compose-failure-logs"),
                "GATEWAY_DOCKER_BUILD_NETWORK": "none",
                "GATEWAY_RUNTIME_COMPOSE_OVERRIDE": str(args.runtime_compose_override.resolve())})
    for key in ("RUSTUP_TOOLCHAIN", "RUSTUP_HOME", "CARGO_HOME", "VIRTUAL_ENV", "CONDA_PREFIX",
                "GATEWAY_COMPOSE_GATE_PREBUILT", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    if command(["git", "rev-parse", "HEAD"], cwd=worktree, env=env).strip() != args.head:
        raise RuntimeError("worktree HEAD differs from the fixed candidate")
    if command(["git", "status", "--porcelain"], cwd=worktree, env=env).strip():
        raise RuntimeError("tested worktree is dirty")
    if not (worktree / "legacy").is_symlink():
        raise RuntimeError("linked worktree lacks its legacy symlink")
    _host_idle(worktree, env)
    busy = Path("/home/dev/gdds-node-busy.d")
    busy.mkdir()  # Atomic whole-node ownership before hashing inputs or writing evidence.
    owner = f"session=s4-e profile={args.profile} mode={args.mode} sample={args.sample} head={args.head} start={utc()}\n"
    marker_released = False
    result: dict[str, Any] = {"head": args.head, "hostname": socket.gethostname(),
                              "profile": args.profile, "mode": args.mode, "sample": args.sample,
                              "project": project, "start_utc": utc(), "journey_exit": None,
                              "sample_pre_release_pass": False,
                              "acceptance_complete": False,
                              "acceptance_rule": "requires stdout s4_sample_release PASS, exit 0 and controller read-only postflight after marker release"}
    error: BaseException | None = None
    lock_paths: list[Path] = []
    locks: dict[str, str] = {}
    expected_images: dict[str, str] = {}
    try:
        (busy / "owner").write_text(owner)
        evidence.mkdir(parents=True, exist_ok=False)
        (evidence / "owner.txt").write_text(owner)
        _host_idle(worktree, env)  # The pre-ownership observation is not the admission check.
        result["input_manifest_sha256"] = sha(args.input_manifest)
        if synthetic and result["input_manifest_sha256"] != SYNTHETIC_MANIFEST_SHA:
            raise RuntimeError("synthetic 13-file manifest differs from the frozen identity")
        result["input_sha256"] = _input_manifest(args.input_manifest, source)
        if synthetic and (len(result["input_sha256"]) != 13 or
                          result["input_sha256"].get("input-summary.json") !=
                          "6b63cf2e8c58cadc96b7ac716a523f9b5554fcb496eea16c0c2f5089199a3896"):
            raise RuntimeError("accepted synthetic input copy must contain the exact 13 pinned files")
        metadata_relative = (f"roots/{workload}/datasets.json" if synthetic else
                             str((root / "datasets.json").resolve().relative_to(source)))
        if metadata_relative not in result["input_sha256"]:
            raise RuntimeError("profile metadata was not included in the fixed input manifest")
        expected_images = json.loads(args.prepared_image_ids.read_text())
        if type(expected_images) is not dict or set(expected_images) != SERVICES:
            raise RuntimeError("prepared image identity receipt is incomplete")
        result["prepared_image_ids_sha256"] = sha(args.prepared_image_ids)
        if sha(args.expected_repository) != args.expected_repository_sha256:
            raise RuntimeError("independent Repository expectation identity changed")
        result["expected_repository_sha256"] = args.expected_repository_sha256
        result["census_sha256"] = sha(census)
        if not synthetic and result["census_sha256"] != "733b506e43164a62f30d3a1d665449471e8edf25b515701150f6e73a824a6988":
            raise RuntimeError("official frozen census identity changed")
        lock_paths = [worktree / "vnext" / package / "uv.lock" for package in (
            "backend", "shared_kernel", "repository_contracts", "repository_client", "repository_service")]
        lock_paths.append(worktree / "vnext/rust/Cargo.lock")
        locks = {str(path): sha(path) for path in lock_paths}
        result["lock_before"] = locks
        result["cpu_count"] = os.cpu_count()
        result["cpus_allowed"] = re.findall(r"^Cpus_allowed_list:\s*(.+)$", Path("/proc/self/status").read_text(), re.M)
        result["filesystem"] = command(["findmnt", "-T", str(evidence.parent), "-n", "-o", "FSTYPE,SOURCE"],
                                          cwd=worktree, env=env).strip()
        docker_root = Path(command(["docker", "info", "--format", "{{.DockerRootDir}}"],
                                   cwd=worktree, env=env).strip()).resolve()
        if not docker_root.is_dir():
            raise RuntimeError("Docker storage root is unavailable")
        disk_paths = {"evidence_filesystem": evidence.parent, "docker_filesystem": docker_root}
        result["disk_mounts"] = {name: command(["findmnt", "-T", str(path), "-n", "-o", "FSTYPE,SOURCE"],
                                               cwd=worktree, env=env).strip() for name, path in disk_paths.items()}
        journey_args = [str(worktree / "vnext/scripts/uv-consume.sh"), "-C", str(worktree / "vnext/backend"),
                        "run", "--no-sync", "python", "benchmarks/real_dump_journey.py", "--tier",
                        args.profile if not synthetic else "t4", "--scope", "full",
                        "--v2-input-completeness", args.mode,
                        "--kernel-threads", "1", "--kernel-memory-budget-bytes", str(OPERATION_BUDGET),
                        "--submit-measurements", str(evidence / "submit-facts"),
                        "--keep-stack", "--project-name", project]
        if synthetic:
            journey_args.extend(["--s3-census", str(census)])
        if synthetic and args.mode == "MODIFIED_ONLY":
            journey_args.append("--s4-skip-repeat-v1")
        (evidence / "command.json").write_text(json.dumps(journey_args) + "\n")
        disk_stop = threading.Event()
        disk_thread = threading.Thread(target=_sample_disk_usage,
                                       args=(disk_paths, disk_stop, result.setdefault("disk_sample", {})),
                                       name="s4-disk-sampler")
        disk_thread.start()
        try:
            with (evidence / "journey.log").open("w") as output:
                output.write(f"hostname={socket.gethostname()} start_utc={utc()} start_HEAD={args.head}\n")
                output.flush()
                try:
                    result["journey_exit"] = subprocess.run(journey_args, cwd=worktree, env=env,
                                                             stdout=output, stderr=subprocess.STDOUT).returncode
                finally:
                    output.write(f"end_utc={utc()} end_HEAD={command(['git', 'rev-parse', 'HEAD'], cwd=worktree, env=env).strip()} journey_exit={result['journey_exit']}\n")
        finally:
            disk_stop.set()
            disk_thread.join(timeout=10)
            if disk_thread.is_alive():
                raise RuntimeError("disk sampler did not stop")
            if "end_used_bytes" not in result["disk_sample"]:
                raise RuntimeError("disk sampler did not seal its endpoints")
        if result["journey_exit"] != 0:
            raise RuntimeError("full S4 journey failed")
        result["journey"] = _completed_result(evidence / "journey.log", args.head, args.profile, args.mode)
        journey = result["journey"]["datasets"][0]
        state_files = result["journey"].get("debug_state_files", [])
        if type(state_files) is not list or len(state_files) != 1:
            raise RuntimeError("fresh journey did not expose one Repository state path")
        stack = json.loads(Path(state_files[0]).read_text()).get("_stack", {})
        repository_id = stack.get("repository_id")
        if type(repository_id) is not str or not repository_id:
            raise RuntimeError("fresh journey Repository identity is invalid")
        repository_containers = [cid for cid in _owned_containers(project, worktree, env)
                                 if _inspect(cid, worktree, env)["Config"]["Labels"].get(
                                     "com.docker.compose.service") == "repository-service"]
        if len(repository_containers) != 1:
            raise RuntimeError("fresh journey Repository container identity is invalid")
        networks = _inspect(repository_containers[0], worktree, env)["NetworkSettings"]["Networks"]
        addresses = [network["IPAddress"] for network in networks.values() if network.get("IPAddress")]
        if len(addresses) != 1:
            raise RuntimeError("Repository container address is ambiguous")
        repository_url = f"http://{addresses[0]}:8000"
        identity_results = []
        for index, version in enumerate(("v1", "v2")):
            dataset_id = journey["datasets"][index]["dataset_id"]
            commit_id = journey["operation_timings"][f"{version}_submit"]["technical_main_after"]
            check_args = [str(worktree / "vnext/scripts/uv-consume.sh"), "-C", str(worktree / "vnext/backend"),
                          "run", "--no-sync", "python", "benchmarks/s4_repository_identity.py",
                          "--base-url", repository_url, "--repository-id", repository_id,
                          "--commit-id", commit_id, "--dataset-id", dataset_id,
                          "--expected", str(args.expected_repository)]
            checked = command(check_args, cwd=worktree, env=env, timeout=1800)
            identity = json.loads(checked)
            if identity.get("conclusion") != "PASS":
                raise RuntimeError("independent Repository identity check did not pass")
            identity_results.append(identity)
        result["repository_identity_checks"] = identity_results
        guards = []
        first_business_utc: str | None = None
        for line in (evidence / "journey.log").read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event") == "s3_resource_start_guard":
                guards.append(event)
            if (isinstance(event, dict) and event.get("event") == "empty_initial_verified"
                    and first_business_utc is None):
                first_business_utc = event.get("timestamp_utc")
        if len(guards) != 1:
            raise RuntimeError("one before-business M40 resource guard is required")
        if type(first_business_utc) is not str:
            raise RuntimeError("first business observation timestamp is missing")
        result["start_resource_guard"] = guards[0]
        result["first_business_observation_utc"] = first_business_utc
        result["business_pass"] = True
    except BaseException as exc:
        error = exc
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        containers: list[str] = []
        end: dict[str, Any] | None = None
        cleanup_errors: list[str] = []
        try:
            containers = _owned_containers(project, worktree, env)
            end = _resource_snapshot(containers, project, worktree, env)
            result["end_resource"] = end
            result["resource_pass"] = _resource_pass(result.get("start_resource_guard", {}), end)
            first_business_text = result.get("first_business_observation_utc")
            if type(first_business_text) is str:
                worker_started = dt.datetime.fromisoformat(
                    end["services"]["worker"]["started_at"].replace("Z", "+00:00"))
                first_business = dt.datetime.fromisoformat(first_business_text.replace("Z", "+00:00"))
                result["same_worker_since_first_business"] = worker_started <= first_business
            else:
                result["same_worker_since_first_business"] = False
            result["resource_pass"] = result["resource_pass"] and result["same_worker_since_first_business"]
        except BaseException as exc:
            cleanup_errors.append(f"resource snapshot: {type(exc).__name__}: {exc}")
            result["resource_pass"] = False
        for container_id in containers:
            try:
                service = _inspect(container_id, worktree, env)["Config"]["Labels"].get(
                    "com.docker.compose.service")
                if service not in SERVICES:
                    raise RuntimeError("unrecognized project container service")
                logs = subprocess.run(["docker", "logs", "--timestamps", container_id], cwd=worktree,
                                      env=env, capture_output=True, text=True, timeout=180)
                (evidence / f"{service}.log").write_text(logs.stdout + "\nSTDERR:\n" + logs.stderr)
                if logs.returncode:
                    cleanup_errors.append(f"{service} logs exit {logs.returncode}")
                if service == "worker":
                    submit_events = []
                    for line in logs.stdout.splitlines():
                        bracket = line.find("{")
                        if bracket < 0:
                            continue
                        try:
                            event = json.loads(line[bracket:])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict) and isinstance(event.get("message"), str):
                            try:
                                event = json.loads(event["message"])
                            except json.JSONDecodeError:
                                pass
                        if isinstance(event, dict) and str(event.get("event", "")).startswith("submit_"):
                            submit_events.append(event)
                    (evidence / "submit-events.json").write_text(
                        json.dumps(submit_events, sort_keys=True) + "\n")
                    result["submit_event_counts"] = {
                        name: sum(item.get("event") == name for item in submit_events)
                        for name in ("submit_storage_table", "submit_storage_summary",
                                     "submit_package_publish", "submit_package_readback",
                                     "submit_checkpoint_verify")
                    }
                    result["submit_event_phases"] = {
                        version: counts for version, counts in zip(
                            ("v1", "v2"), _submit_event_phases(submit_events), strict=True)
                    }
            except BaseException as exc:
                cleanup_errors.append(f"container logs: {type(exc).__name__}: {exc}")
        if end is not None:
            result["image_ids_match_prepared"] = all(
                end["services"][service]["image_id"] == expected_images.get(service)
                for service in SERVICES)
        else:
            result["image_ids_match_prepared"] = False
        for container_id in containers:
            try:
                _stop_normally(container_id, worktree, env)
            except BaseException as exc:
                cleanup_errors.append(f"normal stop: {type(exc).__name__}: {exc}")
        try:
            result["normal_shutdown"] = all(
                not _inspect(container_id, worktree, env)["State"]["Running"] and
                _inspect(container_id, worktree, env)["State"]["ExitCode"] == 0 and
                not _inspect(container_id, worktree, env)["State"]["OOMKilled"]
                for container_id in containers) and len(containers) == 3
            result["lock_after"] = {str(path): sha(path) for path in lock_paths} if lock_paths else {}
            result["end_head"] = command(["git", "rev-parse", "HEAD"], cwd=worktree, env=env).strip()
            result["end_clean"] = not command(["git", "status", "--porcelain"], cwd=worktree, env=env).strip()
        except BaseException as exc:
            cleanup_errors.append(f"postflight: {type(exc).__name__}: {exc}")
        if cleanup_errors:
            result["cleanup_errors"] = cleanup_errors
        if (not cleanup_errors and result.get("business_pass") and result.get("normal_shutdown")):
            try:
                result["stopped_volumes_archive"] = _archive_stopped_volumes(
                    project=project, containers=containers, docker_root=docker_root,
                    evidence=evidence, worktree=worktree, env=env)
            except BaseException as exc:
                cleanup_errors.append(f"stopped volume archive: {type(exc).__name__}: {exc}")
                result["cleanup_errors"] = cleanup_errors
        result["sample_pre_release_pass"] = bool(
            result.get("business_pass") and result["resource_pass"]
            and result["image_ids_match_prepared"] and result.get("normal_shutdown")
            and lock_paths and result.get("lock_after") == locks
            and result.get("end_head") == args.head and result.get("end_clean")
            and result.get("stopped_volumes_archive")
            and not cleanup_errors and error is None
        )
        result["end_utc"] = utc()
        if evidence.exists():
            (evidence / "result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
            checksums = {str(path.relative_to(evidence)): sha(path)
                         for path in evidence.rglob("*") if path.is_file() and path.name != "sha256.json"}
            (evidence / "sha256.json").write_text(json.dumps(checksums, sort_keys=True, indent=2) + "\n")
        # A failed sample retains the marker and stopped project for diagnosis.
        if result["sample_pre_release_pass"]:
            try:
                command(["docker", "rm", *containers], cwd=worktree, env=env)
                for kind in ("volume", "network"):
                    ids = _owned_ids(kind, project, worktree, env)
                    if ids:
                        command(["docker", kind, "rm", *ids], cwd=worktree, env=env)
                _host_idle(worktree, env)
                if (busy / "owner").read_text() != owner:
                    raise RuntimeError("node marker owner changed")
                (busy / "owner").unlink()
                busy.rmdir()
                marker_released = True
            except BaseException as exc:
                result["release_error"] = f"{type(exc).__name__}: {exc}"
    if marker_released:
        print(json.dumps({"event": "s4_sample_release", "status": "PASS", "project": project,
                          "result_sha256": sha(evidence / "result.json"), "manifest_sha256": sha(evidence / "sha256.json"),
                          "released_utc": utc()}, sort_keys=True), flush=True)
        return 0
    print(json.dumps({"event": "s4_sample_release", "status": "HELD", "project": project,
                      "result_sha256": sha(evidence / "result.json") if (evidence / "result.json").is_file() else None,
                      "reason": result.get("release_error") or result.get("error") or
                                result.get("cleanup_errors") or "sample not accepted"}, sort_keys=True), flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
