#!/usr/bin/env python3
"""Backend stage gate. The SSH controller never executes tests locally."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

PACKAGES = ("rust", "shared_kernel", "repository_contracts", "repository_client", "backend", "repository_service")
NODE = "ct108-gw-dms-04"
WORKTREE = Path("/home/dev/gdds-stage-gate")
REPOSITORY = Path("/home/dev/gateway-data-management-system")
RESULTS = Path("/home/dev/gdds-gate-results")
BUSY = Path("/home/dev/gdds-node-busy.d")
TMP = Path("/home/dev/gdds-test-tmp")
CONFIG = Path("/home/dev/gdds-stage-gate-config.json")
FINAL_PURPOSES = {"s5", "release", "production"}
# A semantic change to lookup/failure handling must invalidate old records.
SCHEMA_VERSION = 1
ENV_KEYS = {
    "GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE", "GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES",
    "GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE", "GATEWAY_P2R1_CACHE_URL",
    "GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES", "GATEWAY_REPOSITORY_SERVICE_IMAGE",
    "GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE", "GATEWAY_REPOSITORY_BASE_IMAGE",
    "GATEWAY_TEST_WORKERS", "CARGO_BUILD_JOBS",
}


class GateError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class Interrupted(GateError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def parse_packages(value: str) -> list[str]:
    names = value.split(",")
    if not names or len(set(names)) != len(names) or any(name not in PACKAGES for name in names):
        raise argparse.ArgumentTypeError("packages must be unique names from " + ",".join(PACKAGES))
    return [name for name in PACKAGES if name in names]


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit_sha", help="full local commit SHA (40 lowercase hex characters)")
    parser.add_argument("--packages", type=parse_packages, default=list(PACKAGES))
    parser.add_argument("--fresh", action="store_true", help="run all six packages without lookup")
    parser.add_argument("--purpose", choices=("stage", "s3-ready", "s5", "release", "production"), default="stage")
    parser.add_argument("--session", default="stage-gate")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-id", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit_sha):
        parser.error("commit must be a full 40-character lowercase SHA")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,96}", args.session):
        parser.error("session must be 1–96 letters, digits, dots, underscores or hyphens")
    if args.run_id is not None and not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", args.run_id):
        parser.error("invalid internal run ID")
    args.fresh = args.fresh or args.purpose in FINAL_PURPOSES
    if args.fresh:
        args.packages = list(PACKAGES)
    return args


def runner_manifests(log: str, packages: list[str]) -> dict[str, dict[str, Any]]:
    """Read only the runner's manifest section, before any test can print JSON."""
    found: dict[str, dict[str, Any]] = {}
    for name in packages:
        marker = f"==> test input manifest package={name}"
        matching = [line for line in log.splitlines() if line.startswith(marker + " ") or line == marker]
        if len(matching) != 1:
            raise GateError(f"runner manifest marker missing or duplicated: {name}")
        tail = log.split(matching[0] + "\n", 1)[1]
        try:
            value, _ = json.JSONDecoder().raw_decode(tail.lstrip())
        except (ValueError, TypeError) as exc:
            raise GateError(f"runner manifest missing: {name}") from exc
        if not isinstance(value, dict) or value.get("package") != name:
            raise GateError(f"runner manifest package mismatch: {name}")
        found[name] = value
    return found


class Gate:
    def __init__(self, args: argparse.Namespace, tool_digest: str):
        self.args = args
        self.tool_digest = tool_digest
        self.worktree = WORKTREE
        self.repository = REPOSITORY
        self.results = RESULTS
        self.busy = BUSY
        self.tmp = TMP
        self.run_id = getattr(args, "run_id", None) or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        self.directory = self.results / args.commit_sha / self.run_id
        self.owned = False
        self.cleanup_uncertain = False
        self.preflight_clear = False
        self.temporary_prepared = False
        self.env = self.environment()
        self.closure: Any = None
        self.result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "run_id": self.run_id,
            "commit_sha": args.commit_sha, "node_hostname": socket.gethostname(),
            "worktree": str(self.worktree), "started_at": utc(), "ended_at": None,
            "start_head": None, "end_head": None, "clean_start": None, "clean_end": None,
            "exit_code": None, "runner_exit_code": None, "status": "failed",
            "requested_packages": args.packages, "fresh": args.fresh, "purpose": args.purpose,
            "orchestrator_sha256": tool_digest, "logs": {}, "packages": {
                name: {"mode": "not_run", "total_digest": None, "manifest": None, "source": None,
                       "reason": "not requested" if name not in args.packages else "execution not reached"}
                for name in PACKAGES
            }, "container_gate": {"status": "not_run", "reason": "execution not reached", "images": None},
            "cache_provenance": None, "error": None, "occupancy_released": False,
        }

    @staticmethod
    def environment() -> dict[str, str]:
        # Do not inherit arbitrary runner overrides, proxies or package indexes.
        env = {key: value for key, value in os.environ.items() if key in {
            "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ", "TERM"
        }}
        env.update(PATH="/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                   TMPDIR=str(TMP), UV_OFFLINE="1", CARGO_NET_OFFLINE="true",
                   GATEWAY_TEST_WORKERS="4", CARGO_BUILD_JOBS="4", GATEWAY_DOCKER_BUILD_NETWORK="none")
        return env

    def note(self, text: str) -> None:
        with (self.directory / "gate.log").open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")
        print(text, flush=True)

    def command(self, command: list[str], *, cwd: Path | None = None,
                env: dict[str, str] | None = None, logfile: str = "prepare.log", check: bool = True) -> str:
        with (self.directory / logfile).open("ab") as log:
            process = subprocess.Popen(command, cwd=cwd, env=env or self.env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait()
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=25)
                    # The shell may exit before its children. Kill the remaining group.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                except (OSError, subprocess.TimeoutExpired):
                    self.cleanup_uncertain = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                raise
        if check and code:
            raise GateError(f"command failed (exit {code}); see {logfile}", code if code > 0 else 128 - code)
        return (self.directory / logfile).read_text(errors="replace")

    def output(self, command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
        # Separate files keep parseable output free of earlier command output.
        filename = "command-" + uuid.uuid4().hex[:10] + ".log"
        return self.command(command, cwd=cwd, env=env, logfile=filename).strip()

    def git(self, *args: str, repo: Path | None = None) -> str:
        return self.output(["git", "-C", str(repo or self.worktree), *args])

    def load_config(self) -> None:
        if not CONFIG.exists():
            self.result["cache_provenance"] = {"reason": "node config absent; no cache provenance supplied"}
            return
        data = json.loads(CONFIG.read_text())
        settings = data.get("environment", {})
        if not isinstance(settings, dict) or set(settings) - ENV_KEYS:
            raise GateError("node config contains unsupported environment keys")
        for key, value in settings.items():
            if not isinstance(value, str) or "\n" in value or "\r" in value:
                raise GateError("invalid node environment setting")
            if "://" in value and (urlsplit(value).username or urlsplit(value).password):
                raise GateError("cache settings may not contain URL credentials")
            self.env[key] = value
        provenance = data.get("cache_provenance")
        if not isinstance(provenance, dict):
            raise GateError("node config requires cache_provenance object")
        self.result["cache_provenance"] = provenance
        # Provenance is ordinary operator metadata; never dump the environment.
        self.result["node_config_sha256"] = sha256(CONFIG)
        if any(urlsplit(str(value)).password for value in provenance.values()):
            raise GateError("cache provenance may not contain URL credentials")

    def acquire(self) -> None:
        try:
            self.busy.mkdir()
        except FileExistsError as exc:
            raise GateError("node occupied; marker left untouched", 3) from exc
        self.owned = True
        atomic_json(self.busy / "owner.json", {"run_id": self.run_id, "session": self.args.session,
                    "purpose": "backend stage gate", "started_at": self.result["started_at"], "pid": os.getpid()})

    def site_clear(self) -> None:
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                try:
                    comm = (entry / "comm").read_text().strip()
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
                if comm == "dolt":
                    raise GateError("Dolt process present; not cleaning foreign processes", 3)
        if self.output(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project"]):
            raise GateError("running Compose containers present", 3)
        with socket.socket() as listener:
            try:
                listener.bind(("0.0.0.0", 8000))
            except OSError as exc:
                raise GateError("port 8000 unavailable", 3) from exc

    def checkout(self) -> None:
        resolved = self.git("rev-parse", "--verify", self.args.commit_sha + "^{commit}", repo=self.repository)
        if resolved != self.args.commit_sha:
            raise GateError("target is not the exact committed SHA", 2)
        owner_file = self.worktree.parent / ".gdds-stage-gate-owner.json"
        if self.worktree.exists() or self.worktree.is_symlink():
            if self.worktree.is_symlink() or not owner_file.is_file():
                raise GateError("fixed worktree lacks managed ownership; refusing adoption")
            owner = json.loads(owner_file.read_text())
            if owner != {"repository": str(self.repository), "worktree": str(self.worktree)}:
                raise GateError("fixed worktree ownership mismatch")
            if self.git("status", "--porcelain", "--untracked-files=all"):
                raise GateError("fixed worktree is dirty; refusing checkout")
            if self.git("rev-parse", "--abbrev-ref", "HEAD") != "HEAD":
                raise GateError("fixed worktree is attached to a branch")
        else:
            if owner_file.exists():
                raise GateError("orphan worktree owner record; requires operator inspection")
            self.command(["git", "-C", str(self.repository), "worktree", "add", "--detach",
                          str(self.worktree), self.args.commit_sha])
            atomic_json(owner_file, {"repository": str(self.repository), "worktree": str(self.worktree)})
        self.command(["git", "-C", str(self.worktree), "checkout", "--detach", self.args.commit_sha])
        legacy = self.worktree / "legacy"
        target = self.repository / "legacy"
        if not target.is_dir():
            raise GateError("reference legacy directory unavailable")
        if legacy.is_symlink():
            if legacy.readlink() != target:
                raise GateError("legacy link has an unexpected target")
        elif legacy.exists():
            raise GateError("legacy path has an unexpected type")
        else:
            legacy.symlink_to(target)
        self.result["start_head"] = self.git("rev-parse", "HEAD")
        self.result["clean_start"] = not self.git("status", "--porcelain", "--untracked-files=all")
        if self.result["start_head"] != self.args.commit_sha or not self.result["clean_start"]:
            raise GateError("start identity or cleanliness mismatch")
        self.note(f"start_head={self.result['start_head']} hostname={socket.gethostname()} utc={utc()}")

    def remove_temporary(self) -> None:
        paths = [self.tmp / "gateway-runner-hypothesis" / name for name in self.args.packages if name != "rust"]
        if "rust" in self.args.packages or "backend" in self.args.packages:
            paths.append(self.tmp / "gateway-runner-cargo-target")
        for path in paths:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.exists():
                shutil.rmtree(path)

    def prepare(self) -> None:
        self.tmp.mkdir(exist_ok=True)
        self.temporary_prepared = True
        self.remove_temporary()
        rust = self.worktree / "vnext/rust"
        if "rust" in self.args.packages or "backend" in self.args.packages:
            # rustup which resolves through the checked-in selector, including proxies.
            parents = set()
            for tool in ("rustc", "cargo", "rustfmt", "clippy-driver"):
                resolved = self.output(["rustup", "which", tool], cwd=rust)
                parents.add(str(Path(resolved).parent))
                self.command([tool, "--version"], cwd=rust)
            if len(parents) != 1:
                raise GateError("Rust tools resolve to different toolchains")
        if {"backend", "repository_service"} & set(self.args.packages):
            if not isinstance(self.result["cache_provenance"], dict) or "reason" in self.result["cache_provenance"]:
                raise GateError("container packages require node cache provenance")
            if self.env.get("GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES") != "1":
                raise GateError("repository-service preloaded dependencies required")
        if "backend" in self.args.packages:
            if (self.env.get("GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES") != "1"
                    or not self.env.get("GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE")):
                raise GateError("backend dependency-base must be preloaded and selected")
        for name in self.args.packages:
            if name == "rust":
                continue
            env = dict(self.env)
            command = [str(self.worktree / "vnext/scripts/uv-consume.sh"), "-C", ".", "sync"]
            if name == "backend":
                env["GATEWAY_RUST_BUILD_INPUT"] = self.git("rev-parse", "HEAD:vnext/rust")
                env["CARGO_TARGET_DIR"] = str(self.tmp / "gateway-runner-cargo-target")
                command += ["--reinstall-package", "gateway-compute-python"]
            self.command(command, cwd=self.worktree / "vnext" / name, env=env)
            if name == "backend":
                self.command([str(self.worktree / "vnext/scripts/check-rust-extension-build-input.sh")], cwd=self.worktree)
        spec = importlib.util.spec_from_file_location("stage_gate_closure", self.worktree / "vnext/scripts/test_input_closure.py")
        if spec is None or spec.loader is None:
            raise GateError("closure module unavailable")
        self.closure = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.closure
        spec.loader.exec_module(self.closure)

    def manifest(self, name: str) -> dict[str, Any]:
        env = dict(self.env)
        if name != "rust":
            env["HYPOTHESIS_STORAGE_DIRECTORY"] = str(self.tmp / "gateway-runner-hypothesis" / name)
        manifest = json.loads(self.output(["python3", "-I", str(self.worktree / "vnext/scripts/test_input_closure.py"),
                                         "manifest", "--package", name], cwd=self.worktree, env=env))
        self.validate_manifest(name, manifest)
        return manifest

    def validate_manifest(self, name: str, manifest: dict[str, Any]) -> None:
        if (manifest.get("package") != name or manifest.get("head") != self.args.commit_sha
                or manifest.get("worktree_head") != self.args.commit_sha):
            raise GateError("manifest HEAD/package mismatch")
        self.closure.compare_manifests(manifest, manifest)

    def save_manifest(self, name: str, manifest: dict[str, Any], prefix: str) -> dict[str, str]:
        path = self.directory / f"{prefix}-{name}.json"
        atomic_json(path, manifest)
        return {"path": str(path), "sha256": sha256(path)}

    @staticmethod
    def verified_file(reference: dict[str, str]) -> Path:
        path = Path(reference["path"])
        if not path.is_file() or sha256(path) != reference["sha256"]:
            raise GateError("source artifact absent or SHA mismatch")
        return path

    def source(self, name: str, current: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        reason = "no qualified original successful run with matching closure"
        for path in sorted(self.results.glob("*/*/result.json"), reverse=True):
            try:
                record = json.loads(path.read_text())
                if (record.get("schema_version") != SCHEMA_VERSION
                        or record.get("orchestrator_sha256") != self.tool_digest
                        or record.get("status") != "passed" or record.get("exit_code") != 0
                        or record.get("runner_exit_code") != 0
                        or record.get("node_hostname") != socket.gethostname()
                        or record.get("worktree") != str(self.worktree)
                        or record.get("clean_start") is not True or record.get("clean_end") is not True
                        or record.get("start_head") != record.get("commit_sha")
                        or record.get("end_head") != record.get("commit_sha")):
                    continue
                package = record["packages"][name]
                if package["mode"] != "run" or package.get("runner_status") != "passed":
                    continue
                log = self.verified_file(record["logs"]["runner"])
                source_manifest = json.loads(self.verified_file(package["manifest"]).read_text())
                if source_manifest.get("head") != record["commit_sha"] or source_manifest.get("worktree_head") != record["commit_sha"]:
                    continue
                # Verify status and starting manifest against the immutable raw runner log too.
                raw = log.read_text(errors="replace")
                extracted = runner_manifests(raw, [name])[name]
                if extracted != source_manifest or f"==> {name} status=passed" not in raw.splitlines():
                    continue
                if self.closure.compare_manifests(source_manifest, current)["status"] != "可沿用":
                    continue
                if name in {"backend", "repository_service"}:
                    valid, reason = self.container_equivalent(record, name)
                    if not valid:
                        continue
                return {"record": str(path), "record_sha256": sha256(path), "commit_sha": record["commit_sha"],
                        "run_id": record["run_id"], "log": record["logs"]["runner"], "manifest": package["manifest"]}, "matching original run"
            except (OSError, ValueError, KeyError, TypeError, GateError, self.closure.ClosureError):
                continue
        return None, reason

    def repository_identity(self) -> dict[str, str]:
        return json.loads(self.output(["python3", "-I", str(self.worktree / "vnext/repository_service/tests/support/build_context_digest.py"),
                                      "identity"], cwd=self.worktree))

    def image(self) -> dict[str, Any]:
        tag = self.env.get("GATEWAY_REPOSITORY_SERVICE_IMAGE", "gateway-repository-service:local")
        raw = json.loads(self.output(["docker", "image", "inspect", tag]))[0]
        return {"tag": tag, "image_id": raw["Id"], "rootfs_diff_ids": raw["RootFS"]["Layers"],
                "labels": raw.get("Config", {}).get("Labels") or {}}

    def container_equivalent(self, source: dict[str, Any], package: str) -> tuple[bool, str]:
        original = source["commit_sha"]
        # log covers every intermediate commit: change-and-revert must not erase a boundary trigger.
        try:
            self.git("merge-base", "--is-ancestor", original, self.args.commit_sha)
            changed = self.git("log", "--format=", "--name-only", f"{original}..{self.args.commit_sha}", "--", "vnext")
            if changed.strip():
                return False, "source interval touched vnext container/runtime inputs (conservative boundary)"
            gate = source["container_gate"]
            if gate.get("status") not in {"run", "carried"}:
                return False, "source container gate unavailable"
            expected = self.repository_identity()
            image = self.image()
            labels = image["labels"]
            source_image = gate["images"]["repository_service"]
            for key, label in (("build_input_revision", "gateway.p2r1.build-input-revision"),
                               ("source_tree_sha256", "gateway.p2r1.source-tree-sha256")):
                if labels.get(label) != expected[key] or source_image["labels"].get(label) != expected[key]:
                    return False, "repository-service build-input/source-tree label changed"
            if package == "backend":
                # source() has already validated the same-worktree backend manifest.
                return True, "same-source backend closure and repository-service identity match"
            return True, "same-source repository-service closure and image identity match"
        except (KeyError, ValueError, GateError):
            return False, "container identity could not be verified"

    def execute_runner(self, names: list[str]) -> None:
        env = dict(self.env, GATEWAY_TEST_PACKAGES=",".join(names))
        self.note("runner_packages=" + ",".join(names))
        if set(names) & {"backend", "repository_service"}:
            # A fresh gate always rebuilds the current RS candidate; backend/worker
            # are built by the unmodified Compose harness inside the runner.
            self.command([str(self.worktree / "vnext/scripts/build-repository-service-image.sh")], cwd=self.worktree,
                         logfile="container-build.log")
        logfile = self.directory / "runner.log"
        runner_started_ns = time.time_ns()
        with logfile.open("wb") as log:
            process = subprocess.Popen([str(self.worktree / "vnext/scripts/run-tests.sh")], cwd=self.worktree,
                                       env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait()
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=30)
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                except (OSError, subprocess.TimeoutExpired):
                    self.cleanup_uncertain = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                raise
        self.result["runner_exit_code"] = code if code >= 0 else 128 - code
        self.note("runner_exit_code=" + str(self.result["runner_exit_code"]))
        if code:
            raise GateError("runner failed; no packages from this run are eligible as sources", self.result["runner_exit_code"])
        raw = logfile.read_text(errors="replace")
        manifests = runner_manifests(raw, names)
        for name in names:
            if f"==> {name} status=passed" not in raw.splitlines():
                raise GateError(f"runner did not report package passed: {name}")
            manifest = manifests[name]
            self.validate_manifest(name, manifest)
            entry = self.result["packages"][name]
            entry.update(mode="run", runner_status="passed", total_digest=manifest["total_digest"],
                         manifest=self.save_manifest(name, manifest, "runner"), source=None,
                         reason="fresh requested" if self.args.fresh else entry["reason"])
        # Capture the runner's existing evidence before another run overwrites it.
        provenance = self.worktree / "vnext/backend/tests/support/.last_compose_gate_provenance.json"
        if "backend" in names:
            if not provenance.is_file():
                raise GateError("backend runner succeeded without Compose provenance")
            payload = json.loads(provenance.read_text())
            if provenance.stat().st_mtime_ns < runner_started_ns:
                raise GateError("backend Compose provenance was not produced by this run")
            expected = self.repository_identity()
            labels = payload["repository_service_image"]["labels"]
            if (labels.get("gateway.p2r1.build-input-revision") != expected["build_input_revision"]
                    or labels.get("gateway.p2r1.source-tree-sha256") != expected["source_tree_sha256"]):
                raise GateError("backend Compose provenance identity mismatch")
            copied = self.directory / "compose-provenance.json"
            shutil.copyfile(provenance, copied)
            self.result["container_gate"]["provenance"] = {"path": str(copied), "sha256": sha256(copied)}

    def gate(self) -> None:
        self.load_config()
        self.acquire()
        self.site_clear()
        self.preflight_clear = True
        self.checkout()
        self.prepare()
        to_run = []
        for name in self.args.packages:
            manifest = self.manifest(name)
            reference = self.save_manifest(name, manifest, "prepared")
            source, reason = (None, "fresh requested") if self.args.fresh else self.source(name, manifest)
            entry = self.result["packages"][name]
            entry.update(total_digest=manifest["total_digest"], manifest=reference, reason=reason)
            if source:
                entry.update(mode="carried", source=source)
            else:
                to_run.append(name)
        if to_run:
            self.execute_runner(to_run)
        if set(self.args.packages) & {"backend", "repository_service"}:
            self.result["container_gate"].update(
                status="run" if set(to_run) & {"backend", "repository_service"} else "carried",
                reason={name: self.result["packages"][name]["reason"] for name in self.args.packages
                        if name in {"backend", "repository_service"}},
                images={"repository_service": self.image()}, repository_identity=self.repository_identity())
        else:
            self.result["container_gate"].update(status="not_requested", reason="no container packages requested")

    def finish(self, code: int) -> int:
        if self.owned:
            try:
                if self.result["start_head"]:
                    self.result["end_head"] = self.git("rev-parse", "HEAD")
                    self.result["clean_end"] = not self.git("status", "--porcelain", "--untracked-files=all")
                    if self.result["end_head"] != self.args.commit_sha or not self.result["clean_end"]:
                        raise GateError("end identity/cleanliness mismatch")
                if self.preflight_clear:
                    self.site_clear()
                if self.temporary_prepared:
                    self.remove_temporary()
                owner = json.loads((self.busy / "owner.json").read_text())
                if owner.get("run_id") != self.run_id:
                    raise GateError("occupancy ownership changed")
                if self.cleanup_uncertain:
                    raise GateError("child cleanup uncertain; occupancy retained for inspection")
                (self.busy / "owner.json").unlink()
                self.busy.rmdir()
                self.result["occupancy_released"] = True
            except (OSError, ValueError, GateError) as exc:
                code = code or 1
                self.result["cleanup_error"] = str(exc)
        self.result.update(ended_at=utc(), exit_code=code, status="passed" if code == 0 else "failed")
        self.note(f"end_head={self.result['end_head']} utc={self.result['ended_at']} exit_code={code}")
        for path in self.directory.glob("*.log"):
            self.result["logs"][path.stem] = {"path": str(path), "sha256": sha256(path)}
        atomic_json(self.directory / "result.json", self.result)
        print("result=" + str(self.directory / "result.json"), flush=True)
        return code

    def run(self) -> int:
        self.directory.mkdir(parents=True, exist_ok=False)
        self.note(f"hostname={socket.gethostname()} started_at={self.result['started_at']} commit={self.args.commit_sha}")
        previous = {}
        def interrupted(number: int, _frame: Any) -> None:
            raise Interrupted(f"interrupted by signal {number}", 128 + number)
        for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, interrupted)
        code = 0
        try:
            self.gate()
        except (GateError, OSError, ValueError) as exc:
            code = exc.code if isinstance(exc, GateError) else 1
            self.result["error"] = str(exc)
            self.note("error=" + str(exc))
        except Exception as exc:
            code = 1
            self.result["error"] = f"unexpected {type(exc).__name__}: {exc}"
            self.note(self.result["error"])
        finally:
            # A second signal must not interrupt evidence writing or release.
            for number in previous:
                signal.signal(number, signal.SIG_IGN)
            code = self.finish(code)
            for number, handler in previous.items():
                signal.signal(number, handler)
        return code


def main(argv: list[str] | None = None, *, source: bytes | None = None) -> int:
    args = arguments(argv)
    source = source if source is not None else Path(__file__).read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if args.worker:
        if socket.gethostname() not in {"gw-dms-04", NODE}:
            raise GateError("worker execution is restricted to gate node 04", 2)
        return Gate(args, digest).run()
    tool_path = Path(__file__).resolve()
    tool_repo = tool_path.parent.parent
    tool_relative = tool_path.relative_to(tool_repo).as_posix()
    committed = subprocess.run(["git", "-C", str(tool_repo), "show", "HEAD:" + tool_relative], capture_output=True)
    if committed.returncode or committed.stdout != source:
        print("error: gate tool must be committed without local edits", file=sys.stderr)
        return 2
    resolved = subprocess.run(["git", "rev-parse", "--verify", args.commit_sha + "^{commit}"], capture_output=True, text=True)
    if resolved.returncode or resolved.stdout.strip() != args.commit_sha:
        print("error: commit must resolve locally to the exact full SHA", file=sys.stderr)
        return 2
    checked = subprocess.run(["ssh", "-o", "BatchMode=yes", NODE, "echo OK"])
    if checked.returncode:
        return checked.returncode
    # Transmit only this committed tool; source commits must already be present via approved LAN transfer.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    remote_args = [args.commit_sha, "--run-id", run_id, "--packages", ",".join(args.packages), "--purpose", args.purpose,
                   "--session", args.session, "--worker"]
    if args.fresh:
        remote_args.append("--fresh")
    wrapper = "import sys; source=sys.stdin.buffer.read(); scope={'__name__':'stage_gate_remote'}; exec(compile(source,'run-stage-gate.py','exec'),scope); sys.exit(scope['main'](sys.argv[1:],source=source))"
    remote = "python3 -c " + shlex.quote(wrapper) + " " + shlex.join(remote_args)
    process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", NODE, remote], stdin=subprocess.PIPE)
    previous = {}
    interrupted_signal = None
    def cancel(number: int, _frame: Any) -> None:
        nonlocal interrupted_signal
        if interrupted_signal is not None:
            return
        interrupted_signal = number
        # Signal only the worker identified by this run's atomic occupancy record.
        # Keep the SSH transport open while the worker traps, stops children and writes evidence.
        code = ("import json,os,signal; from pathlib import Path; "
                "p=Path('/home/dev/gdds-node-busy.d/owner.json'); "
                "r=json.loads(p.read_text()) if p.exists() else {}; "
                f"os.kill(r['pid'],{number}) if r.get('run_id')=={run_id!r} else None")
        forwarded = subprocess.run(["ssh", "-o", "BatchMode=yes", NODE, "python3 -c " + shlex.quote(code)])
        if forwarded.returncode:
            print("signal forwarding failed; inspect remote marker and result before reusing node", file=sys.stderr)
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[number] = signal.signal(number, cancel)
    try:
        process.communicate(source)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    return 128 + interrupted_signal if interrupted_signal is not None else process.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as error:
        print("error: " + str(error), file=sys.stderr)
        raise SystemExit(error.code)
